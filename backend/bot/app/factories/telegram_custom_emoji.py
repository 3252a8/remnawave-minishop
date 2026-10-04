"""Bounded custom emoji fallback for immediate and queued Telegram delivery."""

from __future__ import annotations

import asyncio
from collections.abc import Set
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Literal

from aiogram import Bot
from aiogram.client.default import Default
from aiogram.client.session.base import TelegramType
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import Response, TelegramMethod
from aiogram.types import InlineKeyboardMarkup, Message

from bot.services.telegram_emoji_storage import capabilities, observe_capability, read_item
from bot.utils.custom_emoji import custom_emoji_unicode_html, split_decorative_emoji

CUSTOM_EMOJI_PROBE: ContextVar[bool] = ContextVar("telegram_custom_emoji_probe", default=False)
_PERMISSION_ERRORS = (
    "premium account required",
    "premium_account_required",
    "custom emoji are not allowed",
    "custom emoji is not allowed",
    "custom_emoji_not_allowed",
    "custom emoji usage is not allowed",
    "bot can't use custom emoji",
    "bot cannot use custom emoji",
)
_INVALID_ERRORS = (
    "custom emoji identifier",
    "custom emoji id",
    "custom_emoji_id_invalid",
    "emoji_id_invalid",
    "icon_custom_emoji_id",
    "custom emoji document",
    "custom emoji is invalid",
)
CAPABILITY_TTL_SECONDS = 1800


def custom_emoji_error(message: str) -> Literal["permission", "invalid"] | None:
    normalized = message.casefold()
    if any(value in normalized for value in _PERMISSION_ERRORS):
        return "permission"
    if any(value in normalized for value in _INVALID_ERRORS):
        return "invalid"
    return None


def method_features[T](method: TelegramMethod[T]) -> set[Literal["icon", "text"]]:
    features: set[Literal["icon", "text"]] = set()
    markup = getattr(method, "reply_markup", None)
    if isinstance(markup, InlineKeyboardMarkup) and any(
        button.icon_custom_emoji_id for row in markup.inline_keyboard for button in row
    ):
        features.add("icon")
    parse_mode = getattr(method, "parse_mode", None)
    html = parse_mode == "HTML" or isinstance(parse_mode, Default)
    if html and any(
        isinstance(value := getattr(method, key, None), str) and "tg-emoji" in value.lower()
        for key in ("text", "caption")
    ):
        features.add("text")
    if any(
        entity.type == "custom_emoji"
        for key in ("entities", "caption_entities")
        for entity in (getattr(method, key, None) or [])
    ):
        features.add("text")
    return features


def unicode_method[T](bot: Bot, method: TelegramMethod[T], features: Set[str]) -> TelegramMethod[T]:
    update: dict[str, object] = {}
    if "text" in features:
        for key in ("text", "caption"):
            value = getattr(method, key, None)
            if isinstance(value, str):
                update[key] = custom_emoji_unicode_html(value)
        for key in ("entities", "caption_entities"):
            entities = getattr(method, key, None)
            if entities:
                # Removing this entity preserves all UTF-16 offsets and the original fallback text.
                update[key] = [entity for entity in entities if entity.type != "custom_emoji"]
    markup = getattr(method, "reply_markup", None)
    if "icon" in features and isinstance(markup, InlineKeyboardMarkup):
        rows = []
        for row in markup.inline_keyboard:
            buttons = []
            for button in row:
                if button.icon_custom_emoji_id:
                    cached = read_item(bot.id, button.icon_custom_emoji_id)
                    fallback = cached.fallback if cached else "🙂"
                    prefix, _ = split_decorative_emoji(button.text)
                    text = button.text if prefix else f"{fallback} {button.text}"
                    button = button.model_copy(update={"icon_custom_emoji_id": None, "text": text})
                buttons.append(button)
            rows.append(buttons)
        update["reply_markup"] = markup.model_copy(update={"inline_keyboard": rows})
    return method.model_copy(update=update)


class CustomEmojiFallbackMiddleware(BaseRequestMiddleware):
    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Response[TelegramType]:
        features = method_features(method)
        if not features:
            return await make_request(bot, method)
        chat_id = getattr(method, "chat_id", None)
        private = isinstance(chat_id, int) and chat_id > 0
        if private and not CUSTOM_EMOJI_PROBE.get():
            state = await asyncio.to_thread(capabilities, bot.id)
            unavailable = set()
            for feature in features:
                value = getattr(state, feature)
                if value.state == "unavailable" and value.tested_at:
                    try:
                        tested = datetime.fromisoformat(value.tested_at)
                        if tested.tzinfo is None:
                            continue
                    except ValueError:
                        continue
                    if 0 <= (datetime.now(UTC) - tested).total_seconds() < CAPABILITY_TTL_SECONDS:
                        unavailable.add(feature)
            if unavailable:
                method = unicode_method(bot, method, unavailable)
                features -= unavailable
        try:
            response = await make_request(bot, method)
            if private and isinstance(response, Message):
                if "icon" in features and response.reply_markup is not None:
                    present = any(
                        button.icon_custom_emoji_id
                        for row in response.reply_markup.inline_keyboard
                        for button in row
                    )
                    await asyncio.to_thread(observe_capability, bot.id, "icon", present)
                if "text" in features and (
                    response.text is not None or response.caption is not None
                ):
                    present = any(
                        entity.type == "custom_emoji"
                        for entity in [
                            *(response.entities or []),
                            *(response.caption_entities or []),
                        ]
                    )
                    await asyncio.to_thread(observe_capability, bot.id, "text", present)
            return response
        except TelegramBadRequest as exc:
            reason = custom_emoji_error(exc.message)
            if not features or reason is None:
                raise
            if private and reason == "permission":
                for feature in features:
                    await asyncio.to_thread(observe_capability, bot.id, feature, False)
            # A rejected request delivered nothing. Retry once; unrelated errors propagate.
            return await make_request(bot, unicode_method(bot, method, features))
