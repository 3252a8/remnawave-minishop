import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service import SubscriptionService
from bot.services.tariff_worker import TariffTrafficWorker
from config.settings import Settings


def _tariffs_config_payload() -> dict:
    return {
        "default_tariff": "standard",
        "tariffs": [
            {
                "key": "standard",
                "names": {"ru": "Стандарт"},
                "descriptions": {"ru": "Base"},
                "squad_uuids": ["squad-1"],
                "billing_model": "period",
                "monthly_gb": 500,
                "prices_rub": {"1": 150},
                "prices_stars": {"1": 0},
                "enabled_periods": [1],
                "enabled": True,
            }
        ],
    }


class TariffWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_period_tariff_uses_panel_month_strategy_without_resetting(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "tariffs.json"
            config_path.write_text(json.dumps(_tariffs_config_payload()), encoding="utf-8")

            settings = Settings(
                _env_file=None,
                BOT_TOKEN="token",
                POSTGRES_USER="app_user",
                POSTGRES_PASSWORD="app_password",
                TARIFFS_CONFIG_PATH=str(config_path),
            )
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.update_user_details_on_panel = AsyncMock(return_value={"response": {}})
            panel_service.reset_user_traffic = AsyncMock(return_value=True)
            panel_service.add_users_to_internal_squad = AsyncMock(return_value=True)
            subscription_service = SubscriptionService(settings, panel_service)
            worker = TariffTrafficWorker(
                settings=settings,
                session_factory=SimpleNamespace(),
                panel_service=panel_service,
                subscription_service=subscription_service,
            )

            sub = SimpleNamespace(
                subscription_id=1,
                user_id=123,
                panel_user_uuid="panel-uuid",
                end_date=datetime.now(timezone.utc) + timedelta(days=10),
                traffic_limit_bytes=500 * (1024**3),
                topup_balance_bytes=0,
                is_throttled=False,
                status_from_panel="ACTIVE",
            )
            tariff = settings.tariffs_config.require("standard")

            await worker._ensure_period_reset_strategy(
                sub, tariff, sub.traffic_limit_bytes, "NO_RESET"
            )

            panel_service.update_user_details_on_panel.assert_awaited_once()
            panel_service.reset_user_traffic.assert_not_awaited()
            update_payload = panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertEqual(update_payload["trafficLimitStrategy"], "MONTH")
            self.assertEqual(update_payload["trafficLimitBytes"], sub.traffic_limit_bytes)
            self.assertNotIn("status", update_payload)

    async def test_limit_reached_does_not_remove_user_from_squad(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "tariffs.json"
            config_path.write_text(json.dumps(_tariffs_config_payload()), encoding="utf-8")

            settings = Settings(
                _env_file=None,
                BOT_TOKEN="token",
                POSTGRES_USER="app_user",
                POSTGRES_PASSWORD="app_password",
                TARIFFS_CONFIG_PATH=str(config_path),
                TARIFF_TRAFFIC_WARNING_LEVELS="101",
            )
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.remove_users_from_internal_squad = AsyncMock(return_value=True)
            subscription_service = SubscriptionService(settings, panel_service)
            worker = TariffTrafficWorker(
                settings=settings,
                session_factory=SimpleNamespace(),
                panel_service=panel_service,
                subscription_service=subscription_service,
            )

            sub = SimpleNamespace(
                subscription_id=1,
                user_id=123,
                panel_user_uuid="panel-uuid",
                traffic_limit_bytes=100,
                traffic_used_bytes=100,
                is_throttled=False,
                status_from_panel="ACTIVE",
            )
            tariff = settings.tariffs_config.require("standard")

            with patch(
                "bot.services.tariff_worker.tariff_dal.get_warning",
                new=AsyncMock(return_value=True),
            ):
                await worker._maybe_warn_or_throttle(
                    AsyncMock(),
                    sub,
                    tariff,
                    used=100,
                    limit=100,
                    warning_period_start=datetime.now(timezone.utc),
                )

            panel_service.remove_users_from_internal_squad.assert_not_awaited()
            self.assertFalse(sub.is_throttled)

    async def test_premium_limit_removes_only_premium_squad(self):
        payload = _tariffs_config_payload()
        payload["tariffs"][0]["premium_squad_uuids"] = ["premium-squad"]
        payload["tariffs"][0]["premium_monthly_gb"] = 1
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "tariffs.json"
            config_path.write_text(json.dumps(payload), encoding="utf-8")

            settings = Settings(
                _env_file=None,
                BOT_TOKEN="token",
                POSTGRES_USER="app_user",
                POSTGRES_PASSWORD="app_password",
                TARIFFS_CONFIG_PATH=str(config_path),
            )
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.get_internal_squad_accessible_nodes = AsyncMock(
                return_value=[{"uuid": "node-1", "name": "Premium"}]
            )
            panel_service.get_node_users_bandwidth_stats = AsyncMock(
                return_value={
                    "topUsers": [
                        {
                            "username": "tg_123",
                            "total": 2 * (1024**3),
                        }
                    ]
                }
            )
            panel_service.update_user_details_on_panel = AsyncMock(return_value={"response": {}})
            subscription_service = SubscriptionService(settings, panel_service)
            worker = TariffTrafficWorker(
                settings=settings,
                session_factory=SimpleNamespace(),
                panel_service=panel_service,
                subscription_service=subscription_service,
            )
            sub = SimpleNamespace(
                subscription_id=1,
                user_id=123,
                panel_user_uuid="panel-uuid",
                premium_baseline_bytes=1 * (1024**3),
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=0,
                premium_is_limited=False,
                premium_period_start_at=None,
            )
            tariff = settings.tariffs_config.require("standard")

            with patch(
                "bot.services.tariff_worker.tariff_dal.get_warning",
                new=AsyncMock(return_value=True),
            ):
                await worker._sync_premium_squad_limit(
                    AsyncMock(),
                    sub,
                    tariff,
                    datetime.now(timezone.utc),
                    panel_username="tg_123",
                )

            self.assertTrue(sub.premium_is_limited)
            panel_service.update_user_details_on_panel.assert_awaited_once()
            payload = panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertEqual(payload["activeInternalSquads"], ["squad-1"])

    async def test_premium_topup_balance_carries_over_and_is_spent_only_above_monthly_limit(self):
        payload = _tariffs_config_payload()
        payload["tariffs"][0]["premium_squad_uuids"] = ["premium-squad"]
        payload["tariffs"][0]["premium_monthly_gb"] = 1
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "tariffs.json"
            config_path.write_text(json.dumps(payload), encoding="utf-8")

            settings = Settings(
                _env_file=None,
                BOT_TOKEN="token",
                POSTGRES_USER="app_user",
                POSTGRES_PASSWORD="app_password",
                TARIFFS_CONFIG_PATH=str(config_path),
                TARIFF_TRAFFIC_WARNING_LEVELS="101",
            )
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.get_internal_squad_accessible_nodes = AsyncMock(
                return_value=[{"uuid": "node-1"}]
            )
            panel_service.get_node_users_bandwidth_stats = AsyncMock(
                return_value={
                    "topUsers": [
                        {
                            "username": "tg_123",
                            "total": int(1.5 * (1024**3)),
                        }
                    ]
                }
            )
            panel_service.update_user_details_on_panel = AsyncMock(return_value={"response": {}})
            subscription_service = SubscriptionService(settings, panel_service)
            worker = TariffTrafficWorker(
                settings=settings,
                session_factory=SimpleNamespace(),
                panel_service=panel_service,
                subscription_service=subscription_service,
            )
            now = datetime(2026, 5, 9, tzinfo=timezone.utc)
            sub = SimpleNamespace(
                subscription_id=1,
                user_id=123,
                panel_user_uuid="panel-uuid",
                premium_baseline_bytes=1 * (1024**3),
                premium_topup_balance_bytes=2 * (1024**3),
                premium_topup_used_bytes=0,
                premium_used_bytes=0,
                premium_is_limited=False,
                premium_period_start_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            )
            tariff = settings.tariffs_config.require("standard")

            await worker._sync_premium_squad_limit(
                AsyncMock(), sub, tariff, now, panel_username="tg_123"
            )

            self.assertEqual(sub.premium_topup_balance_bytes, int(1.5 * (1024**3)))
            self.assertEqual(sub.premium_topup_used_bytes, int(0.5 * (1024**3)))
            self.assertFalse(sub.premium_is_limited)

            panel_service.get_node_users_bandwidth_stats = AsyncMock(
                return_value={
                    "topUsers": [
                        {
                            "username": "tg_123",
                            "total": int(0.1 * (1024**3)),
                        }
                    ]
                }
            )
            next_month = datetime(2026, 6, 2, tzinfo=timezone.utc)
            await worker._sync_premium_squad_limit(
                AsyncMock(), sub, tariff, next_month, panel_username="tg_123"
            )

            self.assertEqual(sub.premium_topup_balance_bytes, int(1.5 * (1024**3)))
            self.assertEqual(sub.premium_topup_used_bytes, 0)
            self.assertEqual(sub.premium_period_start_at, datetime(2026, 6, 1, tzinfo=timezone.utc))

    async def test_premium_usage_update_does_not_patch_panel_when_access_state_unchanged(self):
        payload = _tariffs_config_payload()
        payload["tariffs"][0]["premium_squad_uuids"] = ["premium-squad"]
        payload["tariffs"][0]["premium_monthly_gb"] = 25
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "tariffs.json"
            config_path.write_text(json.dumps(payload), encoding="utf-8")

            settings = Settings(
                _env_file=None,
                BOT_TOKEN="token",
                POSTGRES_USER="app_user",
                POSTGRES_PASSWORD="app_password",
                TARIFFS_CONFIG_PATH=str(config_path),
                TARIFF_TRAFFIC_WARNING_LEVELS="101",
            )
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.get_internal_squad_accessible_nodes = AsyncMock(
                return_value=[{"uuid": "node-1"}]
            )
            panel_service.get_node_users_bandwidth_stats = AsyncMock(
                return_value={
                    "topUsers": [
                        {"username": "tg_123", "total": 5 * (1024**3)},
                    ]
                }
            )
            panel_service.update_user_details_on_panel = AsyncMock(return_value={"response": {}})
            subscription_service = SubscriptionService(settings, panel_service)
            worker = TariffTrafficWorker(
                settings=settings,
                session_factory=SimpleNamespace(),
                panel_service=panel_service,
                subscription_service=subscription_service,
            )
            now = datetime(2026, 5, 9, tzinfo=timezone.utc)
            sub = SimpleNamespace(
                subscription_id=1,
                user_id=123,
                panel_user_uuid="panel-uuid",
                premium_baseline_bytes=25 * (1024**3),
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=1 * (1024**3),
                premium_is_limited=False,
                premium_period_start_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                premium_unlimited_override=False,
                premium_bonus_bytes=0,
            )
            tariff = settings.tariffs_config.require("standard")

            await worker._sync_premium_squad_limit(
                AsyncMock(),
                sub,
                tariff,
                now,
                panel_username="tg_123",
                panel_user_dict={
                    "activeInternalSquads": [
                        {"uuid": "squad-1"},
                        {"uuid": "premium-squad"},
                    ]
                },
            )

            self.assertEqual(sub.premium_used_bytes, 5 * (1024**3))
            self.assertFalse(sub.premium_is_limited)
            panel_service.update_user_details_on_panel.assert_not_awaited()

    async def test_premium_sync_patches_panel_when_current_squads_are_known_and_wrong(self):
        payload = _tariffs_config_payload()
        payload["tariffs"][0]["premium_squad_uuids"] = ["premium-squad"]
        payload["tariffs"][0]["premium_monthly_gb"] = 25
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "tariffs.json"
            config_path.write_text(json.dumps(payload), encoding="utf-8")

            settings = Settings(
                _env_file=None,
                BOT_TOKEN="token",
                POSTGRES_USER="app_user",
                POSTGRES_PASSWORD="app_password",
                TARIFFS_CONFIG_PATH=str(config_path),
                TARIFF_TRAFFIC_WARNING_LEVELS="101",
            )
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.get_internal_squad_accessible_nodes = AsyncMock(
                return_value=[{"uuid": "node-1"}]
            )
            panel_service.get_node_users_bandwidth_stats = AsyncMock(
                return_value={
                    "topUsers": [
                        {"username": "tg_123", "total": 5 * (1024**3)},
                    ]
                }
            )
            panel_service.update_user_details_on_panel = AsyncMock(return_value={"response": {}})
            subscription_service = SubscriptionService(settings, panel_service)
            worker = TariffTrafficWorker(
                settings=settings,
                session_factory=SimpleNamespace(),
                panel_service=panel_service,
                subscription_service=subscription_service,
            )
            now = datetime(2026, 5, 9, tzinfo=timezone.utc)
            sub = SimpleNamespace(
                subscription_id=1,
                user_id=123,
                panel_user_uuid="panel-uuid",
                premium_baseline_bytes=25 * (1024**3),
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=5 * (1024**3),
                premium_is_limited=False,
                premium_period_start_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                premium_unlimited_override=False,
                premium_bonus_bytes=0,
            )
            tariff = settings.tariffs_config.require("standard")

            await worker._sync_premium_squad_limit(
                AsyncMock(),
                sub,
                tariff,
                now,
                panel_username="tg_123",
                panel_user_dict={"activeInternalSquads": [{"uuid": "squad-1"}]},
            )

            panel_service.update_user_details_on_panel.assert_awaited_once()
            payload_sent = panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertEqual(payload_sent["activeInternalSquads"], ["squad-1", "premium-squad"])

    async def test_premium_unlimited_override_never_throttles(self):
        payload = _tariffs_config_payload()
        payload["tariffs"][0]["premium_squad_uuids"] = ["premium-squad"]
        payload["tariffs"][0]["premium_monthly_gb"] = 1
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "tariffs.json"
            config_path.write_text(json.dumps(payload), encoding="utf-8")

            settings = Settings(
                _env_file=None,
                BOT_TOKEN="token",
                POSTGRES_USER="app_user",
                POSTGRES_PASSWORD="app_password",
                TARIFFS_CONFIG_PATH=str(config_path),
                TARIFF_TRAFFIC_WARNING_LEVELS="101",
            )
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.get_internal_squad_accessible_nodes = AsyncMock(
                return_value=[{"uuid": "node-1"}]
            )
            panel_service.get_node_users_bandwidth_stats = AsyncMock(
                return_value={
                    "topUsers": [
                        {"username": "tg_42", "total": 50 * (1024**3)},
                    ]
                }
            )
            panel_service.update_user_details_on_panel = AsyncMock(return_value={"response": {}})
            subscription_service = SubscriptionService(settings, panel_service)
            worker = TariffTrafficWorker(
                settings=settings,
                session_factory=SimpleNamespace(),
                panel_service=panel_service,
                subscription_service=subscription_service,
            )
            sub = SimpleNamespace(
                subscription_id=1,
                user_id=42,
                panel_user_uuid="panel-uuid",
                premium_baseline_bytes=1 * (1024**3),
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=0,
                premium_is_limited=False,
                premium_period_start_at=None,
                premium_unlimited_override=True,
                premium_bonus_bytes=0,
            )
            tariff = settings.tariffs_config.require("standard")

            await worker._sync_premium_squad_limit(
                AsyncMock(),
                sub,
                tariff,
                datetime.now(timezone.utc),
                panel_username="tg_42",
                panel_user_dict={"activeInternalSquads": [{"uuid": "squad-1"}]},
            )

            self.assertFalse(sub.premium_is_limited)
            self.assertEqual(int(sub.premium_used_bytes), 50 * (1024**3))
            payload_sent = panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertIn("premium-squad", payload_sent["activeInternalSquads"])

    async def test_premium_bonus_extends_limit(self):
        payload = _tariffs_config_payload()
        payload["tariffs"][0]["premium_squad_uuids"] = ["premium-squad"]
        payload["tariffs"][0]["premium_monthly_gb"] = 1
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "tariffs.json"
            config_path.write_text(json.dumps(payload), encoding="utf-8")

            settings = Settings(
                _env_file=None,
                BOT_TOKEN="token",
                POSTGRES_USER="app_user",
                POSTGRES_PASSWORD="app_password",
                TARIFFS_CONFIG_PATH=str(config_path),
                TARIFF_TRAFFIC_WARNING_LEVELS="101",
            )
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.get_internal_squad_accessible_nodes = AsyncMock(
                return_value=[{"uuid": "node-1"}]
            )
            # Used 4 GB > tariff baseline 1 GB, but admin granted +10 GB bonus.
            panel_service.get_node_users_bandwidth_stats = AsyncMock(
                return_value={
                    "topUsers": [
                        {"username": "tg_77", "total": 4 * (1024**3)},
                    ]
                }
            )
            panel_service.update_user_details_on_panel = AsyncMock(return_value={"response": {}})
            subscription_service = SubscriptionService(settings, panel_service)
            worker = TariffTrafficWorker(
                settings=settings,
                session_factory=SimpleNamespace(),
                panel_service=panel_service,
                subscription_service=subscription_service,
            )
            sub = SimpleNamespace(
                subscription_id=1,
                user_id=77,
                panel_user_uuid="panel-uuid",
                premium_baseline_bytes=1 * (1024**3),
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=0,
                premium_is_limited=False,
                premium_period_start_at=None,
                premium_unlimited_override=False,
                premium_bonus_bytes=10 * (1024**3),
            )
            tariff = settings.tariffs_config.require("standard")

            await worker._sync_premium_squad_limit(
                AsyncMock(), sub, tariff, datetime.now(timezone.utc), panel_username="tg_77"
            )

            # 4 GB used vs 1 GB baseline + 10 GB bonus = 11 GB limit → not limited.
            self.assertFalse(sub.premium_is_limited)
            self.assertEqual(int(sub.premium_used_bytes), 4 * (1024**3))

    async def test_premium_usage_lookup_sums_uuid_and_username_without_double_counting(self):
        panel_service = AsyncMock(spec=PanelApiService)
        panel_service.get_node_users_bandwidth_stats = AsyncMock(
            return_value={
                "topUsers": [
                    {"user": {"uuid": "u-1", "username": "alice"}, "total": 10},
                    {"username": "alice", "total": 5},
                    {"userUuid": "u-1", "total": 7},
                    {"user": {"uuid": "other", "username": "alice"}, "total": 3},
                ]
            }
        )
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(),
            session_factory=SimpleNamespace(),
            panel_service=panel_service,
            subscription_service=SimpleNamespace(),
        )

        total = await worker._premium_usage_for_user(
            "u-1",
            ["node-1"],
            "2026-05-01",
            "2026-05-20",
            panel_username="alice",
        )
        total_again = await worker._premium_usage_for_user(
            "u-1",
            ["node-1"],
            "2026-05-01",
            "2026-05-20",
            panel_username="alice",
        )

        # The first row has both uuid and username, so it should be counted once.
        self.assertEqual(total, 25)
        self.assertEqual(total_again, 25)
        panel_service.get_node_users_bandwidth_stats.assert_awaited_once()

    async def test_bulk_panel_prefetch_maps_panel_users_by_uuid_above_threshold(self):
        settings = SimpleNamespace(TARIFF_WORKER_BULK_PANEL_FETCH_THRESHOLD=2)
        panel_service = AsyncMock(spec=PanelApiService)
        panel_service.get_all_panel_users = AsyncMock(
            return_value=[
                {"uuid": "panel-1", "username": "one"},
                {"uuid": "panel-2", "username": "two"},
                {"username": "missing-uuid"},
            ]
        )
        worker = TariffTrafficWorker(
            settings=settings,
            session_factory=SimpleNamespace(),
            panel_service=panel_service,
            subscription_service=SimpleNamespace(),
        )

        result = await worker._prefetch_panel_users_by_uuid(
            [
                SimpleNamespace(panel_user_uuid="panel-1"),
                SimpleNamespace(panel_user_uuid="panel-2"),
            ]
        )

        self.assertEqual(set(result), {"panel-1", "panel-2"})
        panel_service.get_all_panel_users.assert_awaited_once_with(log_responses=False)

    async def test_bulk_panel_prefetch_skips_below_threshold(self):
        settings = SimpleNamespace(TARIFF_WORKER_BULK_PANEL_FETCH_THRESHOLD=3)
        panel_service = AsyncMock(spec=PanelApiService)
        worker = TariffTrafficWorker(
            settings=settings,
            session_factory=SimpleNamespace(),
            panel_service=panel_service,
            subscription_service=SimpleNamespace(),
        )

        result = await worker._prefetch_panel_users_by_uuid(
            [
                SimpleNamespace(panel_user_uuid="panel-1"),
                SimpleNamespace(panel_user_uuid="panel-2"),
            ]
        )

        self.assertIsNone(result)
        panel_service.get_all_panel_users.assert_not_awaited()
