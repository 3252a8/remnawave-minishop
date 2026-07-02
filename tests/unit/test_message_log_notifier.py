import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.services.message_log_notifier import (
    format_message_log_notification,
    notify_message_log,
)


def _settings(**overrides):
    values = {
        "LOG_LEVEL": "DEBUG",
        "LOG_CHAT_ID": -100123,
        "LOG_THREAD_ID": 77,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_format_message_log_notification_omits_raw_update_preview():
    message = format_message_log_notification(
        {
            "user_id": 42,
            "telegram_username": "alice",
            "telegram_first_name": "Alice",
            "event_type": "callback:buy",
            "content": "buy:monthly",
            "raw_update_preview": "SECRET RAW PAYLOAD",
            "timestamp": datetime(2026, 5, 31, tzinfo=UTC),
        }
    )

    assert "callback:buy" in message
    assert "@alice" in message
    assert "buy:monthly" in message
    assert "SECRET RAW PAYLOAD" not in message


def test_notify_message_log_sends_debug_logs_to_queue():
    queue_manager = SimpleNamespace(send_message=AsyncMock())

    with patch(
        "bot.services.message_log_notifier.get_queue_manager",
        return_value=queue_manager,
    ):
        asyncio.run(
            notify_message_log(
                {
                    "user_id": 42,
                    "event_type": "command:/start",
                    "content": "/start",
                },
                settings=_settings(),
            )
        )

    queue_manager.send_message.assert_awaited_once()
    chat_id = queue_manager.send_message.await_args.args[0]
    kwargs = queue_manager.send_message.await_args.kwargs
    assert chat_id == -100123
    assert kwargs["parse_mode"] == "HTML"
    assert kwargs["message_thread_id"] == 77


def test_notify_message_log_ignores_non_debug_level():
    queue_manager = SimpleNamespace(send_message=AsyncMock())

    with patch(
        "bot.services.message_log_notifier.get_queue_manager",
        return_value=queue_manager,
    ):
        asyncio.run(
            notify_message_log(
                {
                    "user_id": 42,
                    "event_type": "command:/start",
                    "content": "/start",
                },
                settings=_settings(LOG_LEVEL="INFO"),
            )
        )

    queue_manager.send_message.assert_not_awaited()
