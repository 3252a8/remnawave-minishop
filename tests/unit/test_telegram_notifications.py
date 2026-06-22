import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.services import telegram_notifications as module
from bot.services.telegram_notifications import (
    TELEGRAM_NOTIFICATIONS_ENABLED,
    telegram_notifications_need_prompt,
)


def _user(status: str):
    return SimpleNamespace(telegram_id=123, telegram_notifications_status=status)


def test_telegram_notifications_prompt_only_for_explicit_unreachable_statuses():
    assert telegram_notifications_need_prompt(_user("needs_start")) is True
    assert telegram_notifications_need_prompt(_user("blocked")) is True
    assert telegram_notifications_need_prompt(_user("enabled")) is False
    assert telegram_notifications_need_prompt(_user("unknown")) is False


def test_telegram_notifications_prompt_requires_linked_telegram():
    user = SimpleNamespace(
        email="user@example.test",
        telegram_id=None,
        telegram_notifications_status="needs_start",
    )

    assert telegram_notifications_need_prompt(user) is False


def test_probe_telegram_notifications_uses_silent_chat_check(monkeypatch):
    user = SimpleNamespace(
        user_id=42,
        telegram_id=123,
        telegram_notifications_status="unknown",
    )
    bot = SimpleNamespace(
        get_chat=AsyncMock(return_value=SimpleNamespace(id=123)),
        send_message=AsyncMock(),
    )
    recorded = []

    async def fake_mark_status(session, user_id, status, *, telegram_id=None, checked_at=None):
        recorded.append((session, user_id, status, telegram_id, checked_at))
        return user

    monkeypatch.setattr(module, "mark_telegram_notifications_status", fake_mark_status)

    result = asyncio.run(
        module.probe_telegram_notifications(
            session="session",
            bot=bot,
            settings=SimpleNamespace(DEFAULT_LANGUAGE="ru"),
            i18n=None,
            user=user,
            bot_username="preview_bot",
        )
    )

    bot.get_chat.assert_awaited_once_with(123)
    bot.send_message.assert_not_called()
    assert result["ok"] is True
    assert result["status"] == TELEGRAM_NOTIFICATIONS_ENABLED
    assert recorded == [("session", 42, TELEGRAM_NOTIFICATIONS_ENABLED, 123, None)]
