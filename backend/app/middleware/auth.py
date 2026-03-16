"""
JWT authentication middleware for MiroFish.
"""

from functools import wraps
from datetime import datetime, timezone
import os

import jwt
from flask import request, g, jsonify

from ..config import Config
from ..models.tenant import TenantManager, PLAN_ORDER


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
            return jsonify({"error": "Invalid token"}), 401

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


def requires_active_subscription(f):
    """
    Decorator that requires the tenant to have an active subscription.
    Must be used after @requires_auth so g.current_tenant is available.
    No free tier — every tenant must pay to use the SaaS.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        tenant = g.current_tenant
        if tenant.subscription_status not in ("active", "canceled"):
            # "canceled" still has access until billing period ends
            # "expired" and "none" are blocked
            return jsonify({
                "error": "Active subscription required",
                "subscription_status": tenant.subscription_status,
            }), 403
        return f(*args, **kwargs)
    return decorated


def requires_plan(min_plan: str):
    """
    Decorator that requires the tenant to be on at least min_plan.
    Must be used after @requires_auth so g.current_tenant is available.

    Plan order: starter < pro < enterprise
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            from ..models.tenant import TenantPlan
            tenant = g.current_tenant
            try:
                required = TenantPlan(min_plan.lower())
            except ValueError:
                return jsonify({"error": f"Unknown plan: {min_plan}"}), 500

            tenant_idx = PLAN_ORDER.index(tenant.plan) if tenant.plan in PLAN_ORDER else 0
            required_idx = PLAN_ORDER.index(required) if required in PLAN_ORDER else 0

            if tenant_idx < required_idx:
                return jsonify({
                    "error": f"Requires {min_plan.upper()} plan or higher"
                }), 403

            return f(*args, **kwargs)
        return decorated
    return decorator


def check_usage_limit(resource: str):
    """
    Decorator that enforces plan usage limits.
    Must be used after @requires_auth so g.current_tenant is available.

    resource: "project" | "simulation" | "plugin" | "graph_memory"
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            tenant = g.current_tenant
            limits = tenant.get_limits()

            if resource == "project":
                max_projects = limits.get("max_projects", 0)
                if max_projects != -1:
                    # Count projects in tenant data dir
                    from ..config import Config as _Config
                    projects_dir = os.path.join(
                        _Config.UPLOAD_FOLDER, 'tenants', tenant.tenant_id, 'data', 'projects'
                    )
                    count = 0
                    if os.path.isdir(projects_dir):
                        count = len([
                            d for d in os.listdir(projects_dir)
                            if os.path.isdir(os.path.join(projects_dir, d))
                        ])
                    if count >= max_projects:
                        return jsonify({"error": f"Plan limit reached: max {max_projects} projects"}), 403

            elif resource == "simulation":
                tenant.reset_monthly_usage_if_needed()
                max_sims = limits.get("max_simulations_per_month", 0)
                if max_sims != -1:
                    used = tenant.usage.get("simulations_this_month", 0)
                    if used >= max_sims:
                        return jsonify({
                            "error": f"Plan limit reached: max {max_sims} simulations per month"
                        }), 403

            elif resource == "plugin":
                max_plugins = limits.get("max_plugins", 0)
                if max_plugins != -1:
                    count = len(tenant.enabled_plugins)
                    if count >= max_plugins:
                        return jsonify({"error": f"Plan limit reached: max {max_plugins} plugins"}), 403

            elif resource == "graph_memory":
                if not limits.get("graph_memory_enabled", False):
                    return jsonify({"error": "Graph memory updates require Starter plan or higher"}), 403

            return f(*args, **kwargs)
        return decorated
    return decorator
