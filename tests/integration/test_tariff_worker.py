import asyncio
import json
import logging
import tempfile
import unittest
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra.redis import close_redis
from bot.services.panel_api_compat import PanelApiCompatibility
from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.services.tariff_worker import TariffTrafficWorker
from bot.services.tariff_worker_premium_batches import PremiumSquadMutationPlan
from bot.services.tariff_worker_shared import canonical_subscriptions_per_panel_user
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


class _FormatI18n:
    def gettext(self, _lang, key, **kwargs):
        templates = {
            "traffic_reset_regular_notification": "regular reset {limit_total}",
            "traffic_reset_premium_notification": ("premium reset {limit_total}\n{servers}"),
            "traffic_warning_regular_almost": "regular almost {left_pct} {limit_total}",
            "traffic_warning_regular_depleted": "regular depleted {limit_total}",
            "traffic_warning_premium_almost": (
                "premium almost {left_pct} {limit_total}\n{servers}"
            ),
            "traffic_warning_premium_depleted": "premium depleted {limit_total}\n{servers}",
            "traffic_warning_premium_generic_servers": "premium servers",
            "traffic_warning_premium_servers_more": "and {count} more",
            "traffic_warning_regular_next_reset_note": (
                "regular next {reset_date} {reset_available}"
            ),
            "traffic_warning_premium_next_reset_note": (
                "premium next {reset_date} {reset_available}"
            ),
            "traffic_warn_btn_topup_webapp_regular": "Top up traffic",
            "traffic_warn_btn_topup_webapp_premium": "Top up premium traffic",
        }
        return templates.get(key, key).format(**kwargs)


class _PeriodTariff:
    billing_model = "period"
    monthly_bytes = 100

    def name(self, _lang, fallback="ru"):
        return "Standard"


class _PremiumTariff:
    key = "standard"
    billing_model = "period"
    squad_uuids: ClassVar[list[str]] = ["squad-1"]
    premium_squad_uuids: ClassVar[list[str]] = ["premium-squad"]
    premium_monthly_bytes = 25 * (1024**3)

    def name(self, _lang, fallback="ru"):
        return "Standard"


class TariffWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        # Settings inherit the CI Redis URL. Close the shared client before
        # IsolatedAsyncioTestCase tears down the event loop that owns its pool.
        await close_redis()

    def test_topup_webapp_button_labels_do_not_mention_mini_app(self):
        class I18n:
            def gettext(self, _lang, key, **_kwargs):
                return {
                    "traffic_warn_btn_topup_webapp_regular": "Top up traffic",
                    "traffic_warn_btn_topup_webapp_premium": "Top up premium traffic",
                }.get(key, key)

        worker = TariffTrafficWorker(
            settings=SimpleNamespace(SUBSCRIPTION_MINI_APP_URL="https://app.example.com"),
            session_factory=SimpleNamespace(),
            panel_service=SimpleNamespace(),
            subscription_service=SimpleNamespace(),
            bot=SimpleNamespace(),
            i18n=I18n(),
        )

        regular = worker._traffic_topup_markup("en", "regular").inline_keyboard[0][0]
        premium = worker._traffic_topup_markup("en", "premium").inline_keyboard[0][0]

        self.assertEqual(regular.text, "Top up traffic")
        self.assertEqual(regular.web_app.url, "https://app.example.com?topup=regular")
        self.assertEqual(premium.text, "Top up premium traffic")
        self.assertEqual(premium.web_app.url, "https://app.example.com?topup=premium")

    def test_panel_last_reset_drives_future_reset_note_date(self):
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(USER_TRAFFIC_STRATEGY="MONTH"),
            session_factory=SimpleNamespace(),
            panel_service=SimpleNamespace(),
            subscription_service=SimpleNamespace(),
        )

        next_reset_at = worker._panel_next_traffic_reset_at(
            {
                "trafficLimitStrategy": "MONTH",
                "lastTrafficResetAt": "2026-04-01T00:00:00Z",
            },
            now=datetime(2026, 7, 1, 12, tzinfo=UTC),
        )
        note = worker._traffic_next_reset_note(
            lambda key, **kwargs: "{reset_date} {reset_available}".format(**kwargs),
            kind="premium",
            period_start_at=datetime(2026, 3, 1, tzinfo=UTC),
            reset_available_bytes=1024,
            user_lang="en",
            next_reset_at=next_reset_at,
        )

        self.assertEqual(next_reset_at, datetime(2026, 8, 1, tzinfo=UTC))
        self.assertEqual(note, "2026-08-01 1.0 KB")

    def test_no_reset_strategy_omits_reset_note(self):
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(USER_TRAFFIC_STRATEGY="NO_RESET"),
            session_factory=SimpleNamespace(),
            panel_service=SimpleNamespace(),
            subscription_service=SimpleNamespace(),
        )

        note = worker._traffic_next_reset_note(
            lambda key, **kwargs: "{reset_date} {reset_available}".format(**kwargs),
            kind="premium",
            period_start_at=datetime(2026, 3, 1, tzinfo=UTC),
            reset_available_bytes=1024,
            user_lang="en",
        )

        self.assertEqual(note, "")

    async def test_regular_reset_notice_sent_after_previous_period_warning(self):
        bot = AsyncMock()
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(
                DEFAULT_LANGUAGE="en",
                SUBSCRIPTION_MINI_APP_URL="https://app.example.com",
                email_auth_configured=False,
                tariff_traffic_warning_levels=[85],
            ),
            session_factory=SimpleNamespace(),
            panel_service=SimpleNamespace(),
            subscription_service=SimpleNamespace(),
            bot=bot,
            i18n=_FormatI18n(),
        )
        worker._user_lang = AsyncMock(return_value="en")
        session = AsyncMock()
        current_period = datetime(2026, 6, 1, tzinfo=UTC)
        previous_period = datetime(2026, 5, 1, tzinfo=UTC)
        sub = SimpleNamespace(subscription_id=10, user_id=123, traffic_used_bytes=1)

        with (
            patch(
                "bot.services.tariff_worker_regular.tariff_dal.has_warning_level_between",
                new=AsyncMock(side_effect=[True, False]),
            ),
            patch(
                "bot.services.tariff_worker_regular.tariff_dal.get_warning",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.tariff_worker_regular.tariff_dal.create_warning",
                new=AsyncMock(),
            ) as create_warning,
            patch(
                "bot.services.tariff_worker_core.log_user_message_delivery",
                new=AsyncMock(),
            ),
        ):
            await worker._maybe_send_regular_reset_notice(
                session,
                sub,
                _PeriodTariff(),
                used=1,
                limit=100,
                period_start_at=current_period,
                previous_period_start=previous_period,
                traffic_strategy="MONTH",
            )

        create_warning.assert_awaited_once()
        self.assertEqual(
            create_warning.await_args.kwargs["level"],
            worker.REGULAR_RESET_NOTICE_LEVEL,
        )
        bot.send_message.assert_awaited_once()
        sent_text = bot.send_message.await_args.args[1]
        self.assertIn("regular reset", sent_text)
        self.assertIn("100 B", sent_text)
        self.assertNotIn("99 B", sent_text)

    async def test_regular_reset_notice_skips_when_current_period_already_near_limit(self):
        bot = AsyncMock()
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(
                DEFAULT_LANGUAGE="en",
                email_auth_configured=False,
                tariff_traffic_warning_levels=[85],
            ),
            session_factory=SimpleNamespace(),
            panel_service=SimpleNamespace(),
            subscription_service=SimpleNamespace(),
            bot=bot,
            i18n=_FormatI18n(),
        )
        session = AsyncMock()

        with patch(
            "bot.services.tariff_worker_regular.tariff_dal.has_warning_level_between",
            new=AsyncMock(),
        ) as has_warning:
            await worker._maybe_send_regular_reset_notice(
                session,
                SimpleNamespace(subscription_id=10, user_id=123),
                _PeriodTariff(),
                used=85,
                limit=100,
                period_start_at=datetime(2026, 6, 1, tzinfo=UTC),
                previous_period_start=datetime(2026, 5, 1, tzinfo=UTC),
                traffic_strategy="MONTH",
            )

        has_warning.assert_not_awaited()
        bot.send_message.assert_not_awaited()

    async def test_regular_reset_notice_skips_same_period_limit_increase(self):
        bot = AsyncMock()
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(
                DEFAULT_LANGUAGE="en",
                email_auth_configured=False,
                tariff_traffic_warning_levels=[85],
            ),
            session_factory=SimpleNamespace(),
            panel_service=SimpleNamespace(),
            subscription_service=SimpleNamespace(),
            bot=bot,
            i18n=_FormatI18n(),
        )
        session = AsyncMock()

        with patch(
            "bot.services.tariff_worker_regular.tariff_dal.has_warning_level_between",
            new=AsyncMock(),
        ) as has_warning:
            await worker._maybe_send_regular_reset_notice(
                session,
                SimpleNamespace(subscription_id=10, user_id=123),
                _PeriodTariff(),
                used=int(817.2 * (1024**3)),
                limit=1000 * (1024**3),
                period_start_at=datetime(2026, 6, 1, tzinfo=UTC),
                previous_period_start=datetime(2026, 6, 1, tzinfo=UTC),
                traffic_strategy="MONTH",
            )

        has_warning.assert_not_awaited()
        bot.send_message.assert_not_awaited()

    async def test_regular_warning_mentions_next_reset_and_regular_limit(self):
        bot = AsyncMock()
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(
                DEFAULT_LANGUAGE="ru",
                SUBSCRIPTION_MINI_APP_URL="https://app.example.com",
                email_auth_configured=False,
                tariff_traffic_warning_levels=[85],
            ),
            session_factory=SimpleNamespace(),
            panel_service=SimpleNamespace(),
            subscription_service=SimpleNamespace(),
            bot=bot,
            i18n=_FormatI18n(),
        )
        worker._user_lang = AsyncMock(return_value="ru")
        worker._send_traffic_warning_email = AsyncMock()
        sub = SimpleNamespace(
            subscription_id=12,
            user_id=123,
            traffic_used_bytes=90,
            traffic_limit_bytes=200,
            is_throttled=False,
        )

        with (
            patch(
                "bot.services.tariff_worker_regular.tariff_dal.get_warning",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.tariff_worker_regular.tariff_dal.create_warning",
                new=AsyncMock(),
            ),
            patch(
                "bot.services.tariff_worker_regular.log_user_message_delivery",
                new=AsyncMock(),
            ),
        ):
            await worker._maybe_warn_or_throttle(
                AsyncMock(),
                sub,
                _PeriodTariff(),
                used=180,
                limit=200,
                warning_period_start=datetime(2026, 6, 1, tzinfo=UTC),
            )

        bot.send_message.assert_awaited_once()
        sent_text = bot.send_message.await_args.args[1]
        self.assertIn("regular next 01.07.2026 200 B", sent_text)
        email_text = worker._send_traffic_warning_email.await_args.kwargs["message_text"]
        self.assertIn("regular next 01.07.2026 200 B", email_text)

    async def test_premium_reset_notice_waits_for_restored_panel_access(self):
        settings = SimpleNamespace(
            DEFAULT_LANGUAGE="en",
            SUBSCRIPTION_MINI_APP_URL="https://app.example.com",
            email_auth_configured=False,
            tariff_traffic_warning_levels=[85],
        )
        panel_service = AsyncMock(spec=PanelApiService)
        panel_service.get_internal_squad_accessible_nodes = AsyncMock(
            return_value=[{"uuid": "node-1", "name": "Premium A"}]
        )
        panel_service.get_node_users_bandwidth_stats = AsyncMock(
            return_value={"topUsers": [{"username": "tg_123", "total": 1 * (1024**3)}]}
        )
        panel_service.update_user_details_on_panel = AsyncMock(return_value={"response": {}})
        subscription_service = SubscriptionService(settings, panel_service)
        subscription_service.premium_access_for_tariff = AsyncMock(
            return_value={"node_labels": ["Premium A"], "squad_labels": []}
        )
        bot = AsyncMock()
        worker = TariffTrafficWorker(
            settings=settings,
            session_factory=SimpleNamespace(),
            panel_service=panel_service,
            subscription_service=subscription_service,
            bot=bot,
            i18n=_FormatI18n(),
        )
        worker._user_lang = AsyncMock(return_value="en")
        sub = SimpleNamespace(
            subscription_id=11,
            user_id=123,
            panel_user_uuid="panel-uuid",
            premium_baseline_bytes=25 * (1024**3),
            premium_topup_balance_bytes=0,
            premium_topup_used_bytes=0,
            premium_used_bytes=25 * (1024**3),
            premium_is_limited=True,
            premium_period_start_at=datetime(2026, 5, 1, tzinfo=UTC),
            premium_unlimited_override=False,
            premium_bonus_bytes=0,
        )

        with (
            patch(
                "bot.services.tariff_worker_premium.tariff_dal.has_warning_level_between",
                new=AsyncMock(side_effect=[True, False]),
            ),
            patch(
                "bot.services.tariff_worker_premium.tariff_dal.get_warning",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.tariff_worker_premium.tariff_dal.create_warning",
                new=AsyncMock(),
            ) as create_warning,
            patch(
                "bot.services.tariff_worker_core.log_user_message_delivery",
                new=AsyncMock(),
            ),
        ):
            await worker._sync_premium_squad_limit(
                AsyncMock(),
                sub,
                _PremiumTariff(),
                datetime(2026, 6, 2, tzinfo=UTC),
                panel_username="tg_123",
                panel_user_dict={"activeInternalSquads": [{"uuid": "squad-1"}]},
            )

        panel_service.update_user_details_on_panel.assert_awaited_once()
        create_warning.assert_awaited_once()
        self.assertEqual(
            create_warning.await_args.kwargs["level"],
            worker.PREMIUM_RESET_NOTICE_LEVEL,
        )
        bot.send_message.assert_awaited_once()
        sent_text = bot.send_message.await_args.args[1]
        self.assertIn("premium reset", sent_text)
        self.assertIn("Premium A", sent_text)

    async def test_premium_warning_mentions_next_reset_and_premium_limit(self):
        bot = AsyncMock()
        subscription_service = SimpleNamespace(
            premium_access_for_tariff=AsyncMock(
                return_value={"node_labels": ["Premium A"], "squad_labels": []}
            )
        )
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(
                DEFAULT_LANGUAGE="en",
                SUBSCRIPTION_MINI_APP_URL="https://app.example.com",
                email_auth_configured=False,
                tariff_traffic_warning_levels=[85],
            ),
            session_factory=SimpleNamespace(),
            panel_service=SimpleNamespace(),
            subscription_service=subscription_service,
            bot=bot,
            i18n=_FormatI18n(),
        )
        worker._user_lang = AsyncMock(return_value="en")
        worker._send_traffic_warning_email = AsyncMock()
        sub = SimpleNamespace(
            subscription_id=13,
            user_id=123,
            premium_baseline_bytes=200,
            premium_topup_balance_bytes=80,
            premium_bonus_bytes=0,
        )

        with (
            patch(
                "bot.services.tariff_worker_premium.tariff_dal.get_warning",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.tariff_worker_premium.tariff_dal.create_warning",
                new=AsyncMock(),
            ),
            patch(
                "bot.services.tariff_worker_premium.log_user_message_delivery",
                new=AsyncMock(),
            ),
        ):
            await worker._maybe_warn_premium_squad_limit(
                AsyncMock(),
                sub,
                _PremiumTariff(),
                used=270,
                limit=300,
                period_start_at=datetime(2026, 6, 1, tzinfo=UTC),
            )

        bot.send_message.assert_awaited_once()
        sent_text = bot.send_message.await_args.args[1]
        self.assertIn("premium next 2026-07-01 280 B", sent_text)
        email_text = worker._send_traffic_warning_email.await_args.kwargs["message_text"]
        self.assertIn("premium next 2026-07-01 280 B", email_text)

    async def test_db_tick_retries_deadlock_once(self):
        class FakeSession:
            def __init__(self):
                self.execute = AsyncMock()
                self.commit = AsyncMock()
                self.rollback = AsyncMock()

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        sessions = []

        def session_factory():
            session = FakeSession()
            sessions.append(session)
            return session

        attempts = 0

        async def tick(_session):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("deadlock detected")

        worker = TariffTrafficWorker(
            settings=SimpleNamespace(),
            session_factory=session_factory,
            panel_service=SimpleNamespace(),
            subscription_service=SimpleNamespace(),
        )

        with patch("bot.services.tariff_worker.asyncio.sleep", new=AsyncMock()) as sleep:
            await worker._run_db_tick_with_retry("test", tick)

        self.assertEqual(attempts, 2)
        self.assertEqual(len(sessions), 2)
        sessions[0].rollback.assert_awaited_once()
        sessions[0].commit.assert_not_awaited()
        sessions[1].commit.assert_awaited_once()
        sleep.assert_awaited_once()

    async def test_retryable_db_exception_detects_wrapped_sqlstate(self):
        class PgError(Exception):
            sqlstate = "40P01"

        class WrappedDbError(Exception):
            def __init__(self, orig):
                super().__init__("wrapped")
                self.orig = orig

        self.assertTrue(TariffTrafficWorker._is_retryable_db_exception(WrappedDbError(PgError())))
        self.assertFalse(TariffTrafficWorker._is_retryable_db_exception(RuntimeError("plain")))

    async def test_period_tariff_preserves_panel_reset_strategy_during_sync(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            now = datetime.now(UTC)
            config_path = Path(tmpdir) / "tariffs.json"
            config_path.write_text(json.dumps(_tariffs_config_payload()), encoding="utf-8")

            settings = Settings(
                _env_file=None,
                BOT_TOKEN="token",
                POSTGRES_USER="app_user",
                POSTGRES_PASSWORD="app_password",
                TARIFFS_CONFIG_PATH=str(config_path),
                USER_TRAFFIC_STRATEGY="NO_RESET",
            )
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.get_user_by_uuid = AsyncMock(
                return_value={
                    "uuid": "panel-uuid",
                    "username": "tg_123",
                    "status": "ACTIVE",
                    "trafficLimitBytes": 500 * (1024**3),
                    "usedTrafficBytes": 1 * (1024**3),
                    "trafficLimitStrategy": "MONTH",
                    "lastTrafficResetAt": "2026-07-01T00:00:00Z",
                    "hwidDeviceLimit": 0,
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
                tariff_key="standard",
                start_date=datetime(2026, 6, 15, tzinfo=UTC),
                end_date=now + timedelta(days=10),
                traffic_limit_bytes=500 * (1024**3),
                traffic_used_bytes=0,
                tier_baseline_bytes=500 * (1024**3),
                topup_balance_bytes=0,
                regular_bonus_bytes=0,
                regular_unlimited_override=False,
                is_throttled=False,
                status_from_panel="ACTIVE",
                period_start_at=None,
                hwid_device_limit=0,
                extra_hwid_devices=0,
                premium_baseline_bytes=0,
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=0,
                premium_is_limited=False,
            )
            result = SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [sub]),
            )
            session = SimpleNamespace(execute=AsyncMock(return_value=result))

            with patch(
                "bot.services.tariff_worker_regular.tariff_dal.get_hwid_device_entitlement_summary",
                new=AsyncMock(
                    return_value={
                        "active_devices": 0,
                        "traffic_bonus_bytes": 0,
                        "legacy_active_devices": 0,
                    }
                ),
            ):
                await worker.traffic_period_tick(session)

            panel_service.update_user_details_on_panel.assert_not_awaited()
            self.assertEqual(
                sub.period_start_at,
                now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
            )

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
                    warning_period_start=datetime.now(UTC),
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
                    datetime.now(UTC),
                    panel_username="tg_123",
                )

            self.assertTrue(sub.premium_is_limited)
            panel_service.update_user_details_on_panel.assert_awaited_once()
            payload = panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertEqual(payload["activeInternalSquads"], ["squad-1"])

    async def test_premium_limit_does_not_persist_managed_premium_as_panel_override(self):
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
                return_value={"topUsers": [{"username": "tg_123", "total": 2 * (1024**3)}]}
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
            session = MagicMock(spec=AsyncSession)
            captured_overrides: list[str] = []

            async def capture_override(*_args, **kwargs):
                captured_overrides.append(kwargs["squad_uuid"])

            async def active_overrides(*_args, **_kwargs):
                return list(captured_overrides)

            with (
                patch(
                    "bot.services.tariff_worker.tariff_dal.get_warning",
                    new=AsyncMock(return_value=True),
                ),
                patch(
                    "bot.services.tariff_worker_premium.tariff_dal.sum_traffic_topups",
                    new=AsyncMock(return_value=0),
                ),
                patch(
                    "bot.services.subscription_service_impl.squad_overrides.override_dal.deactivate_panel_internal_overrides_for_squads",
                    new=AsyncMock(return_value=1),
                ) as deactivate_managed,
                patch(
                    "bot.services.subscription_service_impl.squad_overrides.override_dal.upsert_internal_override",
                    new=AsyncMock(side_effect=capture_override),
                ),
                patch(
                    "bot.services.subscription_service_impl.squad_overrides.override_dal.get_active_internal_squad_uuids",
                    new=AsyncMock(side_effect=active_overrides),
                ),
                patch(
                    "bot.services.subscription_service_impl.squad_overrides.override_dal.get_active_external_override",
                    new=AsyncMock(return_value=None),
                ),
            ):
                await worker._sync_premium_squad_limit(
                    session,
                    sub,
                    tariff,
                    datetime.now(UTC),
                    panel_username="tg_123",
                    panel_user_dict={
                        "activeInternalSquads": [
                            {"uuid": "squad-1"},
                            {"uuid": "premium-squad"},
                        ]
                    },
                    panel_view="full_fetch",
                )

            self.assertEqual(captured_overrides, [])
            deactivate_kwargs = deactivate_managed.await_args.kwargs
            self.assertEqual(
                deactivate_kwargs["squad_uuids"],
                ["squad-1", "premium-squad"],
            )
            panel_payload = panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertEqual(panel_payload["activeInternalSquads"], ["squad-1"])

    async def test_unmetered_premium_squad_is_added_to_existing_subscription(self):
        payload = _tariffs_config_payload()
        payload["tariffs"][0]["premium_squad_uuids"] = ["premium-squad"]
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
                premium_baseline_bytes=0,
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=0,
                premium_is_limited=False,
            )
            tariff = settings.tariffs_config.require("standard")

            await worker._sync_premium_squad_limit(
                AsyncMock(),
                sub,
                tariff,
                datetime.now(UTC),
                panel_user_dict={"activeInternalSquads": [{"uuid": "squad-1"}]},
                panel_view="full_fetch",
            )

            panel_service.update_user_details_on_panel.assert_awaited_once()
            panel_payload = panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertEqual(
                panel_payload["activeInternalSquads"],
                ["squad-1", "premium-squad"],
            )
            panel_service.get_internal_squad_accessible_nodes.assert_not_awaited()
            panel_service.get_node_users_bandwidth_stats.assert_not_awaited()
            self.assertFalse(sub.premium_is_limited)

    async def test_trial_premium_limit_uses_trial_premium_traffic_limit(self):
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
                TRIAL_TRAFFIC_LIMIT_GB=9,
                TRIAL_PREMIUM_TRAFFIC_LIMIT_GB=3,
                TRIAL_SQUAD_UUIDS="squad-1",
                TRIAL_PREMIUM_SQUAD_UUIDS="premium-squad",
                TARIFF_TRAFFIC_WARNING_LEVELS="101",
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
                            "total": 4 * (1024**3),
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
                provider="trial",
                status_from_panel="TRIAL",
                tariff_key=None,
                premium_baseline_bytes=3 * (1024**3),
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=0,
                premium_is_limited=False,
                premium_period_start_at=None,
                premium_unlimited_override=False,
                premium_bonus_bytes=0,
            )
            trial_tariff = worker._trial_premium_tariff()

            self.assertIsNotNone(trial_tariff)
            await worker._sync_premium_squad_limit(
                AsyncMock(),
                sub,
                trial_tariff,
                datetime.now(UTC),
                panel_username="tg_123",
                panel_user_dict={
                    "activeInternalSquads": [
                        {"uuid": "squad-1"},
                        {"uuid": "premium-squad"},
                    ]
                },
            )

            self.assertEqual(sub.premium_baseline_bytes, 3 * (1024**3))
            self.assertEqual(sub.premium_used_bytes, 4 * (1024**3))
            self.assertTrue(sub.premium_is_limited)
            panel_service.update_user_details_on_panel.assert_awaited_once()
            payload = panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertEqual(payload["activeInternalSquads"], ["squad-1"])

    async def test_trial_keeps_panel_regular_usage_and_tracks_premium_usage(self):
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
                TRIAL_TRAFFIC_LIMIT_GB=9,
                TRIAL_PREMIUM_TRAFFIC_LIMIT_GB=3,
                TRIAL_SQUAD_UUIDS="squad-1",
                TRIAL_PREMIUM_SQUAD_UUIDS="premium-squad",
                TARIFF_TRAFFIC_WARNING_LEVELS="101",
            )
            panel_service = AsyncMock(spec=PanelApiService)
            panel_service.get_user_by_uuid = AsyncMock(
                return_value={
                    "uuid": "panel-uuid",
                    "username": "tg_123",
                    "status": "ACTIVE",
                    "trafficLimitBytes": 9 * (1024**3),
                    "usedTrafficBytes": 5 * (1024**3),
                    "activeInternalSquads": [
                        {"uuid": "squad-1"},
                        {"uuid": "premium-squad"},
                    ],
                }
            )
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
                provider="trial",
                status_from_panel="TRIAL",
                tariff_key=None,
                start_date=datetime.now(UTC) - timedelta(days=1),
                end_date=datetime.now(UTC) + timedelta(days=2),
                traffic_limit_bytes=9 * (1024**3),
                traffic_used_bytes=0,
                premium_baseline_bytes=3 * (1024**3),
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=0,
                premium_is_limited=False,
                premium_period_start_at=None,
                premium_unlimited_override=False,
                premium_bonus_bytes=0,
            )
            result = SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [sub]),
            )
            session = SimpleNamespace(execute=AsyncMock(return_value=result))

            await worker.traffic_period_tick(session)

            self.assertEqual(sub.premium_used_bytes, 2 * (1024**3))
            self.assertEqual(sub.traffic_used_bytes, 5 * (1024**3))
            panel_service.update_user_details_on_panel.assert_not_awaited()

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
            now = datetime(2026, 5, 9, tzinfo=UTC)
            sub = SimpleNamespace(
                subscription_id=1,
                user_id=123,
                panel_user_uuid="panel-uuid",
                premium_baseline_bytes=1 * (1024**3),
                premium_topup_balance_bytes=2 * (1024**3),
                premium_topup_used_bytes=0,
                premium_used_bytes=0,
                premium_is_limited=False,
                premium_period_start_at=datetime(2026, 5, 1, tzinfo=UTC),
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
            next_month = datetime(2026, 6, 2, tzinfo=UTC)
            await worker._sync_premium_squad_limit(
                AsyncMock(), sub, tariff, next_month, panel_username="tg_123"
            )

            self.assertEqual(sub.premium_topup_balance_bytes, int(1.5 * (1024**3)))
            self.assertEqual(sub.premium_topup_used_bytes, 0)
            self.assertEqual(sub.premium_period_start_at, datetime(2026, 6, 1, tzinfo=UTC))

    async def test_premium_no_reset_keeps_period_usage_after_month_boundary(self):
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
                USER_TRAFFIC_STRATEGY="NO_RESET",
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
                start_date=datetime(2026, 5, 15, 12, tzinfo=UTC),
                premium_baseline_bytes=1 * (1024**3),
                premium_topup_balance_bytes=2 * (1024**3),
                premium_topup_used_bytes=int(0.25 * (1024**3)),
                premium_used_bytes=1 * (1024**3),
                premium_is_limited=False,
                premium_period_start_at=datetime(2026, 6, 1, tzinfo=UTC),
                premium_unlimited_override=False,
                premium_bonus_bytes=0,
            )
            tariff = settings.tariffs_config.require("standard")

            await worker._sync_premium_squad_limit(
                AsyncMock(),
                sub,
                tariff,
                datetime(2026, 7, 2, tzinfo=UTC),
                panel_username="tg_123",
            )

            stats_call = panel_service.get_node_users_bandwidth_stats.await_args
            self.assertEqual(stats_call.args[0], "node-1")
            self.assertEqual(stats_call.kwargs["start"], "2026-05-15")
            self.assertEqual(stats_call.kwargs["end"], "2026-07-02")
            self.assertEqual(sub.premium_period_start_at, sub.start_date)
            self.assertEqual(sub.premium_topup_balance_bytes, int(1.25 * (1024**3)))
            self.assertEqual(sub.premium_topup_used_bytes, 1 * (1024**3))
            self.assertFalse(sub.premium_is_limited)
            panel_service.update_user_details_on_panel.assert_not_awaited()

    async def test_premium_week_strategy_uses_current_week_start(self):
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
                USER_TRAFFIC_STRATEGY="WEEK",
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
                            "total": int(0.1 * (1024**3)),
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
                start_date=datetime(2026, 6, 10, tzinfo=UTC),
                premium_baseline_bytes=1 * (1024**3),
                premium_topup_balance_bytes=2 * (1024**3),
                premium_topup_used_bytes=int(0.25 * (1024**3)),
                premium_used_bytes=1 * (1024**3),
                premium_is_limited=False,
                premium_period_start_at=datetime(2026, 6, 29, tzinfo=UTC),
                premium_unlimited_override=False,
                premium_bonus_bytes=0,
            )
            tariff = settings.tariffs_config.require("standard")

            await worker._sync_premium_squad_limit(
                AsyncMock(),
                sub,
                tariff,
                datetime(2026, 7, 8, 13, tzinfo=UTC),
                panel_username="tg_123",
            )

            stats_call = panel_service.get_node_users_bandwidth_stats.await_args
            self.assertEqual(stats_call.kwargs["start"], "2026-07-06")
            self.assertEqual(stats_call.kwargs["end"], "2026-07-08")
            self.assertEqual(sub.premium_period_start_at, datetime(2026, 7, 6, tzinfo=UTC))
            self.assertEqual(sub.premium_topup_used_bytes, 0)

    async def test_premium_month_rolling_uses_panel_last_reset_anchor(self):
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
                USER_TRAFFIC_STRATEGY="MONTH_ROLLING",
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
                            "total": int(0.1 * (1024**3)),
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
                start_date=datetime(2026, 5, 3, tzinfo=UTC),
                premium_baseline_bytes=1 * (1024**3),
                premium_topup_balance_bytes=2 * (1024**3),
                premium_topup_used_bytes=int(0.25 * (1024**3)),
                premium_used_bytes=1 * (1024**3),
                premium_is_limited=False,
                premium_period_start_at=datetime(2026, 7, 15, 12, 30, tzinfo=UTC),
                premium_unlimited_override=False,
                premium_bonus_bytes=0,
            )
            tariff = settings.tariffs_config.require("standard")

            await worker._sync_premium_squad_limit(
                AsyncMock(),
                sub,
                tariff,
                datetime(2026, 8, 20, 9, tzinfo=UTC),
                panel_username="tg_123",
                panel_user_dict={
                    "trafficLimitStrategy": "MONTH_ROLLING",
                    "lastTrafficResetAt": "2026-06-15T12:30:00Z",
                },
            )

            stats_call = panel_service.get_node_users_bandwidth_stats.await_args
            self.assertEqual(stats_call.kwargs["start"], "2026-08-15")
            self.assertEqual(stats_call.kwargs["end"], "2026-08-20")
            self.assertEqual(
                sub.premium_period_start_at,
                datetime(2026, 8, 15, 12, 30, tzinfo=UTC),
            )
            self.assertEqual(sub.premium_topup_used_bytes, 0)

    async def test_premium_month_strategy_keeps_saved_anchor_when_panel_list_omits_reset(self):
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
                USER_TRAFFIC_STRATEGY="MONTH",
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
            period_start = datetime(2026, 6, 15, 12, 30, tzinfo=UTC)
            sub = SimpleNamespace(
                subscription_id=1,
                user_id=123,
                panel_user_uuid="panel-uuid",
                start_date=datetime(2026, 5, 3, tzinfo=UTC),
                premium_baseline_bytes=1 * (1024**3),
                premium_topup_balance_bytes=2 * (1024**3),
                premium_topup_used_bytes=0,
                premium_used_bytes=0,
                premium_is_limited=False,
                premium_period_start_at=period_start,
                premium_unlimited_override=False,
                premium_bonus_bytes=0,
            )
            tariff = settings.tariffs_config.require("standard")

            await worker._sync_premium_squad_limit(
                AsyncMock(),
                sub,
                tariff,
                datetime(2026, 7, 4, 9, tzinfo=UTC),
                panel_username="tg_123",
                panel_user_dict={"trafficLimitStrategy": "MONTH"},
                panel_view="list",
            )

            stats_call = panel_service.get_node_users_bandwidth_stats.await_args
            self.assertEqual(stats_call.kwargs["start"], "2026-06-15")
            self.assertEqual(stats_call.kwargs["end"], "2026-07-04")
            self.assertEqual(sub.premium_period_start_at, period_start)
            self.assertEqual(sub.premium_topup_balance_bytes, int(1.5 * (1024**3)))
            self.assertEqual(sub.premium_topup_used_bytes, int(0.5 * (1024**3)))

    async def test_premium_topup_ledger_repairs_missing_balance_before_limiting(self):
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
                        {"username": "tg_123", "total": 40 * (1024**3)},
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
            worker._premium_topup_ledger_total = AsyncMock(return_value=20 * (1024**3))
            now = datetime(2026, 5, 9, tzinfo=UTC)
            sub = SimpleNamespace(
                subscription_id=1,
                user_id=123,
                panel_user_uuid="panel-uuid",
                premium_baseline_bytes=25 * (1024**3),
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=40 * (1024**3),
                premium_is_limited=True,
                premium_period_start_at=datetime(2026, 5, 1, tzinfo=UTC),
                premium_unlimited_override=False,
                premium_bonus_bytes=0,
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
                    now,
                    panel_username="tg_123",
                    panel_user_dict={
                        "activeInternalSquads": [
                            {"uuid": "squad-1"},
                            {"uuid": "premium-squad"},
                        ]
                    },
                )

            self.assertEqual(sub.premium_topup_balance_bytes, 5 * (1024**3))
            self.assertEqual(sub.premium_topup_used_bytes, 15 * (1024**3))
            self.assertFalse(sub.premium_is_limited)
            panel_service.update_user_details_on_panel.assert_not_awaited()

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
            panel_service.get_user_by_uuid = AsyncMock(
                return_value={
                    "activeInternalSquads": [
                        {"uuid": "squad-1"},
                        {"uuid": "premium-squad"},
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
            now = datetime(2026, 5, 9, tzinfo=UTC)
            sub = SimpleNamespace(
                subscription_id=1,
                user_id=123,
                panel_user_uuid="panel-uuid",
                premium_baseline_bytes=25 * (1024**3),
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=1 * (1024**3),
                premium_is_limited=False,
                premium_period_start_at=datetime(2026, 5, 1, tzinfo=UTC),
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
            panel_service.get_user_by_uuid.assert_not_awaited()

    async def test_premium_sync_trusts_full_fetch_over_bulk_list_squad_mismatch(self):
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
            panel_service.get_user_by_uuid = AsyncMock(
                return_value={
                    "activeInternalSquads": [
                        {"uuid": "squad-1"},
                        {"uuid": "premium-squad"},
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
            now = datetime(2026, 5, 9, tzinfo=UTC)
            sub = SimpleNamespace(
                subscription_id=1,
                user_id=123,
                panel_user_uuid="panel-uuid",
                premium_baseline_bytes=25 * (1024**3),
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=5 * (1024**3),
                premium_is_limited=False,
                premium_period_start_at=datetime(2026, 5, 1, tzinfo=UTC),
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
                panel_view="list",
            )

            panel_service.get_user_by_uuid.assert_awaited_once_with(
                "panel-uuid",
                log_response=False,
            )
            panel_service.update_user_details_on_panel.assert_not_awaited()
            panel_service.get_user_by_uuid.reset_mock()

            await worker._sync_premium_squad_limit(
                AsyncMock(),
                sub,
                tariff,
                now,
                panel_username="tg_123",
                panel_user_dict={"activeInternalSquads": [{"uuid": "squad-1"}]},
                panel_view="list",
            )

            panel_service.get_user_by_uuid.assert_not_awaited()
            panel_service.update_user_details_on_panel.assert_not_awaited()

    async def test_premium_state_change_skips_panel_patch_when_full_user_already_matches(self):
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
            panel_service.get_user_by_uuid = AsyncMock(
                return_value={
                    "activeInternalSquads": [
                        {"uuid": "squad-1"},
                        {"uuid": "premium-squad"},
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
            now = datetime(2026, 5, 9, tzinfo=UTC)
            sub = SimpleNamespace(
                subscription_id=1,
                user_id=123,
                panel_user_uuid="panel-uuid",
                premium_baseline_bytes=25 * (1024**3),
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=5 * (1024**3),
                premium_is_limited=True,
                premium_period_start_at=datetime(2026, 5, 1, tzinfo=UTC),
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
                panel_view="list",
            )

            self.assertFalse(sub.premium_is_limited)
            panel_service.get_user_by_uuid.assert_awaited_once_with(
                "panel-uuid",
                log_response=False,
            )
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
            panel_service.get_user_by_uuid = AsyncMock(
                return_value={"activeInternalSquads": [{"uuid": "squad-1"}]}
            )
            panel_service.update_user_details_on_panel = AsyncMock(return_value={"response": {}})
            subscription_service = SubscriptionService(settings, panel_service)
            worker = TariffTrafficWorker(
                settings=settings,
                session_factory=SimpleNamespace(),
                panel_service=panel_service,
                subscription_service=subscription_service,
            )
            now = datetime(2026, 5, 9, tzinfo=UTC)
            sub = SimpleNamespace(
                subscription_id=1,
                user_id=123,
                panel_user_uuid="panel-uuid",
                premium_baseline_bytes=25 * (1024**3),
                premium_topup_balance_bytes=0,
                premium_topup_used_bytes=0,
                premium_used_bytes=5 * (1024**3),
                premium_is_limited=False,
                premium_period_start_at=datetime(2026, 5, 1, tzinfo=UTC),
                premium_unlimited_override=False,
                premium_bonus_bytes=0,
            )
            tariff = settings.tariffs_config.require("standard")

            with self.assertLogs(level="INFO") as logs:
                await worker._sync_premium_squad_limit(
                    AsyncMock(),
                    sub,
                    tariff,
                    now,
                    panel_username="tg_123",
                    panel_user_dict={"activeInternalSquads": [{"uuid": "squad-1"}]},
                    panel_view="list",
                )

            panel_service.update_user_details_on_panel.assert_awaited_once()
            panel_service.get_user_by_uuid.assert_awaited_once_with(
                "panel-uuid",
                log_response=False,
            )
            payload_sent = panel_service.update_user_details_on_panel.await_args.args[1]
            self.assertEqual(payload_sent["activeInternalSquads"], ["squad-1", "premium-squad"])
            self.assertTrue(
                any(
                    "Sync panel PATCH: source=premium_squad_limit" in line
                    and "reasons=activeInternalSquads_mismatch" in line
                    and "fields=activeInternalSquads" in line
                    for line in logs.output
                )
            )

    async def test_premium_unlimited_override_never_throttles_or_spends_topup(self):
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
            panel_service.get_user_by_uuid = AsyncMock(
                return_value={"activeInternalSquads": [{"uuid": "squad-1"}]}
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
                premium_topup_balance_bytes=10 * (1024**3),
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
                datetime.now(UTC),
                panel_username="tg_42",
                panel_user_dict={"activeInternalSquads": [{"uuid": "squad-1"}]},
                panel_view="list",
            )

            self.assertFalse(sub.premium_is_limited)
            self.assertEqual(int(sub.premium_used_bytes), 50 * (1024**3))
            self.assertEqual(int(sub.premium_topup_balance_bytes), 10 * (1024**3))
            self.assertEqual(int(sub.premium_topup_used_bytes), 0)
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
                AsyncMock(), sub, tariff, datetime.now(UTC), panel_username="tg_77"
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

    async def test_v3_premium_usage_batches_all_nodes_and_reuses_snapshot(self):
        compatibility = PanelApiCompatibility.from_metadata({"response": {"version": "3.0.0"}})
        panel_service = AsyncMock(spec=PanelApiService)
        panel_service.get_panel_api_compatibility = AsyncMock(return_value=compatibility)
        panel_service.panel_capability_state = MagicMock(
            side_effect=lambda capability, current: current.supports(capability)
        )
        panel_service.get_multi_node_user_usage = AsyncMock(
            return_value={
                "nodes": [
                    {"uuid": "node-1", "users": [{"id": 42, "totalBytes": 10}]},
                    {
                        "uuid": "node-2",
                        "users": [
                            {"id": 42, "totalBytes": 5},
                            {"id": 43, "totalBytes": 7},
                        ],
                    },
                ]
            }
        )
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(),
            session_factory=SimpleNamespace(),
            panel_service=panel_service,
            subscription_service=SimpleNamespace(),
        )

        first = await worker._premium_usage_for_user(
            "42", ["node-1", "node-2"], "2026-08-01", "2026-08-02"
        )
        second = await worker._premium_usage_for_user(
            "43", ["node-2", "node-1"], "2026-08-01", "2026-08-02"
        )

        self.assertEqual(first, 15)
        self.assertEqual(second, 7)
        panel_service.get_multi_node_user_usage.assert_awaited_once()
        panel_service.get_node_users_bandwidth_stats.assert_not_awaited()

    async def test_v2_premium_usage_retries_a_saturated_aggregate(self):
        compatibility = PanelApiCompatibility.from_metadata({"response": {"version": "2.8.1"}})
        panel_service = AsyncMock(spec=PanelApiService)
        panel_service.get_panel_api_compatibility = AsyncMock(return_value=compatibility)
        panel_service.panel_capability_state = MagicMock(
            side_effect=lambda capability, current: current.supports(capability)
        )
        panel_service.panel_user_count_hint.return_value = 0
        panel_service.get_system_stats = AsyncMock(return_value={"users": {"totalUsers": 2}})
        panel_service.get_multi_node_users_bandwidth_stats = AsyncMock(
            side_effect=[
                {"topUsers": [{"username": "one", "total": 1}] * 3},
                {"topUsers": [{"username": "target", "total": 9}]},
            ]
        )
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(),
            session_factory=SimpleNamespace(),
            panel_service=panel_service,
            subscription_service=SimpleNamespace(),
        )

        with (
            patch("bot.services.tariff_worker_premium_usage.PREMIUM_USAGE_TOP_USERS_FLOOR", 3),
            patch("bot.services.tariff_worker_premium_usage.PREMIUM_USAGE_TOP_USERS_CEILING", 10),
        ):
            total = await worker._premium_usage_for_user(
                "legacy-uuid",
                ["node-1", "node-2"],
                "2026-08-01",
                "2026-08-02",
                panel_username="target",
            )

        self.assertEqual(total, 9)
        limits = [
            call.kwargs["top_users_limit"]
            for call in panel_service.get_multi_node_users_bandwidth_stats.await_args_list
        ]
        self.assertEqual(limits, [3, 5])
        panel_service.get_node_users_bandwidth_stats.assert_not_awaited()

    @staticmethod
    def _premium_mutation_plan(reference: str, desired: tuple[str, ...]):
        return PremiumSquadMutationPlan(
            sub=SimpleNamespace(panel_user_uuid=reference),
            tariff=SimpleNamespace(key="premium"),
            desired_squads=desired,
            effective_payload={"activeInternalSquads": list(desired)},
            squad_match_cache_key=(reference, desired),
            should_limit=True,
            newly_limited=True,
            node_uuids=["node-1"],
            start_date="2026-08-01",
            end_date="2026-08-02",
            panel_username=None,
            send_reset_notice=False,
            premium_used=10,
            premium_limit=5,
            premium_period_start=datetime(2026, 8, 1, tzinfo=UTC),
            previous_period_start=None,
            traffic_strategy="MONTH",
        )

    async def test_premium_squad_writes_group_identical_exact_states(self):
        panel_service = AsyncMock(spec=PanelApiService)
        panel_service.update_users_internal_squads_exact = AsyncMock(return_value=True)
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(),
            session_factory=SimpleNamespace(),
            panel_service=panel_service,
            subscription_service=SimpleNamespace(),
        )
        worker._complete_premium_squad_mutation = AsyncMock()
        worker._premium_squad_mutations = [
            self._premium_mutation_plan("42", ("standard",)),
            self._premium_mutation_plan("43", ("standard",)),
        ]

        await worker._flush_premium_squad_mutations(AsyncMock())

        panel_service.update_users_internal_squads_exact.assert_awaited_once_with(
            ["42", "43"], ["standard"]
        )
        panel_service.update_user_details_on_panel.assert_not_awaited()
        self.assertEqual(worker._complete_premium_squad_mutation.await_count, 2)

    async def test_premium_squad_timeout_is_not_replayed_as_point_writes(self):
        compatibility = PanelApiCompatibility.from_metadata({"response": {"version": "3.0.0"}})
        panel_service = AsyncMock(spec=PanelApiService)
        panel_service.update_users_internal_squads_exact = AsyncMock(return_value=False)
        panel_service.get_panel_api_compatibility = AsyncMock(return_value=compatibility)
        panel_service.panel_capability_state.return_value = True
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(),
            session_factory=SimpleNamespace(),
            panel_service=panel_service,
            subscription_service=SimpleNamespace(),
        )
        worker._complete_premium_squad_mutation = AsyncMock()
        worker._premium_squad_mutations = [
            self._premium_mutation_plan("42", ("standard",)),
        ]

        await worker._flush_premium_squad_mutations(AsyncMock())

        panel_service.update_user_details_on_panel.assert_not_awaited()
        worker._complete_premium_squad_mutation.assert_not_awaited()

    async def test_premium_empty_squad_state_uses_point_patch_without_bulk_a088(self):
        panel_service = AsyncMock(spec=PanelApiService)
        panel_service.update_user_details_on_panel = AsyncMock(return_value={"response": {}})
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(),
            session_factory=SimpleNamespace(),
            panel_service=panel_service,
            subscription_service=SimpleNamespace(),
        )
        worker._complete_premium_squad_mutation = AsyncMock()
        worker._premium_squad_mutations = [self._premium_mutation_plan("42", ())]

        await worker._flush_premium_squad_mutations(AsyncMock())

        panel_service.update_users_internal_squads_exact.assert_not_awaited()
        panel_service.update_user_details_on_panel.assert_awaited_once()
        worker._complete_premium_squad_mutation.assert_awaited_once()

    async def test_bulk_panel_prefetch_maps_panel_users_by_uuid_above_threshold(self):
        settings = SimpleNamespace(TARIFF_WORKER_BULK_PANEL_FETCH_THRESHOLD=2)
        panel_service = AsyncMock(spec=PanelApiService)
        panel_service.panel_user_count_hint.return_value = 2
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

    async def test_missing_panel_subscription_repairs_to_user_panel_uuid(self):
        panel_service = AsyncMock(spec=PanelApiService)
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(),
            session_factory=SimpleNamespace(),
            panel_service=panel_service,
            subscription_service=SimpleNamespace(),
        )
        sub = SimpleNamespace(
            subscription_id=10,
            user_id=123,
            panel_user_uuid="old-panel",
            is_active=True,
            status_from_panel="ACTIVE",
            skip_notifications=False,
        )
        panel_user = {"uuid": "new-panel", "username": "tg_123"}

        with patch(
            "bot.services.tariff_worker.user_dal.get_user_by_id",
            new=AsyncMock(return_value=SimpleNamespace(panel_user_uuid="new-panel")),
        ):
            result = await worker._repair_missing_panel_user_for_subscription(
                AsyncMock(),
                sub,
                panel_users_by_uuid={"new-panel": panel_user},
                semaphore=asyncio.Semaphore(1),
                confirmed_missing=True,
            )

        self.assertEqual(result, panel_user)
        self.assertEqual(sub.panel_user_uuid, "new-panel")
        self.assertTrue(sub.is_active)
        panel_service.get_user_by_uuid.assert_not_awaited()

    async def test_missing_panel_subscription_deactivates_when_bulk_prefetch_confirms_absent(self):
        panel_service = AsyncMock(spec=PanelApiService)
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(),
            session_factory=SimpleNamespace(),
            panel_service=panel_service,
            subscription_service=SimpleNamespace(),
        )
        sub = SimpleNamespace(
            subscription_id=11,
            user_id=123,
            panel_user_uuid="missing-panel",
            is_active=True,
            status_from_panel="ACTIVE",
            skip_notifications=False,
        )

        with patch(
            "bot.services.tariff_worker.user_dal.get_user_by_id",
            new=AsyncMock(return_value=SimpleNamespace(panel_user_uuid="missing-panel")),
        ):
            result = await worker._repair_missing_panel_user_for_subscription(
                AsyncMock(),
                sub,
                panel_users_by_uuid={},
                semaphore=asyncio.Semaphore(1),
                confirmed_missing=True,
            )

        self.assertEqual(result, {})
        self.assertFalse(sub.is_active)
        self.assertTrue(sub.skip_notifications)
        self.assertEqual(sub.status_from_panel, "PANEL_USER_NOT_FOUND")

    async def test_missing_panel_subscription_only_skips_when_absence_is_not_confirmed(self):
        panel_service = AsyncMock(spec=PanelApiService)
        panel_service.get_user_by_uuid = AsyncMock(return_value=None)
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(),
            session_factory=SimpleNamespace(),
            panel_service=panel_service,
            subscription_service=SimpleNamespace(),
        )
        sub = SimpleNamespace(
            subscription_id=12,
            user_id=123,
            panel_user_uuid="missing-panel",
            is_active=True,
            status_from_panel="ACTIVE",
            skip_notifications=False,
        )

        with patch(
            "bot.services.tariff_worker.user_dal.get_user_by_id",
            new=AsyncMock(return_value=SimpleNamespace(panel_user_uuid="missing-panel")),
        ):
            result = await worker._repair_missing_panel_user_for_subscription(
                AsyncMock(),
                sub,
                panel_users_by_uuid=None,
                semaphore=asyncio.Semaphore(1),
                confirmed_missing=False,
            )

        self.assertEqual(result, {})
        self.assertTrue(sub.is_active)
        self.assertFalse(sub.skip_notifications)
        self.assertEqual(sub.status_from_panel, "ACTIVE")

    async def test_stale_v2_reference_is_relinked_before_v3_bulk_miss_can_deactivate(self):
        panel_service = AsyncMock(spec=PanelApiService)
        panel_service.get_panel_api_compatibility = AsyncMock(
            return_value=PanelApiCompatibility.from_metadata({"response": {"version": "3.0.0"}})
        )
        db_user = SimpleNamespace(panel_user_uuid="legacy-panel-uuid")
        panel_user = {"uuid": "42", "id": 42, "username": "tg_123"}
        subscription_service = SimpleNamespace(
            _get_or_create_panel_user_link=AsyncMock(
                return_value=SimpleNamespace(
                    panel_user_uuid="42",
                    panel_user=panel_user,
                )
            )
        )
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(),
            session_factory=SimpleNamespace(),
            panel_service=panel_service,
            subscription_service=subscription_service,
        )
        sub = SimpleNamespace(
            subscription_id=13,
            user_id=123,
            panel_user_uuid="legacy-panel-uuid",
            is_active=True,
            status_from_panel="ACTIVE",
            skip_notifications=False,
        )
        session = AsyncMock()

        with patch(
            "bot.services.tariff_worker.user_dal.get_user_by_id",
            new=AsyncMock(return_value=db_user),
        ):
            result = await worker._repair_missing_panel_user_for_subscription(
                session,
                sub,
                panel_users_by_uuid={"42": panel_user},
                semaphore=asyncio.Semaphore(1),
                confirmed_missing=True,
            )

        self.assertEqual(result, panel_user)
        self.assertEqual(sub.panel_user_uuid, "42")
        self.assertTrue(sub.is_active)
        self.assertFalse(sub.skip_notifications)
        subscription_service._get_or_create_panel_user_link.assert_awaited_once_with(
            session,
            123,
            db_user,
        )

    def test_duplicate_active_subscriptions_sync_only_the_newest(self):
        older = SimpleNamespace(
            subscription_id=1,
            panel_user_uuid="panel-1",
            end_date=datetime(2026, 7, 1, tzinfo=UTC),
        )
        newer = SimpleNamespace(
            subscription_id=2,
            panel_user_uuid="panel-1",
            end_date=datetime(2026, 8, 1, tzinfo=UTC),
        )
        other = SimpleNamespace(
            subscription_id=3,
            panel_user_uuid="panel-2",
            end_date=datetime(2026, 8, 1, tzinfo=UTC),
        )

        with self.assertLogs("bot.services.tariff_worker_shared", level="WARNING") as logs:
            kept = canonical_subscriptions_per_panel_user(
                [older, newer, other],
                logger=logging.getLogger("bot.services.tariff_worker_shared"),
            )

        self.assertEqual([sub.subscription_id for sub in kept], [2, 3])
        self.assertIn("panel-1", " ".join(logs.output))

    async def test_panel_limit_patch_backs_off_when_the_value_never_sticks(self):
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(REDIS_URL=None),
            session_factory=SimpleNamespace(),
            panel_service=SimpleNamespace(),
            subscription_service=SimpleNamespace(),
        )

        allowed = [
            await worker._panel_limit_patch_allowed(
                "panel-1",
                "hwid:4|traffic:-",
                subscription_id=7,
                observed="hwidDeviceLimit=2 trafficLimitBytes=None",
            )
            for _ in range(5)
        ]

        # Three attempts, then the worker stops rewriting the same value.
        self.assertEqual(allowed, [True, True, True, False, False])

    async def test_panel_limit_patch_resumes_after_the_desired_value_changes(self):
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(REDIS_URL=None),
            session_factory=SimpleNamespace(),
            panel_service=SimpleNamespace(),
            subscription_service=SimpleNamespace(),
        )
        for _ in range(4):
            await worker._panel_limit_patch_allowed(
                "panel-1",
                "hwid:4|traffic:-",
                subscription_id=7,
                observed="hwidDeviceLimit=2 trafficLimitBytes=None",
            )

        self.assertTrue(
            await worker._panel_limit_patch_allowed(
                "panel-1",
                "hwid:6|traffic:-",
                subscription_id=7,
                observed="hwidDeviceLimit=2 trafficLimitBytes=None",
            )
        )

    async def test_premium_fast_tick_syncs_only_subscriptions_with_premium_squads(self):
        premium_tariff = _PremiumTariff()
        regular_tariff = _PeriodTariff()
        settings = SimpleNamespace(
            TARIFF_PREMIUM_FAST_WATCH_PERCENT=80,
            TARIFF_PREMIUM_FAST_BATCH_LIMIT=200,
            tariffs_config=SimpleNamespace(
                require=lambda key: premium_tariff if key == "standard" else regular_tariff
            ),
        )
        panel_service = AsyncMock(spec=PanelApiService)
        panel_service.get_user_by_uuid = AsyncMock(
            side_effect=[
                {"uuid": "panel-premium", "username": "tg_1"},
                {"uuid": "panel-regular", "username": "tg_2"},
            ]
        )
        worker = TariffTrafficWorker(
            settings=settings,
            session_factory=SimpleNamespace(),
            panel_service=panel_service,
            subscription_service=SimpleNamespace(),
        )
        worker._trial_premium_tariff = lambda: None
        worker._sync_premium_squad_limit = AsyncMock()
        premium_sub = SimpleNamespace(
            subscription_id=1,
            tariff_key="standard",
            panel_user_uuid="panel-premium",
        )
        regular_sub = SimpleNamespace(
            subscription_id=2,
            tariff_key="basic",
            panel_user_uuid="panel-regular",
        )
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=SimpleNamespace(scalars=lambda: iter([premium_sub, regular_sub]))
        )

        await worker.premium_fast_tick(session)

        worker._sync_premium_squad_limit.assert_awaited_once()
        synced_sub = worker._sync_premium_squad_limit.await_args.args[1]
        self.assertIs(synced_sub, premium_sub)
        self.assertEqual(
            worker._sync_premium_squad_limit.await_args.kwargs["panel_view"],
            "full_fetch",
        )
        self.assertEqual(
            worker._sync_premium_squad_limit.await_args.kwargs["panel_username"],
            "tg_1",
        )
        # Only the watched subscription is fetched from the panel.
        self.assertEqual(panel_service.get_user_by_uuid.await_count, 1)

    def test_premium_fast_candidates_query_watches_limited_and_near_limit_subscriptions(self):
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(
                TARIFF_PREMIUM_FAST_WATCH_PERCENT=80,
                TARIFF_PREMIUM_FAST_BATCH_LIMIT=25,
            ),
            session_factory=SimpleNamespace(),
            panel_service=SimpleNamespace(),
            subscription_service=SimpleNamespace(),
        )
        worker._trial_premium_tariff = lambda: None

        sql = str(
            worker._premium_fast_candidates_query(datetime(2026, 6, 1, tzinfo=UTC)).compile(
                compile_kwargs={"literal_binds": True}
            )
        )

        self.assertIn("subscriptions.premium_is_limited IS true", sql)
        self.assertIn("subscriptions.premium_unlimited_override IS false", sql)
        self.assertIn("80 *", sql)
        self.assertIn("LIMIT 25", sql)

    def test_premium_fast_tick_is_disabled_when_interval_is_not_shorter(self):
        def worker_for(fast_seconds, tick_seconds=300):
            return TariffTrafficWorker(
                settings=SimpleNamespace(
                    TARIFF_PREMIUM_FAST_TICK_SECONDS=fast_seconds,
                    TARIFF_WORKER_TICK_SECONDS=tick_seconds,
                ),
                session_factory=SimpleNamespace(),
                panel_service=SimpleNamespace(),
                subscription_service=SimpleNamespace(),
            )

        self.assertEqual(worker_for(60).premium_fast_tick_seconds(), 60)
        self.assertEqual(worker_for(0).premium_fast_tick_seconds(), 0)
        self.assertEqual(worker_for(300).premium_fast_tick_seconds(), 0)
        self.assertEqual(worker_for(600).premium_fast_tick_seconds(), 0)

    async def test_run_interleaves_premium_fast_ticks_between_full_ticks(self):
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(
                tariffs_config=SimpleNamespace(),
                TARIFF_WORKER_TICK_SECONDS=2,
                TARIFF_PREMIUM_FAST_TICK_SECONDS=1,
                TARIFF_WORKER_LOCK_TTL_SECONDS=10,
            ),
            session_factory=SimpleNamespace(),
            panel_service=SimpleNamespace(),
            subscription_service=SimpleNamespace(),
        )
        ticks: list[str] = []

        async def _record_tick(tick_name, _tick):
            ticks.append(tick_name)
            if len(ticks) >= 3:
                worker.stop()

        @asynccontextmanager
        async def _lock(*_args, **_kwargs):
            yield True

        worker._run_db_tick_with_retry = _record_tick
        with patch("bot.services.tariff_worker_core.redis_lock", new=_lock):
            await worker.run()

        self.assertEqual(ticks, ["traffic_period", "legacy_throttle_recovery", "premium_fast"])

    def _premium_enforcement_worker(self, *, drop_enabled=True, cooldown=0):
        settings = SimpleNamespace(
            DEFAULT_LANGUAGE="en",
            SUBSCRIPTION_MINI_APP_URL="",
            email_auth_configured=False,
            tariff_traffic_warning_levels=[85],
            USER_TRAFFIC_STRATEGY="MONTH",
            TARIFF_PREMIUM_DROP_CONNECTIONS=drop_enabled,
            TARIFF_PREMIUM_DROP_CONNECTIONS_COOLDOWN_SECONDS=cooldown,
        )
        panel_service = AsyncMock(spec=PanelApiService)
        panel_service.get_internal_squad_accessible_nodes = AsyncMock(
            return_value=[{"uuid": "node-1", "name": "Premium A"}]
        )
        panel_service.update_user_details_on_panel = AsyncMock(return_value={"response": {}})
        panel_service.drop_user_connections = AsyncMock(return_value=True)
        subscription_service = SubscriptionService(settings, panel_service)
        subscription_service.premium_access_for_tariff = AsyncMock(
            return_value={"node_labels": ["Premium A"], "squad_labels": []}
        )
        worker = TariffTrafficWorker(
            settings=settings,
            session_factory=SimpleNamespace(),
            panel_service=panel_service,
            subscription_service=subscription_service,
        )
        worker._user_lang = AsyncMock(return_value="en")
        worker._maybe_warn_premium_squad_limit = AsyncMock()
        worker._maybe_send_premium_reset_notice = AsyncMock()
        return worker, panel_service

    @staticmethod
    def _premium_enforcement_subscription(*, used_gb, limited):
        return SimpleNamespace(
            subscription_id=41,
            user_id=123,
            panel_user_uuid="panel-uuid",
            premium_baseline_bytes=25 * (1024**3),
            premium_topup_balance_bytes=0,
            premium_topup_used_bytes=0,
            premium_used_bytes=used_gb * (1024**3),
            premium_is_limited=limited,
            premium_period_start_at=datetime(2026, 6, 1, tzinfo=UTC),
            premium_unlimited_override=False,
            premium_bonus_bytes=0,
        )

    async def _run_premium_sync(self, worker, sub, *, node_usage_gb):
        worker.panel_service.get_node_users_bandwidth_stats = AsyncMock(
            return_value={
                "topUsers": [{"username": "tg_123", "total": int(node_usage_gb * (1024**3))}]
            }
        )
        worker._premium_node_usage_tick_cache = {}
        with patch(
            "bot.services.tariff_worker_premium.tariff_dal.sum_traffic_topups",
            new=AsyncMock(return_value=None),
        ):
            await worker._sync_premium_squad_limit(
                AsyncMock(),
                sub,
                _PremiumTariff(),
                datetime(2026, 6, 15, tzinfo=UTC),
                panel_username="tg_123",
                panel_user_dict={
                    "activeInternalSquads": [{"uuid": "squad-1"}, {"uuid": "premium-squad"}]
                },
            )

    async def test_premium_limit_drops_live_connections_on_premium_nodes(self):
        worker, panel_service = self._premium_enforcement_worker()
        sub = self._premium_enforcement_subscription(used_gb=10, limited=False)

        await self._run_premium_sync(worker, sub, node_usage_gb=30)

        self.assertTrue(sub.premium_is_limited)
        panel_service.drop_user_connections.assert_awaited_once_with("panel-uuid", ["node-1"])

    async def test_premium_limit_does_not_drop_connections_when_disabled(self):
        worker, panel_service = self._premium_enforcement_worker(drop_enabled=False)
        sub = self._premium_enforcement_subscription(used_gb=10, limited=False)

        await self._run_premium_sync(worker, sub, node_usage_gb=30)

        self.assertTrue(sub.premium_is_limited)
        panel_service.drop_user_connections.assert_not_awaited()

    async def test_premium_traffic_after_limit_warns_and_drops_again(self):
        worker, panel_service = self._premium_enforcement_worker()
        sub = self._premium_enforcement_subscription(used_gb=10, limited=False)

        # First pass limits the subscription and records the per-node baseline.
        await self._run_premium_sync(worker, sub, node_usage_gb=30)
        panel_service.drop_user_connections.reset_mock()

        # The client keeps spending on the premium node despite being limited.
        # Expire the short cross-tick snapshot: production refreshes it after
        # Remnawave's roughly two-minute usage aggregation cadence.
        worker._premium_usage_snapshot_cache.clear()
        worker._premium_usage_batch_tick_cache.clear()
        with (
            patch(
                "bot.services.tariff_worker_premium_enforcement.cache_get_json",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.tariff_worker_premium_enforcement.cache_set_json",
                new=AsyncMock(),
            ) as cache_set,
            self.assertLogs(
                "bot.services.tariff_worker_premium_enforcement", level="WARNING"
            ) as logs,
        ):
            worker.settings.REDIS_URL = "redis://localhost:6379/0"
            worker.settings.REDIS_KEY_PREFIX = "test"
            await self._run_premium_sync(worker, sub, node_usage_gb=35)

        panel_service.drop_user_connections.assert_awaited_once_with("panel-uuid", ["node-1"])
        self.assertTrue(any("CAP_NET_ADMIN" in line for line in logs.output))
        recorded = cache_set.await_args.args[2]
        self.assertEqual(recorded["node-1"]["name"], "Premium A")
        self.assertEqual(recorded["node-1"]["subscriptions"], [41])

    async def test_premium_leak_watch_is_dropped_when_access_is_restored(self):
        worker, _panel_service = self._premium_enforcement_worker()
        sub = self._premium_enforcement_subscription(used_gb=10, limited=False)

        await self._run_premium_sync(worker, sub, node_usage_gb=30)
        self.assertIn(41, worker._premium_leak_usage)

        # A top-up lifted the limit: the per-node baseline must not linger.
        sub.premium_topup_balance_bytes = 50 * (1024**3)
        await self._run_premium_sync(worker, sub, node_usage_gb=30)

        self.assertFalse(sub.premium_is_limited)
        self.assertNotIn(41, worker._premium_leak_usage)

    async def test_resolved_premium_leak_is_removed_from_admin_warning(self):
        worker, _panel_service = self._premium_enforcement_worker()
        sub = self._premium_enforcement_subscription(used_gb=10, limited=False)
        worker.settings.REDIS_URL = "redis://localhost:6379/0"
        worker.settings.REDIS_KEY_PREFIX = "test"

        await self._run_premium_sync(worker, sub, node_usage_gb=30)
        sub.premium_topup_balance_bytes = 50 * (1024**3)
        stored = {
            "node-1": {
                "name": "Premium A",
                "last_seen_at": datetime.now(UTC).isoformat(),
                "subscriptions": [41, 99],
            },
            "node-2": {
                "name": "Premium B",
                "last_seen_at": datetime.now(UTC).isoformat(),
                "subscriptions": [41],
            },
        }
        with (
            patch(
                "bot.services.tariff_worker_premium_enforcement.cache_get_json",
                new=AsyncMock(return_value=stored),
            ),
            patch(
                "bot.services.tariff_worker_premium_enforcement.cache_set_json",
                new=AsyncMock(),
            ) as cache_set,
            patch(
                "bot.services.tariff_worker_premium_enforcement.cache_delete",
                new=AsyncMock(),
            ) as cache_delete,
        ):
            await self._run_premium_sync(worker, sub, node_usage_gb=30)

        cache_delete.assert_not_awaited()
        persisted = cache_set.await_args.args[2]
        self.assertEqual(persisted["node-1"]["subscriptions"], [99])
        self.assertNotIn("node-2", persisted)

    async def test_premium_usage_keeps_stored_total_when_node_stats_are_unavailable(self):
        settings = SimpleNamespace(
            DEFAULT_LANGUAGE="en",
            SUBSCRIPTION_MINI_APP_URL="",
            email_auth_configured=False,
            tariff_traffic_warning_levels=[85],
            USER_TRAFFIC_STRATEGY="MONTH",
        )
        panel_service = AsyncMock(spec=PanelApiService)
        panel_service.get_internal_squad_accessible_nodes = AsyncMock(
            return_value=[{"uuid": "node-1"}]
        )
        # The panel failed to answer the bandwidth stats request for this node.
        panel_service.get_node_users_bandwidth_stats = AsyncMock(return_value=None)
        panel_service.update_user_details_on_panel = AsyncMock(return_value={"response": {}})
        subscription_service = SubscriptionService(settings, panel_service)
        worker = TariffTrafficWorker(
            settings=settings,
            session_factory=SimpleNamespace(),
            panel_service=panel_service,
            subscription_service=subscription_service,
        )
        worker._maybe_warn_premium_squad_limit = AsyncMock()
        worker._maybe_send_premium_reset_notice = AsyncMock()
        sub = SimpleNamespace(
            subscription_id=31,
            user_id=123,
            panel_user_uuid="panel-uuid",
            premium_baseline_bytes=25 * (1024**3),
            premium_topup_balance_bytes=0,
            premium_topup_used_bytes=0,
            premium_used_bytes=30 * (1024**3),
            premium_is_limited=True,
            premium_period_start_at=datetime(2026, 6, 1, tzinfo=UTC),
            premium_unlimited_override=False,
            premium_bonus_bytes=0,
        )

        with patch(
            "bot.services.tariff_worker_premium.tariff_dal.sum_traffic_topups",
            new=AsyncMock(return_value=None),
        ):
            await worker._sync_premium_squad_limit(
                AsyncMock(),
                sub,
                _PremiumTariff(),
                datetime(2026, 6, 15, tzinfo=UTC),
                panel_username="tg_123",
                panel_user_dict={"activeInternalSquads": [{"uuid": "squad-1"}]},
            )

        # Missing stats must not look like "the user spent nothing" and restore access.
        self.assertTrue(sub.premium_is_limited)
        self.assertEqual(int(sub.premium_used_bytes), 30 * (1024**3))
        panel_service.update_user_details_on_panel.assert_not_awaited()
