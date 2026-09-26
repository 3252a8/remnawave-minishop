import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

from bot.app.web.admin_api_impl import users_ban
from bot.app.web.admin_api_impl.schemas import AdminUserBanBody
from db.models import User


class FakeSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.refreshed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def refresh(self, user):
        self.refreshed = True


class AdminUserBanRouteTests(unittest.IsolatedAsyncioTestCase):
    def _setup_route(self, *, banned, user, panel_uuids, panel_service=None, fallback=False):
        session = FakeSession()
        settings = SimpleNamespace()
        app = {"settings": settings, "async_session_factory": lambda: session}
        if fallback:
            app["subscription_service"] = SimpleNamespace(panel_service=panel_service)
        else:
            app["panel_service"] = panel_service
        request = SimpleNamespace(app=app, match_info={"user_id": "42"})
        patches = {
            "auth": patch.object(users_ban, "_require_admin_user_id", return_value=100),
            "body": patch.object(
                users_ban,
                "parse_body_or_400",
                AsyncMock(return_value=AdminUserBanBody(banned=banned)),
            ),
            "user": patch.object(
                users_ban.user_dal, "get_user_by_id", AsyncMock(return_value=user)
            ),
            "uuids": patch.object(
                users_ban.user_dal,
                "get_panel_user_uuids_for_user",
                AsyncMock(return_value=panel_uuids),
            ),
            "invalidate": patch.object(
                users_ban, "_invalidate_after_admin_user_mutation", AsyncMock()
            ),
        }
        mocks = {}
        for name, item in patches.items():
            mocks[name] = item.start()
            self.addCleanup(item.stop)
        return request, session, settings, mocks

    async def test_syncs_ban_unban_and_repeated_ban_before_commit(self):
        for initial, desired in ((False, True), (True, False), (True, True), (False, False)):
            with self.subTest(initial=initial, desired=desired):
                user = User(user_id=42, is_banned=initial, panel_user_uuid="panel-main")

                update = AsyncMock()
                request, session, settings, mocks = self._setup_route(
                    banned=desired,
                    user=user,
                    panel_uuids=["panel-main", "123"],
                    panel_service=SimpleNamespace(update_user_status_on_panel=update),
                )

                async def update_status(
                    panel_uuid, enable, *, session=session, user=user, initial=initial
                ):
                    self.assertFalse(session.committed)
                    self.assertEqual(user.is_banned, initial)
                    return True

                update.side_effect = update_status

                response = await users_ban.admin_user_ban_route(request)

                self.assertEqual(response.status, 200)
                payload = json.loads(response.text)
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["user"]["is_banned"], desired)
                self.assertEqual(
                    update.await_args_list,
                    [call("panel-main", not desired), call("123", not desired)],
                )
                mocks["uuids"].assert_awaited_once_with(session, 42, user=user)
                mocks["invalidate"].assert_awaited_once_with(settings, 42)
                self.assertTrue(session.committed)
                self.assertTrue(session.refreshed)
                self.assertFalse(session.rolled_back)

    async def test_uses_subscription_service_panel_for_subscription_only_reference(self):
        update = AsyncMock(return_value=True)
        user = User(user_id=42, is_banned=False, panel_user_uuid=None)
        request, session, _, _ = self._setup_route(
            banned=True,
            user=user,
            panel_uuids=["panel-sub"],
            panel_service=SimpleNamespace(update_user_status_on_panel=update),
            fallback=True,
        )

        response = await users_ban.admin_user_ban_route(request)

        self.assertEqual(response.status, 200)
        update.assert_awaited_once_with("panel-sub", False)
        self.assertTrue(user.is_banned)
        self.assertTrue(session.committed)

    async def test_updates_local_only_user_without_panel_service(self):
        for desired in (True, False):
            with self.subTest(banned=desired):
                user = User(user_id=42, is_banned=not desired, panel_user_uuid=None)
                request, session, _, mocks = self._setup_route(
                    banned=desired, user=user, panel_uuids=[]
                )

                response = await users_ban.admin_user_ban_route(request)

                self.assertEqual(response.status, 200)
                self.assertEqual(user.is_banned, desired)
                self.assertTrue(session.committed)
                mocks["invalidate"].assert_awaited_once()

    async def test_missing_panel_service_preserves_local_status(self):
        for desired in (True, False):
            with self.subTest(banned=desired):
                user = User(user_id=42, is_banned=not desired)
                request, session, _, mocks = self._setup_route(
                    banned=desired, user=user, panel_uuids=["panel-main"]
                )

                response = await users_ban.admin_user_ban_route(request)

                self.assertEqual(response.status, 503)
                self.assertEqual(json.loads(response.text)["error"], "panel_service_unavailable")
                self.assertEqual(user.is_banned, not desired)
                self.assertTrue(session.rolled_back)
                self.assertFalse(session.committed)
                self.assertFalse(session.refreshed)
                mocks["invalidate"].assert_not_awaited()

    async def test_panel_failure_preserves_local_status_and_stops_updates(self):
        for desired in (True, False):
            for failure in (False, RuntimeError("panel unavailable")):
                with self.subTest(banned=desired, failure=failure):
                    user = User(user_id=42, is_banned=not desired)
                    update = AsyncMock(side_effect=[True, failure, True])
                    request, session, _, mocks = self._setup_route(
                        banned=desired,
                        user=user,
                        panel_uuids=["panel-main", "panel-sub", "panel-other"],
                        panel_service=SimpleNamespace(update_user_status_on_panel=update),
                    )

                    response = await users_ban.admin_user_ban_route(request)

                    self.assertEqual(response.status, 502)
                    self.assertFalse(json.loads(response.text)["ok"])
                    self.assertEqual(
                        json.loads(response.text)["error"], "panel_status_update_failed"
                    )
                    self.assertEqual(update.await_count, 2)
                    self.assertEqual(user.is_banned, not desired)
                    self.assertTrue(session.rolled_back)
                    self.assertFalse(session.committed)
                    self.assertFalse(session.refreshed)
                    mocks["invalidate"].assert_not_awaited()

    async def test_missing_user_does_not_mutate_panel_or_database(self):
        update = AsyncMock(return_value=True)
        request, session, _, mocks = self._setup_route(
            banned=True,
            user=None,
            panel_uuids=["panel-main"],
            panel_service=SimpleNamespace(update_user_status_on_panel=update),
        )

        response = await users_ban.admin_user_ban_route(request)

        self.assertEqual(response.status, 404)
        self.assertEqual(json.loads(response.text)["error"], "not_found")
        self.assertFalse(session.committed)
        mocks["uuids"].assert_not_awaited()
        mocks["invalidate"].assert_not_awaited()
        update.assert_not_awaited()
