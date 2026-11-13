import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import web

from bot.app.web.admin_api_impl import users_devices


class AdminUserHwidDevicesResetTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session = AsyncMock()
        self.session.__aenter__.return_value = self.session
        self.settings = SimpleNamespace()
        self.panel = SimpleNamespace(reset_user_hwid_devices=AsyncMock(return_value=True))
        self.user = SimpleNamespace(panel_user_uuid="panel-user")
        self.active = SimpleNamespace(
            panel_user_uuid="active-user",
            hwid_device_limit=3,
            extra_hwid_devices=2,
            subscription_url="https://example.test/unchanged",
        )
        self.request = SimpleNamespace(
            app={
                "settings": self.settings,
                "async_session_factory": lambda: self.session,
                "panel_service": self.panel,
            },
            match_info={"user_id": "42"},
        )
        self.auth = self._patch(users_devices, "_require_admin_user_id", return_value=100)
        self.get_user = self._patch(
            users_devices.user_dal, "get_user_by_id", new=AsyncMock(return_value=self.user)
        )
        self.get_active = self._patch(
            users_devices.subscription_dal,
            "get_active_subscription_by_user_id",
            new=AsyncMock(return_value=self.active),
        )
        self.audit = self._patch(
            users_devices.message_log_dal, "create_message_log_no_commit", new=AsyncMock()
        )
        self.invalidate = self._patch(
            users_devices, "_invalidate_after_admin_user_mutation", new=AsyncMock()
        )

    def _patch(self, target, name, **kwargs):
        patcher = patch.object(target, name, **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    async def test_resets_devices_for_canonical_user_and_audits_actor(self):
        original_subscription = vars(self.active).copy()
        response = await users_devices.admin_user_hwid_devices_reset_route(self.request)
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.text), {"ok": True})
        self.panel.reset_user_hwid_devices.assert_awaited_once_with("panel-user")
        self.assertEqual(vars(self.active), original_subscription)
        self.session.commit.assert_awaited_once()
        self.invalidate.assert_awaited_once_with(self.settings, 42)
        payload = self.audit.await_args.args[1]
        self.assertEqual(payload["user_id"], 100)
        self.assertEqual(payload["target_user_id"], 42)
        self.assertEqual(payload["event_type"], "admin_hwid_devices_reset_webapp")

    async def test_resets_devices_without_active_subscription(self):
        self.get_active.return_value = None
        response = await users_devices.admin_user_hwid_devices_reset_route(self.request)
        self.assertEqual(response.status, 200)
        self.panel.reset_user_hwid_devices.assert_awaited_once_with("panel-user")

    async def test_falls_back_to_active_subscription_panel_user(self):
        self.user.panel_user_uuid = None
        response = await users_devices.admin_user_hwid_devices_reset_route(self.request)
        self.assertEqual(response.status, 200)
        self.panel.reset_user_hwid_devices.assert_awaited_once_with("active-user")

    async def test_falls_back_to_subscription_service_panel(self):
        self.request.app.pop("panel_service")
        self.request.app["subscription_service"] = SimpleNamespace(panel_service=self.panel)
        response = await users_devices.admin_user_hwid_devices_reset_route(self.request)
        self.assertEqual(response.status, 200)
        self.panel.reset_user_hwid_devices.assert_awaited_once_with("panel-user")

    async def test_missing_user_or_panel_link_does_not_mutate(self):
        for user in (None, SimpleNamespace(panel_user_uuid=None)):
            with self.subTest(user=user):
                self.get_user.return_value = user
                self.get_active.return_value = None
                response = await users_devices.admin_user_hwid_devices_reset_route(self.request)
                self.assertEqual(response.status, 404)
        self.panel.reset_user_hwid_devices.assert_not_awaited()
        self.audit.assert_not_awaited()

    async def test_missing_panel_service(self):
        self.request.app.pop("panel_service")
        response = await users_devices.admin_user_hwid_devices_reset_route(self.request)
        self.assertEqual(response.status, 503)
        self.get_user.assert_not_awaited()

    async def test_panel_failures_invalidate_partial_changes_without_success_audit(self):
        for raises in (False, True):
            with self.subTest(raises=raises):
                self.panel.reset_user_hwid_devices.return_value = False
                self.panel.reset_user_hwid_devices.side_effect = RuntimeError() if raises else None
                response = await users_devices.admin_user_hwid_devices_reset_route(self.request)
                self.assertEqual(response.status, 502)
                self.assertEqual(json.loads(response.text)["error"], "panel_hwid_reset_failed")
        self.assertEqual(self.invalidate.await_count, 2)
        self.audit.assert_not_awaited()
        self.session.commit.assert_not_awaited()

    async def test_rejects_unauthenticated_and_non_admin_before_mutating(self):
        for exception in (web.HTTPUnauthorized, web.HTTPForbidden):
            with self.subTest(exception=exception):
                self.auth.side_effect = exception
                with self.assertRaises(exception):
                    await users_devices.admin_user_hwid_devices_reset_route(self.request)
        self.get_user.assert_not_awaited()
        self.panel.reset_user_hwid_devices.assert_not_awaited()
