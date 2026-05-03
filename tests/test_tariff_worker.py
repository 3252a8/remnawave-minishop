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

            await worker._ensure_period_reset_strategy(sub, tariff, sub.traffic_limit_bytes, "NO_RESET")

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

            with patch("bot.services.tariff_worker.tariff_dal.get_warning", new=AsyncMock(return_value=True)):
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
