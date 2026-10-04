"""Shared authentication, settings refresh, and safe errors for Telegram design APIs."""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from pathlib import Path

from aiogram import Bot
from aiohttp import web
from pydantic import BaseModel

from bot.app.web.context import get_bot, get_i18n, get_session_factory, get_settings
from bot.middlewares.i18n import JsonI18n
from bot.services.settings_override_service import refresh_overrides_from_db, update_overrides
from bot.services.telegram_emoji_catalog import TelegramEmojiError
from config.settings import Settings
from config.telegram_menu import TELEGRAM_MENU_SETTING_KEYS

from .auth import _require_admin_user_id
from .common import _error

type Handler = Callable[[web.Request], Awaitable[web.Response]]


def telegram_route(handler: Handler) -> Handler:
    @functools.wraps(handler)
    async def guarded(request: web.Request) -> web.Response:
        _require_admin_user_id(request)
        try:
            return await handler(request)
        except TelegramEmojiError as exc:
            return _error(exc.status, exc.code)
        except ValueError:
            return _error(400, "telegram_emoji_invalid_source")
        except OSError:
            return _error(503, "telegram_emoji_storage_unavailable")

    return guarded


def optional_bot(request: web.Request) -> Bot | None:
    try:
        return get_bot(request)
    except KeyError:
        return None


def required_bot(request: web.Request) -> Bot:
    bot = optional_bot(request)
    if bot is None:
        raise TelegramEmojiError("telegram_emoji_bot_required", 503)
    return bot


async def current_settings(request: web.Request) -> Settings:
    settings = get_settings(request)
    await refresh_overrides_from_db(
        settings, get_session_factory(request), keys=TELEGRAM_MENU_SETTING_KEYS
    )
    return settings


def menu_i18n(request: web.Request) -> JsonI18n:
    return get_i18n(request) or JsonI18n(
        str(Path(__file__).resolve().parents[5] / "locales"),
        default=get_settings(request).DEFAULT_LANGUAGE,
    )


async def persist_setting(request: web.Request, key: str, value: BaseModel, revision: str) -> None:
    result = await update_overrides(
        get_settings(request),
        get_session_factory(request),
        updates={key: value.model_dump(mode="json")},
        actor_id=_require_admin_user_id(request),
        expected_revisions={key: revision},
    )
    if not result["ok"]:
        conflict = any(
            message == "telegram_menu_conflict" for message in result.get("errors", {}).values()
        )
        raise TelegramEmojiError(
            "telegram_menu_conflict" if conflict else "telegram_emoji_invalid_source",
            409 if conflict else 400,
        )
