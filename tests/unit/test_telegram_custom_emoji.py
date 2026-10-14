from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.app.factories.telegram_custom_emoji import (
    CUSTOM_EMOJI_PROBE,
    CustomEmojiFallbackMiddleware,
)
from bot.services import telegram_emoji_storage as storage
from bot.services.broadcast_personalization import telegram_html_error
from bot.services.email_templates_common import _telegram_html_to_email_html
from bot.utils.custom_emoji import custom_emoji_unicode_html, valid_emoji_fallback

ID = "9007199254740993"
HTML = f'<b>Hello <tg-emoji emoji-id="{ID}">👩🏽‍💻</tg-emoji></b>'


@pytest.mark.parametrize("value", ["🙂", "👩🏽‍💻", "👨‍👩‍👧‍👦", "❤️", "1️⃣", "🇷🇺", "🏳️‍🌈", "©"])
def test_fallback_accepts_complete_emoji_sequences(value) -> None:
    assert valid_emoji_fallback(value)


@pytest.mark.parametrize(
    "value", ["", "prose", "🙂🙂", " 🙂", "🇷", "🇷🇺‍🇷🇺", "1️⃣‍1️⃣", "🏽", "🙂️️", "<b>🙂</b>", "→", "□", "⍰"]
)
def test_fallback_rejects_multiple_or_broken_sequences(value) -> None:
    assert not valid_emoji_fallback(value)


@pytest.mark.parametrize("value", ["\ufffd", "\u2193", "\u219a", "\U0001fffe", "-", "_"])
def test_fallback_rejects_characters_outside_unicode_pictographic_ranges(value: str) -> None:
    assert not valid_emoji_fallback(value)


@pytest.mark.parametrize("value", ["\u2194", "\u2199", "\U0001fc00", "\U0001fffd"])
def test_fallback_preserves_unicode_pictographic_range_endpoints(value: str) -> None:
    assert valid_emoji_fallback(value)


def test_lint_validates_entities_and_email_keeps_only_unicode_fallback() -> None:
    assert telegram_html_error(HTML) is None
    assert (
        telegram_html_error('<tg-emoji emoji-id="invalid">🙂</tg-emoji>')
        == "custom_emoji_invalid_id"
    )
    assert (
        telegram_html_error(f'<tg-emoji emoji-id="{ID}">hello</tg-emoji>')
        == "custom_emoji_invalid_fallback"
    )
    assert (
        telegram_html_error(f'<tg-emoji emoji-id="{ID}">→</tg-emoji>')
        == "custom_emoji_invalid_fallback"
    )
    assert (
        telegram_html_error(f'<tg-emoji emoji-id="{ID}"><b>🙂</b></tg-emoji>')
        == "custom_emoji_nested_markup"
    )
    assert (
        telegram_html_error(f'<code><tg-emoji emoji-id="{ID}">🙂</tg-emoji></code>')
        == "custom_emoji_in_code"
    )
    assert custom_emoji_unicode_html(HTML) == "<b>Hello 👩🏽‍💻</b>"
    email = _telegram_html_to_email_html(HTML)
    assert "👩🏽‍💻" in email and "tg-emoji" not in email and "<strong>" in email


def message() -> SendMessage:
    return SendMessage(
        chat_id=42,
        text=HTML,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Support",
                        callback_data="help",
                        style="success",
                        icon_custom_emoji_id=ID,
                    ),
                ]
            ]
        ),
    )


def test_permission_failure_retries_once_preserving_style_and_actions(
    tmp_path, monkeypatch
) -> None:
    async def run() -> None:
        monkeypatch.setattr(storage, "ROOT", tmp_path)
        bot = MagicMock(spec=Bot)
        bot.id = 1234
        request = message()
        result = object()
        send = AsyncMock(
            side_effect=[
                TelegramBadRequest(method=request, message="PREMIUM_ACCOUNT_REQUIRED"),
                result,
            ]
        )
        assert await CustomEmojiFallbackMiddleware()(send, bot, request) is result
        assert send.await_count == 2
        fallback = send.call_args.args[1]
        assert fallback.text == "<b>Hello 👩🏽‍💻</b>"
        button = fallback.reply_markup.inline_keyboard[0][0]
        assert button.icon_custom_emoji_id is None
        assert button.style == "success" and button.callback_data == "help"
        assert storage.capabilities(bot.id).icon.state == "unavailable"
        assert storage.capabilities(bot.id).text.state == "unavailable"
        # A confirmed refusal changes subsequent delivery before a request is made.
        send = AsyncMock(return_value=result)
        await CustomEmojiFallbackMiddleware()(send, bot, request)
        assert (
            send.call_args.args[1].reply_markup.inline_keyboard[0][0].icon_custom_emoji_id is None
        )
        probe = CUSTOM_EMOJI_PROBE.set(True)
        try:
            await CustomEmojiFallbackMiddleware()(send, bot, request)
            assert (
                send.call_args.args[1].reply_markup.inline_keyboard[0][0].icon_custom_emoji_id == ID
            )
        finally:
            CUSTOM_EMOJI_PROBE.reset(probe)

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["network", "flood", "other"])
def test_unrelated_failures_never_retry_or_change_capability(kind, tmp_path, monkeypatch) -> None:
    async def run() -> None:
        monkeypatch.setattr(storage, "ROOT", tmp_path)
        bot = MagicMock(spec=Bot)
        bot.id = 1234
        request = message()
        failure = (
            TelegramNetworkError(method=request, message="timeout")
            if kind == "network"
            else TelegramRetryAfter(method=request, message="Too many requests", retry_after=60)
            if kind == "flood"
            else TelegramBadRequest(method=request, message="chat not found")
        )
        send = AsyncMock(side_effect=failure)
        with pytest.raises(type(failure)):
            await CustomEmojiFallbackMiddleware()(send, bot, request)
        assert send.await_count == 1
        assert storage.capabilities(bot.id).text.state == "unknown"

    asyncio.run(run())


def test_bad_id_fallback_does_not_mark_the_bot_ineligible(tmp_path, monkeypatch) -> None:
    async def run() -> None:
        monkeypatch.setattr(storage, "ROOT", tmp_path)
        bot = MagicMock(spec=Bot)
        bot.id = 1234
        request = message()
        send = AsyncMock(
            side_effect=[
                TelegramBadRequest(method=request, message="CUSTOM_EMOJI_ID_INVALID"),
                object(),
            ]
        )
        await CustomEmojiFallbackMiddleware()(send, bot, request)
        assert send.await_count == 2
        assert storage.capabilities(bot.id).icon.state == "unknown"

    asyncio.run(run())
