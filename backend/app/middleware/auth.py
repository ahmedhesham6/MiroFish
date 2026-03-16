"""
JWT authentication middleware for MiroFish.
"""

from functools import wraps
from datetime import datetime, timezone

import jwt
from flask import request, g, jsonify

from ..config import Config
from ..models.tenant import TenantManager


def _extract_bearer_token() -> str | None:
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    token = auth_header[len('Bearer '):]
    return token.strip() or None


def requires_auth(f):
    """Decorator that validates a JWT and sets g.current_user / g.current_tenant."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_bearer_token()
        if not token:
            return jsonify({"error": "Authorization header missing or invalid"}), 401

        try:
            payload = jwt.decode(
                token,
                Config.JWT_SECRET_KEY,
                algorithms=["HS256"],
                options={"require": ["sub", "tenant_id", "exp"]},
            )
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError as exc:
            return jsonify({"error": f"Invalid token: {exc}"}), 401

        user_id = payload.get("sub")
        tenant_id = payload.get("tenant_id")

        user = TenantManager.get_user_by_id(user_id, tenant_id)
        if not user:
            return jsonify({"error": "User not found"}), 401

        tenant = TenantManager.get_tenant(tenant_id)
        if not tenant:
            return jsonify({"error": "Tenant not found"}), 401

        g.current_user = user
        g.current_tenant = tenant

        return f(*args, **kwargs)

    return decorated
