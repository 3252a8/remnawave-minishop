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

GIB = 1024**3


def _settings(tmpdir: str) -> Settings:
    config_path = Path(tmpdir) / "tariffs.json"
    config_path.write_text(
        json.dumps(
            {
                "default_tariff": "standard",
                "tariffs": [
                    {
                        "key": "standard",
                        "names": {"en": "Standard"},
                        "descriptions": {"en": "Standard"},
                        "squad_uuids": ["regular-squad"],
                        "premium_squad_uuids": ["premium-squad"],
                        "billing_model": "period",
                        "monthly_gb": 100,
                        "premium_monthly_gb": 25,
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
    return Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="user",
        POSTGRES_PASSWORD="password",
        TARIFFS_CONFIG_PATH=str(config_path),
    )


class PromoTrafficGrantTests(unittest.IsolatedAsyncioTestCase):
    async def test_composite_grant_uses_persistent_topup_balances(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.get_user_by_uuid = AsyncMock(return_value={"tag": None})
            panel_service.update_user_details_on_panel = AsyncMock(
                side_effect=lambda panel_uuid, payload, **kwargs: {
                    **payload,
                    "uuid": panel_uuid,
                }
            )
            service = SubscriptionService(_settings(tmpdir), panel_service)
            service._resolve_hwid_device_limits = AsyncMock(
                return_value=SimpleNamespace(base=3, extra=0, effective=3)
            )
            service._hwid_device_traffic_bonus_bytes_for_sub = AsyncMock(return_value=0)
            service._premium_accounting_period_start = lambda sub, now: sub.premium_period_start_at
            service._same_premium_accounting_period = lambda sub, start, now: True
            service.build_effective_panel_squad_fields = AsyncMock(
                return_value={"activeInternalSquads": ["regular-squad", "premium-squad"]}
            )
            service._confirmed_panel_entitlement = AsyncMock(
                side_effect=lambda panel_uuid, result, payload, **kwargs: result
            )
            now = datetime.now(UTC)
            old_end = now + timedelta(days=10)
            user = SimpleNamespace(
                user_id=42,
                panel_user_uuid="panel-uuid",
                username="tester",
                first_name="Tester",
                last_name=None,
                email=None,
                telegram_id=42,
            )
            sub = SimpleNamespace(
                subscription_id=7,
                user_id=42,
                panel_user_uuid="panel-uuid",
                end_date=old_end,
                tariff_key="standard",
                tier_baseline_bytes=100 * GIB,
                topup_balance_bytes=5 * GIB,
                traffic_limit_bytes=105 * GIB,
                traffic_used_bytes=20 * GIB,
                regular_bonus_bytes=0,
                regular_unlimited_override=False,
                premium_baseline_bytes=25 * GIB,
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=30 * GIB,
                premium_bonus_bytes=0,
                premium_unlimited_override=False,
                premium_is_limited=True,
                premium_period_start_at=now.replace(day=1, hour=0, minute=0, second=0),
                is_throttled=True,
                last_notification_sent="expiry_soon",
                hwid_device_limit=3,
                extra_hwid_devices=0,
            )

            async def update_subscription(_session, _subscription_id, values):
                for key, value in values.items():
                    setattr(sub, key, value)
                return sub

            topup_log = AsyncMock()
            extend_hwid = AsyncMock(return_value=0)
            with (
                patch(
                    "bot.services.subscription_service_impl.topups.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
                patch(
                    "bot.services.subscription_service_impl.topups.subscription_dal.get_active_subscription_by_user_id_for_update",
                    AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.topups.subscription_dal.update_subscription",
                    AsyncMock(side_effect=update_subscription),
                ),
                patch(
                    "bot.services.subscription_service_impl.topups.tariff_dal.create_traffic_topup",
                    topup_log,
                ),
                patch(
                    "bot.services.subscription_service_impl.topups.tariff_dal.extend_hwid_device_purchases_for_subscription_bonus",
                    extend_hwid,
                ),
            ):
                result = await service.grant_promo_entitlements(
                    AsyncMock(),
                    42,
                    bonus_days=7,
                    regular_traffic_gb=50,
                    premium_traffic_gb=20,
                )

            self.assertIsNotNone(result)
            self.assertEqual(
                panel_service.update_user_details_on_panel.await_args.args[1]["tag"], "STANDARD"
            )
            self.assertEqual(user.managed_panel_tariff_tag, "STANDARD")
            self.assertEqual(sub.topup_balance_bytes, 55 * GIB)
            self.assertEqual(sub.premium_topup_used_bytes, 5 * GIB)
            self.assertEqual(sub.premium_topup_balance_bytes, 15 * GIB)
            self.assertEqual(sub.end_date, old_end + timedelta(days=7))
            self.assertEqual(topup_log.await_count, 2)
            self.assertEqual(
                {call.kwargs["kind"] for call in topup_log.await_args_list},
                {"promo_topup", "promo_premium_topup"},
            )
            extend_hwid.assert_awaited_once()

    async def test_failed_panel_confirmation_restores_local_balances(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = SubscriptionService(_settings(tmpdir), AsyncMock(spec=PanelApiService))
            service.panel_service.update_user_details_on_panel = AsyncMock(return_value=None)
            service._confirmed_panel_entitlement = AsyncMock(return_value=None)
            service._resolve_hwid_device_limits = AsyncMock(
                return_value=SimpleNamespace(base=3, extra=0, effective=3)
            )
            service._hwid_device_traffic_bonus_bytes_for_sub = AsyncMock(return_value=0)
            service.build_effective_panel_squad_fields = AsyncMock(
                return_value={"activeInternalSquads": ["regular-squad"]}
            )
            now = datetime.now(UTC)
            sub = SimpleNamespace(
                subscription_id=7,
                end_date=now + timedelta(days=10),
                tariff_key="standard",
                tier_baseline_bytes=100 * GIB,
                topup_balance_bytes=5 * GIB,
                traffic_limit_bytes=105 * GIB,
                traffic_used_bytes=0,
                regular_bonus_bytes=0,
                regular_unlimited_override=False,
                premium_baseline_bytes=25 * GIB,
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=0,
                premium_bonus_bytes=0,
                premium_unlimited_override=False,
                premium_is_limited=False,
                premium_period_start_at=now.replace(day=1),
                is_throttled=False,
                last_notification_sent=None,
                hwid_device_limit=3,
                extra_hwid_devices=0,
            )
            update = AsyncMock(return_value=sub)
            with (
                patch(
                    "bot.services.subscription_service_impl.topups.user_dal.get_user_by_id",
                    AsyncMock(
                        return_value=SimpleNamespace(
                            panel_user_uuid="panel-uuid",
                            username=None,
                            first_name=None,
                            last_name=None,
                            email=None,
                            telegram_id=42,
                        )
                    ),
                ),
                patch(
                    "bot.services.subscription_service_impl.topups.subscription_dal.get_active_subscription_by_user_id_for_update",
                    AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.topups.subscription_dal.update_subscription",
                    update,
                ),
                patch(
                    "bot.services.subscription_service_impl.topups.tariff_dal.create_traffic_topup",
                    AsyncMock(),
                ) as topup_log,
            ):
                result = await service.grant_promo_entitlements(
                    AsyncMock(), 42, regular_traffic_gb=10
                )

            self.assertIsNone(result)
            self.assertEqual(update.await_count, 2)
            rollback = update.await_args_list[1].args[2]
            self.assertEqual(rollback["topup_balance_bytes"], 5 * GIB)
            self.assertEqual(rollback["traffic_limit_bytes"], 105 * GIB)
            topup_log.assert_not_awaited()
