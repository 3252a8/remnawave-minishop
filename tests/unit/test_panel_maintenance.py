"""Automatic maintenance must follow observed outages without changing manual intent."""

import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.services.notification_service import NotificationService
from bot.services.panel_api_service import PanelApiService
from bot.services.panel_maintenance import (
    PANEL_MAINTENANCE_STATE_KEY,
    PanelMaintenanceState,
    maintenance_mode_enabled,
    panel_maintenance_identity,
)
from bot.services.panel_maintenance_worker import PanelMaintenanceWorker
from tests.support.settings_stub import settings_stub

_ROOT = Path(__file__).resolve().parents[2]


class PanelMaintenanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.settings = settings_stub(
            MAINTENANCE_MODE_AUTO_ENABLED=True,
            MAINTENANCE_MODE_AUTO_DELAY_SECONDS=60,
            PANEL_WRITE_MODE="live",
        )
        self.now = 1000.0
        self.records: dict[str, Any] = {}
        self.session = AsyncMock(spec=AsyncSession)
        lock_result = MagicMock()
        lock_result.scalar.return_value = True
        self.session.execute.return_value = lock_result
        context = AsyncMock()
        context.__aenter__.return_value = self.session
        self.factory = cast(sessionmaker, MagicMock(return_value=context))
        self.panel = AsyncMock(spec=PanelApiService)
        self.panel.get_system_stats.return_value = None
        self.notifier = AsyncMock(spec=NotificationService)
        self.notifier.i18n = JsonI18n(str(_ROOT / "locales"), default="ru")

        async def read(_session: AsyncSession, key: str) -> tuple[bool, Any]:
            return key in self.records, self.records.get(key)

        async def write(_session: AsyncSession, *, key: str, value: Any, updated_by: int | None):
            self.records[key] = value

        async def delete(_session: AsyncSession, key: str) -> bool:
            return self.records.pop(key, None) is not None

        self.upsert = self.enterContext(
            patch("db.dal.app_settings_dal.upsert_override", AsyncMock(side_effect=write))
        )
        self.enterContext(
            patch("db.dal.app_settings_dal.get_override_value", AsyncMock(side_effect=read))
        )
        self.enterContext(
            patch("db.dal.app_settings_dal.delete_override", AsyncMock(side_effect=delete))
        )
        self.worker = self.new_worker()

    def new_worker(self) -> PanelMaintenanceWorker:
        return PanelMaintenanceWorker(
            self.settings,
            self.factory,
            self.panel,
            cast(NotificationService, self.notifier),
            clock=lambda: self.now,
        )

    async def active(self) -> bool:
        enabled = await maintenance_mode_enabled(self.settings, self.factory, now=self.now)
        assert isinstance(enabled, bool)
        return enabled

    async def test_only_sustained_failure_activates_and_notifies_once(self):
        for elapsed in (0, 15, 30, 45):
            self.now = 1000 + elapsed
            await self.worker.tick()
            self.assertFalse(await self.active())
        self.notifier.send_custom_notification.assert_not_awaited()

        self.now = 1060
        await self.worker.tick()
        self.assertTrue(await self.active())
        self.notifier.send_custom_notification.assert_awaited_once()
        notice = self.notifier.send_custom_notification.await_args
        self.assertIn("60", notice.args[0])
        self.assertEqual(notice.kwargs, {"to_admins": True, "to_log_channel": False})
        self.assertFalse(self.settings.MAINTENANCE_MODE_ENABLED)

        self.now = 1075
        await self.worker.tick()
        self.assertTrue(await self.active())
        self.notifier.send_custom_notification.assert_awaited_once()
        self.assertEqual(
            {item.kwargs["key"] for item in self.upsert.await_args_list},
            {PANEL_MAINTENANCE_STATE_KEY},
        )

    async def test_a_successful_empty_stats_response_resets_the_outage_timer(self):
        await self.worker.tick()
        self.now += 45
        self.panel.get_system_stats.return_value = {}
        await self.worker.tick()
        self.now += 15
        self.panel.get_system_stats.return_value = None
        await self.worker.tick()
        self.now += 45
        await self.worker.tick()
        self.assertFalse(await self.active())
        self.notifier.send_custom_notification.assert_not_awaited()
        self.now += 15
        await self.worker.tick()
        self.assertTrue(await self.active())

    async def test_recovery_preserves_manual_mode_and_notifies_once(self):
        self.settings.MAINTENANCE_MODE_AUTO_DELAY_SECONDS = 0
        self.settings.MAINTENANCE_MODE_ENABLED = True
        await self.worker.tick()
        self.assertTrue(await self.active())
        self.now += 15
        self.panel.get_system_stats.return_value = {}
        await self.worker.tick()
        self.assertTrue(self.settings.MAINTENANCE_MODE_ENABLED)
        self.assertTrue(await self.active())
        self.assertEqual(self.notifier.send_custom_notification.await_count, 2)
        self.assertIn("снова доступна", self.notifier.send_custom_notification.await_args.args[0])
        self.settings.MAINTENANCE_MODE_ENABLED = False
        self.assertFalse(await self.active())
        self.now += 15
        await self.worker.tick()
        self.assertEqual(self.notifier.send_custom_notification.await_count, 2)

    async def test_disable_and_dry_run_clear_only_the_automatic_state(self):
        for mode in ("disabled", "dry_run", "unconfigured"):
            with self.subTest(mode=mode):
                self.settings.MAINTENANCE_MODE_AUTO_ENABLED = True
                self.settings.PANEL_WRITE_MODE = "live"
                self.settings.PANEL_API_URL = "https://panel.example.test/api"
                self.settings.MAINTENANCE_MODE_AUTO_DELAY_SECONDS = 0
                self.now += 30
                await self.worker.tick()
                self.assertTrue(await self.active())
                if mode == "disabled":
                    self.settings.MAINTENANCE_MODE_AUTO_ENABLED = False
                elif mode == "dry_run":
                    self.settings.PANEL_WRITE_MODE = "dry_run"
                else:
                    self.settings.PANEL_API_URL = None
                self.panel.get_system_stats.reset_mock()
                self.assertFalse(await self.active())
                await self.worker.tick()
                self.panel.get_system_stats.assert_not_awaited()
                self.assertNotIn(PANEL_MAINTENANCE_STATE_KEY, self.records)
                self.assertFalse(self.settings.MAINTENANCE_MODE_ENABLED)

    async def test_restart_continues_recent_observations_but_not_a_stale_gap(self):
        await self.worker.tick()
        self.now += 30
        await self.new_worker().tick()
        self.now += 30
        await self.new_worker().tick()
        self.assertTrue(await self.active())
        self.now += 91
        self.assertFalse(await self.active())
        await self.new_worker().tick()
        self.assertFalse(await self.active())

    async def test_stale_different_panel_and_malformed_state_do_not_block_users(self):
        self.records[PANEL_MAINTENANCE_STATE_KEY] = PanelMaintenanceState(
            panel_id=panel_maintenance_identity(self.settings),
            checked_at=self.now,
            unavailable_since=self.now - 60,
            active=True,
        ).model_dump(mode="json")
        self.assertTrue(await self.active())
        self.settings.PANEL_API_KEY = "a-different-panel-key"
        self.assertFalse(await self.active())
        self.records[PANEL_MAINTENANCE_STATE_KEY] = {"active": True}
        self.assertFalse(await self.active())
        self.settings.MAINTENANCE_MODE_ENABLED = True
        self.assertTrue(await self.active())

    async def test_another_worker_or_recent_probe_does_not_duplicate_the_request(self):
        await self.worker.tick()
        await self.new_worker().tick()
        self.panel.get_system_stats.assert_awaited_once()
        self.now += 15
        self.session.execute.return_value.scalar.return_value = False
        await self.new_worker().tick()
        self.panel.get_system_stats.assert_awaited_once()

    async def test_probe_exceptions_count_as_unavailable_without_exposing_details(self):
        self.settings.MAINTENANCE_MODE_AUTO_DELAY_SECONDS = 0
        self.panel.get_system_stats.side_effect = TimeoutError("private transport details")
        await self.worker.tick()
        self.assertTrue(await self.active())
        self.assertNotIn(
            "private transport", self.notifier.send_custom_notification.await_args.args[0]
        )

    async def test_notification_failure_does_not_prevent_maintenance_and_can_be_retried(self):
        self.settings.MAINTENANCE_MODE_AUTO_DELAY_SECONDS = 0
        self.notifier.send_custom_notification.side_effect = RuntimeError("Telegram unavailable")
        with self.assertRaisesRegex(RuntimeError, "Telegram unavailable"):
            await self.worker.tick()
        self.assertTrue(await self.active())
        self.notifier.send_custom_notification.side_effect = None
        self.now += 15
        await self.worker.tick()
        self.assertEqual(self.notifier.send_custom_notification.await_count, 2)
        self.assertIsNone(self.records[PANEL_MAINTENANCE_STATE_KEY]["notice"])

    async def test_database_failure_cannot_clear_manual_maintenance(self):
        cast(MagicMock, self.factory).side_effect = RuntimeError("database unavailable")
        self.assertFalse(await self.active())
        self.settings.MAINTENANCE_MODE_ENABLED = True
        self.assertTrue(await self.active())

    async def test_longer_delay_applies_immediately_to_an_active_observation(self):
        self.settings.MAINTENANCE_MODE_AUTO_DELAY_SECONDS = 0
        await self.worker.tick()
        self.assertTrue(await self.active())
        self.settings.MAINTENANCE_MODE_AUTO_DELAY_SECONDS = 120
        self.assertFalse(await self.active())

    async def test_a_zero_epoch_timestamp_is_not_replaced_by_the_current_time(self):
        self.now = 0
        await self.worker.tick()
        self.now = 60
        await self.worker.tick()
        self.assertTrue(await self.active())
        self.assertIn("60", self.notifier.send_custom_notification.await_args.args[0])
