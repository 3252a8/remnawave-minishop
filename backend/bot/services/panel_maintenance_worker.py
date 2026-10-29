"""Probe panel availability and coordinate automatic maintenance across workers."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable

from sqlalchemy.orm import sessionmaker

from bot.services.notification_service import NotificationService
from bot.services.panel_api_service import PanelApiService
from bot.services.panel_maintenance import (
    PANEL_MAINTENANCE_INTERVAL_SECONDS,
    PANEL_MAINTENANCE_SETTING_KEYS,
    PANEL_MAINTENANCE_STATE_KEY,
    PANEL_MAINTENANCE_STATE_TTL_SECONDS,
    PanelMaintenanceState,
    acquire_panel_maintenance_lock,
    panel_maintenance_configured,
    panel_maintenance_identity,
    read_panel_maintenance_state,
)
from bot.services.settings_override_service import refresh_overrides_from_db
from config.settings import Settings
from db.dal import app_settings_dal

logger = logging.getLogger(__name__)


class PanelMaintenanceWorker:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker,
        panel_service: PanelApiService,
        notification_service: NotificationService | None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.panel_service = panel_service
        self.notification_service = notification_service
        self.clock = clock

    async def run(self) -> None:
        while True:
            try:
                await refresh_overrides_from_db(
                    self.settings, self.session_factory, keys=PANEL_MAINTENANCE_SETTING_KEYS
                )
                await self.tick()
            except Exception:
                logger.exception("Panel maintenance tick failed")
            await asyncio.sleep(PANEL_MAINTENANCE_INTERVAL_SECONDS)

    async def tick(self) -> None:
        async with self.session_factory() as session:
            if not await acquire_panel_maintenance_lock(session):
                return
            if not panel_maintenance_configured(self.settings):
                await app_settings_dal.delete_override(session, PANEL_MAINTENANCE_STATE_KEY)
                await session.commit()
                return

            panel_id = panel_maintenance_identity(self.settings)
            previous = await read_panel_maintenance_state(session, panel_id)
            now = self.clock()
            if previous is not None:
                age = now - previous.checked_at
                if 0 <= age < PANEL_MAINTENANCE_INTERVAL_SECONDS:
                    return
                if not 0 <= age <= PANEL_MAINTENANCE_STATE_TTL_SECONDS:
                    previous = None
            try:
                # get_system_stats reads the panel directly, without a reference-data cache.
                async with asyncio.timeout(10):
                    stats = await self.panel_service.get_system_stats()
                available = isinstance(stats, dict) and not stats.get("error")
            except Exception as exc:
                logger.warning("Panel availability probe failed (%s)", type(exc).__name__)
                available = False

            now = self.clock()
            state = (
                previous.model_copy()
                if previous is not None
                else PanelMaintenanceState(panel_id=panel_id, checked_at=now)
            )
            was_active = state.active
            state.checked_at = now
            if available:
                state.unavailable_since = None
                state.active = False
            else:
                if state.unavailable_since is None:
                    state.unavailable_since = now
                state.active = (
                    now - state.unavailable_since
                    >= self.settings.MAINTENANCE_MODE_AUTO_DELAY_SECONDS
                )
            if state.active and not was_active:
                state.notice = "unavailable"
                state.notice_id = uuid.uuid4().hex
                logger.warning("Automatic panel maintenance activated")
            elif available and was_active:
                state.notice = "recovered"
                state.notice_id = uuid.uuid4().hex
                logger.info("Automatic panel maintenance cleared after panel recovery")
            await app_settings_dal.upsert_override(
                session,
                key=PANEL_MAINTENANCE_STATE_KEY,
                value=state.model_dump(mode="json"),
                updated_by=None,
            )
            # Telegram delivery must not prevent the maintenance state from taking effect.
            await session.commit()
        await self._deliver_notice(state)

    async def _deliver_notice(self, state: PanelMaintenanceState) -> None:
        notifier = self.notification_service
        if state.notice is None or notifier is None or notifier.i18n is None:
            return
        message = notifier.i18n.gettext(
            self.settings.DEFAULT_LANGUAGE,
            f"admin_panel_maintenance_{state.notice}",
            seconds=max(
                0,
                int(state.checked_at - state.unavailable_since)
                if state.unavailable_since is not None
                else 0,
            ),
        )
        await notifier.send_custom_notification(message, to_admins=True, to_log_channel=False)
        async with self.session_factory() as session:
            await acquire_panel_maintenance_lock(session, wait=True)
            current = await read_panel_maintenance_state(session, state.panel_id)
            # A slow delivery must not acknowledge a newer outage or recovery notice.
            if current is None or current.notice_id != state.notice_id:
                return
            current.notice = None
            current.notice_id = ""
            await app_settings_dal.upsert_override(
                session,
                key=PANEL_MAINTENANCE_STATE_KEY,
                value=current.model_dump(mode="json"),
                updated_by=None,
            )
            await session.commit()
