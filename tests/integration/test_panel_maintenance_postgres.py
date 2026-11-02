"""Separate workers and API processes share one outage state and notification."""

import asyncio
import os
import uuid
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.services.notification_service import NotificationService
from bot.services.panel_api_service import PanelApiService
from bot.services.panel_maintenance import maintenance_mode_enabled
from bot.services.panel_maintenance_worker import PanelMaintenanceWorker
from db.dal import app_settings_dal
from db.models import AppSettingOverride
from tests.support.settings_stub import settings_stub

DATABASE_URL = os.environ.get("CORE_PERFORMANCE_TEST_DATABASE_URL", "")
_ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="Disposable PostgreSQL URL is required")


def test_workers_coordinate_probes_and_keep_manual_intent_in_separate_sessions():
    async def run() -> None:
        schema = "panel_maintenance_test_" + uuid.uuid4().hex
        admin = create_async_engine(DATABASE_URL)
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(
            DATABASE_URL, connect_args={"server_settings": {"search_path": schema}}
        )
        try:
            async with engine.begin() as connection:
                await connection.run_sync(AppSettingOverride.__table__.create)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            reader_factory = async_sessionmaker(engine, expire_on_commit=False)
            settings = settings_stub(
                MAINTENANCE_MODE_AUTO_ENABLED=True,
                MAINTENANCE_MODE_AUTO_DELAY_SECONDS=0,
                PANEL_WRITE_MODE="live",
            )
            clock = [1000.0]
            panel = AsyncMock(spec=PanelApiService)
            panel.get_system_stats.return_value = None
            notifier = AsyncMock(spec=NotificationService)
            notifier.i18n = JsonI18n(str(_ROOT / "locales"))
            workers = [
                PanelMaintenanceWorker(
                    settings,
                    cast(sessionmaker, factory),
                    panel,
                    cast(NotificationService, notifier),
                    clock=lambda: clock[0],
                )
                for _ in range(2)
            ]

            await asyncio.gather(*(worker.tick() for worker in workers))
            panel.get_system_stats.assert_awaited_once()
            notifier.send_custom_notification.assert_awaited_once()
            assert await maintenance_mode_enabled(
                settings, cast(sessionmaker, reader_factory), now=clock[0]
            )
            assert not settings.MAINTENANCE_MODE_ENABLED

            settings.MAINTENANCE_MODE_ENABLED = True
            clock[0] += 15
            panel.get_system_stats.return_value = {}
            await workers[0].tick()
            assert await maintenance_mode_enabled(
                settings, cast(sessionmaker, reader_factory), now=clock[0]
            )
            assert notifier.send_custom_notification.await_count == 2
            settings.MAINTENANCE_MODE_ENABLED = False
            assert not await maintenance_mode_enabled(
                settings, cast(sessionmaker, reader_factory), now=clock[0]
            )

            settings.MAINTENANCE_MODE_AUTO_ENABLED = False
            await workers[1].tick()
            async with reader_factory() as session:
                assert await app_settings_dal.get_all_overrides(session) == {}
        finally:
            await engine.dispose()
            async with admin.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin.dispose()

    asyncio.run(run())
