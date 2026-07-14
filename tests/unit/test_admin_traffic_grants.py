"""Unit tests for admin-driven traffic grants on SubscriptionService.

These tests cover the new ``admin_grant_topup`` and ``admin_grant_premium_topup``
methods that let admins credit GB to a user as if they had purchased a top-up.
The DAL and panel-service interactions are mocked so the tests stay hermetic.
"""

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings


def _tariffs_config_payload(premium: bool = False) -> dict:
    tariff = {
        "key": "standard",
        "names": {"ru": "Стандарт"},
        "descriptions": {"ru": "Base"},
        "squad_uuids": ["squad-1"],
        "billing_model": "period",
        "monthly_gb": 100,
        "prices_rub": {"1": 150},
        "prices_stars": {"1": 0},
        "enabled_periods": [1],
        "enabled": True,
    }
    if premium:
        tariff["premium_squad_uuids"] = ["premium-squad"]
        tariff["premium_monthly_gb"] = 25
    return {"default_tariff": "standard", "tariffs": [tariff]}


def _make_settings(payload: dict, tmpdir: str, **overrides) -> Settings:
    config_path = Path(tmpdir) / "tariffs.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    values = {
        "_env_file": None,
        "BOT_TOKEN": "token",
        "POSTGRES_USER": "app_user",
        "POSTGRES_PASSWORD": "app_password",
        "TARIFFS_CONFIG_PATH": str(config_path),
    }
    values.update(overrides)
    return Settings(**values)


class FixedDateTime(datetime):
    fixed_now = datetime(2026, 7, 4, 12, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.fixed_now.replace(tzinfo=None)
        return cls.fixed_now.astimezone(tz)


async def _echo_panel_entitlement(panel_uuid, payload, *_args, **_kwargs):
    return {**payload, "uuid": panel_uuid}


class AdminGrantTopupTests(unittest.IsolatedAsyncioTestCase):
    async def test_hwid_limit_sync_pushes_effective_device_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.update_user_details_on_panel = AsyncMock(
                side_effect=_echo_panel_entitlement
            )
            service = SubscriptionService(settings, panel_service)

            db_user = SimpleNamespace(
                user_id=42,
                first_name="Tester",
                last_name=None,
                username="tester",
                language_code="ru",
                panel_user_uuid="panel-uuid",
                email=None,
                telegram_id=42,
            )
            sub = SimpleNamespace(
                subscription_id=7,
                user_id=42,
                panel_user_uuid="panel-uuid",
                end_date=datetime.now(UTC) + timedelta(days=10),
                tariff_key="standard",
                hwid_device_limit=4,
                extra_hwid_devices=0,
            )

            with (
                patch(
                    "bot.services.subscription_service_impl._runtime.user_dal.get_user_by_id",
                    new=AsyncMock(return_value=db_user),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.get_active_subscription_by_user_id",
                    new=AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.tariff_dal.sum_active_hwid_devices",
                    new=AsyncMock(return_value=2),
                ),
            ):
                effective_limit = await service.sync_hwid_device_limit_to_panel(AsyncMock(), 42)

            self.assertEqual(effective_limit, 6)
            self.assertEqual(sub.extra_hwid_devices, 2)
            panel_service.update_user_details_on_panel.assert_awaited_once()
            panel_payload = panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertEqual(panel_payload["hwidDeviceLimit"], 6)

    async def test_hwid_limit_sync_keeps_zero_unlimited(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.update_user_details_on_panel = AsyncMock(
                side_effect=_echo_panel_entitlement
            )
            service = SubscriptionService(settings, panel_service)

            db_user = SimpleNamespace(
                user_id=42,
                first_name="Tester",
                last_name=None,
                username="tester",
                language_code="ru",
                panel_user_uuid="panel-uuid",
                email=None,
                telegram_id=42,
            )
            sub = SimpleNamespace(
                subscription_id=7,
                user_id=42,
                panel_user_uuid="panel-uuid",
                end_date=datetime.now(UTC) + timedelta(days=10),
                tariff_key="standard",
                hwid_device_limit=0,
                extra_hwid_devices=0,
            )

            with (
                patch(
                    "bot.services.subscription_service_impl._runtime.user_dal.get_user_by_id",
                    new=AsyncMock(return_value=db_user),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.get_active_subscription_by_user_id",
                    new=AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.tariff_dal.sum_active_hwid_devices",
                    new=AsyncMock(return_value=3),
                ),
            ):
                effective_limit = await service.sync_hwid_device_limit_to_panel(AsyncMock(), 42)

            self.assertEqual(effective_limit, 0)
            panel_payload = panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertEqual(panel_payload["hwidDeviceLimit"], 0)

    async def test_hwid_limit_sync_treats_missing_default_as_unlimited(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.update_user_details_on_panel = AsyncMock(
                side_effect=_echo_panel_entitlement
            )
            service = SubscriptionService(settings, panel_service)

            db_user = SimpleNamespace(
                user_id=42,
                first_name="Tester",
                last_name=None,
                username="tester",
                language_code="ru",
                panel_user_uuid="panel-uuid",
                email=None,
                telegram_id=42,
            )
            sub = SimpleNamespace(
                subscription_id=7,
                user_id=42,
                panel_user_uuid="panel-uuid",
                end_date=datetime.now(UTC) + timedelta(days=10),
                tariff_key="standard",
                hwid_device_limit=None,
                extra_hwid_devices=0,
            )

            with (
                patch(
                    "bot.services.subscription_service_impl._runtime.user_dal.get_user_by_id",
                    new=AsyncMock(return_value=db_user),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.get_active_subscription_by_user_id",
                    new=AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.tariff_dal.sum_active_hwid_devices",
                    new=AsyncMock(return_value=2),
                ),
            ):
                effective_limit = await service.sync_hwid_device_limit_to_panel(AsyncMock(), 42)

            self.assertEqual(effective_limit, 0)
            panel_payload = panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertEqual(panel_payload["hwidDeviceLimit"], 0)

    async def test_regular_grant_increases_balance_and_panel_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.update_user_details_on_panel = AsyncMock(
                side_effect=_echo_panel_entitlement
            )
            service = SubscriptionService(settings, panel_service)

            db_user = SimpleNamespace(
                user_id=42,
                first_name="Tester",
                last_name=None,
                username="tester",
                language_code="ru",
                panel_user_uuid="panel-uuid",
                email=None,
                telegram_id=42,
            )
            sub = SimpleNamespace(
                subscription_id=7,
                user_id=42,
                panel_user_uuid="panel-uuid",
                end_date=datetime.now(UTC) + timedelta(days=10),
                tariff_key="standard",
                tier_baseline_bytes=100 * (1024**3),
                topup_balance_bytes=5 * (1024**3),
                traffic_limit_bytes=105 * (1024**3),
                is_throttled=True,
                hwid_device_limit=3,
                extra_hwid_devices=0,
                premium_is_limited=False,
            )
            updated_sub = SimpleNamespace(**vars(sub))
            updated_sub.topup_balance_bytes = 55 * (1024**3)
            updated_sub.traffic_limit_bytes = 155 * (1024**3)
            updated_sub.is_throttled = False

            with (
                patch(
                    "bot.services.subscription_service_impl._runtime.user_dal.get_user_by_id",
                    new=AsyncMock(return_value=db_user),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.get_active_subscription_by_user_id",
                    new=AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.update_subscription",
                    new=AsyncMock(return_value=updated_sub),
                ) as upd,
                patch(
                    "bot.services.subscription_service_impl._runtime.tariff_dal.create_traffic_topup",
                    new=AsyncMock(),
                ) as topup_log,
            ):
                result = await service.admin_grant_topup(AsyncMock(), 42, 50.0)

            self.assertIsNotNone(result)
            self.assertEqual(result["topup_balance_bytes"], 55 * (1024**3))
            self.assertEqual(result["traffic_limit_bytes"], 155 * (1024**3))
            self.assertEqual(result["granted_bytes"], 50 * (1024**3))

            upd.assert_awaited_once()
            sub_update_payload = upd.await_args.args[2]
            self.assertEqual(sub_update_payload["topup_balance_bytes"], 55 * (1024**3))
            self.assertEqual(sub_update_payload["traffic_limit_bytes"], 155 * (1024**3))
            self.assertFalse(sub_update_payload["is_throttled"])

            topup_log.assert_awaited_once()
            self.assertEqual(topup_log.await_args.kwargs["kind"], "admin_topup")
            self.assertIsNone(topup_log.await_args.kwargs["payment_id"])
            self.assertEqual(topup_log.await_args.kwargs["purchased_bytes"], 50 * (1024**3))

            panel_service.update_user_details_on_panel.assert_awaited_once()
            panel_payload = panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertEqual(panel_payload["trafficLimitBytes"], 155 * (1024**3))

    async def test_regular_grant_returns_none_and_skips_audit_when_panel_update_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.update_user_details_on_panel = AsyncMock(return_value=None)
            service = SubscriptionService(settings, panel_service)

            db_user = SimpleNamespace(
                user_id=42,
                first_name="Tester",
                last_name=None,
                username="tester",
                language_code="ru",
                panel_user_uuid="panel-uuid",
                email=None,
                telegram_id=42,
            )
            sub = SimpleNamespace(
                subscription_id=7,
                user_id=42,
                panel_user_uuid="panel-uuid",
                end_date=datetime.now(UTC) + timedelta(days=10),
                tariff_key="standard",
                tier_baseline_bytes=100 * (1024**3),
                topup_balance_bytes=5 * (1024**3),
                traffic_limit_bytes=105 * (1024**3),
                is_throttled=True,
                hwid_device_limit=3,
                extra_hwid_devices=0,
                premium_is_limited=False,
            )
            updated_sub = SimpleNamespace(**vars(sub))
            updated_sub.topup_balance_bytes = 55 * (1024**3)
            updated_sub.traffic_limit_bytes = 155 * (1024**3)
            updated_sub.is_throttled = False

            with (
                patch(
                    "bot.services.subscription_service_impl._runtime.user_dal.get_user_by_id",
                    new=AsyncMock(return_value=db_user),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.get_active_subscription_by_user_id",
                    new=AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.update_subscription",
                    new=AsyncMock(return_value=updated_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.tariff_dal.create_traffic_topup",
                    new=AsyncMock(),
                ) as topup_log,
            ):
                result = await service.admin_grant_topup(AsyncMock(), 42, 50.0)

            self.assertIsNone(result)
            topup_log.assert_not_awaited()
            panel_service.update_user_details_on_panel.assert_awaited_once()

    async def test_regular_grant_rejects_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            service = SubscriptionService(settings, AsyncMock(spec=PanelApiService))
            self.assertIsNone(await service.admin_grant_topup(AsyncMock(), 1, 0))
            self.assertIsNone(await service.admin_grant_topup(AsyncMock(), 1, -10))

    async def test_regular_unlimited_override_syncs_zero_panel_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.update_user_details_on_panel = AsyncMock(
                side_effect=_echo_panel_entitlement
            )
            service = SubscriptionService(settings, panel_service)

            db_user = SimpleNamespace(
                user_id=42,
                first_name="Tester",
                last_name=None,
                username="tester",
                language_code="ru",
                panel_user_uuid="panel-uuid",
                email=None,
                telegram_id=42,
            )
            sub = SimpleNamespace(
                subscription_id=7,
                user_id=42,
                panel_user_uuid="panel-uuid",
                end_date=datetime.now(UTC) + timedelta(days=10),
                tariff_key="standard",
                tier_baseline_bytes=100 * (1024**3),
                topup_balance_bytes=0,
                traffic_limit_bytes=105 * (1024**3),
                traffic_used_bytes=2 * (1024**5),
                regular_bonus_bytes=0,
                regular_unlimited_override=True,
                is_throttled=True,
                hwid_device_limit=3,
                extra_hwid_devices=0,
                premium_is_limited=False,
            )

            with (
                patch(
                    "bot.services.subscription_service_impl._runtime.user_dal.get_user_by_id",
                    new=AsyncMock(return_value=db_user),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.get_active_subscription_by_user_id",
                    new=AsyncMock(return_value=sub),
                ),
            ):
                await service.sync_main_traffic_limit_to_panel(AsyncMock(), 42)

            self.assertEqual(sub.traffic_limit_bytes, 0)
            self.assertFalse(sub.is_throttled)
            panel_service.update_user_details_on_panel.assert_awaited_once()
            panel_payload = panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertEqual(panel_payload["trafficLimitBytes"], 0)

    async def test_premium_grant_clears_limited_state_when_balance_covers_overuse(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(premium=True), tmpdir)
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.update_user_details_on_panel = AsyncMock(
                side_effect=_echo_panel_entitlement
            )
            service = SubscriptionService(settings, panel_service)

            db_user = SimpleNamespace(
                user_id=77,
                first_name="Premium",
                last_name=None,
                username="premium",
                language_code="ru",
                panel_user_uuid="panel-uuid",
                email=None,
                telegram_id=77,
            )
            # User has used 30 GB on a 25 GB premium baseline → currently
            # premium_is_limited=True. Admin grants 20 GB of premium top-up.
            sub = SimpleNamespace(
                subscription_id=9,
                user_id=77,
                panel_user_uuid="panel-uuid",
                tariff_key="standard",
                premium_baseline_bytes=25 * (1024**3),
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=30 * (1024**3),
                premium_is_limited=True,
                premium_period_start_at=datetime.now(UTC).replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                ),
                premium_unlimited_override=False,
                premium_bonus_bytes=0,
            )
            updated_sub = SimpleNamespace(**vars(sub))

            with (
                patch(
                    "bot.services.subscription_service_impl._runtime.user_dal.get_user_by_id",
                    new=AsyncMock(return_value=db_user),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.get_active_subscription_by_user_id",
                    new=AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.update_subscription",
                    new=AsyncMock(return_value=updated_sub),
                ) as upd,
                patch(
                    "bot.services.subscription_service_impl._runtime.tariff_dal.create_traffic_topup",
                    new=AsyncMock(),
                ) as topup_log,
            ):
                result = await service.admin_grant_premium_topup(AsyncMock(), 77, 20.0)

            self.assertIsNotNone(result)
            self.assertFalse(result["premium_is_limited"])
            # 5 GB of overuse should be backfilled into premium_topup_used.
            self.assertEqual(result["premium_topup_used_bytes"], 5 * (1024**3))
            # Remaining balance after backfill: 15 GB.
            self.assertEqual(result["premium_topup_balance_bytes"], 15 * (1024**3))
            self.assertEqual(result["granted_bytes"], 20 * (1024**3))

            topup_log.assert_awaited_once()
            self.assertEqual(topup_log.await_args.kwargs["kind"], "admin_premium_topup")
            self.assertIsNone(topup_log.await_args.kwargs["payment_id"])

            panel_service.update_user_details_on_panel.assert_awaited_once()
            panel_payload = panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertIn("premium-squad", panel_payload["activeInternalSquads"])

            sub_update_payload = upd.await_args.args[2]
            self.assertFalse(sub_update_payload["premium_is_limited"])

    async def test_paid_premium_topup_preserves_active_anchored_period_without_panel_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                _tariffs_config_payload(premium=True),
                tmpdir,
                USER_TRAFFIC_STRATEGY="MONTH",
            )
            panel_service = AsyncMock(spec=PanelApiService)
            service = SubscriptionService(settings, panel_service)
            service._record_payment_context = AsyncMock()
            service._send_payment_success_email = AsyncMock()
            service._sync_panel_squads_if_needed = AsyncMock(return_value=True)

            db_user = SimpleNamespace(
                user_id=77,
                first_name="Premium",
                last_name=None,
                username="premium",
                language_code="ru",
                panel_user_uuid="panel-uuid",
                email=None,
                telegram_id=77,
            )
            period_start = datetime(2026, 6, 15, 12, 30, tzinfo=UTC)
            sub = SimpleNamespace(
                subscription_id=9,
                user_id=77,
                panel_user_uuid="panel-uuid",
                tariff_key="standard",
                premium_baseline_bytes=25 * (1024**3),
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=30 * (1024**3),
                premium_is_limited=True,
                premium_period_start_at=period_start,
                premium_unlimited_override=False,
                premium_bonus_bytes=0,
                end_date=datetime(2026, 8, 1, tzinfo=UTC),
            )
            updated_sub = SimpleNamespace(**vars(sub))

            with (
                patch(
                    "bot.services.subscription_service_impl.topups.datetime",
                    FixedDateTime,
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.user_dal.get_user_by_id",
                    new=AsyncMock(return_value=db_user),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.get_active_subscription_by_user_id",
                    new=AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.update_subscription",
                    new=AsyncMock(return_value=updated_sub),
                ) as upd,
                patch(
                    "bot.services.subscription_service_impl._runtime.tariff_dal.create_traffic_topup",
                    new=AsyncMock(),
                ),
            ):
                result = await service.activate_premium_topup(
                    AsyncMock(),
                    77,
                    "standard",
                    20.0,
                    350.0,
                    11,
                )

            self.assertIsNotNone(result)
            self.assertEqual(result["premium_topup_used_bytes"], 5 * (1024**3))
            self.assertEqual(result["premium_topup_balance_bytes"], 15 * (1024**3))
            sub_update_payload = upd.await_args.args[2]
            self.assertEqual(sub_update_payload["premium_period_start_at"], period_start)

    async def test_premium_grant_preserves_active_anchored_period_without_panel_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                _tariffs_config_payload(premium=True),
                tmpdir,
                USER_TRAFFIC_STRATEGY="MONTH",
            )
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.update_user_details_on_panel = AsyncMock(
                side_effect=_echo_panel_entitlement
            )
            service = SubscriptionService(settings, panel_service)

            db_user = SimpleNamespace(
                user_id=77,
                first_name="Premium",
                last_name=None,
                username="premium",
                language_code="ru",
                panel_user_uuid="panel-uuid",
                email=None,
                telegram_id=77,
            )
            period_start = datetime(2026, 6, 15, 12, 30, tzinfo=UTC)
            sub = SimpleNamespace(
                subscription_id=9,
                user_id=77,
                panel_user_uuid="panel-uuid",
                tariff_key="standard",
                premium_baseline_bytes=25 * (1024**3),
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=30 * (1024**3),
                premium_is_limited=True,
                premium_period_start_at=period_start,
                premium_unlimited_override=False,
                premium_bonus_bytes=0,
            )
            updated_sub = SimpleNamespace(**vars(sub))

            with (
                patch(
                    "bot.services.subscription_service_impl.topups.datetime",
                    FixedDateTime,
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.user_dal.get_user_by_id",
                    new=AsyncMock(return_value=db_user),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.get_active_subscription_by_user_id",
                    new=AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.update_subscription",
                    new=AsyncMock(return_value=updated_sub),
                ) as upd,
                patch(
                    "bot.services.subscription_service_impl._runtime.tariff_dal.create_traffic_topup",
                    new=AsyncMock(),
                ),
            ):
                result = await service.admin_grant_premium_topup(AsyncMock(), 77, 20.0)

            self.assertIsNotNone(result)
            self.assertEqual(result["premium_topup_used_bytes"], 5 * (1024**3))
            self.assertEqual(result["premium_topup_balance_bytes"], 15 * (1024**3))
            sub_update_payload = upd.await_args.args[2]
            self.assertEqual(sub_update_payload["premium_period_start_at"], period_start)

    async def test_premium_grant_returns_none_and_skips_audit_when_panel_sync_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(premium=True), tmpdir)
            service = SubscriptionService(settings, AsyncMock(spec=PanelApiService))
            service._sync_panel_squads_if_needed = AsyncMock(return_value=False)

            db_user = SimpleNamespace(
                user_id=77,
                first_name="Premium",
                last_name=None,
                username="premium",
                language_code="ru",
                panel_user_uuid="panel-uuid",
                email=None,
                telegram_id=77,
            )
            sub = SimpleNamespace(
                subscription_id=9,
                user_id=77,
                panel_user_uuid="panel-uuid",
                tariff_key="standard",
                premium_baseline_bytes=25 * (1024**3),
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=30 * (1024**3),
                premium_is_limited=True,
                premium_period_start_at=datetime.now(UTC).replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                ),
                premium_unlimited_override=False,
                premium_bonus_bytes=0,
            )
            updated_sub = SimpleNamespace(**vars(sub))

            with (
                patch(
                    "bot.services.subscription_service_impl._runtime.user_dal.get_user_by_id",
                    new=AsyncMock(return_value=db_user),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.get_active_subscription_by_user_id",
                    new=AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.update_subscription",
                    new=AsyncMock(return_value=updated_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.tariff_dal.create_traffic_topup",
                    new=AsyncMock(),
                ) as topup_log,
            ):
                result = await service.admin_grant_premium_topup(AsyncMock(), 77, 20.0)

            self.assertIsNone(result)
            topup_log.assert_not_awaited()
            service._sync_panel_squads_if_needed.assert_awaited_once()

    async def test_premium_grant_skips_panel_patch_when_squads_already_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(premium=True), tmpdir)
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.get_user_by_uuid = AsyncMock(
                return_value={
                    "activeInternalSquads": [
                        {"uuid": "squad-1"},
                        {"uuid": "premium-squad"},
                    ]
                }
            )
            panel_service.update_user_details_on_panel = AsyncMock(
                side_effect=_echo_panel_entitlement
            )
            service = SubscriptionService(settings, panel_service)

            db_user = SimpleNamespace(
                user_id=77,
                first_name="Premium",
                last_name=None,
                username="premium",
                language_code="ru",
                panel_user_uuid="panel-uuid",
                email=None,
                telegram_id=77,
            )
            sub = SimpleNamespace(
                subscription_id=9,
                user_id=77,
                panel_user_uuid="panel-uuid",
                tariff_key="standard",
                premium_baseline_bytes=25 * (1024**3),
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=30 * (1024**3),
                premium_is_limited=True,
                premium_period_start_at=datetime.now(UTC).replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                ),
                premium_unlimited_override=False,
                premium_bonus_bytes=0,
            )
            updated_sub = SimpleNamespace(**vars(sub))

            with (
                patch(
                    "bot.services.subscription_service_impl._runtime.user_dal.get_user_by_id",
                    new=AsyncMock(return_value=db_user),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.get_active_subscription_by_user_id",
                    new=AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.update_subscription",
                    new=AsyncMock(return_value=updated_sub),
                ) as upd,
                patch(
                    "bot.services.subscription_service_impl._runtime.tariff_dal.create_traffic_topup",
                    new=AsyncMock(),
                ) as topup_log,
            ):
                result = await service.admin_grant_premium_topup(AsyncMock(), 77, 20.0)

            self.assertIsNotNone(result)
            self.assertFalse(result["premium_is_limited"])
            upd.assert_awaited_once()
            topup_log.assert_awaited_once()
            panel_service.get_user_by_uuid.assert_awaited_once_with(
                "panel-uuid",
                log_response=False,
            )
            panel_service.update_user_details_on_panel.assert_not_awaited()

    async def test_premium_grant_fails_when_tariff_has_no_premium_squads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(premium=False), tmpdir)
            service = SubscriptionService(settings, AsyncMock(spec=PanelApiService))

            db_user = SimpleNamespace(
                user_id=11,
                panel_user_uuid="panel-uuid",
            )
            sub = SimpleNamespace(
                subscription_id=1, user_id=11, panel_user_uuid="panel-uuid", tariff_key="standard"
            )

            with (
                patch(
                    "bot.services.subscription_service_impl._runtime.user_dal.get_user_by_id",
                    new=AsyncMock(return_value=db_user),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.get_active_subscription_by_user_id",
                    new=AsyncMock(return_value=sub),
                ),
            ):
                self.assertIsNone(await service.admin_grant_premium_topup(AsyncMock(), 11, 10.0))

    async def test_sync_premium_squad_access_updates_limited_flag_and_panel(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(premium=True), tmpdir)
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.update_user_details_on_panel = AsyncMock(
                side_effect=_echo_panel_entitlement
            )
            service = SubscriptionService(settings, panel_service)

            db_user = SimpleNamespace(
                user_id=88,
                panel_user_uuid="panel-uuid",
            )
            sub = SimpleNamespace(
                subscription_id=3,
                user_id=88,
                panel_user_uuid="panel-uuid",
                tariff_key="standard",
                premium_baseline_bytes=25 * (1024**3),
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=30 * (1024**3),
                premium_is_limited=True,
                premium_period_start_at=datetime.now(UTC).replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                ),
                premium_unlimited_override=False,
                premium_bonus_bytes=10 * (1024**3),
            )

            with (
                patch(
                    "bot.services.subscription_service_impl._runtime.user_dal.get_user_by_id",
                    new=AsyncMock(return_value=db_user),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.get_active_subscription_by_user_id",
                    new=AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl._runtime.subscription_dal.update_subscription",
                    new=AsyncMock(return_value=sub),
                ) as upd,
            ):
                await service.sync_premium_squad_access_to_panel(AsyncMock(), 88)

            upd.assert_awaited_once()
            self.assertFalse(upd.await_args.args[2]["premium_is_limited"])
            panel_service.update_user_details_on_panel.assert_awaited_once()
            squads = panel_service.update_user_details_on_panel.await_args.args[1][
                "activeInternalSquads"
            ]
            self.assertIn("premium-squad", squads)


if __name__ == "__main__":
    unittest.main()
