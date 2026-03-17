"""
BYOK settings API endpoints.
"""

from flask import g, jsonify, request

from . import settings_bp
from ..middleware.auth import requires_auth, requires_plan
from ..models.tenant import TenantConfig, TenantManager
from ..utils.logger import get_logger

logger = get_logger("mirofish.api.settings")

_BYOK_FIELDS = ("llm_api_key", "llm_base_url", "llm_model_name", "zep_api_key")


def _mask_key(value: str | None) -> str | None:
    """Return last-4-char masked version of a secret key, or None if unset."""
    if not value:
        return None
    if len(value) <= 4:
        return "***" + value
    return "***" + value[-4:]


def _masked_config(config: TenantConfig) -> dict:
    return {
        "llm_api_key": _mask_key(config.llm_api_key),
        "llm_base_url": config.llm_base_url,
        "llm_model_name": config.llm_model_name,
        "zep_api_key": _mask_key(config.zep_api_key),
    }


# ---------------------------------------------------------------------------
# GET /api/settings/keys
# ---------------------------------------------------------------------------

@settings_bp.route("/keys", methods=["GET"])
@requires_auth
@requires_plan("pro")
def get_keys():
    tenant = g.current_tenant
    return jsonify(_masked_config(tenant.config)), 200


# ---------------------------------------------------------------------------
# PUT /api/settings/keys
# ---------------------------------------------------------------------------

@settings_bp.route("/keys", methods=["PUT"])
@requires_auth
@requires_plan("pro")
def put_keys():
    tenant = g.current_tenant
    data = request.get_json(silent=True) or {}

    for field in _BYOK_FIELDS:
        if field in data:
            setattr(tenant.config, field, data[field])  # None clears the field

    TenantManager.save_tenant(tenant)
    logger.info("BYOK config updated for tenant %s", tenant.tenant_id)

    return jsonify(_masked_config(tenant.config)), 200
