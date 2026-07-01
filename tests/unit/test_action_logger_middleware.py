import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.middlewares.action_logger_middleware import ActionLoggerMiddleware


class ActionLoggerMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    def _message_update(self, *, chat_id: int = 42, text: str = "/start"):
        return SimpleNamespace(
            event_type="message",
            message=SimpleNamespace(
                text=text,
                content_type="text",
                chat=SimpleNamespace(id=chat_id),
            ),
            callback_query=None,
            model_dump_json=lambda **_kwargs: '{"message":{}}',
        )

    async def test_skip_action_log_flag_suppresses_database_logging(self):
        middleware = ActionLoggerMiddleware(SimpleNamespace(ADMIN_IDS=[], LOG_ADMIN_ACTIONS=True))
        event = SimpleNamespace(event_type="message")
        data = {
            "session": object(),
            "event_from_user": SimpleNamespace(id=42, username="user", first_name="User"),
        }

        async def handler(_event, handler_data):
            handler_data["skip_action_log"] = True
            return "ok"

        with (
            patch(
                "bot.middlewares.action_logger_middleware.user_dal.get_user_by_id",
                AsyncMock(),
            ) as get_user,
            patch(
                "bot.middlewares.action_logger_middleware.message_log_dal.create_message_log_no_commit",
                AsyncMock(),
            ) as create_log,
        ):
            result = await middleware(handler, event, data)

        self.assertEqual(result, "ok")
        get_user.assert_not_awaited()
        create_log.assert_not_awaited()

    async def test_debug_log_level_sends_action_log_to_log_chat(self):
        settings = SimpleNamespace(
            ADMIN_IDS=[],
            LOG_ADMIN_ACTIONS=True,
            LOG_LEVEL="DEBUG",
            LOG_CHAT_ID=-100123,
            LOG_THREAD_ID=None,
        )
        middleware = ActionLoggerMiddleware(settings)
        event = self._message_update(text="/start ref")
        data = {
            "session": object(),
            "event_from_user": SimpleNamespace(id=42, username="user", first_name="User"),
        }

        async def handler(_event, _handler_data):
            return "ok"

        with (
            patch(
                "bot.middlewares.action_logger_middleware.user_dal.get_user_by_id",
                AsyncMock(return_value=object()),
            ),
            patch(
                "bot.middlewares.action_logger_middleware.message_log_dal.create_message_log_no_commit",
                AsyncMock(),
            ) as create_log,
            patch(
                "bot.middlewares.action_logger_middleware.notify_message_log",
                AsyncMock(),
            ) as notify_log,
        ):
            result = await middleware(handler, event, data)

        self.assertEqual(result, "ok")
        payload = create_log.await_args.args[1]
        self.assertEqual(payload["event_type"], "command:/start")
        notify_log.assert_awaited_once_with(payload, settings=settings, bot=None)

    async def test_debug_log_chat_source_is_not_echoed_back_to_log_chat(self):
        settings = SimpleNamespace(
            ADMIN_IDS=[],
            LOG_ADMIN_ACTIONS=True,
            LOG_LEVEL="DEBUG",
            LOG_CHAT_ID=-100123,
            LOG_THREAD_ID=None,
        )
        middleware = ActionLoggerMiddleware(settings)
        event = self._message_update(chat_id=-100123, text="operator note")
        data = {
            "session": object(),
            "event_from_user": SimpleNamespace(id=42, username="user", first_name="User"),
        }

        async def handler(_event, _handler_data):
            return "ok"

        with (
            patch(
                "bot.middlewares.action_logger_middleware.user_dal.get_user_by_id",
                AsyncMock(return_value=object()),
            ),
            patch(
                "bot.middlewares.action_logger_middleware.message_log_dal.create_message_log_no_commit",
                AsyncMock(),
            ) as create_log,
            patch(
                "bot.middlewares.action_logger_middleware.notify_message_log",
                AsyncMock(),
            ) as notify_log,
        ):
            result = await middleware(handler, event, data)

        self.assertEqual(result, "ok")
        create_log.assert_awaited_once()
        notify_log.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
