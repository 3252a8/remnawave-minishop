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


def _settings(tmpdir: str) -> Settings:
    payload = {
        "default_tariff": "basic",
        "tariffs": [
            {
                "key": "basic",
                "names": {"en": "Basic"},
                "descriptions": {"en": "Basic"},
                "squad_uuids": ["basic"],
                "billing_model": "period",
                "monthly_gb": 100,
                "prices_rub": {"1": 100},
                "enabled_periods": [1],
                "hwid_device_limit": 3,
                "enabled": True,
            },
            {
                "key": "pro",
                "names": {"en": "Pro"},
                "descriptions": {"en": "Pro"},
                "squad_uuids": ["pro"],
                "billing_model": "period",
                "monthly_gb": 200,
                "prices_rub": {"1": 200},
                "enabled_periods": [1],
                "hwid_device_limit": 5,
                "enabled": True,
            },
        ],
    }
    return _settings_from_payload(payload, tmpdir)


def _settings_from_payload(payload: dict, tmpdir: str) -> Settings:
    config_path = Path(tmpdir) / "tariffs.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    return Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="u",
        POSTGRES_PASSWORD="p",
        TARIFFS_CONFIG_PATH=str(config_path),
    )


def _service(settings: Settings) -> SubscriptionService:
    panel = AsyncMock(spec=PanelApiService)
    panel.update_user_details_on_panel = AsyncMock(return_value={"ok": True})
    return SubscriptionService(settings, panel)


class HwidTariffSwitchConversionTests(unittest.IsolatedAsyncioTestCase):
    async def test_hwid_remaining_rub_value_is_converted_to_target_tariff_days(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _settings(tmpdir)
            service = _service(settings)
            now = datetime(2099, 1, 15, tzinfo=UTC)
            sub = SimpleNamespace(subscription_id=11)

            with patch(
                "bot.services.subscription_service_impl.tariffs.tariff_dal.get_hwid_device_value_entries",
                AsyncMock(
                    return_value=[
                        {
                            "purchase_id": 7,
                            "purchased_devices": 1,
                            "valid_from": now - timedelta(days=15),
                            "valid_until": now + timedelta(days=15),
                            "created_at": now - timedelta(days=15),
                            "amount": 100,
                            "currency": "RUB",
                        }
                    ]
                ),
            ):
                credit = await service._hwid_conversion_credit(
                    AsyncMock(),
                    sub,
                    at=now,
                )

        self.assertEqual(credit["purchase_ids"], [7])
        self.assertAlmostEqual(credit["value_rub"], 50)

    async def test_switch_expires_converted_hwid_purchases_and_audits_value(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _settings(tmpdir)
            service = _service(settings)
            user = SimpleNamespace(
                user_id=42,
                telegram_id=42,
                panel_user_uuid="panel-user",
                email=None,
                username="u",
                first_name="U",
                last_name="L",
            )
            sub = SimpleNamespace(
                subscription_id=11,
                user_id=42,
                panel_user_uuid="panel-user",
                panel_subscription_uuid="panel-sub",
                tariff_key="basic",
                start_date=datetime(2099, 1, 1, tzinfo=UTC),
                end_date=datetime(2099, 2, 1, tzinfo=UTC),
                effective_monthly_price_rub=100,
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=0,
                topup_balance_bytes=0,
                regular_bonus_bytes=0,
                regular_unlimited_override=False,
                traffic_used_bytes=0,
                extra_hwid_devices=1,
                hwid_device_limit=3,
            )
            updated = SimpleNamespace(**{**sub.__dict__, "tariff_key": "pro"})
            updated.hwid_device_limit = 5
            updated.extra_hwid_devices = 0
            updated.traffic_limit_bytes = 200 * (1024**3)
            updated.premium_is_limited = False
            updated.effective_monthly_price_rub = 200

            with (
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=sub),
                ),
                patch.object(
                    service,
                    "calculate_tariff_switch_options_with_hwid",
                    AsyncMock(
                        return_value={
                            "mode": "period_to_period",
                            "remaining_days": 20,
                            "recalc_days": 25,
                            "paid_diff_rub": 0,
                            "target_monthly_rub": 200,
                            "converted_hwid_value_rub": 50,
                            "converted_hwid_days": 7,
                            "convertible_hwid_purchase_ids": [7],
                        }
                    ),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.expire_hwid_device_purchases",
                    AsyncMock(return_value=1),
                ) as expire_purchases,
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.sum_active_hwid_devices",
                    AsyncMock(return_value=0),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription",
                    AsyncMock(return_value=updated),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.deactivate_other_active_subscriptions",
                    AsyncMock(),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.create_tariff_change",
                    AsyncMock(),
                ) as create_change,
            ):
                result = await service.switch_tariff_without_payment(
                    AsyncMock(),
                    user_id=42,
                    target_tariff_key="pro",
                    mode="recalc_days",
                )

        self.assertEqual(result["tariff_key"], "pro")
        expire_purchases.assert_awaited_once()
        change_payload = create_change.await_args.args[1]
        self.assertEqual(change_payload["converted_hwid_value_rub"], 50)
        self.assertEqual(change_payload["converted_hwid_days"], 7)

    async def test_admin_assign_converts_trial_subscription_to_admin_tariff(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _settings(tmpdir)
            service = _service(settings)
            user = SimpleNamespace(
                user_id=42,
                telegram_id=42,
                panel_user_uuid="panel-user",
                email=None,
                username="u",
                first_name="U",
                last_name="L",
            )
            sub = SimpleNamespace(
                subscription_id=11,
                user_id=42,
                panel_user_uuid="panel-user",
                panel_subscription_uuid="panel-sub",
                tariff_key="basic",
                start_date=datetime(2099, 1, 1, tzinfo=UTC),
                end_date=datetime(2099, 1, 8, tzinfo=UTC),
                duration_months=0,
                provider="trial",
                status_from_panel="ACTIVE",
                effective_monthly_price_rub=0,
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=0,
                topup_balance_bytes=0,
                regular_bonus_bytes=0,
                regular_unlimited_override=False,
                traffic_used_bytes=0,
                extra_hwid_devices=0,
                hwid_device_limit=3,
            )
            updated = SimpleNamespace(**{**sub.__dict__, "tariff_key": "pro"})
            updated.provider = "admin"
            updated.status_from_panel = "ACTIVE"
            updated.duration_months = 1
            updated.hwid_device_limit = 5
            updated.extra_hwid_devices = 0
            updated.traffic_limit_bytes = 200 * (1024**3)
            updated.premium_is_limited = False
            updated.effective_monthly_price_rub = 200

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
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.sum_active_hwid_devices",
                    AsyncMock(return_value=0),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription",
                    AsyncMock(return_value=updated),
                ) as update_subscription,
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.deactivate_other_active_subscriptions",
                    AsyncMock(),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.create_tariff_change",
                    AsyncMock(),
                ),
            ):
                result = await service.switch_tariff_without_payment(
                    AsyncMock(),
                    user_id=42,
                    target_tariff_key="pro",
                    mode="admin_assign",
                )

        self.assertEqual(result["tariff_key"], "pro")
        update_data = update_subscription.await_args.args[2]
        self.assertEqual(update_data["tariff_key"], "pro")
        self.assertEqual(update_data["provider"], "admin")
        self.assertEqual(update_data["status_from_panel"], "ACTIVE")
        self.assertEqual(update_data["duration_months"], 1)
        self.assertEqual(update_data["hwid_device_limit"], 3)
        self.assertFalse(update_data["skip_notifications"])
        self.assertFalse(update_data["suppress_early_expiry_notifications"])

    async def test_admin_assign_can_apply_target_tariff_hwid_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _settings(tmpdir)
            service = _service(settings)
            user = SimpleNamespace(
                user_id=42,
                telegram_id=42,
                panel_user_uuid="panel-user",
                email=None,
                username="u",
                first_name="U",
                last_name="L",
            )
            sub = SimpleNamespace(
                subscription_id=11,
                user_id=42,
                panel_user_uuid="panel-user",
                panel_subscription_uuid="panel-sub",
                tariff_key="basic",
                start_date=datetime(2099, 1, 1, tzinfo=UTC),
                end_date=datetime(2099, 2, 1, tzinfo=UTC),
                effective_monthly_price_rub=100,
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=0,
                topup_balance_bytes=0,
                regular_bonus_bytes=0,
                regular_unlimited_override=False,
                traffic_used_bytes=0,
                extra_hwid_devices=1,
                hwid_device_limit=0,
            )
            updated = SimpleNamespace(**{**sub.__dict__, "tariff_key": "pro"})
            updated.hwid_device_limit = 5
            updated.extra_hwid_devices = 1
            updated.traffic_limit_bytes = 200 * (1024**3)
            updated.premium_is_limited = False
            updated.effective_monthly_price_rub = 200

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
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.sum_active_hwid_devices",
                    AsyncMock(return_value=1),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription",
                    AsyncMock(return_value=updated),
                ) as update_subscription,
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.deactivate_other_active_subscriptions",
                    AsyncMock(),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.create_tariff_change",
                    AsyncMock(),
                ),
            ):
                result = await service.switch_tariff_without_payment(
                    AsyncMock(),
                    user_id=42,
                    target_tariff_key="pro",
                    mode="admin_assign",
                    apply_tariff_hwid_limit=True,
                )

        self.assertEqual(result["tariff_key"], "pro")
        update_data = update_subscription.await_args.args[2]
        self.assertEqual(update_data["hwid_device_limit"], 5)
        panel_payload = service.panel_service.update_user_details_on_panel.await_args.args[1]
        self.assertEqual(panel_payload["hwidDeviceLimit"], 6)

    async def test_paid_switch_records_payment_id_in_single_tariff_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _settings(tmpdir)
            service = _service(settings)
            user = SimpleNamespace(
                user_id=42,
                telegram_id=42,
                panel_user_uuid="panel-user",
                email=None,
                username="u",
                first_name="U",
                last_name="L",
            )
            sub = SimpleNamespace(
                subscription_id=11,
                user_id=42,
                panel_user_uuid="panel-user",
                panel_subscription_uuid="panel-sub",
                tariff_key="basic",
                start_date=datetime(2099, 1, 1, tzinfo=UTC),
                end_date=datetime(2099, 2, 1, tzinfo=UTC),
                effective_monthly_price_rub=100,
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=0,
                topup_balance_bytes=0,
                regular_bonus_bytes=0,
                regular_unlimited_override=False,
                traffic_used_bytes=0,
                extra_hwid_devices=0,
                hwid_device_limit=3,
            )
            updated = SimpleNamespace(**{**sub.__dict__, "tariff_key": "pro"})
            updated.hwid_device_limit = 5
            updated.extra_hwid_devices = 0
            updated.traffic_limit_bytes = 200 * (1024**3)
            updated.premium_is_limited = False
            updated.effective_monthly_price_rub = 200

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
                    "bot.services.subscription_service_impl.lifecycle.payment_dal.get_payment_by_db_id",
                    AsyncMock(
                        return_value=SimpleNamespace(
                            payment_id=99,
                            user_id=42,
                            amount=50,
                            sale_mode="tariff_upgrade",
                            tariff_key="pro",
                        )
                    ),
                ),
                patch.object(
                    service,
                    "calculate_tariff_switch_options_with_hwid",
                    AsyncMock(
                        return_value={
                            "mode": "period_to_period",
                            "remaining_days": 20,
                            "recalc_days": 20,
                            "paid_diff_rub": 50,
                            "target_monthly_rub": 200,
                            "converted_hwid_value_rub": 0,
                            "converted_hwid_days": 0,
                            "convertible_hwid_purchase_ids": [],
                        }
                    ),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.sum_active_hwid_devices",
                    AsyncMock(return_value=0),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription",
                    AsyncMock(return_value=updated),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.deactivate_other_active_subscriptions",
                    AsyncMock(),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.create_tariff_change",
                    AsyncMock(),
                ) as create_change,
            ):
                result = await service.switch_tariff_without_payment(
                    AsyncMock(),
                    user_id=42,
                    target_tariff_key="pro",
                    mode="paid_diff",
                    payment_id=99,
                )

        self.assertEqual(result["tariff_key"], "pro")
        create_change.assert_awaited_once()
        change_payload = create_change.await_args.args[1]
        self.assertEqual(change_payload["payment_id"], 99)
        self.assertEqual(change_payload["mode"], "paid_diff")

    async def test_paid_switch_without_payment_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _settings(tmpdir)
            service = _service(settings)
            user = SimpleNamespace(user_id=42, panel_user_uuid="panel-user")
            sub = SimpleNamespace(
                subscription_id=11,
                user_id=42,
                panel_user_uuid="panel-user",
                panel_subscription_uuid="panel-sub",
                tariff_key="basic",
                start_date=datetime(2099, 1, 1, tzinfo=UTC),
                end_date=datetime(2099, 2, 1, tzinfo=UTC),
                effective_monthly_price_rub=100,
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
                patch.object(
                    service,
                    "calculate_tariff_switch_options_with_hwid",
                    AsyncMock(
                        return_value={
                            "mode": "period_to_period",
                            "remaining_days": 20,
                            "recalc_days": 20,
                            "paid_diff_rub": 50,
                            "target_monthly_rub": 200,
                            "convertible_hwid_purchase_ids": [],
                        }
                    ),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription",
                    AsyncMock(),
                ) as update_subscription,
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.create_tariff_change",
                    AsyncMock(),
                ) as create_change,
            ):
                result = await service.switch_tariff_without_payment(
                    AsyncMock(),
                    user_id=42,
                    target_tariff_key="pro",
                    mode="paid_diff",
                )

        self.assertIsNone(result)
        update_subscription.assert_not_awaited()
        create_change.assert_not_awaited()

    async def test_paid_switch_underpaid_payment_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _settings(tmpdir)
            service = _service(settings)
            user = SimpleNamespace(user_id=42, panel_user_uuid="panel-user")
            sub = SimpleNamespace(
                subscription_id=11,
                user_id=42,
                panel_user_uuid="panel-user",
                panel_subscription_uuid="panel-sub",
                tariff_key="basic",
                start_date=datetime(2099, 1, 1, tzinfo=UTC),
                end_date=datetime(2099, 2, 1, tzinfo=UTC),
                effective_monthly_price_rub=100,
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
                    "bot.services.subscription_service_impl.lifecycle.payment_dal.get_payment_by_db_id",
                    AsyncMock(
                        return_value=SimpleNamespace(
                            payment_id=99,
                            user_id=42,
                            amount=49,
                            sale_mode="tariff_upgrade@pro",
                        )
                    ),
                ),
                patch.object(
                    service,
                    "calculate_tariff_switch_options_with_hwid",
                    AsyncMock(
                        return_value={
                            "mode": "period_to_period",
                            "remaining_days": 20,
                            "recalc_days": 20,
                            "paid_diff_rub": 50,
                            "target_monthly_rub": 200,
                            "convertible_hwid_purchase_ids": [],
                        }
                    ),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription",
                    AsyncMock(),
                ) as update_subscription,
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.create_tariff_change",
                    AsyncMock(),
                ) as create_change,
            ):
                result = await service.switch_tariff_without_payment(
                    AsyncMock(),
                    user_id=42,
                    target_tariff_key="pro",
                    mode="paid_diff",
                    payment_id=99,
                )

        self.assertIsNone(result)
        update_subscription.assert_not_awaited()
        create_change.assert_not_awaited()

    async def test_legacy_missing_effective_price_uses_current_tariff_price(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _settings(tmpdir)
            service = _service(settings)
            target = settings.tariffs_config.require("pro")
            sub = SimpleNamespace(
                tariff_key="basic",
                end_date=datetime.now(UTC) + timedelta(days=20, hours=1),
                effective_monthly_price_rub=None,
            )

            options = service.calculate_tariff_switch_options(sub, target)

        self.assertEqual(options["mode"], "period_to_period")
        self.assertEqual(options["remaining_days"], 20)
        self.assertEqual(options["recalc_days"], 10)
        self.assertEqual(options["paid_diff_rub"], 67)

    async def test_multi_month_target_price_is_normalized_to_monthly_equivalent(self):
        payload = {
            "default_tariff": "basic",
            "tariffs": [
                {
                    "key": "basic",
                    "names": {"en": "Basic"},
                    "descriptions": {"en": "Basic"},
                    "squad_uuids": ["basic"],
                    "billing_model": "period",
                    "monthly_gb": 100,
                    "prices_rub": {"1": 100},
                    "enabled_periods": [1],
                    "enabled": True,
                },
                {
                    "key": "pro",
                    "names": {"en": "Pro"},
                    "descriptions": {"en": "Pro"},
                    "squad_uuids": ["pro"],
                    "billing_model": "period",
                    "monthly_gb": 200,
                    "prices_rub": {"3": 270},
                    "enabled_periods": [3],
                    "enabled": True,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _settings_from_payload(payload, tmpdir)
            service = _service(settings)
            target = settings.tariffs_config.require("pro")
            sub = SimpleNamespace(
                tariff_key="basic",
                end_date=datetime.now(UTC) + timedelta(days=30, hours=1),
                effective_monthly_price_rub=100,
            )

            options = service.calculate_tariff_switch_options(sub, target)

        self.assertEqual(options["remaining_days"], 30)
        self.assertEqual(options["target_monthly_rub"], 90)
        self.assertEqual(options["recalc_days"], 33)
        self.assertEqual(options["paid_diff_rub"], 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
