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
from db.dal.subscription_dal import _subscription_model_payload

GIB = 1024**3


def _tariffs_config_payload() -> dict:
    return {
        "default_tariff": "standard",
        "tariffs": [
            {
                "key": "standard",
                "names": {"en": "Standard"},
                "descriptions": {"en": "Base period plan"},
                "squad_uuids": ["main-squad", "shared-squad"],
                "premium_squad_uuids": ["premium-squad", "shared-squad"],
                "premium_monthly_gb": 25,
                "billing_model": "period",
                "monthly_gb": 100,
                "prices_rub": {"1": 150},
                "prices_stars": {"1": 0},
                "enabled_periods": [1],
                "hwid_device_limit": 3,
                "enabled": True,
            },
            {
                "key": "traffic",
                "names": {"en": "Traffic"},
                "descriptions": {"en": "Traffic package"},
                "squad_uuids": ["traffic-squad"],
                "billing_model": "traffic",
                "monthly_gb": 0,
                "traffic_packages": {"rub": [{"gb": 50, "price": 400}], "stars": []},
                "enabled": True,
            },
        ],
    }


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


def _make_service(settings: Settings) -> SubscriptionService:
    panel_service = AsyncMock(spec=PanelApiService)
    return SubscriptionService(settings, panel_service)


class SubscriptionServiceCalculationTests(unittest.TestCase):
    def test_panel_squads_for_tariff_deduplicates_and_can_hide_premium(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            service = _make_service(settings)
            tariff = settings.tariffs_config.require("standard")

            self.assertEqual(
                service._panel_squads_for_tariff(tariff),
                ["main-squad", "shared-squad", "premium-squad"],
            )
            self.assertEqual(
                service._panel_squads_for_tariff(tariff, include_premium=False),
                ["main-squad", "shared-squad"],
            )

    def test_panel_squads_falls_back_to_default_settings_without_tariff(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                _tariffs_config_payload(),
                tmpdir,
                USER_SQUAD_UUIDS="fallback-a, fallback-b",
            )
            service = _make_service(settings)

            self.assertEqual(
                service._panel_squads_for_tariff(None),
                ["fallback-a", "fallback-b"],
            )

    def test_main_traffic_limit_includes_topup_bonus_and_unlimited_floor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            service = _make_service(settings)

            regular_limit = service._compute_main_traffic_limit_bytes(
                tier_baseline_bytes=100 * GIB,
                topup_balance_bytes=10 * GIB,
                regular_bonus_bytes=5 * GIB,
                regular_unlimited_override=False,
                traffic_used_bytes=500 * GIB,
            )
            self.assertEqual(regular_limit, 115 * GIB)

            unlimited_limit = service._compute_main_traffic_limit_bytes(
                tier_baseline_bytes=100 * GIB,
                topup_balance_bytes=0,
                regular_bonus_bytes=0,
                regular_unlimited_override=True,
                traffic_used_bytes=2 * (1024**5),
            )
            self.assertEqual(unlimited_limit, 2 * (1024**5) + 512 * GIB)

    def test_premium_effective_limit_ignores_negative_balances(self):
        self.assertEqual(
            SubscriptionService._premium_effective_limit_bytes(
                premium_baseline_bytes=25 * GIB,
                premium_topup_balance_bytes=-5 * GIB,
                premium_topup_used_bytes=3 * GIB,
                premium_bonus_bytes=-1 * GIB,
            ),
            28 * GIB,
        )

    def test_build_panel_update_payload_preserves_panel_contract_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                _tariffs_config_payload(),
                tmpdir,
                USER_SQUAD_UUIDS="squad-a,squad-b",
                USER_EXTERNAL_SQUAD_UUID="external-squad",
                USER_TRAFFIC_STRATEGY="MONTH",
            )
            service = _make_service(settings)
            expire_at = datetime(2026, 5, 13, 12, 34, 56, 789000, tzinfo=timezone.utc)

            payload = service._build_panel_update_payload(
                panel_user_uuid="panel-uuid",
                expire_at=expire_at,
                status="ACTIVE",
                traffic_limit_bytes=12345,
                hwid_device_limit="4",
            )

            self.assertEqual(payload["uuid"], "panel-uuid")
            self.assertEqual(payload["expireAt"], "2026-05-13T12:34:56.789Z")
            self.assertEqual(payload["status"], "ACTIVE")
            self.assertEqual(payload["trafficLimitBytes"], 12345)
            self.assertEqual(payload["trafficLimitStrategy"], "MONTH")
            self.assertEqual(payload["hwidDeviceLimit"], 4)
            self.assertEqual(payload["activeInternalSquads"], ["squad-a", "squad-b"])
            self.assertEqual(payload["externalSquadUuid"], "external-squad")

    def test_extract_panel_traffic_details_accepts_nested_and_top_level_shapes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            service = _make_service(settings)

            self.assertEqual(
                service._extract_panel_traffic_details(
                    {
                        "userTraffic": {
                            "usedTrafficBytes": 15,
                            "trafficLimitStrategy": "MONTH",
                        },
                        "trafficLimitBytes": 100,
                    }
                ),
                (15, 100, "MONTH"),
            )
            self.assertEqual(
                service._extract_panel_traffic_details(
                    {
                        "usedTrafficBytes": 20,
                        "trafficLimitBytes": 200,
                        "trafficLimitStrategy": "NO_RESET",
                    }
                ),
                (20, 200, "NO_RESET"),
            )


class SubscriptionServiceActivationDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_activate_trial_keeps_panel_strategy_out_of_local_subscription_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                _tariffs_config_payload(),
                tmpdir,
                TRIAL_ENABLED=True,
                TRIAL_DURATION_DAYS=3,
                TRIAL_TRAFFIC_LIMIT_GB=5,
                TRIAL_TRAFFIC_STRATEGY="WEEK",
                USER_SQUAD_UUIDS="fallback-squad",
                TRIAL_SQUAD_UUIDS="trial-squad",
            )
            service = _make_service(settings)
            service.has_had_any_subscription = AsyncMock(return_value=False)
            service._get_or_create_panel_user_link_details = AsyncMock(
                return_value=("panel-user", "panel-sub", "short", True)
            )
            service.panel_service.update_user_details_on_panel = AsyncMock(
                return_value={"subscriptionUrl": "https://example.test/sub", "shortUuid": "short"}
            )
            session = AsyncMock()
            db_user = SimpleNamespace(
                user_id=42,
                telegram_id=42,
                email=None,
                username="trial-user",
                first_name="Trial",
                last_name="User",
            )

            with (
                patch(
                    "bot.services.subscription_service_impl.trial.user_dal.get_user_by_id",
                    AsyncMock(return_value=db_user),
                ),
                patch(
                    "bot.services.subscription_service_impl.trial.subscription_dal.deactivate_other_active_subscriptions",
                    AsyncMock(),
                ),
                patch(
                    "bot.services.subscription_service_impl.trial.subscription_dal.upsert_subscription",
                    AsyncMock(),
                ) as upsert_subscription,
            ):
                result = await service.activate_trial_subscription(session, user_id=42)

            self.assertTrue(result["activated"])
            sub_payload = upsert_subscription.await_args.args[1]
            self.assertNotIn("traffic_limit_strategy", sub_payload)
            self.assertEqual(sub_payload["traffic_limit_bytes"], 5 * GIB)

            panel_payload = service.panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertEqual(panel_payload["trafficLimitStrategy"], "WEEK")
            self.assertEqual(panel_payload["activeInternalSquads"], ["trial-squad"])

    async def test_activate_trial_falls_back_to_default_user_squads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                _tariffs_config_payload(),
                tmpdir,
                TRIAL_ENABLED=True,
                TRIAL_DURATION_DAYS=3,
                USER_SQUAD_UUIDS="fallback-a,fallback-b",
                TRIAL_SQUAD_UUIDS=" , ",
            )
            service = _make_service(settings)
            service.has_had_any_subscription = AsyncMock(return_value=False)
            service._get_or_create_panel_user_link_details = AsyncMock(
                return_value=("panel-user", "panel-sub", "short", True)
            )
            service.panel_service.update_user_details_on_panel = AsyncMock(
                return_value={"subscriptionUrl": "https://example.test/sub", "shortUuid": "short"}
            )
            session = AsyncMock()
            db_user = SimpleNamespace(
                user_id=42,
                telegram_id=42,
                email=None,
                username="trial-user",
                first_name="Trial",
                last_name="User",
            )

            with (
                patch(
                    "bot.services.subscription_service_impl.trial.user_dal.get_user_by_id",
                    AsyncMock(return_value=db_user),
                ),
                patch(
                    "bot.services.subscription_service_impl.trial.subscription_dal.deactivate_other_active_subscriptions",
                    AsyncMock(),
                ),
                patch(
                    "bot.services.subscription_service_impl.trial.subscription_dal.upsert_subscription",
                    AsyncMock(),
                ),
            ):
                result = await service.activate_trial_subscription(session, user_id=42)

            self.assertTrue(result["activated"])
            panel_payload = service.panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertEqual(panel_payload["activeInternalSquads"], ["fallback-a", "fallback-b"])

    async def test_activate_subscription_dispatches_traffic_sale_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            service = _make_service(settings)
            service._activate_traffic_package = AsyncMock(return_value={"kind": "traffic"})

            result = await service.activate_subscription(
                session=AsyncMock(),
                user_id=42,
                months=3,
                payment_amount=500,
                payment_db_id=9,
                provider="stars",
                sale_mode="traffic@traffic",
            )

            self.assertEqual(result, {"kind": "traffic"})
            service._activate_traffic_package.assert_awaited_once()
            kwargs = service._activate_traffic_package.await_args.kwargs
            self.assertEqual(kwargs["user_id"], 42)
            self.assertEqual(kwargs["traffic_gb"], 3.0)
            self.assertEqual(kwargs["payment_db_id"], 9)
            self.assertEqual(kwargs["provider"], "stars")
            self.assertEqual(kwargs["tariff_key"], "traffic")
            self.assertEqual(kwargs["sale_mode"], "traffic_package")

    async def test_activate_subscription_dispatches_regular_topup_sale_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            service = _make_service(settings)
            service.activate_topup = AsyncMock(return_value={"kind": "topup"})

            result = await service.activate_subscription(
                session=AsyncMock(),
                user_id=42,
                months=1,
                payment_amount=250,
                payment_db_id=10,
                provider="yookassa",
                sale_mode="topup@standard",
                traffic_gb=12.5,
            )

            self.assertEqual(result, {"kind": "topup"})
            service.activate_topup.assert_awaited_once()
            kwargs = service.activate_topup.await_args.kwargs
            self.assertEqual(kwargs["user_id"], 42)
            self.assertEqual(kwargs["tariff_key"], "standard")
            self.assertEqual(kwargs["traffic_gb"], 12.5)
            self.assertEqual(kwargs["payment_amount"], 250)
            self.assertEqual(kwargs["payment_db_id"], 10)

    async def test_activate_subscription_dispatches_premium_topup_sale_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            service = _make_service(settings)
            service.activate_premium_topup = AsyncMock(return_value={"kind": "premium"})

            result = await service.activate_subscription(
                session=AsyncMock(),
                user_id=77,
                months=1,
                payment_amount=350,
                payment_db_id=11,
                provider="cryptopay",
                sale_mode="premium_topup|standard",
                traffic_gb=20,
            )

            self.assertEqual(result, {"kind": "premium"})
            service.activate_premium_topup.assert_awaited_once()
            kwargs = service.activate_premium_topup.await_args.kwargs
            self.assertEqual(kwargs["user_id"], 77)
            self.assertEqual(kwargs["tariff_key"], "standard")
            self.assertEqual(kwargs["traffic_gb"], 20)
            self.assertEqual(kwargs["provider"], "cryptopay")

    async def test_activate_subscription_dispatches_hwid_device_sale_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            service = _make_service(settings)
            service.activate_hwid_device_topup = AsyncMock(return_value={"kind": "hwid"})

            result = await service.activate_subscription(
                session=AsyncMock(),
                user_id=88,
                months=2,
                payment_amount=150,
                payment_db_id=12,
                sale_mode="hwid_devices@standard",
            )

            self.assertEqual(result, {"kind": "hwid"})
            service.activate_hwid_device_topup.assert_awaited_once()
            kwargs = service.activate_hwid_device_topup.await_args.kwargs
            self.assertEqual(kwargs["user_id"], 88)
            self.assertEqual(kwargs["device_count"], 2)
            self.assertEqual(kwargs["tariff_key"], "standard")
            self.assertEqual(kwargs["payment_db_id"], 12)


class SubscriptionServiceActiveDetailsTests(unittest.IsolatedAsyncioTestCase):
    def _local_active_sub(self) -> SimpleNamespace:
        return SimpleNamespace(
            subscription_id=7,
            user_id=42,
            panel_user_uuid="panel-user",
            panel_subscription_uuid="short-uuid",
            end_date=datetime.now(timezone.utc) + timedelta(days=10),
            is_active=True,
            status_from_panel="ACTIVE",
            traffic_limit_bytes=1000,
            traffic_used_bytes=100,
            tariff_key=None,
            tier_baseline_bytes=None,
            topup_balance_bytes=0,
            regular_bonus_bytes=0,
            regular_unlimited_override=False,
            premium_baseline_bytes=0,
            premium_topup_balance_bytes=0,
            premium_topup_used_bytes=0,
            premium_used_bytes=0,
            premium_bonus_bytes=0,
            premium_unlimited_override=False,
            premium_is_limited=False,
            premium_period_start_at=None,
            period_start_at=None,
            is_throttled=False,
            hwid_device_limit=None,
            extra_hwid_devices=0,
        )

    async def test_get_active_subscription_details_preserves_local_subscription_on_panel_error(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            service = _make_service(settings)
            service.panel_service.get_user_by_uuid_lookup = AsyncMock(
                return_value={
                    "ok": False,
                    "user": None,
                    "not_found": False,
                    "failure_reason": "classification=panel_lookup_failed status_code=-1 "
                    "message=Connection error",
                    "response": {"error": True, "status_code": -1},
                }
            )
            service.panel_service.get_subscription_link = AsyncMock(
                return_value="https://panel.example.test/sub/short-uuid"
            )
            session = AsyncMock()
            db_user = SimpleNamespace(
                user_id=42,
                panel_user_uuid="panel-user",
                username="alice",
                language_code="en",
            )
            local_sub = self._local_active_sub()

            with (
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.get_user_by_id",
                    AsyncMock(return_value=db_user),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=local_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.deactivate_all_user_subscriptions",
                    AsyncMock(),
                ) as deactivate_all,
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.update_user",
                    AsyncMock(),
                ) as update_user,
                patch(
                    "bot.services.subscription_service_impl.lifecycle.logging.warning",
                ) as warning_log,
            ):
                result = await service.get_active_subscription_details(session, user_id=42)

        self.assertIsNotNone(result)
        self.assertFalse(result["is_panel_data"])
        self.assertEqual(result["end_date"], local_sub.end_date)
        self.assertEqual(result["config_link"], "https://panel.example.test/sub/short-uuid")
        deactivate_all.assert_not_awaited()
        update_user.assert_not_awaited()
        warning_text = " ".join(str(call) for call in warning_log.call_args_list)
        self.assertIn("panel access/API problem", warning_text)
        self.assertIn("status_code=-1", warning_text)
        self.assertIn("Connection error", warning_text)

    async def test_get_active_subscription_details_clears_link_only_when_panel_confirms_absent(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            service = _make_service(settings)
            service.panel_service.get_user_by_uuid_lookup = AsyncMock(
                return_value={
                    "ok": False,
                    "user": None,
                    "not_found": True,
                    "failure_reason": "classification=confirmed_not_found status_code=404",
                    "response": {"error": True, "status_code": 404},
                }
            )
            session = AsyncMock()
            db_user = SimpleNamespace(
                user_id=42,
                panel_user_uuid="panel-user",
                username="alice",
                language_code="en",
            )

            with (
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.get_user_by_id",
                    AsyncMock(return_value=db_user),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=self._local_active_sub()),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.deactivate_all_user_subscriptions",
                    AsyncMock(),
                ) as deactivate_all,
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.update_user",
                    AsyncMock(),
                ) as update_user,
            ):
                result = await service.get_active_subscription_details(session, user_id=42)

        self.assertIsNone(result)
        deactivate_all.assert_awaited_once_with(session, 42)
        update_user.assert_awaited_once_with(session, 42, {"panel_user_uuid": None})


class SubscriptionDalPayloadTests(unittest.TestCase):
    def test_subscription_model_payload_drops_panel_only_keys(self):
        payload = _subscription_model_payload(
            {
                "user_id": 42,
                "panel_user_uuid": "panel-user",
                "panel_subscription_uuid": "panel-sub",
                "end_date": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "traffic_limit_strategy": "WEEK",
            }
        )

        self.assertEqual(payload["user_id"], 42)
        self.assertNotIn("traffic_limit_strategy", payload)


if __name__ == "__main__":
    unittest.main()
