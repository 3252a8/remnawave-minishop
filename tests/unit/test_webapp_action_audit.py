from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiohttp import web

from bot.app.web.webapp import action_audit


class _SessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _SessionFactory:
    def __call__(self):
        return _SessionContext()


class WebappActionAuditTests(IsolatedAsyncioTestCase):
    async def test_successful_webapp_mutation_is_written_to_user_log(self) -> None:
        request = SimpleNamespace(
            method="POST",
            path="/api/devices/disconnect",
            match_info=SimpleNamespace(
                route=SimpleNamespace(resource=SimpleNamespace(canonical="/api/devices/disconnect"))
            ),
        )
        handler = AsyncMock(return_value=web.json_response({"ok": True}))
        create_log = AsyncMock()

        with (
            patch.object(action_audit, "_extract_authenticated_user_id", return_value=42),
            patch.object(action_audit, "get_session_factory", return_value=_SessionFactory()),
            patch.object(
                action_audit.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=SimpleNamespace(username="alice", first_name="Alice")),
            ),
            patch.object(action_audit.message_log_dal, "create_message_log", create_log),
        ):
            response = await action_audit.webapp_action_audit_middleware(request, handler)

        self.assertEqual(response.status, 200)
        awaited_call = create_log.await_args
        self.assertIsNotNone(awaited_call)
        assert awaited_call is not None
        payload = awaited_call.args[1]
        self.assertEqual(payload["user_id"], 42)
        self.assertEqual(payload["event_type"], "webapp:device_disconnect")
        self.assertEqual(payload["content"], "POST /api/devices/disconnect; status=200")

    async def test_read_only_post_and_failed_mutation_are_not_audited(self) -> None:
        create_log = AsyncMock()
        requests_and_responses = (
            ("/api/subscription/quote", web.json_response({"ok": True})),
            ("/api/devices/disconnect", web.json_response({"ok": False}, status=400)),
        )

        with (
            patch.object(action_audit, "_extract_authenticated_user_id", return_value=42),
            patch.object(action_audit.message_log_dal, "create_message_log", create_log),
        ):
            for path, response in requests_and_responses:
                request = SimpleNamespace(method="POST", path=path, match_info={})
                await action_audit.webapp_action_audit_middleware(
                    request, AsyncMock(return_value=response)
                )

        create_log.assert_not_awaited()
