import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service import SubscriptionService
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
            now = datetime(2099, 1, 15, tzinfo=timezone.utc)
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
                start_date=datetime(2099, 1, 1, tzinfo=timezone.utc),
                end_date=datetime(2099, 2, 1, tzinfo=timezone.utc),
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
                start_date=datetime(2099, 1, 1, tzinfo=timezone.utc),
                end_date=datetime(2099, 2, 1, tzinfo=timezone.utc),
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
