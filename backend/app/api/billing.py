"""
Billing endpoints and Polar webhook handler.
"""

import logging

from flask import g, request, jsonify

from . import billing_bp, webhook_bp
from ..middleware.auth import requires_auth
from ..models.tenant import TenantManager, TenantPlan
from ..services.polar_service import PolarService
from ..config import Config

logger = logging.getLogger(__name__)

# Plan name -> TenantPlan mapping from Polar product name fragments
_POLAR_PRODUCT_PLAN_MAP = {
    "starter": TenantPlan.STARTER,
    "pro": TenantPlan.PRO,
    "enterprise": TenantPlan.ENTERPRISE,
}


# ── Billing status ────────────────────────────────────────────────────────────

@billing_bp.route('/status', methods=['GET'])
@requires_auth
def billing_status():
    """Return current plan, usage, and limits for the authenticated tenant."""
    tenant = g.current_tenant

    tenant.reset_monthly_usage_if_needed()
    limits = tenant.get_limits()

    return jsonify({
        "plan": tenant.plan.value,
        "subscription_status": tenant.subscription_status,
        "usage": {
            "projects": _count_tenant_projects(tenant),
            "simulations_this_month": tenant.usage.get("simulations_this_month", 0),
        },
        "limits": {
            "max_projects": limits["max_projects"],
            "max_simulations_per_month": limits["max_simulations_per_month"],
            "max_plugins": limits["max_plugins"],
            "graph_memory_enabled": limits["graph_memory_enabled"],
            "byok_enabled": limits["byok_enabled"],
        },
    })


# ── Checkout ──────────────────────────────────────────────────────────────────

@billing_bp.route('/checkout', methods=['POST'])
@requires_auth
def billing_checkout():
    """
    Create a Polar checkout session.
    Body: {"plan": "<polar_price_id>"}
    Returns: {"checkout_url": "..."}
    """
    tenant = g.current_tenant

    data = request.get_json() or {}
    plan = data.get("plan")
    if not plan:
        return jsonify({"error": "Missing required field: plan"}), 400

    if not Config.POLAR_ACCESS_TOKEN:
        return jsonify({"error": "Billing not configured"}), 503

    try:
        url = PolarService.get_checkout_url(tenant_id=tenant.tenant_id, plan=plan)
        return jsonify({"checkout_url": url})
    except Exception as exc:
        logger.error("Polar checkout error: %s", exc)
        return jsonify({"error": "Failed to create checkout session"}), 502


# ── Polar webhook ─────────────────────────────────────────────────────────────

@webhook_bp.route('/polar', methods=['POST'])
def polar_webhook():
    """
    Receive Polar webhook events. No auth — validated by signature.
    """
    payload = request.get_data()
    headers = dict(request.headers)

    if not Config.POLAR_WEBHOOK_SECRET:
        logger.warning("Polar webhook received but POLAR_WEBHOOK_SECRET not configured")
        return jsonify({"error": "Webhook not configured"}), 503

    try:
        event = PolarService.validate_webhook(payload, headers)
    except Exception as exc:
        logger.warning("Polar webhook signature invalid: %s", exc)
        return jsonify({"error": "Invalid webhook signature"}), 403

    _handle_webhook_event(event)
    return jsonify({"received": True}), 200


def _handle_webhook_event(event) -> None:
    """Dispatch parsed Polar webhook event to the appropriate handler."""
    event_type = getattr(event, "TYPE", None)
    data = getattr(event, "data", None)

    if event_type == "subscription.active":
        _on_subscription_active(data)
    elif event_type == "subscription.canceled":
        _on_subscription_canceled(data)
    elif event_type == "customer.state_changed":
        _on_customer_state_changed(data)
    else:
        logger.debug("Unhandled Polar event type: %s", event_type)


def _on_subscription_active(subscription) -> None:
    tenant_id = getattr(subscription, "customer_external_id", None)
    if not tenant_id:
        # Fall back to metadata
        metadata = getattr(subscription, "metadata", {}) or {}
        tenant_id = metadata.get("tenant_id")

    if not tenant_id:
        logger.warning("subscription.active: could not determine tenant_id")
        return

    tenant = TenantManager.get_tenant(tenant_id)
    if not tenant:
        logger.warning("subscription.active: tenant not found: %s", tenant_id)
        return

    # Map Polar product name to internal plan
    product = getattr(subscription, "product", None)
    product_name = (getattr(product, "name", "") or "").lower()
    plan = TenantPlan.FREE
    for key, val in _POLAR_PRODUCT_PLAN_MAP.items():
        if key in product_name:
            plan = val
            break

    polar_subscription_id = getattr(subscription, "id", None)
    polar_customer_id = getattr(subscription, "customer_id", None)

    tenant.plan = plan
    tenant.polar_subscription_id = polar_subscription_id
    if polar_customer_id:
        tenant.polar_customer_id = polar_customer_id
    tenant.subscription_status = "active"
    TenantManager.save_tenant(tenant)
    logger.info("Tenant %s activated plan %s", tenant_id, plan.value)


def _on_subscription_canceled(subscription) -> None:
    tenant_id = getattr(subscription, "customer_external_id", None)
    if not tenant_id:
        metadata = getattr(subscription, "metadata", {}) or {}
        tenant_id = metadata.get("tenant_id")

    if not tenant_id:
        logger.warning("subscription.canceled: could not determine tenant_id")
        return

    tenant = TenantManager.get_tenant(tenant_id)
    if not tenant:
        logger.warning("subscription.canceled: tenant not found: %s", tenant_id)
        return

    tenant.plan = TenantPlan.FREE
    tenant.subscription_status = "canceled"
    TenantManager.save_tenant(tenant)
    logger.info("Tenant %s downgraded to FREE (subscription canceled)", tenant_id)


def _on_customer_state_changed(customer_state) -> None:
    external_id = getattr(customer_state, "external_id", None)
    if not external_id:
        logger.debug("customer.state_changed: no external_id, skipping")
        return

    tenant = TenantManager.get_tenant(external_id)
    if not tenant:
        logger.debug("customer.state_changed: tenant not found: %s", external_id)
        return

    # Sync plan from active subscriptions
    active_subs = getattr(customer_state, "active_subscriptions", []) or []
    if active_subs:
        # Use first active subscription to determine plan
        sub = active_subs[0]
        product = getattr(sub, "product", None)
        product_name = (getattr(product, "name", "") or "").lower()
        plan = TenantPlan.FREE
        for key, val in _POLAR_PRODUCT_PLAN_MAP.items():
            if key in product_name:
                plan = val
                break
        tenant.plan = plan
        tenant.subscription_status = "active"
    else:
        tenant.plan = TenantPlan.FREE
        tenant.subscription_status = "none"

    polar_customer_id = getattr(customer_state, "id", None)
    if polar_customer_id:
        tenant.polar_customer_id = polar_customer_id

    TenantManager.save_tenant(tenant)
    logger.info("Tenant %s synced from customer.state_changed: plan=%s", external_id, tenant.plan.value)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _count_tenant_projects(tenant) -> int:
    import os
    from ..config import Config as _Config
    projects_dir = os.path.join(
        _Config.UPLOAD_FOLDER, 'tenants', tenant.tenant_id, 'data', 'projects'
    )
    if not os.path.isdir(projects_dir):
        return 0
    return len([
        d for d in os.listdir(projects_dir)
        if os.path.isdir(os.path.join(projects_dir, d))
    ])
