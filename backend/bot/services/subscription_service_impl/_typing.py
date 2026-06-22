from __future__ import annotations

from typing import Any, Protocol

from aiogram import Bot

from bot.middlewares.i18n import JsonI18n
from bot.services.panel_api_service import PanelApiService
from config.settings import Settings


class SubscriptionServiceMixinContract(Protocol):
    settings: Settings
    panel_service: PanelApiService
    bot: Bot | None
    i18n: JsonI18n | None
    _premium_access_cache: dict[tuple[str, ...], dict[str, Any]]
    recurring_provider_services: dict[str, Any]

    def __getattr__(self, name: str) -> Any: ...
