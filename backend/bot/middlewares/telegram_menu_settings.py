"""Refresh shared menu settings in the worker before handling a Telegram update."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.orm import sessionmaker

from bot.services.settings_override_service import refresh_overrides_from_db
from config.settings import Settings
from config.telegram_menu import TELEGRAM_MENU_SETTING_KEYS


class TelegramMenuSettingsMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings, session_factory: sessionmaker) -> None:
        self.settings = settings
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        await refresh_overrides_from_db(
            self.settings, self.session_factory, keys=TELEGRAM_MENU_SETTING_KEYS
        )
        return await handler(event, data)
