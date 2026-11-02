"""Shared, expiring panel maintenance state, independent of the manual switch."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from config.settings import Settings
from db.dal import app_settings_dal

logger = logging.getLogger(__name__)

PANEL_MAINTENANCE_STATE_KEY = "PANEL_MAINTENANCE_STATE"
PANEL_MAINTENANCE_INTERVAL_SECONDS = 15
PANEL_MAINTENANCE_STATE_TTL_SECONDS = 90
PANEL_MAINTENANCE_SETTING_KEYS = {
    "MAINTENANCE_MODE_ENABLED",
    "MAINTENANCE_MODE_AUTO_ENABLED",
    "MAINTENANCE_MODE_AUTO_DELAY_SECONDS",
}


class PanelMaintenanceState(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    panel_id: str
    checked_at: float = Field(ge=0)
    unavailable_since: float | None = Field(default=None, ge=0)
    active: bool = False
    notice: Literal["unavailable", "recovered"] | None = None
    notice_id: str = ""


def panel_maintenance_configured(settings: Settings) -> bool:
    return bool(
        settings.MAINTENANCE_MODE_AUTO_ENABLED
        and settings.panel_settings.api_url
        and not settings.panel_dry_run_enabled
    )


def panel_maintenance_identity(settings: Settings) -> str:
    panel = settings.panel_settings
    identity = "\0".join((panel.api_url or "", panel.api_key or "", panel.api_cookie or ""))
    return hashlib.sha256(identity.encode()).hexdigest()


async def acquire_panel_maintenance_lock(session: AsyncSession, *, wait: bool = False) -> bool:
    result = await session.execute(
        text(
            "SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"
            if wait
            else "SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"
        ),
        {"key": "minishop:panel-maintenance"},
    )
    return wait or bool(result.scalar())


async def read_panel_maintenance_state(
    session: AsyncSession, panel_id: str
) -> PanelMaintenanceState | None:
    present, raw = await app_settings_dal.get_override_value(session, PANEL_MAINTENANCE_STATE_KEY)
    if not present:
        return None
    try:
        state = PanelMaintenanceState.model_validate(raw)
    except ValidationError:
        return None
    return state if state.panel_id == panel_id else None


async def maintenance_mode_enabled(
    settings: Settings,
    session_factory: sessionmaker,
    *,
    now: float | None = None,
) -> bool:
    if settings.MAINTENANCE_MODE_ENABLED:
        return True
    if not panel_maintenance_configured(settings):
        return False
    try:
        async with session_factory() as session:
            state = await read_panel_maintenance_state(
                session, panel_maintenance_identity(settings)
            )
    except Exception as exc:
        logger.warning("Could not read automatic maintenance state (%s)", type(exc).__name__)
        return False
    checked_now = time.time() if now is None else now
    return bool(
        state is not None
        and state.active
        and 0 <= checked_now - state.checked_at <= PANEL_MAINTENANCE_STATE_TTL_SECONDS
        and state.unavailable_since is not None
        and checked_now - state.unavailable_since >= settings.MAINTENANCE_MODE_AUTO_DELAY_SECONDS
    )
