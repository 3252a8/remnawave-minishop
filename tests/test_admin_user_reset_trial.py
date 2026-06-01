import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.app.web.admin_api_impl import users as admin_users


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


class AdminUserResetTrialRouteTests(unittest.IsolatedAsyncioTestCase):
    def _request(self, session: FakeSession):
        return SimpleNamespace(
            app={
                "settings": SimpleNamespace(),
                "async_session_factory": lambda: session,
            },
            match_info={"user_id": "42"},
        )

    async def test_marks_trial_reset_without_deleting_subscription_history(self):
        session = FakeSession()
        request = self._request(session)
        user = SimpleNamespace(user_id=42)

        with (
            patch.object(admin_users, "_require_admin_user_id", return_value=100),
            patch.object(admin_users.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                admin_users.user_dal,
                "mark_trial_eligibility_reset",
                AsyncMock(return_value=object()),
            ) as mark_reset,
            patch.object(
                admin_users.subscription_dal,
                "delete_all_user_subscriptions",
                AsyncMock(),
            ) as delete_all,
            patch.object(
                admin_users.message_log_dal, "create_message_log_no_commit", AsyncMock()
            ) as log,
            patch.object(
                admin_users, "_invalidate_after_admin_user_mutation", AsyncMock()
            ) as invalidate,
        ):
            response = await admin_users.admin_user_reset_trial_route(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.text)["ok"], True)
        mark_reset.assert_awaited_once_with(session, 42)
        delete_all.assert_not_awaited()
        log_payload = log.await_args.args[1]
        self.assertEqual(log_payload["event_type"], "admin_reset_trial_webapp")
        self.assertEqual(log_payload["target_user_id"], 42)
        invalidate.assert_awaited_once()
        self.assertTrue(session.committed)
        self.assertFalse(session.rolled_back)


if __name__ == "__main__":
    unittest.main()
