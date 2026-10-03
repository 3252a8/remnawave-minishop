import copy
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings
from db.base import Base
from db.models import Subscription, User

GIB = 1024**3


class PaidTrialTrafficTransitionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        config_path = Path(self.tmpdir.name) / "tariffs.json"
        config_path.write_text(
            json.dumps(
                {
                    "default_tariff": "paid",
                    "tariffs": [
                        {
                            "key": key,
                            "names": {"en": key},
                            "billing_model": "period",
                            "monthly_gb": limit,
                            "traffic_limit_strategy": strategy,
                            "squad_uuids": ["paid-squad"],
                            "hwid_device_limit": 3,
                            "prices_rub": {"1": 150},
                            "enabled_periods": [1],
                            "enabled": True,
                        }
                        for key, limit, strategy in (
                            ("paid", 10, "MONTH"),
                            ("large", 100, "WEEK"),
                            ("daily", 10, "DAY"),
                            ("no_reset", 10, "NO_RESET"),
                            ("unlimited", 0, "MONTH"),
                        )
                    ],
                }
            ),
            encoding="utf-8",
        )
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="test_user",
            POSTGRES_PASSWORD="test_password",
            TARIFFS_CONFIG_PATH=str(config_path),
            TRIAL_SQUAD_UUIDS="trial-squad",
            TRIAL_DAYS_STRATEGY="start_from_payment",
        )
        self.panel = AsyncMock(spec=PanelApiService)
        self.service = SubscriptionService(settings, self.panel)
        self.service._record_payment_context = AsyncMock()
        self.service._send_payment_success_email = AsyncMock()
        self.service.deactivate_panel_managed_internal_overrides = AsyncMock(return_value=0)

        async def squad_fields(_session, *, managed_internal_squads, **_kwargs):
            return {"activeInternalSquads": list(managed_internal_squads or [])}

        self.service.build_effective_panel_squad_fields = AsyncMock(side_effect=squad_fields)
        self.service._get_or_create_panel_user_link_details = AsyncMock(
            return_value=("panel-user", "panel-sub", "short", False)
        )
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.addAsyncCleanup(self.engine.dispose)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.session = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.addAsyncCleanup(self.session.close)
        self.user = User(user_id=42, panel_user_uuid="panel-user", language_code="en")
        self.sub = Subscription(
            user_id=42,
            panel_user_uuid="panel-user",
            panel_subscription_uuid="panel-sub",
            start_date=datetime.now(UTC) - timedelta(days=4),
            end_date=datetime.now(UTC) - timedelta(hours=1),
            is_active=False,
            provider="trial",
            status_from_panel="LIMITED",
            traffic_limit_bytes=50 * GIB,
            traffic_used_bytes=50 * GIB,
            tier_baseline_bytes=50 * GIB,
            traffic_period_lifetime_start_bytes=100 * GIB,
        )
        self.session.add_all([self.user, self.sub])
        await self.session.commit()
        payment = SimpleNamespace(
            subscription_duration_months=1,
            subscription_duration_days=30,
            period_semantics="fixed_days",
            checkout_bundle_snapshot=None,
        )
        self.enterContext(
            patch(
                "bot.services.subscription_service_impl.lifecycle_activation.payment_dal.get_payment_by_db_id",
                AsyncMock(return_value=payment),
            )
        )
        self.events: list[str] = []
        self.state = {
            "uuid": "panel-user",
            "shortUuid": "short",
            "subscriptionUrl": "https://panel.test/sub/short",
            "status": "LIMITED",
            "expireAt": self.sub.end_date.isoformat(),
            "trafficLimitBytes": 50 * GIB,
            "trafficLimitStrategy": "NO_RESET",
            "activeInternalSquads": ["trial-squad"],
            "hwidDeviceLimit": 1,
            "lastTrafficResetAt": (datetime.now(UTC) - timedelta(days=4)).isoformat(),
            "userTraffic": {
                "usedTrafficBytes": 50 * GIB,
                "lifetimeUsedTrafficBytes": 150 * GIB,
            },
        }

        async def get_user(_uuid, **_kwargs):
            return copy.deepcopy(self.state)

        async def update_user(_uuid, payload):
            self.events.append("patch")
            self.state.update(payload)
            stats = self.state.get("userTraffic", self.state)
            limit = int(self.state["trafficLimitBytes"])
            if limit > 0 and int(stats["usedTrafficBytes"]) >= limit:
                self.state["status"] = "LIMITED"
            return copy.deepcopy(self.state)

        async def reset_traffic(_uuid):
            self.events.append("reset")
            stats = self.state.get("userTraffic", self.state)
            stats["usedTrafficBytes"] = 0
            self.state["lastTrafficResetAt"] = datetime.now(UTC).isoformat()
            return True

        self.panel.get_user_by_uuid.side_effect = get_user
        self.panel.update_user_details_on_panel.side_effect = update_user
        self.panel.reset_user_traffic.side_effect = reset_traffic

    async def activate(self, tariff_key="paid"):
        result = await self.service.activate_subscription(
            self.session,
            user_id=42,
            months=1,
            payment_amount=150,
            payment_db_id=99,
            provider="qa",
            sale_mode=f"subscription@{tariff_key}",
        )
        if result is None:
            await self.session.rollback()
        else:
            await self.session.commit()
        await self.session.refresh(self.sub)
        return result

    def assert_paid_access(self, result, limit_gb=10, used_bytes=0, lifetime_bytes=150 * GIB):
        self.assertIsNotNone(result)
        self.assertEqual(self.state["status"], "ACTIVE")
        self.assertEqual(self.state["trafficLimitBytes"], limit_gb * GIB)
        stats = self.state.get("userTraffic", self.state)
        self.assertEqual(stats["usedTrafficBytes"], used_bytes)
        self.assertEqual(stats["lifetimeUsedTrafficBytes"], lifetime_bytes)
        self.assertEqual(self.state["activeInternalSquads"], ["paid-squad"])
        self.assertEqual(self.state["hwidDeviceLimit"], 3)
        self.assertEqual(self.sub.status_from_panel, "ACTIVE")
        self.assertEqual(self.sub.traffic_used_bytes, used_bytes)
        self.assertEqual(self.sub.traffic_period_lifetime_start_bytes, lifetime_bytes - used_bytes)
        self.panel.reset_user_traffic.assert_awaited_once_with("panel-user")
        self.assertEqual(self.events, ["reset", "patch"])
        self.service._send_payment_success_email.assert_awaited_once()

    async def test_exhausted_expired_trial_gets_the_entire_paid_allowance(self):
        self.assert_paid_access(await self.activate())
        self.assertEqual(self.sub.provider, "qa")
        self.assertTrue(self.sub.is_active)
        self.assertEqual(self.sub.tariff_key, "paid")

    async def test_exhausted_active_trial_gets_the_entire_paid_allowance(self):
        self.sub.is_active = True
        self.sub.end_date = datetime.now(UTC) + timedelta(days=1)
        await self.session.commit()
        self.assert_paid_access(await self.activate())

    async def test_partially_used_trial_does_not_reduce_the_paid_allowance(self):
        self.sub.is_active = True
        self.sub.end_date = datetime.now(UTC) + timedelta(days=1)
        self.sub.traffic_used_bytes = 2 * GIB
        self.state["userTraffic"]["usedTrafficBytes"] = 2 * GIB
        await self.session.commit()
        self.assert_paid_access(await self.activate())

    async def test_daily_paid_plan_gets_a_fresh_counter(self):
        self.assert_paid_access(await self.activate("daily"))
        self.assertEqual(self.state["trafficLimitStrategy"], "DAY")

    async def test_no_reset_paid_plan_gets_a_fresh_counter(self):
        self.assert_paid_access(await self.activate("no_reset"))
        self.assertEqual(self.state["trafficLimitStrategy"], "NO_RESET")

    async def test_unlimited_paid_plan_also_clears_trial_usage(self):
        self.assert_paid_access(await self.activate("unlimited"), limit_gb=0)

    async def test_paid_plan_larger_than_trial_still_gets_its_entire_allowance(self):
        self.assert_paid_access(await self.activate("large"), limit_gb=100)
        self.assertEqual(self.state["trafficLimitStrategy"], "WEEK")

    async def test_legacy_trial_status_is_recognized(self):
        self.sub.provider = "legacy"
        self.sub.status_from_panel = "TRIAL"
        await self.session.commit()
        self.assert_paid_access(await self.activate())

    async def test_flat_panel_counters_are_supported(self):
        self.state.update(self.state.pop("userTraffic"))
        self.assert_paid_access(await self.activate())

    async def test_paid_renewal_preserves_usage_and_purchased_topups(self):
        self.sub.is_active = True
        self.sub.end_date = datetime.now(UTC) + timedelta(days=1)
        self.sub.provider = "qa"
        self.sub.status_from_panel = "ACTIVE"
        self.sub.tariff_key = "paid"
        self.sub.tier_baseline_bytes = 10 * GIB
        self.sub.topup_balance_bytes = 7 * GIB
        self.sub.traffic_used_bytes = 2 * GIB
        self.state["userTraffic"]["usedTrafficBytes"] = 2 * GIB
        await self.session.commit()
        self.assertIsNotNone(await self.activate())
        self.panel.reset_user_traffic.assert_not_awaited()
        self.assertEqual(self.state["trafficLimitBytes"], 17 * GIB)
        self.assertEqual(self.sub.traffic_used_bytes, 2 * GIB)
        self.assertEqual(self.sub.topup_balance_bytes, 7 * GIB)
        self.assertEqual(self.sub.traffic_period_lifetime_start_bytes, 100 * GIB)

    async def test_expired_paid_plan_is_not_mistaken_for_an_expired_trial(self):
        self.sub.provider = "qa"
        self.sub.status_from_panel = "EXPIRED"
        self.sub.tariff_key = "paid"
        self.sub.traffic_used_bytes = 2 * GIB
        self.state["userTraffic"]["usedTrafficBytes"] = 2 * GIB
        await self.session.commit()
        self.assertIsNotNone(await self.activate())
        self.panel.reset_user_traffic.assert_not_awaited()
        self.assertEqual(self.sub.traffic_used_bytes, 2 * GIB)

    async def test_recreated_panel_user_does_not_need_a_reset(self):
        self.service._get_or_create_panel_user_link_details.return_value = (
            "panel-user",
            "panel-sub",
            "short",
            True,
        )
        self.state["userTraffic"]["usedTrafficBytes"] = 0
        self.assertIsNotNone(await self.activate())
        self.panel.reset_user_traffic.assert_not_awaited()

    async def test_database_failure_does_not_reset_the_trial(self):
        with patch(
            "bot.services.subscription_service_impl.lifecycle_activation.subscription_dal.upsert_subscription",
            AsyncMock(side_effect=RuntimeError("database unavailable")),
        ):
            self.assertIsNone(await self.activate())
        self.assertEqual(self.sub.provider, "trial")
        self.panel.reset_user_traffic.assert_not_awaited()
        self.panel.update_user_details_on_panel.assert_not_awaited()
        self.service._send_payment_success_email.assert_not_awaited()

    async def test_stale_trial_link_cannot_reset_another_panel_users_traffic(self):
        self.sub.is_active = True
        self.sub.end_date = datetime.now(UTC) + timedelta(days=1)
        self.sub.panel_user_uuid = "stale-panel-user"
        self.state["userTraffic"]["usedTrafficBytes"] = 2 * GIB
        await self.session.commit()
        self.assertIsNotNone(await self.activate())
        self.panel.reset_user_traffic.assert_not_awaited()
        self.assertEqual(self.state["userTraffic"]["usedTrafficBytes"], 2 * GIB)

    async def test_failed_reset_keeps_the_trial_and_sends_no_success_message(self):
        self.panel.reset_user_traffic.side_effect = None
        self.panel.reset_user_traffic.return_value = False
        self.assertIsNone(await self.activate("large"))
        self.assertEqual(self.sub.provider, "trial")
        self.panel.update_user_details_on_panel.assert_not_awaited()
        self.service._send_payment_success_email.assert_not_awaited()

    async def test_reset_exception_keeps_the_trial_and_sends_no_success_message(self):
        self.panel.reset_user_traffic.side_effect = TimeoutError("panel unavailable")
        self.assertIsNone(await self.activate("large"))
        self.assertEqual(self.sub.provider, "trial")
        self.panel.update_user_details_on_panel.assert_not_awaited()
        self.service._send_payment_success_email.assert_not_awaited()

    async def test_ignored_reset_response_cannot_finalize_the_payment(self):
        self.panel.reset_user_traffic.side_effect = None
        self.panel.reset_user_traffic.return_value = True
        self.assertIsNone(await self.activate("large"))
        self.assertEqual(self.sub.provider, "trial")
        self.panel.reset_user_traffic.assert_awaited_once()
        self.panel.update_user_details_on_panel.assert_not_awaited()
        self.service._send_payment_success_email.assert_not_awaited()

    async def test_reset_verification_waits_for_a_stale_read_to_clear(self):
        old_state = copy.deepcopy(self.state)

        async def get_user(_uuid, **_kwargs):
            if self.events == ["reset"] and not getattr(self, "stale_read_seen", False):
                self.stale_read_seen = True
                return copy.deepcopy(old_state)
            return copy.deepcopy(self.state)

        self.panel.get_user_by_uuid.side_effect = get_user
        self.assert_paid_access(await self.activate())
        self.assertTrue(self.stale_read_seen)
        self.assertTrue(
            all(
                call.kwargs.get("use_cache") is False
                for call in self.panel.get_user_by_uuid.await_args_list
            )
        )

    async def test_reset_marker_allows_new_usage_before_verification(self):
        self.state["userTraffic"]["usedTrafficBytes"] = GIB
        original_reset = self.panel.reset_user_traffic.side_effect

        async def reset_and_use(uuid):
            await original_reset(uuid)
            self.state["userTraffic"]["usedTrafficBytes"] = 2 * GIB
            self.state["userTraffic"]["lifetimeUsedTrafficBytes"] = 152 * GIB
            return True

        self.panel.reset_user_traffic.side_effect = reset_and_use
        self.assert_paid_access(await self.activate(), used_bytes=2 * GIB, lifetime_bytes=152 * GIB)
