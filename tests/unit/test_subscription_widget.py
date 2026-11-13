import asyncio
import zlib
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot, types
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.exceptions import TelegramNotFound

from bot.handlers.user.subscription_widget import SendSubscriptionWidget, router
from bot.middlewares.i18n import JsonI18n
from config.settings import Settings


@pytest.mark.parametrize(
    ("chat_type", "enabled", "has_subscription", "api_supports_widgets"),
    [
        ("private", True, True, True),
        ("private", True, False, False),
        ("private", False, True, True),
        ("group", True, True, True),
    ],
)
def test_subscription_widget_command(chat_type, enabled, has_subscription, api_supports_widgets):
    bot = AsyncMock(spec=Bot)
    bot.me.return_value = SimpleNamespace(username="example_bot")
    if not api_supports_widgets:
        bot.side_effect = _reject_widget
    settings = Settings.model_construct(TELEGRAM_SUBSCRIPTION_WIDGET_ENABLED=enabled)
    end_date = datetime(2027, 1, 15, tzinfo=UTC)
    message = types.Message(
        message_id=1,
        date=end_date,
        chat=types.Chat(id=42, type=chat_type),
        from_user=types.User(id=42, is_bot=False, first_name="User"),
        text="/widget",
    )
    subscription_service = SimpleNamespace(
        get_active_subscription_details=AsyncMock(
            return_value=(
                {
                    "status_from_panel": "ACTIVE",
                    "end_date": end_date,
                    "traffic_used_bytes": 2**30,
                    "traffic_limit_bytes": 2 * 2**30,
                    "config_link": "https://example.com/private-subscription-token",
                }
                if has_subscription
                else None
            )
        )
    )
    session = AsyncMock()
    with (
        patch(
            "bot.handlers.user.subscription_widget.user_dal.get_user_by_telegram_id",
            AsyncMock(return_value=SimpleNamespace(user_id=51)),
        ) as get_user,
        patch.object(types.Message, "answer", new_callable=AsyncMock) as answer,
    ):
        result = asyncio.run(
            router.propagate_event(
                "message",
                message,
                bot=bot,
                settings=settings,
                i18n_data={
                    "i18n_instance": JsonI18n("locales", default="en"),
                    "current_language": "en",
                },
                subscription_service=subscription_service,
                session=session,
            )
        )

    if chat_type != "private" or not enabled:
        if chat_type != "private":
            assert result is UNHANDLED
        get_user.assert_not_awaited()
        bot.assert_not_awaited()
        answer.assert_not_awaited()
        return

    get_user.assert_awaited_once_with(session, 42)
    subscription_service.get_active_subscription_details.assert_awaited_once_with(session, 51)
    bot.assert_awaited_once()
    method = bot.await_args.args[0]
    assert isinstance(method, SendSubscriptionWidget)
    assert method.__api_method__ == "sendWidget"
    assert method.chat_id == 42
    assert len(zlib.compress(method.html.encode(), level=9)) <= 4096
    assert "private-subscription-token" not in method.html
    assert method.reply_markup.inline_keyboard[0][0].callback_data == (
        "main_action:back_to_main_keep"
    )
    assert 'href="https://t.me/example_bot?start=widget_renew"' in method.html
    if has_subscription:
        assert 'href="https://t.me/example_bot?start=widget_connect"' in method.html
        assert "2027-01-15" in method.caption
        assert "1.00 GiB of 2.00 GiB" in method.caption
        answer.assert_not_awaited()
    else:
        assert "No active subscription" in method.caption
        assert "widget_connect" not in method.html
        answer.assert_awaited_once_with(
            method.caption, parse_mode=None, reply_markup=method.reply_markup
        )


def _reject_widget(method: SendSubscriptionWidget) -> None:
    raise TelegramNotFound(method=method, message="Not Found")
