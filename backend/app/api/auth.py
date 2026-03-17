"""
Authentication API endpoints.
"""

from datetime import datetime, timezone, timedelta

import jwt
from flask import request, jsonify, g

from . import auth_bp
from ..config import Config
from ..middleware.auth import requires_auth
from ..models.tenant import TenantManager, verify_password


def _make_token(user) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.user_id,
        "tenant_id": user.tenant_id,
        "email": user.email,
        "role": user.role,
        "exp": now + timedelta(hours=Config.JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm="HS256")


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    POST /api/auth/register
    Body: {email, password, display_name, tenant_name}
    Returns: {user, tenant, access_token}
    """
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''
    display_name = (data.get('display_name') or '').strip()
    tenant_name = (data.get('tenant_name') or '').strip()

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400
    if not tenant_name:
        return jsonify({"error": "tenant_name is required"}), 400

    # Duplicate email check
    existing = TenantManager.get_user_by_email(email)
    if existing:
        return jsonify({"error": "Email already registered"}), 409

    tenant, user = TenantManager.create_tenant(
        name=tenant_name,
        owner_email=email,
        owner_password=password,
        owner_name=display_name,
    )

    token = _make_token(user)

    return jsonify({
        "user": user.to_dict(),
        "tenant": tenant.to_dict(),
        "access_token": token,
    }), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    POST /api/auth/login
    Body: {email, password}
    Returns: {user, tenant, access_token}
    """
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    user = TenantManager.get_user_by_email(email)
    if not user or not verify_password(user.password_hash, password):
        return jsonify({"error": "Invalid email or password"}), 401

    tenant = TenantManager.get_tenant(user.tenant_id)
    if not tenant:
        return jsonify({"error": "Tenant not found"}), 401

    token = _make_token(user)

    return jsonify({
        "user": user.to_dict(),
        "tenant": tenant.to_dict(),
        "access_token": token,
    })


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """
    POST /api/auth/logout
    Stateless JWT — client simply discards the token.
    """
    return jsonify({"message": "Logged out successfully"})


@auth_bp.route('/me', methods=['GET'])
@requires_auth
def me():
    """
    GET /api/auth/me
    Returns current user and tenant.
    """
    return jsonify({
        "user": g.current_user.to_dict(),
        "tenant": g.current_tenant.to_dict(),
    })
