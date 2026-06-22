import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.middlewares.action_logger_middleware import ActionLoggerMiddleware


class ActionLoggerMiddlewareTests(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
