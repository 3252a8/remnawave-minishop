import json
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.app.web.admin_api_impl import logs as admin_logs_module
from bot.handlers.admin import logs_admin


class _SessionFactory:
    def __init__(self):
        self.session = object()

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _message_log(**overrides):
    values = {
        "log_id": 101,
        "user_id": 42,
        "telegram_username": "alice",
        "telegram_first_name": "Alice",
        "event_type": "command:/start",
        "content": "Bot entry flow opened.",
        "is_admin_event": False,
        "target_user_id": None,
        "timestamp": datetime(2026, 6, 18, 9, 30, tzinfo=UTC),
        "author_user": SimpleNamespace(email="alice@example.test", telegram_id=100500),
        "target_user": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class AdminLogsLoadingTests(unittest.IsolatedAsyncioTestCase):
    async def test_web_admin_logs_route_returns_serialized_rows(self):
        session_factory = _SessionFactory()
        request = SimpleNamespace(
            query={"page": "0", "page_size": "50"},
            app={"async_session_factory": session_factory},
        )
        log_entry = _message_log()

        with (
            patch.object(admin_logs_module, "_require_admin_user_id", return_value=1),
            patch.object(
                admin_logs_module.message_log_dal,
                "get_all_message_logs",
                AsyncMock(return_value=[log_entry]),
            ) as get_all_logs,
            patch.object(
                admin_logs_module.message_log_dal,
                "count_all_message_logs",
                AsyncMock(return_value=1),
            ),
        ):
            response = await admin_logs_module.admin_logs_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["logs"][0]["log_id"], 101)
        self.assertEqual(payload["logs"][0]["user_label"], "Alice")
        self.assertEqual(payload["logs"][0]["email"], "alice@example.test")
        get_all_logs.assert_awaited_once_with(session_factory.session, 50, 0)

    async def test_telegram_admin_logs_handler_uses_message_log_dal(self):
        callback = SimpleNamespace(
            data="admin_logs:view_all:2",
            message=object(),
            answer=AsyncMock(),
        )
        settings = SimpleNamespace(LOGS_PAGE_SIZE=10, DEFAULT_LANGUAGE="ru")
        i18n = SimpleNamespace(gettext=lambda _lang, key, **_kwargs: key)
        log_entry = _message_log(log_id=202)
        session = object()

        with (
            patch.object(
                logs_admin.message_log_dal,
                "get_all_message_logs",
                AsyncMock(return_value=[log_entry]),
            ) as get_all_logs,
            patch.object(
                logs_admin.message_log_dal,
                "count_all_message_logs",
                AsyncMock(return_value=21),
            ) as count_all_logs,
            patch.object(
                logs_admin,
                "_display_formatted_logs",
                AsyncMock(),
            ) as display_logs,
        ):
            await logs_admin.view_all_logs_handler(
                callback,
                settings,
                {"current_language": "ru", "i18n_instance": i18n},
                session,
            )

        get_all_logs.assert_awaited_once_with(session, 10, 20)
        count_all_logs.assert_awaited_once_with(session)
        display_logs.assert_awaited_once()
        self.assertEqual(display_logs.await_args.kwargs["logs"], [log_entry])
        self.assertEqual(display_logs.await_args.kwargs["total_logs"], 21)
        self.assertEqual(display_logs.await_args.kwargs["current_page_idx"], 2)
        callback.answer.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
