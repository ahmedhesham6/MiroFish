"""
Tests for billing plan enforcement, usage limits, and webhook handling.
"""

import json
import hmac
import hashlib
import time
import base64
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

from app import create_app
from app.models.tenant import Tenant, TenantPlan, TenantConfig, PLAN_LIMITS, PLAN_ORDER, TenantManager


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_tenant(plan: TenantPlan = TenantPlan.STARTER) -> Tenant:
    return Tenant(
        tenant_id="tn_test",
        name="Test Tenant",
        plan=plan,
        usage={"simulations_this_month": 0, "usage_month": datetime.now().strftime("%Y-%m")},
    )


# ── PLAN_LIMITS tests ─────────────────────────────────────────────────────────

class TestPlanLimits(unittest.TestCase):

    def test_no_free_plan(self):
        """Free tier should not exist in PLAN_LIMITS."""
        for plan in PLAN_LIMITS:
            self.assertNotEqual(plan.value, "free")

    def test_starter_plan_limits(self):
        limits = PLAN_LIMITS[TenantPlan.STARTER]
        self.assertEqual(limits["max_projects"], 20)
        self.assertEqual(limits["max_simulations_per_month"], 20)
        self.assertEqual(limits["max_plugins"], 10)
        self.assertTrue(limits["graph_memory_enabled"])
        self.assertFalse(limits["byok_enabled"])

    def test_pro_plan_unlimited(self):
        limits = PLAN_LIMITS[TenantPlan.PRO]
        self.assertEqual(limits["max_projects"], -1)
        self.assertEqual(limits["max_simulations_per_month"], -1)
        self.assertTrue(limits["byok_enabled"])

    def test_plan_order(self):
        self.assertEqual(PLAN_ORDER[0], TenantPlan.STARTER)
        self.assertEqual(PLAN_ORDER[-1], TenantPlan.ENTERPRISE)
        starter_idx = PLAN_ORDER.index(TenantPlan.STARTER)
        pro_idx = PLAN_ORDER.index(TenantPlan.PRO)
        self.assertLess(starter_idx, pro_idx)

    def test_free_not_in_plan_order(self):
        plan_values = [p.value for p in PLAN_ORDER]
        self.assertNotIn("free", plan_values)


# ── Tenant model tests ────────────────────────────────────────────────────────

class TestTenantModel(unittest.TestCase):

    def test_default_plan_is_starter(self):
        t = Tenant(tenant_id="tn_x", name="X")
        self.assertEqual(t.plan, TenantPlan.STARTER)

    def test_polar_fields_default(self):
        t = _make_tenant()
        self.assertIsNone(t.polar_customer_id)
        self.assertIsNone(t.polar_subscription_id)
        self.assertEqual(t.subscription_status, "none")

    def test_to_dict_includes_polar_fields(self):
        t = _make_tenant()
        t.polar_customer_id = "pol_cus_123"
        d = t.to_dict()
        self.assertEqual(d["polar_customer_id"], "pol_cus_123")
        self.assertIn("subscription_status", d)
        self.assertIn("usage", d)

    def test_from_dict_round_trip(self):
        t = _make_tenant(TenantPlan.PRO)
        t.polar_customer_id = "pol_cus_abc"
        t.subscription_status = "active"
        t.usage = {"simulations_this_month": 5, "usage_month": "2026-03"}
        d = t.to_dict()
        t2 = Tenant.from_dict(d)
        self.assertEqual(t2.plan, TenantPlan.PRO)
        self.assertEqual(t2.polar_customer_id, "pol_cus_abc")
        self.assertEqual(t2.subscription_status, "active")
        self.assertEqual(t2.usage["simulations_this_month"], 5)

    def test_from_dict_migrates_free_to_starter(self):
        """Legacy tenants with plan=free should be migrated to starter."""
        data = {
            "tenant_id": "tn_legacy",
            "name": "Legacy",
            "plan": "free",
        }
        t = Tenant.from_dict(data)
        self.assertEqual(t.plan, TenantPlan.STARTER)

    def test_reset_monthly_usage_new_month(self):
        t = _make_tenant()
        t.usage = {"simulations_this_month": 10, "usage_month": "2025-01"}
        t.reset_monthly_usage_if_needed()
        self.assertEqual(t.usage["simulations_this_month"], 0)
        self.assertEqual(t.usage["usage_month"], datetime.now().strftime("%Y-%m"))

    def test_reset_monthly_usage_same_month(self):
        t = _make_tenant()
        current_month = datetime.now().strftime("%Y-%m")
        t.usage = {"simulations_this_month": 7, "usage_month": current_month}
        t.reset_monthly_usage_if_needed()
        self.assertEqual(t.usage["simulations_this_month"], 7)  # unchanged

    def test_get_limits_returns_correct_plan(self):
        t = _make_tenant(TenantPlan.STARTER)
        limits = t.get_limits()
        self.assertEqual(limits["max_simulations_per_month"], 20)


# ── requires_plan decorator tests ─────────────────────────────────────────────

class TestRequiresPlan(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def _make_jwt(self, tenant_id: str = "tn_test", user_id: str = "u1") -> str:
        import jwt as pyjwt
        from app.config import Config
        payload = {
            "sub": user_id,
            "tenant_id": tenant_id,
            "email": "test@example.com",
            "role": "owner",
            "exp": int(time.time()) + 3600,
        }
        return pyjwt.encode(payload, Config.JWT_SECRET_KEY, algorithm="HS256")

    def _auth_headers(self, tenant_id: str = "tn_test") -> dict:
        return {"Authorization": f"Bearer {self._make_jwt(tenant_id)}"}

    @patch("app.middleware.auth.TenantManager")
    def test_requires_plan_blocks_starter_from_pro_gate(self, mock_tm):
        starter_tenant = _make_tenant(TenantPlan.STARTER)
        mock_user = MagicMock()
        mock_tm.get_user_by_id.return_value = mock_user
        mock_tm.get_tenant.return_value = starter_tenant

        with self.app.app_context():
            from app.middleware.auth import requires_auth, requires_plan
            from flask import Blueprint, jsonify as _jsonify
            bp = Blueprint("test_plan", __name__)

            @bp.route("/test-plan-gate")
            @requires_auth
            @requires_plan("pro")
            def gated():
                return _jsonify({"ok": True})

            self.app.register_blueprint(bp)

        resp = self.client.get("/test-plan-gate", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertIn("Requires", data["error"])

    @patch("app.middleware.auth.TenantManager")
    def test_requires_plan_allows_sufficient_plan(self, mock_tm):
        pro_tenant = _make_tenant(TenantPlan.PRO)
        mock_user = MagicMock()
        mock_tm.get_user_by_id.return_value = mock_user
        mock_tm.get_tenant.return_value = pro_tenant

        with self.app.app_context():
            from app.middleware.auth import requires_auth, requires_plan
            from flask import Blueprint, jsonify as _jsonify
            bp = Blueprint("test_plan_ok", __name__)

            @bp.route("/test-plan-ok")
            @requires_auth
            @requires_plan("starter")
            def ok_route():
                return _jsonify({"ok": True})

            self.app.register_blueprint(bp)

        resp = self.client.get("/test-plan-ok", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)


# ── Webhook handling tests ────────────────────────────────────────────────────

class TestWebhookHandling(unittest.TestCase):

    def _make_tenant_with_id(self, plan=TenantPlan.STARTER) -> Tenant:
        t = _make_tenant(plan)
        t.tenant_id = "tn_abc"
        return t

    def test_on_subscription_active_updates_plan(self):
        tenant = self._make_tenant_with_id()

        sub = MagicMock()
        sub.customer_external_id = "tn_abc"
        sub.id = "sub_123"
        sub.customer_id = "pol_cus_xyz"
        product = MagicMock()
        product.name = "Starter Monthly"
        sub.product = product
        sub.metadata = {}

        with patch("app.api.billing.TenantManager") as mock_tm:
            mock_tm.get_tenant.return_value = tenant
            from app.api.billing import _on_subscription_active
            _on_subscription_active(sub)
            self.assertEqual(tenant.plan, TenantPlan.STARTER)
            self.assertEqual(tenant.subscription_status, "active")
            self.assertEqual(tenant.polar_subscription_id, "sub_123")
            mock_tm.save_tenant.assert_called_once_with(tenant)

    def test_on_subscription_canceled_keeps_plan(self):
        """Canceled subscription keeps current plan until billing period ends."""
        tenant = self._make_tenant_with_id(TenantPlan.PRO)
        tenant.subscription_status = "active"

        sub = MagicMock()
        sub.customer_external_id = "tn_abc"
        sub.metadata = {}

        with patch("app.api.billing.TenantManager") as mock_tm:
            mock_tm.get_tenant.return_value = tenant
            from app.api.billing import _on_subscription_canceled
            _on_subscription_canceled(sub)
            # Plan should stay PRO (no downgrade to free)
            self.assertEqual(tenant.plan, TenantPlan.PRO)
            self.assertEqual(tenant.subscription_status, "canceled")
            mock_tm.save_tenant.assert_called_once()

    def test_on_customer_state_changed_syncs_plan(self):
        tenant = self._make_tenant_with_id()

        active_sub = MagicMock()
        product = MagicMock()
        product.name = "Pro Annual"
        active_sub.product = product

        customer_state = MagicMock()
        customer_state.external_id = "tn_abc"
        customer_state.id = "pol_cus_xyz"
        customer_state.active_subscriptions = [active_sub]

        with patch("app.api.billing.TenantManager") as mock_tm:
            mock_tm.get_tenant.return_value = tenant
            from app.api.billing import _on_customer_state_changed
            _on_customer_state_changed(customer_state)
            self.assertEqual(tenant.plan, TenantPlan.PRO)
            self.assertEqual(tenant.subscription_status, "active")
            mock_tm.save_tenant.assert_called_once()

    def test_on_customer_state_changed_no_subs_marks_expired(self):
        """No active subscriptions marks tenant as expired (no free tier)."""
        tenant = self._make_tenant_with_id(TenantPlan.STARTER)

        customer_state = MagicMock()
        customer_state.external_id = "tn_abc"
        customer_state.id = "pol_cus_xyz"
        customer_state.active_subscriptions = []

        with patch("app.api.billing.TenantManager") as mock_tm:
            mock_tm.get_tenant.return_value = tenant
            from app.api.billing import _on_customer_state_changed
            _on_customer_state_changed(customer_state)
            # Plan stays as-is, but status is expired
            self.assertEqual(tenant.plan, TenantPlan.STARTER)
            self.assertEqual(tenant.subscription_status, "expired")

    def test_polar_webhook_rejects_bad_signature(self):
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()

        with patch("app.api.billing.Config") as mock_cfg:
            mock_cfg.POLAR_WEBHOOK_SECRET = "test-secret"
            mock_cfg.POLAR_ACCESS_TOKEN = None

            with patch("app.api.billing.PolarService.validate_webhook", side_effect=Exception("bad sig")):
                resp = client.post(
                    "/api/webhooks/polar",
                    data=b'{"type":"subscription.active"}',
                    content_type="application/json",
                )
                self.assertEqual(resp.status_code, 403)


# ── Usage limit enforcement ───────────────────────────────────────────────────

class TestUsageLimitEnforcement(unittest.TestCase):

    def test_simulation_limit_enforced_for_starter(self):
        t = _make_tenant(TenantPlan.STARTER)
        t.reset_monthly_usage_if_needed()
        t.usage["simulations_this_month"] = 20  # at limit

        limits = t.get_limits()
        max_sims = limits["max_simulations_per_month"]
        used = t.usage["simulations_this_month"]
        self.assertGreaterEqual(used, max_sims)

    def test_simulation_limit_not_enforced_for_pro(self):
        t = _make_tenant(TenantPlan.PRO)
        t.usage["simulations_this_month"] = 9999
        limits = t.get_limits()
        self.assertEqual(limits["max_simulations_per_month"], -1)

    def test_graph_memory_enabled_for_starter(self):
        t = _make_tenant(TenantPlan.STARTER)
        limits = t.get_limits()
        self.assertTrue(limits["graph_memory_enabled"])

    def test_graph_memory_enabled_for_pro(self):
        t = _make_tenant(TenantPlan.PRO)
        limits = t.get_limits()
        self.assertTrue(limits["graph_memory_enabled"])


if __name__ == "__main__":
    unittest.main()
