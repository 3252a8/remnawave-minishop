"""Regression tests for silent panel-update failures in top-up / tariff-switch flows.

Three sibling methods — ``activate_topup``, ``activate_premium_topup``, and
``switch_tariff_without_payment`` — used to ignore the result of
``panel_service.update_user_details_on_panel``. When the panel update failed,
the local DB still recorded the top-up / tariff change and the function
reported success. The user paid, saw the new traffic / tariff in the app,
but Remnawave never received the change, so the new entitlement was unusable.

Other activation paths (``activate_subscription``, ``_activate_traffic_package``,
``activate_hwid_device_topup``) all check the panel response. These tests pin
the same contract on the three previously-broken paths.
"""

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings

GIB = 1024**3


def _tariffs_config_payload() -> dict:
    return {
        "default_tariff": "standard",
        "tariffs": [
            {
                "key": "standard",
                "names": {"en": "Standard"},
                "descriptions": {"en": "Base"},
                "squad_uuids": ["main-squad"],
                "premium_squad_uuids": ["premium-squad"],
                "premium_monthly_gb": 25,
                "billing_model": "period",
                "monthly_gb": 100,
                "prices_rub": {"1": 150, "3": 400},
                "prices_stars": {"1": 0},
                "enabled_periods": [1, 3],
                "hwid_device_limit": 3,
                "topup_packages": {
                    "rub": [{"gb": 10, "price": 50}],
                    "stars": [],
                },
                "premium_topup_packages": {
                    "rub": [{"gb": 10, "price": 100}],
                    "stars": [],
                },
                "enabled": True,
            },
            {
                "key": "premium",
                "names": {"en": "Premium"},
                "descriptions": {"en": "Premium plan"},
                "squad_uuids": ["main-squad", "premium-extra"],
                "premium_squad_uuids": ["premium-squad"],
                "premium_monthly_gb": 50,
                "billing_model": "period",
                "monthly_gb": 200,
                "prices_rub": {"1": 300, "3": 800},
                "prices_stars": {"1": 0},
                "enabled_periods": [1, 3],
                "enabled": True,
            },
        ],
    }


def _make_settings(tmpdir: str, **overrides: Any) -> Settings:
    config_path = Path(tmpdir) / "tariffs.json"
    config_path.write_text(json.dumps(_tariffs_config_payload()), encoding="utf-8")
    values: dict[str, Any] = {
        "_env_file": None,
        "BOT_TOKEN": "token",
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
        "TARIFFS_CONFIG_PATH": str(config_path),
    }
    values.update(overrides)
    return Settings(**values)


def _make_service(settings: Settings) -> SubscriptionService:
    panel_service = AsyncMock(spec=PanelApiService)
    return SubscriptionService(settings, panel_service)


def _make_sub(**overrides):
    base = dict(
        subscription_id=11,
        user_id=42,
        panel_user_uuid="panel-uuid",
        panel_subscription_uuid="panel-sub",
        tariff_key="standard",
        traffic_limit_bytes=100 * GIB,
        traffic_used_bytes=10 * GIB,
        topup_balance_bytes=0,
        tier_baseline_bytes=100 * GIB,
        regular_bonus_bytes=0,
        regular_unlimited_override=False,
        extra_hwid_devices=0,
        hwid_device_limit=3,
        premium_baseline_bytes=25 * GIB,
        premium_topup_balance_bytes=0,
        premium_topup_used_bytes=0,
        premium_used_bytes=0,
        premium_bonus_bytes=0,
        premium_unlimited_override=False,
        premium_is_limited=False,
        premium_period_start_at=None,
        effective_monthly_price_rub=150,
        end_date=datetime(2099, 1, 1, tzinfo=UTC),
        is_active=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_user():
    return SimpleNamespace(
        user_id=42,
        telegram_id=42,
        email=None,
        username="u",
        first_name="U",
        last_name="L",
        language_code="en",
        panel_user_uuid="panel-uuid",
    )


class ActivateTopupPanelFailureTests(unittest.IsolatedAsyncioTestCase):
    """Regular (non-premium) period top-up. The bug was traffic.py:252 ignoring panel result."""

    async def _run(self, *, panel_response):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir)
            service = _make_service(settings)
            sub = _make_sub()
            user = _make_user()

            service.panel_service.update_user_details_on_panel = AsyncMock(
                return_value=panel_response
            )
            updated_sub = SimpleNamespace(end_date=sub.end_date, subscription_id=11)

            with (
                patch(
                    "bot.services.subscription_service_impl.payments.payment_dal.get_payment_by_db_id",
                    AsyncMock(return_value=SimpleNamespace()),
                ),
                patch(
                    "bot.services.subscription_service_impl.traffic.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
                patch(
                    "bot.services.subscription_service_impl.traffic.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.traffic.subscription_dal.update_subscription",
                    AsyncMock(return_value=updated_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.traffic.tariff_dal.create_traffic_topup",
                    AsyncMock(),
                ) as create_topup,
            ):
                result = await service.activate_topup(
                    session=AsyncMock(),
                    user_id=42,
                    tariff_key="standard",
                    traffic_gb=10,
                    payment_amount=50,
                    payment_db_id=1,
                )
            return result, create_topup

    async def test_returns_none_when_panel_returns_none(self):
        result, create_topup = await self._run(panel_response=None)
        self.assertIsNone(result)
        # The local audit row must NOT be written when the panel rejected the change.
        create_topup.assert_not_awaited()

    async def test_returns_none_when_panel_returns_error_dict(self):
        result, create_topup = await self._run(panel_response={"error": True})
        self.assertIsNone(result)
        create_topup.assert_not_awaited()

    async def test_returns_payload_when_panel_succeeds(self):
        result, create_topup = await self._run(panel_response={"ok": True, "uuid": "panel-uuid"})
        self.assertIsNotNone(result)
        self.assertEqual(result["tariff_key"], "standard")
        self.assertEqual(result["topup_balance_bytes"], 10 * GIB)
        create_topup.assert_awaited_once()


class ActivatePremiumTopupPanelFailureTests(unittest.IsolatedAsyncioTestCase):
    """Premium top-up. The bug was traffic.py:350 ignoring panel result — meant a user could
    pay to lift the premium quota but the panel never re-granted premium squad access."""

    async def _run(self, *, panel_response):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir)
            service = _make_service(settings)
            # Start with premium_is_limited=True so the recompute path is exercised.
            sub = _make_sub(
                premium_topup_balance_bytes=0,
                premium_used_bytes=30 * GIB,  # already over the 25 GB baseline
                premium_is_limited=True,
            )
            user = _make_user()

            service.panel_service.update_user_details_on_panel = AsyncMock(
                return_value=panel_response
            )

            with (
                patch(
                    "bot.services.subscription_service_impl.payments.payment_dal.get_payment_by_db_id",
                    AsyncMock(return_value=SimpleNamespace()),
                ),
                patch(
                    "bot.services.subscription_service_impl.traffic.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
                patch(
                    "bot.services.subscription_service_impl.traffic.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.traffic.subscription_dal.update_subscription",
                    AsyncMock(),
                ),
                patch(
                    "bot.services.subscription_service_impl.traffic.tariff_dal.create_traffic_topup",
                    AsyncMock(),
                ) as create_topup,
            ):
                result = await service.activate_premium_topup(
                    session=AsyncMock(),
                    user_id=42,
                    tariff_key="standard",
                    traffic_gb=10,
                    payment_amount=100,
                    payment_db_id=2,
                )
            return result, create_topup

    async def test_returns_none_when_panel_returns_none(self):
        result, create_topup = await self._run(panel_response=None)
        self.assertIsNone(result)
        create_topup.assert_not_awaited()

    async def test_returns_none_when_panel_returns_error_dict(self):
        result, create_topup = await self._run(panel_response={"error": True})
        self.assertIsNone(result)
        create_topup.assert_not_awaited()

    async def test_returns_payload_when_panel_succeeds(self):
        result, create_topup = await self._run(panel_response={"ok": True, "uuid": "panel-uuid"})
        self.assertIsNotNone(result)
        self.assertEqual(result["tariff_key"], "standard")
        create_topup.assert_awaited_once()

    async def test_skips_panel_patch_when_premium_squads_already_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir)
            service = _make_service(settings)
            sub = _make_sub(
                premium_topup_balance_bytes=0,
                premium_used_bytes=30 * GIB,
                premium_is_limited=True,
            )
            user = _make_user()
            service.panel_service.get_user_by_uuid = AsyncMock(
                return_value={
                    "activeInternalSquads": [
                        {"uuid": "main-squad"},
                        {"uuid": "premium-squad"},
                    ]
                }
            )
            service.panel_service.update_user_details_on_panel = AsyncMock(
                return_value={"ok": True, "uuid": "panel-uuid"}
            )

            with (
                patch(
                    "bot.services.subscription_service_impl.payments.payment_dal.get_payment_by_db_id",
                    AsyncMock(return_value=SimpleNamespace()),
                ),
                patch(
                    "bot.services.subscription_service_impl.traffic.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
                patch(
                    "bot.services.subscription_service_impl.traffic.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.traffic.subscription_dal.update_subscription",
                    AsyncMock(),
                ),
                patch(
                    "bot.services.subscription_service_impl.traffic.tariff_dal.create_traffic_topup",
                    AsyncMock(),
                ) as create_topup,
            ):
                result = await service.activate_premium_topup(
                    session=AsyncMock(),
                    user_id=42,
                    tariff_key="standard",
                    traffic_gb=10,
                    payment_amount=100,
                    payment_db_id=2,
                )

            self.assertIsNotNone(result)
            create_topup.assert_awaited_once()
            service.panel_service.get_user_by_uuid.assert_awaited_once_with(
                "panel-uuid",
                log_response=False,
            )
            service.panel_service.update_user_details_on_panel.assert_not_awaited()


class SwitchTariffPanelFailureTests(unittest.IsolatedAsyncioTestCase):
    """Free tariff switch. The bug was lifecycle.py:121 ignoring panel result — the tariff_key
    flipped in the local DB while the panel kept the user on the old squad set."""

    async def _run(self, *, panel_response, mode="recalc_days"):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir)
            service = _make_service(settings)
            sub = _make_sub(
                tariff_key="standard",
                end_date=datetime.now(UTC) + timedelta(days=20),
            )
            user = _make_user()
            updated = _make_sub(
                tariff_key="premium",
                end_date=datetime.now(UTC) + timedelta(days=10),
                premium_is_limited=False,
                effective_monthly_price_rub=300,
            )

            service.panel_service.update_user_details_on_panel = AsyncMock(
                return_value=panel_response
            )

            with (
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription",
                    AsyncMock(return_value=updated),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.deactivate_other_active_subscriptions",
                    AsyncMock(),
                ) as deactivate_other,
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.create_tariff_change",
                    AsyncMock(),
                ) as create_change,
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.create_traffic_topup",
                    AsyncMock(),
                ),
            ):
                result = await service.switch_tariff_without_payment(
                    session=AsyncMock(),
                    user_id=42,
                    target_tariff_key="premium",
                    mode=mode,
                )
            return result, create_change, deactivate_other

    async def test_returns_none_when_panel_returns_none(self):
        result, create_change, deactivate_other = await self._run(panel_response=None)
        self.assertIsNone(result)
        # tariff_changes audit row must NOT be inserted on panel failure.
        create_change.assert_not_awaited()
        deactivate_other.assert_not_awaited()

    async def test_returns_none_when_panel_returns_error_dict(self):
        result, create_change, deactivate_other = await self._run(panel_response={"error": True})
        self.assertIsNone(result)
        create_change.assert_not_awaited()
        deactivate_other.assert_not_awaited()

    async def test_returns_payload_when_panel_succeeds(self):
        result, create_change, deactivate_other = await self._run(panel_response={"ok": True})
        self.assertIsNotNone(result)
        self.assertEqual(result["tariff_key"], "premium")
        self.assertEqual(deactivate_other.await_args.args[1:], ("panel-uuid", "panel-sub"))
        create_change.assert_awaited_once()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
