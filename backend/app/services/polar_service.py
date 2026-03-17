"""
Polar billing service — thin wrapper around polar-sdk.
All Polar SDK calls go through this class.
"""

from __future__ import annotations

import logging
from typing import Optional

from polar_sdk import Polar
from polar_sdk.webhooks import validate_event, WebhookVerificationError

from ..config import Config

logger = logging.getLogger(__name__)


class PolarService:

    @staticmethod
    def _client() -> Polar:
        return Polar(access_token=Config.POLAR_ACCESS_TOKEN or "")

    @staticmethod
    def get_checkout_url(tenant_id: str, plan: str) -> str:
        """Create a Polar checkout session and return the URL."""
        client = PolarService._client()
        result = client.checkouts.create(
            request={
                "product_price_id": plan,
                "success_url": None,
                "metadata": {"tenant_id": tenant_id},
                "customer_external_id": tenant_id,
            }
        )
        return result.url

    @staticmethod
    def get_customer_state(tenant_id: str) -> dict:
        """Return Polar customer state for a tenant (keyed by external_id = tenant_id)."""
        client = PolarService._client()
        state = client.customers.get_state_external(id=tenant_id)
        return {
            "polar_customer_id": state.id,
            "email": state.email,
            "active_subscriptions": [
                {
                    "id": sub.id,
                    "product_id": sub.product_id,
                    "status": sub.status,
                }
                for sub in (state.active_subscriptions or [])
            ],
        }

    @staticmethod
    def validate_webhook(payload: bytes, headers: dict) -> object:
        """
        Validate and parse an incoming Polar webhook.
        Returns a parsed payload object.
        Raises WebhookVerificationError on invalid signature.
        """
        secret = Config.POLAR_WEBHOOK_SECRET
        if not secret:
            raise ValueError("POLAR_WEBHOOK_SECRET is not configured")
        return validate_event(payload, headers, secret)

    @staticmethod
    def report_usage(tenant_id: str, meter_name: str, value: int) -> None:
        """Ingest a usage event to Polar meters (internal tracking only)."""
        try:
            client = PolarService._client()
            client.meters.ingest(
                request={
                    "events": [
                        {
                            "name": meter_name,
                            "external_customer_id": tenant_id,
                            "value": value,
                        }
                    ]
                }
            )
        except Exception as exc:
            # Non-critical — log and continue
            logger.warning("Failed to report usage to Polar: %s", exc)
