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


def _settings(**overrides):
    values = {"email_auth_configured": True}
    values.update(overrides)
    return SimpleNamespace(**values)


def _user(email="user@example.test", panel_user_uuid="panel-uuid"):
    return SimpleNamespace(
        user_id=42,
        email=email,
        panel_user_uuid=panel_user_uuid,
        language_code="en",
    )


class AdminUserSubscriptionReissueRouteTests(unittest.IsolatedAsyncioTestCase):
    def _request(self, session: FakeSession, settings=None):
        return SimpleNamespace(
            app={
                "settings": settings if settings is not None else _settings(),
                "async_session_factory": lambda: session,
            },
            match_info={"user_id": "42"},
        )

    def _patch_common(
        self,
        *,
        user,
        panel_service,
        active_subscription=None,
        email_result=True,
    ):
        patches = {
            "require_admin": patch.object(
                users_actions, "_require_admin_user_id", return_value=100
            ),
            "get_user": patch.object(
                admin_users.user_dal, "get_user_by_id", AsyncMock(return_value=user)
            ),
            "get_active": patch.object(
                admin_users.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=active_subscription),
            ),
            "panel_service": patch.object(
                users_actions, "get_panel_service", return_value=panel_service
            ),
            "i18n": patch.object(users_actions, "get_i18n", return_value=None),
            "send_email": patch.object(
                users_actions,
                "send_subscription_reissue_email",
                AsyncMock(return_value=email_result),
            ),
            "log": patch.object(
                admin_users.message_log_dal, "create_message_log_no_commit", AsyncMock()
            ),
            "invalidate": patch.object(
                users_actions, "_invalidate_after_admin_user_mutation", AsyncMock()
            ),
        }
        started = {}
        for name, item in patches.items():
            started[name] = item.start()
            self.addCleanup(item.stop)
        return started

    async def test_reissues_link_and_emails_user(self):
        session = FakeSession()
        panel_service = SimpleNamespace(
            revoke_user_subscription=AsyncMock(
                return_value={"subscriptionUrl": "https://sub.example/new"}
            )
        )
        mocks = self._patch_common(user=_user(), panel_service=panel_service)
        request = self._request(session)

        response = await users_actions.admin_user_subscription_reissue_route(request)

        self.assertEqual(response.status, 200)
        body = json.loads(response.text)
        self.assertTrue(body["ok"])
        self.assertTrue(body["email_sent"])
        panel_service.revoke_user_subscription.assert_awaited_once_with("panel-uuid")
        mocks["send_email"].assert_awaited_once()
        log_payload = mocks["log"].await_args.args[1]
        self.assertEqual(log_payload["event_type"], "admin_subscription_reissue_webapp")
        self.assertEqual(log_payload["target_user_id"], 42)
        mocks["invalidate"].assert_awaited_once()
        self.assertTrue(session.committed)

    async def test_reissue_without_linked_email_skips_email(self):
        session = FakeSession()
        panel_service = SimpleNamespace(
            revoke_user_subscription=AsyncMock(return_value={"subscriptionUrl": "u"})
        )
        mocks = self._patch_common(user=_user(email=""), panel_service=panel_service)
        request = self._request(session)

        response = await users_actions.admin_user_subscription_reissue_route(request)

        self.assertEqual(response.status, 200)
        body = json.loads(response.text)
        self.assertTrue(body["ok"])
        self.assertFalse(body["email_sent"])
        mocks["send_email"].assert_not_awaited()
        self.assertTrue(session.committed)

    async def test_reissue_not_gated_on_email_configuration(self):
        session = FakeSession()
        panel_service = SimpleNamespace(
            revoke_user_subscription=AsyncMock(return_value={"subscriptionUrl": "u"})
        )
        mocks = self._patch_common(user=_user(), panel_service=panel_service)
        request = self._request(session, settings=_settings(email_auth_configured=False))

        response = await users_actions.admin_user_subscription_reissue_route(request)

        self.assertEqual(response.status, 200)
        self.assertFalse(json.loads(response.text)["email_sent"])
        mocks["send_email"].assert_not_awaited()

    async def test_reissue_falls_back_to_active_subscription_uuid(self):
        session = FakeSession()
        panel_service = SimpleNamespace(
            revoke_user_subscription=AsyncMock(return_value={"subscriptionUrl": "u"})
        )
        active = SimpleNamespace(panel_user_uuid="sub-uuid")
        self._patch_common(
            user=_user(panel_user_uuid=None),
            panel_service=panel_service,
            active_subscription=active,
        )
        request = self._request(session)

        response = await users_actions.admin_user_subscription_reissue_route(request)

        self.assertEqual(response.status, 200)
        panel_service.revoke_user_subscription.assert_awaited_once_with("sub-uuid")

    async def test_missing_panel_user_returns_404(self):
        session = FakeSession()
        panel_service = SimpleNamespace(revoke_user_subscription=AsyncMock())
        self._patch_common(user=_user(panel_user_uuid=None), panel_service=panel_service)
        request = self._request(session)

        response = await users_actions.admin_user_subscription_reissue_route(request)

        self.assertEqual(response.status, 404)
        self.assertEqual(json.loads(response.text)["error"], "no_panel_user")
        panel_service.revoke_user_subscription.assert_not_awaited()
        self.assertFalse(session.committed)

    async def test_panel_failure_returns_502(self):
        session = FakeSession()
        panel_service = SimpleNamespace(revoke_user_subscription=AsyncMock(return_value=None))
        mocks = self._patch_common(user=_user(), panel_service=panel_service)
        request = self._request(session)

        response = await users_actions.admin_user_subscription_reissue_route(request)

        self.assertEqual(response.status, 502)
        self.assertEqual(json.loads(response.text)["error"], "subscription_reissue_failed")
        mocks["send_email"].assert_not_awaited()
        self.assertFalse(session.committed)


if __name__ == "__main__":
    unittest.main()
