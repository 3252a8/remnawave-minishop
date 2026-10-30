import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from aiogram import types
from aiogram.dispatcher.event.bases import UNHANDLED

from bot.handlers.user.support_hint import build_support_hint_router, support_hint
from bot.middlewares.i18n import JsonI18n
from tests.support.settings_stub import settings_stub


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_plain_text_offers_normalized_support_and_mini_app(lang):
    settings = settings_stub(
        SUPPORT_LINK="@help_team", SUBSCRIPTION_MINI_APP_URL="https://app.example.com/"
    )
    i18n = JsonI18n(path="locales", default="en")
    message = types.Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=types.Chat(id=42, type="private"),
        from_user=types.User(id=42, is_bot=False, first_name="User"),
        text="How do I install the app?",
    )
    with patch.object(types.Message, "answer", new_callable=AsyncMock) as answer:
        asyncio.run(
            build_support_hint_router().propagate_event(
                "message",
                message,
                raw_state=None,
                settings=settings,
                i18n_data={"i18n_instance": i18n, "current_language": lang},
            )
        )
    answer.assert_awaited_once()
    assert 'href="https://t.me/help_team"' in answer.call_args.args[0]
    buttons = answer.call_args.kwargs["reply_markup"].inline_keyboard
    assert buttons[0][0].url == "https://t.me/help_team"
    assert buttons[1][0].web_app.url == "https://app.example.com/"


@pytest.mark.parametrize(
    ("text", "chat_type", "raw_state", "is_bot"),
    [
        ("/start", "private", None, False),
        (" /unknown", "private", None, False),
        ("CODE", "private", "UserPromoStates:waiting_for_promo_code", False),
        ("hello", "group", None, False),
        (None, "private", None, False),
        ("hello", "private", None, True),
    ],
)
def test_fallback_leaves_commands_states_groups_and_non_text_unhandled(
    text, chat_type, raw_state, is_bot
):
    message = types.Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=types.Chat(id=42, type=chat_type),
        from_user=types.User(id=42, is_bot=is_bot, first_name="User"),
        text=text,
    )
    result = asyncio.run(
        build_support_hint_router().propagate_event("message", message, raw_state=raw_state)
    )
    assert result is UNHANDLED


def test_no_configured_links_gives_start_instruction():
    settings = settings_stub(SUPPORT_LINK="javascript:bad", SUBSCRIPTION_MINI_APP_URL=None)
    i18n = JsonI18n(path="locales", default="en")
    message = AsyncMock()
    asyncio.run(support_hint(message, settings, {"i18n_instance": i18n, "current_language": "en"}))
    assert "/start" in message.answer.call_args.args[0]
    assert message.answer.call_args.kwargs["reply_markup"] is None
