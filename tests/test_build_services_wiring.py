"""Pins the cross-service wiring that ``build_core_services`` performs.

Two non-obvious attachments are critical and have already been the cause of
silent regressions:

* ``subscription_service.yookassa_service`` powers auto-renew. Without it the
  charge step logs ``YooKassa unavailable for auto-renew`` and gives up.
* ``panel_webhook_service.subscription_service`` lets the 24h-before-expiry
  panel webhook trigger an auto-renew through the subscription service.

These tests catch any future regression that drops either attachment, or
silently swallows the wiring step.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from bot.app.factories.build_services import build_core_services
from bot.payment_providers.yookassa import YooKassaService
from bot.services.panel_webhook_service import PanelWebhookService
from bot.services.subscription_service import SubscriptionService
from config.settings import Settings

# Strip all provider env so per-provider BaseSettings models don't pick up
# real credentials from the local .env file during tests.
_PROVIDER_ENV_PREFIXES = (
    "FREEKASSA_",
    "PLATEGA_",
    "SEVERPAY_",
    "WATA_",
    "HELEKET_",
    "CRYPTOPAY_",
    "YOOKASSA_",
    "STARS_",
)


def _clean_env() -> dict[str, str]:
    return {
        k: v
        for k, v in os.environ.items()
        if not any(k.startswith(p) for p in _PROVIDER_ENV_PREFIXES) and not k.startswith("PAYMENT_")
    }


def _make_settings(tmpdir: str, **overrides: Any) -> Settings:
    config_path = Path(tmpdir) / "tariffs.json"
    config_path.write_text(
        json.dumps(
            {
                "default_tariff": "standard",
                "tariffs": [
                    {
                        "key": "standard",
                        "names": {"en": "Standard"},
                        "descriptions": {"en": "Base"},
                        "squad_uuids": ["main"],
                        "billing_model": "period",
                        "monthly_gb": 100,
                        "prices_rub": {"1": 100},
                        "prices_stars": {"1": 0},
                        "enabled_periods": [1],
                        "enabled": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    values: dict[str, Any] = {
        "_env_file": None,
        "BOT_TOKEN": "token",
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
        "TARIFFS_CONFIG_PATH": str(config_path),
    }
    values.update(overrides)
    return Settings(**values)


class BuildServicesWiringTests(unittest.TestCase):
    def test_subscription_service_receives_yookassa_handle(self):
        """Auto-renew reads ``self.yookassa_service`` directly. If this
        attachment ever disappears, every YooKassa auto-renew will silently
        return False without anyone noticing until a charge is missed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir)
            services = build_core_services(
                settings=settings,
                bot=MagicMock(),
                async_session_factory=MagicMock(),
                i18n=MagicMock(),
                bot_username_for_default_return="testbot",
            )

        subscription = services["subscription_service"]
        yookassa = services["yookassa_service"]
        self.assertIsInstance(subscription, SubscriptionService)
        self.assertIsInstance(yookassa, YooKassaService)
        # Identity check: the wired attribute must be the *same* instance.
        self.assertIs(getattr(subscription, "yookassa_service", None), yookassa)
        self.assertIs(getattr(yookassa, "subscription_service", None), subscription)

    def test_panel_webhook_service_can_reach_subscription_service(self):
        """The 24h pre-expiry handler in panel_webhook_service.handle_event
        calls ``getattr(self, 'subscription_service', None)`` and skips the
        auto-renew nudge if it returns None. Pin the back-reference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir)
            services = build_core_services(
                settings=settings,
                bot=MagicMock(),
                async_session_factory=MagicMock(),
                i18n=MagicMock(),
                bot_username_for_default_return="testbot",
            )

        panel_webhook = services["panel_webhook_service"]
        subscription = services["subscription_service"]
        self.assertIsInstance(panel_webhook, PanelWebhookService)
        self.assertIs(getattr(panel_webhook, "subscription_service", None), subscription)

    def test_factory_returns_every_documented_service(self):
        """Guards against silently dropping a service from the bundle. The
        web layer reads these keys off ``request.app`` directly — a missing
        key turns into a runtime KeyError at request time."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir)
            services = build_core_services(
                settings=settings,
                bot=MagicMock(),
                async_session_factory=MagicMock(),
                i18n=MagicMock(),
                bot_username_for_default_return="testbot",
            )

        expected_keys = {
            "panel_service",
            "subscription_service",
            "referral_service",
            "promo_code_service",
            "notification_service",
            "email_auth_service",
            "support_service",
            "stars_service",
            "cryptopay_service",
            "freekassa_service",
            "panel_webhook_service",
            "yookassa_service",
            "lknpd_service",
            "platega_service",
            "severpay_service",
            "wata_service",
            "heleket_service",
        }
        self.assertEqual(set(services), expected_keys)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
