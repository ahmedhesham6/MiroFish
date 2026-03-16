"""
Integration tests for the Plugin Management API blueprint (/api/plugins).
"""

import io
import json
import os
import shutil
import tempfile
import textwrap
import zipfile

import pytest

# ---- Setup temp dir before importing app ----
_TEMP_DIR = tempfile.mkdtemp()
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ["JWT_EXPIRY_HOURS"] = "48"

import app.config as _cfg  # noqa: E402
_cfg.Config.UPLOAD_FOLDER = _TEMP_DIR

from app import create_app  # noqa: E402
from app.models.tenant import TenantManager  # noqa: E402
from app.plugins.registry import _tenant_plugins_dir  # noqa: E402

TenantManager.TENANTS_DIR = os.path.join(_TEMP_DIR, "tenants")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    application = create_app()
    application.config["TESTING"] = True
    with application.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def clean_state():
    """Reset tenant data between tests."""
    yield
    if os.path.exists(TenantManager.TENANTS_DIR):
        shutil.rmtree(TenantManager.TENANTS_DIR)


def _register_and_login(client, email="user@example.com", password="pw123", tenant="TestCo", plan="starter"):
    resp = client.post("/api/auth/register", json={
        "email": email,
        "password": password,
        "display_name": "Tester",
        "tenant_name": tenant,
    })
    assert resp.status_code == 201
    data = resp.get_json()
    token = data["access_token"]
    tenant_id = data["tenant"]["tenant_id"]
    # Set plan directly for tests that need pro
    if plan != "starter":
        t = TenantManager.get_tenant(tenant_id)
        from app.models.tenant import TenantPlan
        t.plan = TenantPlan(plan)
        t.subscription_status = "active"
        TenantManager.save_tenant(t)
    return token, tenant_id


def _make_plugin_in_tenant(tenant_id: str, plugin_name: str = "test-plugin", plugin_type: str = "source"):
    plugin_dir = os.path.join(_tenant_plugins_dir(tenant_id), plugin_name)
    os.makedirs(plugin_dir, exist_ok=True)
    manifest = textwrap.dedent(f"""
        name: {plugin_name}
        version: 1.0.0
        type: {plugin_type}
        entry_point: main:TestPlugin
        description: A test plugin
        author: MiroFish
        config_schema:
          type: object
          properties:
            api_key:
              type: string
          required: [api_key]
    """)
    with open(os.path.join(plugin_dir, "plugin.yaml"), "w") as f:
        f.write(manifest)
    with open(os.path.join(plugin_dir, "main.py"), "w") as f:
        f.write("from app.plugins.sdk import SourcePlugin\nclass TestPlugin(SourcePlugin):\n    def fetch_data(self, config):\n        return {'documents': [], 'metadata': {}}\n")
    return plugin_dir


def _make_plugin_zip(plugin_name: str = "zip-plugin", plugin_type: str = "source") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        manifest = textwrap.dedent(f"""
            name: {plugin_name}
            version: 2.0.0
            type: {plugin_type}
            entry_point: main:ZipPlugin
            description: Uploaded via zip
            author: MiroFish
        """)
        zf.writestr("plugin.yaml", manifest)
        zf.writestr("main.py", "from app.plugins.sdk import SourcePlugin\nclass ZipPlugin(SourcePlugin):\n    def fetch_data(self, config):\n        return {'documents': [], 'metadata': {}}\n")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

def test_list_plugins_requires_auth(client):
    resp = client.get("/api/plugins")
    assert resp.status_code == 401


def test_get_plugin_requires_auth(client):
    resp = client.get("/api/plugins/some-plugin")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/plugins
# ---------------------------------------------------------------------------

def test_list_plugins_empty(client):
    token, tenant_id = _register_and_login(client, "list@test.com", tenant="ListCo")
    resp = client.get("/api/plugins", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"] == []


def test_list_plugins_with_plugin(client):
    token, tenant_id = _register_and_login(client, "list2@test.com", tenant="ListCo2")
    _make_plugin_in_tenant(tenant_id, "my-plugin")
    resp = client.get("/api/plugins", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.get_json()
    names = [p["name"] for p in data["data"]]
    assert "my-plugin" in names


# ---------------------------------------------------------------------------
# GET /api/plugins/<name>
# ---------------------------------------------------------------------------

def test_get_plugin_not_found(client):
    token, tenant_id = _register_and_login(client, "get404@test.com", tenant="GetCo")
    resp = client.get("/api/plugins/nonexistent", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_get_plugin_found(client):
    token, tenant_id = _register_and_login(client, "get200@test.com", tenant="GetCo2")
    _make_plugin_in_tenant(tenant_id, "my-plugin")
    resp = client.get("/api/plugins/my-plugin", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["name"] == "my-plugin"
    assert "config_schema" in data["data"]


# ---------------------------------------------------------------------------
# POST /api/plugins/<name>/enable and /disable
# ---------------------------------------------------------------------------

def test_enable_plugin(client):
    token, tenant_id = _register_and_login(client, "enable@test.com", tenant="EnableCo")
    _make_plugin_in_tenant(tenant_id, "my-plugin")
    resp = client.post("/api/plugins/my-plugin/enable", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    tenant = TenantManager.get_tenant(tenant_id)
    assert "my-plugin" in tenant.enabled_plugins


def test_enable_plugin_not_found(client):
    token, tenant_id = _register_and_login(client, "enable404@test.com", tenant="EnableCo2")
    resp = client.post("/api/plugins/ghost/enable", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_disable_plugin(client):
    token, tenant_id = _register_and_login(client, "disable@test.com", tenant="DisableCo")
    _make_plugin_in_tenant(tenant_id, "my-plugin")
    client.post("/api/plugins/my-plugin/enable", headers={"Authorization": f"Bearer {token}"})
    resp = client.post("/api/plugins/my-plugin/disable", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    tenant = TenantManager.get_tenant(tenant_id)
    assert "my-plugin" not in tenant.enabled_plugins


def test_enable_already_enabled_is_idempotent(client):
    token, tenant_id = _register_and_login(client, "idem@test.com", tenant="IdemCo")
    _make_plugin_in_tenant(tenant_id, "my-plugin")
    client.post("/api/plugins/my-plugin/enable", headers={"Authorization": f"Bearer {token}"})
    client.post("/api/plugins/my-plugin/enable", headers={"Authorization": f"Bearer {token}"})
    tenant = TenantManager.get_tenant(tenant_id)
    assert tenant.enabled_plugins.count("my-plugin") == 1


# ---------------------------------------------------------------------------
# GET/PUT /api/plugins/<name>/config
# ---------------------------------------------------------------------------

def test_get_config_empty(client):
    token, tenant_id = _register_and_login(client, "cfg_get@test.com", tenant="CfgGet")
    _make_plugin_in_tenant(tenant_id, "my-plugin")
    resp = client.get("/api/plugins/my-plugin/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.get_json()["data"] == {}


def test_put_config_valid(client):
    token, tenant_id = _register_and_login(client, "cfg_put@test.com", tenant="CfgPut")
    _make_plugin_in_tenant(tenant_id, "my-plugin")
    resp = client.put(
        "/api/plugins/my-plugin/config",
        json={"api_key": "secret-key"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["api_key"] == "secret-key"


def test_put_config_invalid_schema_returns_422(client):
    token, tenant_id = _register_and_login(client, "cfg_invalid@test.com", tenant="CfgInvalid")
    _make_plugin_in_tenant(tenant_id, "my-plugin")
    # api_key is required but not provided
    resp = client.put(
        "/api/plugins/my-plugin/config",
        json={"other_field": "value"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    data = resp.get_json()
    assert data["success"] is False
    assert "details" in data


def test_put_config_not_found_returns_404(client):
    token, tenant_id = _register_and_login(client, "cfg404@test.com", tenant="CfgNotFound")
    resp = client.put(
        "/api/plugins/nonexistent/config",
        json={"api_key": "k"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_put_config_non_json_returns_400(client):
    token, tenant_id = _register_and_login(client, "cfg400@test.com", tenant="CfgBad")
    _make_plugin_in_tenant(tenant_id, "my-plugin")
    resp = client.put(
        "/api/plugins/my-plugin/config",
        data="not-json",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "text/plain",
        },
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/plugins/upload
# ---------------------------------------------------------------------------

def test_upload_requires_pro_plan(client):
    token, tenant_id = _register_and_login(client, "upload_starter@test.com", tenant="StarterUp", plan="starter")
    zip_bytes = _make_plugin_zip("new-plugin")
    resp = client.post(
        "/api/plugins/upload",
        data={"file": (io.BytesIO(zip_bytes), "plugin.zip")},
        headers={"Authorization": f"Bearer {token}"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 403


def test_upload_plugin_success(client):
    token, tenant_id = _register_and_login(client, "upload_pro@test.com", tenant="ProUp", plan="pro")
    zip_bytes = _make_plugin_zip("uploaded-plugin")
    resp = client.post(
        "/api/plugins/upload",
        data={"file": (io.BytesIO(zip_bytes), "plugin.zip")},
        headers={"Authorization": f"Bearer {token}"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["name"] == "uploaded-plugin"

    # Verify files on disk
    plugin_dir = os.path.join(_tenant_plugins_dir(tenant_id), "uploaded-plugin")
    assert os.path.isdir(plugin_dir)
    assert os.path.isfile(os.path.join(plugin_dir, "plugin.yaml"))


def test_upload_no_file_returns_400(client):
    token, tenant_id = _register_and_login(client, "upload_nofile@test.com", tenant="NoFileCo", plan="pro")
    resp = client.post(
        "/api/plugins/upload",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_upload_bad_zip_returns_400(client):
    token, tenant_id = _register_and_login(client, "upload_badzip@test.com", tenant="BadZipCo", plan="pro")
    resp = client.post(
        "/api/plugins/upload",
        data={"file": (io.BytesIO(b"not a zip"), "plugin.zip")},
        headers={"Authorization": f"Bearer {token}"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_upload_zip_without_manifest_returns_422(client):
    token, tenant_id = _register_and_login(client, "upload_nomanifest@test.com", tenant="NoManifest", plan="pro")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("main.py", "pass")
    resp = client.post(
        "/api/plugins/upload",
        data={"file": (io.BytesIO(buf.getvalue()), "plugin.zip")},
        headers={"Authorization": f"Bearer {token}"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/plugins/<name>
# ---------------------------------------------------------------------------

def test_delete_requires_pro_plan(client):
    token, tenant_id = _register_and_login(client, "del_starter@test.com", tenant="DelStarter", plan="starter")
    _make_plugin_in_tenant(tenant_id, "my-plugin")
    resp = client.delete("/api/plugins/my-plugin", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_delete_plugin_success(client):
    token, tenant_id = _register_and_login(client, "del_pro@test.com", tenant="DelPro", plan="pro")
    _make_plugin_in_tenant(tenant_id, "my-plugin")
    # Enable first
    client.post("/api/plugins/my-plugin/enable", headers={"Authorization": f"Bearer {token}"})
    resp = client.delete("/api/plugins/my-plugin", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    # Plugin dir removed
    plugin_dir = os.path.join(_tenant_plugins_dir(tenant_id), "my-plugin")
    assert not os.path.isdir(plugin_dir)
    # Tenant no longer has it enabled
    tenant = TenantManager.get_tenant(tenant_id)
    assert "my-plugin" not in tenant.enabled_plugins


def test_delete_plugin_not_found(client):
    token, tenant_id = _register_and_login(client, "del_404@test.com", tenant="DelNotFound", plan="pro")
    resp = client.delete("/api/plugins/ghost", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
