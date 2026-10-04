"""Serialize cosmetic settings writes, including writes through the general settings API."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from config.telegram_menu import TELEGRAM_MENU_SETTING_KEYS, telegram_setting_revision
from db.dal import app_settings_dal


async def lock_telegram_settings(
    session: AsyncSession, keys: Iterable[str], expected: dict[str, str]
) -> str | None:
    touched = sorted(TELEGRAM_MENU_SETTING_KEYS.intersection(keys))
    if not touched:
        return None
    defaults = Settings()
    for key in touched:
        # The lock also covers a not-yet-created override row. Always acquire in key order.
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "minishop:telegram:" + key},
        )
        if key in expected:
            exists, value = await app_settings_dal.get_override_value(session, key)
            current = value if exists else getattr(defaults, key)
            if telegram_setting_revision(key, current) != expected[key]:
                return key
    return None
