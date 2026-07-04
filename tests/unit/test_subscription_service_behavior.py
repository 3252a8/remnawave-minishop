import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.utils.date_utils import add_months
from config.settings import Settings
from db.dal.subscription_dal import _subscription_model_payload
from db.database_setup import _trial_premium_baseline_bytes

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


async def _echo_panel_expiry(_panel_uuid, payload, *_args, **_kwargs):
    return {"ok": True, "expireAt": payload.get("expireAt")}


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

    def test_trial_premium_baseline_uses_separate_trial_premium_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                _tariffs_config_payload(),
                tmpdir,
                TRIAL_TRAFFIC_LIMIT_GB=7,
                TRIAL_PREMIUM_TRAFFIC_LIMIT_GB=3,
                TRIAL_SQUAD_UUIDS="main-squad",
                TRIAL_PREMIUM_SQUAD_UUIDS="premium-squad",
            )
            service = _make_service(settings)

            self.assertEqual(service._trial_premium_squad_uuids(), ["premium-squad"])
            self.assertEqual(service._trial_premium_baseline_bytes(), 3 * GIB)
            self.assertEqual(_trial_premium_baseline_bytes(settings), 3 * GIB)

    def test_trial_premium_baseline_is_zero_without_configured_premium_squad(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                _tariffs_config_payload(),
                tmpdir,
                TRIAL_TRAFFIC_LIMIT_GB=7,
                TRIAL_PREMIUM_TRAFFIC_LIMIT_GB=3,
                TRIAL_SQUAD_UUIDS="main-squad,premium-squad",
            )
            service = _make_service(settings)

            self.assertEqual(service._trial_premium_squad_uuids(), [])
            self.assertEqual(service._trial_panel_squad_uuids(), ["main-squad"])
            self.assertEqual(service._trial_all_panel_squad_uuids(), ["main-squad"])
            self.assertEqual(service._trial_premium_baseline_bytes(), 0)

    def test_main_traffic_limit_includes_topup_bonus_and_unlimited_zero(self):
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
            self.assertEqual(unlimited_limit, 0)

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


class SubscriptionServicePremiumAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_premium_access_hides_hidden_and_disabled_hosts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            service = _make_service(settings)
            tariff = settings.tariffs_config.require("standard")
            service.panel_service.get_internal_squads = AsyncMock(
                return_value=[
                    {
                        "uuid": "premium-squad",
                        "name": "Premium",
                        "inbounds": [
                            {"uuid": "in-visible"},
                            {"uuid": "in-hidden"},
                            {"uuid": "in-disabled"},
                        ],
                    },
                    {
                        "uuid": "shared-squad",
                        "name": "Shared Premium",
                        "inbounds": [{"uuid": "in-shared"}],
                    },
                ]
            )
            service.panel_service.get_internal_squad = AsyncMock(return_value=None)
            service.panel_service.get_internal_squad_accessible_nodes = AsyncMock(return_value=[])
            service.panel_service.get_hosts = AsyncMock(
                return_value=[
                    {
                        "remark": "Visible Premium",
                        "inbound": {"configProfileInboundUuid": "in-visible"},
                        "isHidden": False,
                        "isDisabled": False,
                    },
                    {
                        "remark": "Hidden Premium",
                        "inbound": {"configProfileInboundUuid": "in-hidden"},
                        "isHidden": True,
                        "isDisabled": False,
                    },
                    {
                        "remark": "Disabled Premium",
                        "inboundUuid": "in-disabled",
                        "isHidden": False,
                        "isDisabled": True,
                    },
                    {
                        "remark": "Shared Visible",
                        "configProfileInboundUuid": "in-shared",
                    },
                ]
            )

            access = await service.premium_access_for_tariff(tariff)

            self.assertEqual(access["node_labels"], ["Visible Premium", "Shared Visible"])
            self.assertNotIn("Hidden Premium", access["node_labels"])
            self.assertNotIn("Disabled Premium", access["node_labels"])


class SubscriptionServicePanelPayloadTests(unittest.TestCase):
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
            expire_at = datetime(2026, 5, 13, 12, 34, 56, 789000, tzinfo=UTC)

            payload = service._build_panel_update_payload(
                panel_user_uuid="panel-uuid",
                expire_at=expire_at,
                status="ACTIVE",
                traffic_limit_bytes=12345,
                traffic_limit_strategy="MONTH",
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

    def test_build_panel_update_payload_omits_strategy_unless_explicit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                _tariffs_config_payload(),
                tmpdir,
                USER_TRAFFIC_STRATEGY="NO_RESET",
            )
            service = _make_service(settings)

            payload = service._build_panel_update_payload(
                panel_user_uuid="panel-uuid",
                traffic_limit_bytes=12345,
            )

            self.assertEqual(payload["trafficLimitBytes"], 12345)
            self.assertNotIn("trafficLimitStrategy", payload)

    def test_extract_panel_traffic_details_accepts_nested_and_top_level_shapes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            service = _make_service(settings)

            self.assertEqual(
                service._extract_panel_traffic_details(
                    {
                        "userTraffic": {
                            "usedTrafficBytes": "15",
                            "trafficLimitStrategy": "MONTH",
                        },
                        "trafficLimitBytes": 100.0,
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
                TRIAL_TRAFFIC_STRATEGY="MONTHLY",
                USER_SQUAD_UUIDS="fallback-squad",
                TRIAL_SQUAD_UUIDS="trial-squad",
            )
            service = _make_service(settings)
            service.has_trial_blocking_subscription = AsyncMock(return_value=False)
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
            self.assertEqual(panel_payload["trafficLimitStrategy"], "MONTH")
            self.assertEqual(panel_payload["activeInternalSquads"], ["trial-squad"])

    async def test_activate_trial_records_premium_baseline_from_trial_premium_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                _tariffs_config_payload(),
                tmpdir,
                TRIAL_ENABLED=True,
                TRIAL_DURATION_DAYS=3,
                TRIAL_TRAFFIC_LIMIT_GB=7,
                TRIAL_PREMIUM_TRAFFIC_LIMIT_GB=3,
                TRIAL_SQUAD_UUIDS="main-squad",
                TRIAL_PREMIUM_SQUAD_UUIDS="premium-squad",
            )
            service = _make_service(settings)
            service.has_trial_blocking_subscription = AsyncMock(return_value=False)
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
            self.assertIsNone(sub_payload.get("tariff_key"))
            self.assertEqual(sub_payload["traffic_limit_bytes"], 7 * GIB)
            self.assertEqual(sub_payload["premium_baseline_bytes"], 3 * GIB)
            self.assertEqual(sub_payload["premium_topup_balance_bytes"], 0)
            self.assertEqual(sub_payload["premium_used_bytes"], 0)

            panel_payload = service.panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertEqual(panel_payload["activeInternalSquads"], ["main-squad", "premium-squad"])

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
            service.has_trial_blocking_subscription = AsyncMock(return_value=False)
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

    async def test_activate_trial_rejects_users_with_blocking_subscription_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                _tariffs_config_payload(),
                tmpdir,
                TRIAL_ENABLED=True,
                TRIAL_DURATION_DAYS=3,
            )
            service = _make_service(settings)
            service.has_trial_blocking_subscription = AsyncMock(return_value=True)
            service._get_or_create_panel_user_link_details = AsyncMock()
            service.panel_service.update_user_details_on_panel = AsyncMock()
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
                    "bot.services.subscription_service_impl.trial.subscription_dal.upsert_subscription",
                    AsyncMock(),
                ) as upsert_subscription,
            ):
                result = await service.activate_trial_subscription(session, user_id=42)

            self.assertFalse(result["activated"])
            self.assertFalse(result["eligible"])
            self.assertEqual(result["message_key"], "trial_already_had_subscription_or_trial")
            service._get_or_create_panel_user_link_details.assert_not_awaited()
            service.panel_service.update_user_details_on_panel.assert_not_awaited()
            upsert_subscription.assert_not_awaited()

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

    async def test_activate_subscription_regular_topup_uses_active_subscription_tariff(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            service = _make_service(settings)
            service.activate_topup = AsyncMock(return_value={"kind": "topup"})
            session = AsyncMock()
            active_user = SimpleNamespace(panel_user_uuid="panel-user")
            active_sub = SimpleNamespace(tariff_key="standard")

            with (
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.get_user_by_id",
                    AsyncMock(return_value=active_user),
                ) as get_user,
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=active_sub),
                ) as get_active_subscription,
            ):
                result = await service.activate_subscription(
                    session=session,
                    user_id=42,
                    months=7,
                    payment_amount=250,
                    payment_db_id=10,
                    provider="yookassa",
                    sale_mode="topup",
                    traffic_gb=None,
                )

            self.assertEqual(result, {"kind": "topup"})
            get_user.assert_awaited_once_with(session, 42)
            get_active_subscription.assert_awaited_once_with(session, 42, "panel-user")
            service.activate_topup.assert_awaited_once()
            kwargs = service.activate_topup.await_args.kwargs
            self.assertEqual(kwargs["tariff_key"], "standard")
            self.assertEqual(kwargs["traffic_gb"], 7.0)

    async def test_activate_subscription_regular_topup_without_active_subscription_returns_none(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            service = _make_service(settings)
            service.activate_topup = AsyncMock(return_value={"kind": "topup"})
            session = AsyncMock()

            with (
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.get_user_by_id",
                    AsyncMock(return_value=SimpleNamespace(panel_user_uuid="panel-user")),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=None),
                ),
            ):
                result = await service.activate_subscription(
                    session=session,
                    user_id=42,
                    months=7,
                    payment_amount=250,
                    payment_db_id=10,
                    sale_mode="topup",
                )

            self.assertIsNone(result)
            service.activate_topup.assert_not_awaited()

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

    async def test_activate_subscription_premium_topup_uses_active_subscription_tariff(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            service = _make_service(settings)
            service.activate_premium_topup = AsyncMock(return_value={"kind": "premium"})
            session = AsyncMock()
            active_user = SimpleNamespace(panel_user_uuid="panel-user")
            active_sub = SimpleNamespace(tariff_key="standard")

            with (
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.get_user_by_id",
                    AsyncMock(return_value=active_user),
                ) as get_user,
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=active_sub),
                ) as get_active_subscription,
            ):
                result = await service.activate_subscription(
                    session=session,
                    user_id=77,
                    months=9,
                    payment_amount=350,
                    payment_db_id=11,
                    provider="cryptopay",
                    sale_mode="premium_topup",
                    traffic_gb=None,
                )

            self.assertEqual(result, {"kind": "premium"})
            get_user.assert_awaited_once_with(session, 77)
            get_active_subscription.assert_awaited_once_with(session, 77, "panel-user")
            service.activate_premium_topup.assert_awaited_once()
            kwargs = service.activate_premium_topup.await_args.kwargs
            self.assertEqual(kwargs["tariff_key"], "standard")
            self.assertEqual(kwargs["traffic_gb"], 9.0)
            self.assertEqual(kwargs["provider"], "cryptopay")

    async def test_activate_subscription_premium_topup_without_active_subscription_returns_none(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            service = _make_service(settings)
            service.activate_premium_topup = AsyncMock(return_value={"kind": "premium"})
            session = AsyncMock()

            with (
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.get_user_by_id",
                    AsyncMock(return_value=SimpleNamespace(panel_user_uuid="panel-user")),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=None),
                ),
            ):
                result = await service.activate_subscription(
                    session=session,
                    user_id=77,
                    months=9,
                    payment_amount=350,
                    payment_db_id=11,
                    sale_mode="premium_topup",
                )

            self.assertIsNone(result)
            service.activate_premium_topup.assert_not_awaited()

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

    async def test_activate_subscription_records_hwid_renewal_without_inflating_tariff_price(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(_tariffs_config_payload(), tmpdir)
            service = _make_service(settings)
            service._get_or_create_panel_user_link_details = AsyncMock(
                return_value=("panel-user", "short-uuid", "short", False)
            )
            service.panel_service.update_user_details_on_panel = AsyncMock(
                return_value={"subscriptionUrl": "https://panel/sub", "shortUuid": "short"}
            )
            service._send_payment_success_email = AsyncMock()
            now = datetime.now(UTC)
            current_end = now + timedelta(days=20)
            current_sub = SimpleNamespace(
                subscription_id=10,
                end_date=current_end,
                tariff_key="standard",
                topup_balance_bytes=0,
                extra_hwid_devices=1,
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=0,
                premium_period_start_at=None,
                regular_bonus_bytes=0,
                regular_unlimited_override=False,
            )
            updated_sub = SimpleNamespace(subscription_id=10)
            payment = SimpleNamespace(
                purchased_hwid_devices=1,
                hwid_valid_from=current_end,
                hwid_valid_until=current_end + timedelta(days=30),
                hwid_full_price=50,
                hwid_pricing_period_months=1,
                hwid_proration_ratio=1.0,
            )
            db_user = SimpleNamespace(
                user_id=42,
                panel_user_uuid="panel-user",
                telegram_id=42,
                username="alice",
                email=None,
                language_code="en",
            )

            with (
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.get_user_by_id",
                    AsyncMock(return_value=db_user),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.payment_dal.get_payment_by_db_id",
                    AsyncMock(return_value=payment),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=current_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.deactivate_other_active_subscriptions",
                    AsyncMock(),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.upsert_subscription",
                    AsyncMock(return_value=updated_sub),
                ) as upsert_subscription,
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.get_hwid_device_entitlement_summary",
                    AsyncMock(
                        return_value={
                            "active_devices": 1,
                            "active_until": current_end,
                        }
                    ),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.create_hwid_device_purchase",
                    AsyncMock(),
                ) as create_hwid_purchase,
            ):
                result = await service.activate_subscription(
                    session=AsyncMock(),
                    user_id=42,
                    months=1,
                    payment_amount=150,
                    payment_db_id=99,
                    sale_mode="subscription@standard",
                )

        self.assertEqual(result["hwid_devices_renewed_count"], 1)
        sub_payload = upsert_subscription.await_args.args[1]
        self.assertEqual(sub_payload["effective_monthly_price_rub"], 100)
        create_hwid_purchase.assert_awaited_once()
        purchase_kwargs = create_hwid_purchase.await_args.kwargs
        self.assertEqual(purchase_kwargs["payment_id"], 99)
        self.assertEqual(purchase_kwargs["purchased_devices"], 1)
        self.assertEqual(purchase_kwargs["valid_from"], current_end)


class SubscriptionServiceBonusExtensionTests(unittest.IsolatedAsyncioTestCase):
    async def test_promo_bonus_without_active_subscription_uses_default_tariff_squads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                _tariffs_config_payload(),
                tmpdir,
                USER_TRAFFIC_LIMIT_GB=999,
                USER_EXTERNAL_SQUAD_UUID="external-squad",
            )
            service = _make_service(settings)
            service._get_or_create_panel_user_link_details = AsyncMock(
                return_value=("panel-user", "short-uuid", "short", False)
            )
            service.panel_service.update_user_details_on_panel = AsyncMock(
                side_effect=_echo_panel_expiry
            )
            updated_sub = SimpleNamespace(
                subscription_id=10,
                end_date=datetime.now(UTC) + timedelta(days=7),
                traffic_limit_bytes=100 * GIB,
                tariff_key="standard",
                hwid_device_limit=3,
            )

            with (
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.get_user_by_id",
                    AsyncMock(return_value=SimpleNamespace(user_id=42)),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=None),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.deactivate_other_active_subscriptions",
                    AsyncMock(),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.upsert_subscription",
                    AsyncMock(return_value=updated_sub),
                ) as upsert_subscription,
            ):
                await service.extend_active_subscription_days(
                    session=AsyncMock(),
                    user_id=42,
                    bonus_days=7,
                    reason="promo code HELLO",
                    tariff_key="standard",
                )

            sub_payload = upsert_subscription.await_args.args[1]
            self.assertEqual(sub_payload["tariff_key"], "standard")
            self.assertEqual(sub_payload["traffic_limit_bytes"], 100 * GIB)
            self.assertEqual(sub_payload["tier_baseline_bytes"], 100 * GIB)
            self.assertEqual(sub_payload["premium_baseline_bytes"], 25 * GIB)
            self.assertEqual(sub_payload["hwid_device_limit"], 3)

            panel_payload = service.panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertEqual(panel_payload["trafficLimitBytes"], 100 * GIB)
            self.assertEqual(panel_payload["trafficLimitStrategy"], "NO_RESET")
            self.assertEqual(panel_payload["hwidDeviceLimit"], 3)
            self.assertEqual(
                panel_payload["activeInternalSquads"],
                ["main-squad", "shared-squad", "premium-squad"],
            )
            self.assertEqual(panel_payload["externalSquadUuid"], "external-squad")

    async def test_referral_extension_preserves_existing_tariff_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                _tariffs_config_payload(),
                tmpdir,
                USER_TRAFFIC_LIMIT_GB=999,
            )
            service = _make_service(settings)
            service._get_or_create_panel_user_link_details = AsyncMock(
                return_value=("panel-user", "short-uuid", "short", False)
            )
            service.panel_service.update_user_details_on_panel = AsyncMock(
                side_effect=_echo_panel_expiry
            )
            active_sub = SimpleNamespace(
                subscription_id=10,
                end_date=datetime.now(UTC) + timedelta(days=5),
                traffic_limit_bytes=100 * GIB,
                tariff_key="standard",
            )
            updated_sub = SimpleNamespace(
                subscription_id=10,
                end_date=active_sub.end_date + timedelta(days=3),
                traffic_limit_bytes=100 * GIB,
                tariff_key="standard",
            )

            with (
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.get_user_by_id",
                    AsyncMock(return_value=SimpleNamespace(user_id=42)),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=active_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription_end_date",
                    AsyncMock(return_value=updated_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription",
                    AsyncMock(),
                ) as update_subscription,
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.extend_hwid_device_purchases_for_subscription_bonus",
                    AsyncMock(return_value=1),
                ) as extend_hwid,
            ):
                await service.extend_active_subscription_days(
                    session=AsyncMock(),
                    user_id=42,
                    bonus_days=3,
                    reason="referral bonus from Alice",
                )

            update_subscription.assert_not_awaited()
            extend_hwid.assert_awaited_once()
            self.assertEqual(extend_hwid.await_args.kwargs["subscription_id"], 10)
            self.assertEqual(extend_hwid.await_args.kwargs["delta"], timedelta(days=3))
            payload = service.panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertNotIn("trafficLimitBytes", payload)
            self.assertNotIn("trafficLimitStrategy", payload)

    async def test_referral_extension_verifies_missing_patch_expiry_with_panel_lookup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                _tariffs_config_payload(),
                tmpdir,
                USER_TRAFFIC_LIMIT_GB=999,
            )
            service = _make_service(settings)
            service._get_or_create_panel_user_link_details = AsyncMock(
                return_value=("panel-user", "short-uuid", "short", False)
            )
            service.panel_service.update_user_details_on_panel = AsyncMock(
                return_value={"ok": True}
            )

            async def get_panel_user(panel_uuid, *_args, **_kwargs):
                payload = service.panel_service.update_user_details_on_panel.await_args.args[1]
                return {"uuid": panel_uuid, "expireAt": payload["expireAt"]}

            service.panel_service.get_user_by_uuid = AsyncMock(side_effect=get_panel_user)
            current_end = datetime.now(UTC) + timedelta(days=5)
            active_sub = SimpleNamespace(
                subscription_id=10,
                end_date=current_end,
                traffic_limit_bytes=100 * GIB,
                tariff_key="standard",
            )
            updated_sub = SimpleNamespace(
                subscription_id=10,
                end_date=current_end + timedelta(days=3),
                traffic_limit_bytes=100 * GIB,
                tariff_key="standard",
            )

            with (
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.get_user_by_id",
                    AsyncMock(return_value=SimpleNamespace(user_id=42)),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=active_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription_end_date",
                    AsyncMock(return_value=updated_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.extend_hwid_device_purchases_for_subscription_bonus",
                    AsyncMock(return_value=1),
                ) as extend_hwid,
            ):
                result = await service.extend_active_subscription_days(
                    session=AsyncMock(),
                    user_id=42,
                    bonus_days=3,
                    reason="referral bonus from Alice",
                )

            self.assertEqual(result, current_end + timedelta(days=3))
            service.panel_service.get_user_by_uuid.assert_awaited_once()
            extend_hwid.assert_awaited_once()

    async def test_referral_extension_reverts_when_panel_keeps_old_expiry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                _tariffs_config_payload(),
                tmpdir,
                USER_TRAFFIC_LIMIT_GB=999,
            )
            service = _make_service(settings)
            service._get_or_create_panel_user_link_details = AsyncMock(
                return_value=("panel-user", "short-uuid", "short", False)
            )
            current_end = datetime.now(UTC) + timedelta(days=5)
            service.panel_service.update_user_details_on_panel = AsyncMock(
                return_value={
                    "uuid": "panel-user",
                    "expireAt": current_end.isoformat(timespec="milliseconds").replace(
                        "+00:00", "Z"
                    ),
                }
            )
            active_sub = SimpleNamespace(
                subscription_id=10,
                end_date=current_end,
                traffic_limit_bytes=100 * GIB,
                tariff_key="standard",
                is_active=True,
                status_from_panel="ACTIVE",
                last_notification_sent=datetime(2026, 1, 1, tzinfo=UTC),
            )
            updated_sub = SimpleNamespace(
                **{**active_sub.__dict__, "end_date": current_end + timedelta(days=3)}
            )
            session = AsyncMock()

            with (
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.get_user_by_id",
                    AsyncMock(return_value=SimpleNamespace(user_id=42)),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=active_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription_end_date",
                    AsyncMock(return_value=updated_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription",
                    AsyncMock(return_value=active_sub),
                ) as update_subscription,
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.extend_hwid_device_purchases_for_subscription_bonus",
                    AsyncMock(return_value=1),
                ) as extend_hwid,
            ):
                result = await service.extend_active_subscription_days(
                    session=session,
                    user_id=42,
                    bonus_days=3,
                    reason="referral bonus from Alice",
                )

            self.assertIsNone(result)
            update_subscription.assert_awaited_once_with(
                session,
                10,
                {
                    "end_date": current_end,
                    "last_notification_sent": active_sub.last_notification_sent,
                    "is_active": True,
                    "status_from_panel": "ACTIVE",
                    "tariff_key": "standard",
                    "traffic_limit_bytes": 100 * GIB,
                },
            )
            extend_hwid.assert_not_awaited()

    async def test_admin_extension_can_skip_hwid_purchase_extension(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                _tariffs_config_payload(),
                tmpdir,
                USER_TRAFFIC_LIMIT_GB=999,
            )
            service = _make_service(settings)
            service._get_or_create_panel_user_link_details = AsyncMock(
                return_value=("panel-user", "short-uuid", "short", False)
            )
            service.panel_service.update_user_details_on_panel = AsyncMock(
                side_effect=_echo_panel_expiry
            )
            active_sub = SimpleNamespace(
                subscription_id=10,
                end_date=datetime.now(UTC) + timedelta(days=5),
                traffic_limit_bytes=100 * GIB,
                tariff_key="standard",
            )
            updated_sub = SimpleNamespace(
                subscription_id=10,
                end_date=active_sub.end_date + timedelta(days=3),
                traffic_limit_bytes=100 * GIB,
                tariff_key="standard",
            )

            with (
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.get_user_by_id",
                    AsyncMock(return_value=SimpleNamespace(user_id=42)),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=active_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription_end_date",
                    AsyncMock(return_value=updated_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.extend_hwid_device_purchases_for_subscription_bonus",
                    AsyncMock(return_value=1),
                ) as extend_hwid,
            ):
                await service.extend_active_subscription_days(
                    session=AsyncMock(),
                    user_id=42,
                    bonus_days=3,
                    reason="admin_extend_subscription_webapp",
                    extend_hwid_devices=False,
                )

            extend_hwid.assert_not_awaited()

    async def test_admin_extension_applies_selected_tariff_to_active_subscription(self):
        payload = _tariffs_config_payload()
        payload["tariffs"].append(
            {
                "key": "plus",
                "names": {"en": "Plus"},
                "descriptions": {"en": "Plus period plan"},
                "squad_uuids": ["plus-squad"],
                "premium_squad_uuids": ["plus-premium"],
                "premium_monthly_gb": 50,
                "billing_model": "period",
                "monthly_gb": 200,
                "prices_rub": {"1": 300},
                "prices_stars": {"1": 0},
                "enabled_periods": [1],
                "hwid_device_limit": 5,
                "enabled": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(payload, tmpdir, USER_EXTERNAL_SQUAD_UUID="external-squad")
            service = _make_service(settings)
            service._get_or_create_panel_user_link_details = AsyncMock(
                return_value=("panel-user", "short-uuid", "short", False)
            )
            service.panel_service.update_user_details_on_panel = AsyncMock(
                side_effect=_echo_panel_expiry
            )
            current_end = datetime.now(UTC) + timedelta(days=5)
            active_sub = SimpleNamespace(
                subscription_id=10,
                end_date=current_end,
                traffic_limit_bytes=100 * GIB,
                traffic_used_bytes=7 * GIB,
                tariff_key="standard",
                topup_balance_bytes=3 * GIB,
                regular_bonus_bytes=4 * GIB,
                regular_unlimited_override=False,
                premium_topup_balance_bytes=2 * GIB,
                premium_topup_used_bytes=1 * GIB,
                premium_used_bytes=10 * GIB,
                premium_bonus_bytes=6 * GIB,
                extra_hwid_devices=1,
                effective_monthly_price_rub=150,
            )
            extended_sub = SimpleNamespace(
                **{**active_sub.__dict__, "end_date": current_end + timedelta(days=10)}
            )
            updated_sub = SimpleNamespace(
                **{
                    **extended_sub.__dict__,
                    "tariff_key": "plus",
                    "traffic_limit_bytes": 207 * GIB,
                    "tier_baseline_bytes": 200 * GIB,
                    "premium_baseline_bytes": 50 * GIB,
                    "premium_is_limited": False,
                    "hwid_device_limit": 5,
                    "extra_hwid_devices": 2,
                }
            )

            with (
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.get_user_by_id",
                    AsyncMock(return_value=SimpleNamespace(user_id=42)),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=active_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription_end_date",
                    AsyncMock(return_value=extended_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription",
                    AsyncMock(return_value=updated_sub),
                ) as update_subscription,
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.sum_active_hwid_devices",
                    AsyncMock(return_value=2),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.extend_hwid_device_purchases_for_subscription_bonus",
                    AsyncMock(return_value=0),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.create_tariff_change",
                    AsyncMock(),
                ) as create_tariff_change,
            ):
                result = await service.extend_active_subscription_days(
                    session=AsyncMock(),
                    user_id=42,
                    bonus_days=10,
                    reason="admin_manual_extension",
                    tariff_key="plus",
                )

            self.assertEqual(result, current_end + timedelta(days=10))
            update_data = update_subscription.await_args.args[2]
            self.assertEqual(update_data["tariff_key"], "plus")
            self.assertEqual(update_data["traffic_limit_bytes"], 207 * GIB)
            self.assertEqual(update_data["premium_baseline_bytes"], 50 * GIB)
            self.assertEqual(update_data["hwid_device_limit"], 5)
            self.assertEqual(update_data["extra_hwid_devices"], 2)
            create_tariff_change.assert_awaited_once()

            panel_payload = service.panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertEqual(panel_payload["trafficLimitBytes"], 207 * GIB)
            self.assertEqual(panel_payload["trafficLimitStrategy"], "NO_RESET")
            self.assertEqual(panel_payload["hwidDeviceLimit"], 7)
            self.assertEqual(panel_payload["activeInternalSquads"], ["plus-squad", "plus-premium"])
            self.assertEqual(panel_payload["externalSquadUuid"], "external-squad")

    async def test_admin_tariff_assignment_does_not_record_change_before_panel_confirmation(self):
        payload = _tariffs_config_payload()
        payload["tariffs"].append(
            {
                "key": "plus",
                "names": {"en": "Plus"},
                "descriptions": {"en": "Plus period plan"},
                "squad_uuids": ["plus-squad"],
                "premium_squad_uuids": ["plus-premium"],
                "premium_monthly_gb": 50,
                "billing_model": "period",
                "monthly_gb": 200,
                "prices_rub": {"1": 300},
                "prices_stars": {"1": 0},
                "enabled_periods": [1],
                "hwid_device_limit": 5,
                "enabled": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(payload, tmpdir, USER_EXTERNAL_SQUAD_UUID="external-squad")
            service = _make_service(settings)
            service._get_or_create_panel_user_link_details = AsyncMock(
                return_value=("panel-user", "short-uuid", "short", False)
            )
            current_end = datetime.now(UTC) + timedelta(days=5)
            service.panel_service.update_user_details_on_panel = AsyncMock(
                return_value={
                    "uuid": "panel-user",
                    "expireAt": current_end.isoformat(timespec="milliseconds").replace(
                        "+00:00",
                        "Z",
                    ),
                }
            )
            service.panel_service.get_user_by_uuid = AsyncMock(
                return_value={
                    "uuid": "panel-user",
                    "expireAt": current_end.isoformat(timespec="milliseconds").replace(
                        "+00:00",
                        "Z",
                    ),
                }
            )
            active_sub = SimpleNamespace(
                subscription_id=10,
                end_date=current_end,
                is_active=True,
                status_from_panel="ACTIVE",
                last_notification_sent=None,
                traffic_limit_bytes=100 * GIB,
                traffic_used_bytes=7 * GIB,
                tariff_key="standard",
                tier_baseline_bytes=100 * GIB,
                topup_balance_bytes=3 * GIB,
                regular_bonus_bytes=4 * GIB,
                regular_unlimited_override=False,
                premium_baseline_bytes=25 * GIB,
                premium_topup_balance_bytes=2 * GIB,
                premium_topup_used_bytes=1 * GIB,
                premium_used_bytes=10 * GIB,
                premium_bonus_bytes=6 * GIB,
                premium_is_limited=False,
                premium_period_start_at=None,
                period_start_at=None,
                is_throttled=False,
                hwid_device_limit=3,
                extra_hwid_devices=1,
                effective_monthly_price_rub=150,
            )
            extended_sub = SimpleNamespace(
                **{**active_sub.__dict__, "end_date": current_end + timedelta(days=10)}
            )
            updated_sub = SimpleNamespace(
                **{
                    **extended_sub.__dict__,
                    "tariff_key": "plus",
                    "traffic_limit_bytes": 207 * GIB,
                    "tier_baseline_bytes": 200 * GIB,
                    "premium_baseline_bytes": 50 * GIB,
                    "premium_is_limited": False,
                    "hwid_device_limit": 5,
                    "extra_hwid_devices": 2,
                }
            )

            with (
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.get_user_by_id",
                    AsyncMock(return_value=SimpleNamespace(user_id=42)),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=active_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription_end_date",
                    AsyncMock(return_value=extended_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription",
                    AsyncMock(return_value=updated_sub),
                ) as update_subscription,
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.sum_active_hwid_devices",
                    AsyncMock(return_value=2),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.extend_hwid_device_purchases_for_subscription_bonus",
                    AsyncMock(return_value=0),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.create_tariff_change",
                    AsyncMock(),
                ) as create_tariff_change,
            ):
                result = await service.extend_active_subscription_days(
                    session=AsyncMock(),
                    user_id=42,
                    bonus_days=10,
                    reason="admin_manual_extension",
                    tariff_key="plus",
                )

            self.assertIsNone(result)
            create_tariff_change.assert_not_awaited()
            rollback_data = update_subscription.await_args_list[-1].args[2]
            self.assertEqual(rollback_data["tariff_key"], "standard")
            self.assertEqual(rollback_data["traffic_limit_bytes"], 100 * GIB)
            self.assertEqual(rollback_data["hwid_device_limit"], 3)
            self.assertEqual(rollback_data["extra_hwid_devices"], 1)


class SubscriptionServiceActiveDetailsTests(unittest.IsolatedAsyncioTestCase):
    def _local_active_sub(self) -> SimpleNamespace:
        return SimpleNamespace(
            subscription_id=7,
            user_id=42,
            panel_user_uuid="panel-user",
            panel_subscription_uuid="short-uuid",
            end_date=datetime.now(UTC) + timedelta(days=10),
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
                    "bot.services.subscription_service_impl.lifecycle_details.logger.warning",
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

    async def test_local_active_subscription_fallback_includes_reset_dates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                _tariffs_config_payload(),
                tmpdir,
                USER_TRAFFIC_STRATEGY="MONTH",
            )
            service = _make_service(settings)
            service.panel_service.get_user_by_uuid_lookup = AsyncMock(
                return_value={
                    "ok": False,
                    "user": None,
                    "not_found": False,
                    "failure_reason": "classification=panel_lookup_failed status_code=-1",
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
            period_start = datetime.now(UTC).replace(
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            local_sub = self._local_active_sub()
            local_sub.tariff_key = "standard"
            local_sub.start_date = period_start - timedelta(days=10)
            local_sub.period_start_at = period_start
            local_sub.premium_period_start_at = period_start
            local_sub.premium_baseline_bytes = 25 * GIB

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
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.user_dal.update_user",
                    AsyncMock(),
                ),
            ):
                result = await service.get_active_subscription_details(session, user_id=42)

        self.assertIsNotNone(result)
        self.assertFalse(result["is_panel_data"])
        self.assertEqual(result["traffic_limit_strategy"], "MONTH")
        self.assertEqual(result["period_start_at"], period_start)
        self.assertEqual(result["traffic_next_reset_at"], add_months(period_start, 1))
        self.assertEqual(result["premium_period_start_at"], period_start)
        self.assertEqual(result["premium_next_reset_at"], add_months(period_start, 1))

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

    async def test_get_active_subscription_details_includes_device_topup_renewal_fields(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                _tariffs_config_payload(),
                tmpdir,
                USER_TRAFFIC_STRATEGY="MONTH",
            )
            service = _make_service(settings)
            active_until = datetime(2099, 1, 2, 3, 4, tzinfo=UTC)
            service.panel_service.get_user_by_uuid_lookup = AsyncMock(
                return_value={
                    "ok": True,
                    "user": {
                        "uuid": "panel-user",
                        "shortUuid": "short-uuid",
                        "status": "ACTIVE",
                        "expireAt": "2099-02-01T00:00:00Z",
                        "subscriptionUrl": "https://panel.example.test/sub/short-uuid",
                        "trafficLimitBytes": 1000,
                        "trafficLimitStrategy": "MONTH",
                        "nextTrafficResetAt": "2099-01-01T00:00:00Z",
                        "userTraffic": {
                            "usedTrafficBytes": 100,
                            "lifetimeUsedTrafficBytes": 100,
                        },
                    },
                }
            )
            service.premium_access_for_tariff = AsyncMock(
                return_value={"squad_uuids": [], "squad_labels": [], "node_labels": []}
            )
            session = AsyncMock()
            db_user = SimpleNamespace(
                user_id=42,
                panel_user_uuid="panel-user",
                username="alice",
                language_code="en",
                lifetime_used_traffic_bytes=100,
            )
            local_sub = self._local_active_sub()
            local_sub.tariff_key = "standard"
            local_sub.extra_hwid_devices = 0
            local_sub.hwid_device_limit = 3
            local_sub.premium_baseline_bytes = 25 * GIB
            premium_period_start = datetime.now(UTC).replace(
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            local_sub.premium_period_start_at = premium_period_start

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
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription",
                    AsyncMock(),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.get_hwid_device_entitlement_summary",
                    AsyncMock(
                        return_value={
                            "active_devices": 1,
                            "active_until": active_until,
                            "next_valid_from": None,
                        }
                    ),
                ),
            ):
                result = await service.get_active_subscription_details(session, user_id=42)

        self.assertTrue(result["device_topup_renewal_available"])
        self.assertEqual(result["extra_hwid_devices"], 1)
        self.assertEqual(result["extra_hwid_devices_valid_until"], active_until)
        self.assertEqual(result["extra_hwid_devices_valid_until_text"], "02.01.2099 03:04")
        self.assertEqual(result["traffic_next_reset_at"], datetime(2099, 1, 1, tzinfo=UTC))
        self.assertEqual(result["premium_next_reset_at"], add_months(premium_period_start, 1))

    async def test_traffic_tariff_details_use_global_strategy_for_premium_next_reset(self):
        payload = _tariffs_config_payload()
        payload["tariffs"][1]["premium_squad_uuids"] = ["premium-squad"]
        payload["tariffs"][1]["premium_monthly_gb"] = 25
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(payload, tmpdir, USER_TRAFFIC_STRATEGY="MONTH")
            service = _make_service(settings)
            period_start = datetime.now(UTC).replace(
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            service.panel_service.get_user_by_uuid_lookup = AsyncMock(
                return_value={
                    "ok": True,
                    "user": {
                        "uuid": "panel-user",
                        "shortUuid": "short-uuid",
                        "status": "ACTIVE",
                        "expireAt": "2099-02-01T00:00:00Z",
                        "subscriptionUrl": "https://panel.example.test/sub/short-uuid",
                        "trafficLimitBytes": 1000,
                        "trafficLimitStrategy": "NO_RESET",
                        "userTraffic": {
                            "usedTrafficBytes": 100,
                            "lifetimeUsedTrafficBytes": 100,
                        },
                    },
                }
            )
            service.premium_access_for_tariff = AsyncMock(
                return_value={"squad_uuids": [], "squad_labels": [], "node_labels": []}
            )
            session = AsyncMock()
            db_user = SimpleNamespace(
                user_id=42,
                panel_user_uuid="panel-user",
                username="alice",
                language_code="en",
                lifetime_used_traffic_bytes=100,
            )
            local_sub = self._local_active_sub()
            local_sub.tariff_key = "traffic"
            local_sub.start_date = period_start - timedelta(days=10)
            local_sub.period_start_at = None
            local_sub.premium_period_start_at = period_start
            local_sub.premium_baseline_bytes = 25 * GIB

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
                    "bot.services.subscription_service_impl.lifecycle.subscription_dal.update_subscription",
                    AsyncMock(),
                ),
                patch(
                    "bot.services.subscription_service_impl.lifecycle.tariff_dal.get_hwid_device_entitlement_summary",
                    AsyncMock(return_value={"active_devices": 0}),
                ),
            ):
                result = await service.get_active_subscription_details(session, user_id=42)

        self.assertEqual(result["billing_model"], "traffic")
        self.assertEqual(result["traffic_limit_strategy"], "NO_RESET")
        self.assertIsNone(result["traffic_next_reset_at"])
        self.assertEqual(result["premium_period_start_at"], period_start)
        self.assertEqual(result["premium_next_reset_at"], add_months(period_start, 1))


class SubscriptionDalPayloadTests(unittest.TestCase):
    def test_subscription_model_payload_drops_panel_only_keys(self):
        payload = _subscription_model_payload(
            {
                "user_id": 42,
                "panel_user_uuid": "panel-user",
                "panel_subscription_uuid": "panel-sub",
                "end_date": datetime(2026, 1, 1, tzinfo=UTC),
                "traffic_limit_strategy": "WEEK",
            }
        )

        self.assertEqual(payload["user_id"], 42)
        self.assertNotIn("traffic_limit_strategy", payload)


if __name__ == "__main__":
    unittest.main()
