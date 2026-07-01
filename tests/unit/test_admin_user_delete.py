import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.app.web.admin_api_impl import users as admin_users
from bot.app.web.admin_api_impl import users_actions


class FakeSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class AdminUserDeleteRouteTests(unittest.IsolatedAsyncioTestCase):
    def _request(self, session: FakeSession, app_overrides=None):
        app = {
            "settings": SimpleNamespace(),
            "async_session_factory": lambda: session,
        }
        app.update(app_overrides or {})
        return SimpleNamespace(
            app=app,
            match_info={"user_id": "42"},
        )

    async def test_deletes_panel_users_before_bot_db_user(self):
        session = FakeSession()
        calls = []

        async def delete_panel_user(panel_uuid, log_response=False):
            calls.append(("panel", panel_uuid, log_response))
            return True

        async def delete_db_user(_session, user_id):
            calls.append(("db", user_id))
            return True

        panel_service = SimpleNamespace(
            delete_user_from_panel=AsyncMock(side_effect=delete_panel_user),
        )
        request = self._request(session, {"panel_service": panel_service})
        user = SimpleNamespace(user_id=42, panel_user_uuid="panel-main")

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=100),
            patch.object(admin_users.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                admin_users.user_dal,
                "get_panel_user_uuids_for_user",
                AsyncMock(return_value=["panel-main", "panel-sub"]),
            ) as collect_uuids,
            patch.object(
                admin_users.user_dal,
                "delete_user_and_relations",
                AsyncMock(side_effect=delete_db_user),
            ),
            patch.object(
                admin_users.message_log_dal,
                "create_message_log_no_commit",
                AsyncMock(),
            ) as log_mock,
            patch.object(users_actions, "_invalidate_after_admin_user_mutation", AsyncMock()),
        ):
            response = await admin_users.admin_user_delete_route(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.text)["ok"], True)
        self.assertEqual(
            calls,
            [
                ("panel", "panel-main", False),
                ("panel", "panel-sub", False),
                ("db", 42),
            ],
        )
        collect_uuids.assert_awaited_once_with(session, 42, user=user)
        log_payload = log_mock.await_args.args[1]
        self.assertEqual(log_payload["event_type"], "admin_delete_user_webapp")
        self.assertIn("panel-main,panel-sub", log_payload["content"])
        self.assertTrue(session.committed)
        self.assertFalse(session.rolled_back)

    async def test_returns_success_when_post_commit_invalidation_fails(self):
        session = FakeSession()
        request = self._request(session)
        user = SimpleNamespace(user_id=42, panel_user_uuid=None)

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=100),
            patch.object(admin_users.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                admin_users.user_dal,
                "get_panel_user_uuids_for_user",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                admin_users.user_dal,
                "delete_user_and_relations",
                AsyncMock(return_value=True),
            ),
            patch.object(
                admin_users.message_log_dal,
                "create_message_log_no_commit",
                AsyncMock(),
            ),
            patch.object(
                users_actions,
                "_invalidate_after_admin_user_mutation",
                AsyncMock(side_effect=RuntimeError("redis unavailable")),
            ),
        ):
            response = await admin_users.admin_user_delete_route(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.text)["ok"], True)
        self.assertTrue(session.committed)
        self.assertFalse(session.rolled_back)

    async def test_aborts_when_panel_service_is_unavailable_for_panel_user(self):
        session = FakeSession()
        request = self._request(session)
        user = SimpleNamespace(user_id=42, panel_user_uuid="panel-main")

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=100),
            patch.object(admin_users.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                admin_users.user_dal,
                "get_panel_user_uuids_for_user",
                AsyncMock(return_value=["panel-main"]),
            ),
            patch.object(
                admin_users.user_dal,
                "delete_user_and_relations",
                AsyncMock(),
            ) as delete_db,
        ):
            response = await admin_users.admin_user_delete_route(request)

        self.assertEqual(response.status, 503)
        self.assertEqual(json.loads(response.text)["error"], "panel_service_unavailable")
        delete_db.assert_not_awaited()
        self.assertTrue(session.rolled_back)
        self.assertFalse(session.committed)

    async def test_aborts_when_panel_delete_fails(self):
        session = FakeSession()
        panel_service = SimpleNamespace(
            delete_user_from_panel=AsyncMock(return_value=False),
        )
        request = self._request(session, {"panel_service": panel_service})
        user = SimpleNamespace(user_id=42, panel_user_uuid="panel-main")

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=100),
            patch.object(admin_users.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                admin_users.user_dal,
                "get_panel_user_uuids_for_user",
                AsyncMock(return_value=["panel-main"]),
            ),
            patch.object(
                admin_users.user_dal,
                "delete_user_and_relations",
                AsyncMock(),
            ) as delete_db,
        ):
            response = await admin_users.admin_user_delete_route(request)

        self.assertEqual(response.status, 502)
        self.assertEqual(json.loads(response.text)["error"], "panel_delete_failed")
        panel_service.delete_user_from_panel.assert_awaited_once_with(
            "panel-main",
            log_response=False,
        )
        delete_db.assert_not_awaited()
        self.assertTrue(session.rolled_back)
        self.assertFalse(session.committed)
