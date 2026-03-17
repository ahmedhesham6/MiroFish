"""
Plugin management API endpoints for tenant plugin CRUD operations.
"""

import io
import json
import os
import shutil
import zipfile
from datetime import datetime

import jsonschema
from flask import g, jsonify, request

from . import plugins_bp
from ..config import Config
from ..middleware.auth import requires_auth, requires_plan, check_usage_limit
from ..models.tenant import TenantManager
from ..plugins.registry import PluginRegistry, _tenant_plugins_dir
from ..plugins.sdk import validate_plugin_name
from ..utils.logger import get_logger

logger = get_logger("mirofish.api.plugins")


def _check_plugin_name(name: str):
    """Validate a plugin name from a URL parameter. Returns a 400 response or None."""
    try:
        validate_plugin_name(name)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    return None


def _plugin_config_path(tenant_id: str, plugin_name: str) -> str:
    return os.path.join(_tenant_plugins_dir(tenant_id), plugin_name, "config.json")


def _load_plugin_config(tenant_id: str, plugin_name: str) -> dict:
    path = _plugin_config_path(tenant_id, plugin_name)
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_plugin_config(tenant_id: str, plugin_name: str, config: dict) -> None:
    path = _plugin_config_path(tenant_id, plugin_name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# GET /api/plugins — list all plugins for tenant
# ---------------------------------------------------------------------------

@plugins_bp.route("", methods=["GET"])
@requires_auth
def list_plugins():
    tenant = g.current_tenant
    manifests = PluginRegistry.discover_plugins(tenant.tenant_id)
    plugins = []
    for m in manifests:
        plugins.append({
            "name": m.name,
            "version": m.version,
            "type": m.plugin_type,
            "description": m.description,
            "author": m.author,
            "enabled": m.name in tenant.enabled_plugins,
        })
    return jsonify({"success": True, "data": plugins})


# ---------------------------------------------------------------------------
# GET /api/plugins/<name> — get plugin details + config schema
# ---------------------------------------------------------------------------

@plugins_bp.route("/<name>", methods=["GET"])
@requires_auth
def get_plugin(name: str):
    err = _check_plugin_name(name)
    if err:
        return err
    tenant = g.current_tenant
    plugins_dir = _tenant_plugins_dir(tenant.tenant_id)
    manifest_path = os.path.join(plugins_dir, name, "plugin.yaml")
    if not os.path.isfile(manifest_path):
        return jsonify({"success": False, "error": f"Plugin not found: {name}"}), 404

    try:
        manifest = PluginRegistry.validate_manifest(manifest_path)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 422

    config = _load_plugin_config(tenant.tenant_id, name)
    return jsonify({
        "success": True,
        "data": {
            **manifest.to_dict(),
            "enabled": name in tenant.enabled_plugins,
            "config": config,
        },
    })


# ---------------------------------------------------------------------------
# POST /api/plugins/<name>/enable — enable plugin for tenant
# ---------------------------------------------------------------------------

@plugins_bp.route("/<name>/enable", methods=["POST"])
@requires_auth
@check_usage_limit("plugin")
def enable_plugin(name: str):
    err = _check_plugin_name(name)
    if err:
        return err
    tenant = g.current_tenant
    plugins_dir = _tenant_plugins_dir(tenant.tenant_id)
    manifest_path = os.path.join(plugins_dir, name, "plugin.yaml")
    if not os.path.isfile(manifest_path):
        return jsonify({"success": False, "error": f"Plugin not found: {name}"}), 404

    if name not in tenant.enabled_plugins:
        tenant.enabled_plugins.append(name)
        TenantManager.save_tenant(tenant)

    return jsonify({"success": True, "message": f"Plugin '{name}' enabled"})


# ---------------------------------------------------------------------------
# POST /api/plugins/<name>/disable — disable plugin for tenant
# ---------------------------------------------------------------------------

@plugins_bp.route("/<name>/disable", methods=["POST"])
@requires_auth
def disable_plugin(name: str):
    err = _check_plugin_name(name)
    if err:
        return err
    tenant = g.current_tenant
    if name in tenant.enabled_plugins:
        tenant.enabled_plugins.remove(name)
        TenantManager.save_tenant(tenant)
    return jsonify({"success": True, "message": f"Plugin '{name}' disabled"})


# ---------------------------------------------------------------------------
# GET /api/plugins/<name>/config — get current plugin configuration
# ---------------------------------------------------------------------------

@plugins_bp.route("/<name>/config", methods=["GET"])
@requires_auth
def get_plugin_config(name: str):
    err = _check_plugin_name(name)
    if err:
        return err
    tenant = g.current_tenant
    plugins_dir = _tenant_plugins_dir(tenant.tenant_id)
    if not os.path.isdir(os.path.join(plugins_dir, name)):
        return jsonify({"success": False, "error": f"Plugin not found: {name}"}), 404

    config = _load_plugin_config(tenant.tenant_id, name)
    return jsonify({"success": True, "data": config})


# ---------------------------------------------------------------------------
# PUT /api/plugins/<name>/config — update plugin configuration
# ---------------------------------------------------------------------------

@plugins_bp.route("/<name>/config", methods=["PUT"])
@requires_auth
def update_plugin_config(name: str):
    err = _check_plugin_name(name)
    if err:
        return err
    tenant = g.current_tenant
    plugins_dir = _tenant_plugins_dir(tenant.tenant_id)
    manifest_path = os.path.join(plugins_dir, name, "plugin.yaml")
    if not os.path.isfile(manifest_path):
        return jsonify({"success": False, "error": f"Plugin not found: {name}"}), 404

    new_config = request.get_json(silent=True)
    if new_config is None:
        return jsonify({"success": False, "error": "Request body must be JSON"}), 400

    try:
        manifest = PluginRegistry.validate_manifest(manifest_path)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 422

    if manifest.config_schema:
        try:
            manifest.validate_config(new_config)
        except jsonschema.ValidationError as exc:
            return jsonify({
                "success": False,
                "error": "Config validation failed",
                "details": exc.message,
            }), 422
        except jsonschema.SchemaError as exc:
            return jsonify({
                "success": False,
                "error": "Plugin config_schema is invalid",
                "details": exc.message,
            }), 422

    _save_plugin_config(tenant.tenant_id, name, new_config)
    return jsonify({"success": True, "data": new_config})


# ---------------------------------------------------------------------------
# POST /api/plugins/upload — upload a new plugin (zip file)
# ---------------------------------------------------------------------------

@plugins_bp.route("/upload", methods=["POST"])
@requires_auth
@requires_plan("pro")
def upload_plugin():
    tenant = g.current_tenant

    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename or not file.filename.endswith(".zip"):
        return jsonify({"success": False, "error": "File must be a .zip archive"}), 400

    zip_data = file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_data))
    except zipfile.BadZipFile:
        return jsonify({"success": False, "error": "Invalid zip file"}), 400

    # Find plugin.yaml inside zip
    manifest_candidates = [n for n in zf.namelist() if n.endswith("plugin.yaml")]
    if not manifest_candidates:
        return jsonify({"success": False, "error": "No plugin.yaml found in zip"}), 422

    # Prefer the shallowest manifest
    manifest_candidates.sort(key=lambda p: p.count("/"))
    manifest_zip_path = manifest_candidates[0]
    plugin_root_in_zip = os.path.dirname(manifest_zip_path)

    # Read and validate manifest from zip
    manifest_bytes = zf.read(manifest_zip_path)
    tmp_manifest = None
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tmp:
            tmp.write(manifest_bytes)
            tmp_manifest = tmp.name
        manifest = PluginRegistry.validate_manifest(tmp_manifest)
    except Exception as exc:
        return jsonify({"success": False, "error": f"Invalid manifest: {exc}"}), 422
    finally:
        if tmp_manifest and os.path.exists(tmp_manifest):
            os.unlink(tmp_manifest)

    plugin_name = manifest.name
    plugins_dir = _tenant_plugins_dir(tenant.tenant_id)
    plugin_dir = os.path.join(plugins_dir, plugin_name)

    # Extract zip contents into plugin dir
    os.makedirs(plugin_dir, exist_ok=True)
    for member in zf.namelist():
        # Strip plugin root prefix if present
        if plugin_root_in_zip:
            if not member.startswith(plugin_root_in_zip + "/"):
                continue
            rel_path = member[len(plugin_root_in_zip) + 1:]
        else:
            rel_path = member

        if not rel_path:
            continue

        target = os.path.join(plugin_dir, rel_path)
        # Security: prevent path traversal
        if not os.path.abspath(target).startswith(os.path.abspath(plugin_dir)):
            return jsonify({"success": False, "error": "Invalid zip path"}), 400

        if member.endswith("/"):
            os.makedirs(target, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                dst.write(src.read())

    logger.info(f"Uploaded plugin '{plugin_name}' for tenant {tenant.tenant_id}")
    return jsonify({"success": True, "data": manifest.to_dict()}), 201


# ---------------------------------------------------------------------------
# DELETE /api/plugins/<name> — remove a plugin
# ---------------------------------------------------------------------------

@plugins_bp.route("/<name>", methods=["DELETE"])
@requires_auth
@requires_plan("pro")
def delete_plugin(name: str):
    err = _check_plugin_name(name)
    if err:
        return err
    tenant = g.current_tenant
    plugins_dir = _tenant_plugins_dir(tenant.tenant_id)
    plugin_dir = os.path.join(plugins_dir, name)

    if not os.path.isdir(plugin_dir):
        return jsonify({"success": False, "error": f"Plugin not found: {name}"}), 404

    # Disable first if enabled
    if name in tenant.enabled_plugins:
        tenant.enabled_plugins.remove(name)
    if name in tenant.plugin_configs:
        del tenant.plugin_configs[name]
    TenantManager.save_tenant(tenant)

    shutil.rmtree(plugin_dir)
    logger.info(f"Deleted plugin '{name}' for tenant {tenant.tenant_id}")
    return jsonify({"success": True, "message": f"Plugin '{name}' deleted"})
