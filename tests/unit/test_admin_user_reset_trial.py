import json
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.app.web.admin_api_impl import common as admin_common
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


class AdminUserResetTrialRouteTests(unittest.IsolatedAsyncioTestCase):
    def _request(self, session: FakeSession):
        return SimpleNamespace(
            app={
                "settings": SimpleNamespace(),
                "async_session_factory": lambda: session,
            },
            match_info={"user_id": "42"},
        )

    async def test_expires_active_trial_without_deleting_subscription_history(self):
        session = FakeSession()
        request = self._request(session)
        user = SimpleNamespace(user_id=42)
        reset_at = datetime(2026, 9, 17, 10, 11, 12, tzinfo=UTC)
        active = SimpleNamespace(
            panel_user_uuid="panel-user",
            provider="trial",
            end_date=datetime(2026, 9, 24, tzinfo=UTC),
            is_active=True,
            status_from_panel="TRIAL",
            skip_notifications=False,
            auto_renew_enabled=True,
        )
        panel_service = SimpleNamespace(
            update_user_details_on_panel=AsyncMock(return_value={"uuid": "panel-user"})
        )
        request.app["panel_service"] = panel_service

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=100),
            patch.object(admin_users.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                admin_users.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=active),
            ),
            patch.object(
                admin_users.user_dal,
                "mark_trial_eligibility_reset",
                AsyncMock(return_value=reset_at),
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
                users_actions, "_invalidate_after_admin_user_mutation", AsyncMock()
            ) as invalidate,
        ):
            response = await admin_users.admin_user_reset_trial_route(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.text)["ok"], True)
        mark_reset.assert_awaited_once_with(session, 42)
        delete_all.assert_not_awaited()
        panel_service.update_user_details_on_panel.assert_awaited_once_with(
            "panel-user",
            {"uuid": "panel-user", "expireAt": "2026-09-17T10:11:12.000Z"},
        )
        self.assertEqual(active.end_date, reset_at)
        self.assertFalse(active.is_active)
        self.assertEqual(active.status_from_panel, "EXPIRED_TRIAL_RESET")
        self.assertTrue(active.skip_notifications)
        self.assertFalse(active.auto_renew_enabled)
        log_payload = log.await_args.args[1]
        self.assertEqual(log_payload["event_type"], "admin_reset_trial_webapp")
        self.assertEqual(log_payload["target_user_id"], 42)
        invalidate.assert_awaited_once()
        self.assertTrue(session.committed)
        self.assertFalse(session.rolled_back)

    async def test_keeps_active_paid_subscription_unchanged(self):
        session = FakeSession()
        request = self._request(session)
        user = SimpleNamespace(user_id=42)
        paid_end = datetime(2026, 10, 17, tzinfo=UTC)
        active = SimpleNamespace(
            panel_user_uuid="panel-user",
            provider="yookassa",
            end_date=paid_end,
            is_active=True,
            status_from_panel="ACTIVE",
        )

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=100),
            patch.object(admin_users.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                admin_users.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=active),
            ),
            patch.object(
                admin_users.user_dal,
                "mark_trial_eligibility_reset",
                AsyncMock(return_value=datetime(2026, 9, 17, tzinfo=UTC)),
            ),
            patch.object(admin_users.message_log_dal, "create_message_log_no_commit", AsyncMock()),
            patch.object(users_actions, "_invalidate_after_admin_user_mutation", AsyncMock()),
        ):
            response = await admin_users.admin_user_reset_trial_route(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(active.end_date, paid_end)
        self.assertTrue(active.is_active)
        self.assertEqual(active.status_from_panel, "ACTIVE")


class AdminUserTrialPresentationTests(unittest.TestCase):
    def test_trial_subscription_serializes_display_label(self):
        start_at = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
        end_at = datetime(2026, 1, 9, 3, 4, tzinfo=UTC)
        sub = SimpleNamespace(
            subscription_id=7,
            panel_user_uuid="panel-user",
            panel_subscription_uuid=None,
            start_date=start_at,
            end_date=end_at,
            duration_months=None,
            is_active=False,
            status_from_panel="EXPIRED",
            traffic_limit_bytes=10,
            traffic_used_bytes=2,
            tier_baseline_bytes=0,
            topup_balance_bytes=0,
            premium_used_bytes=0,
            premium_baseline_bytes=0,
            premium_topup_balance_bytes=0,
            premium_topup_used_bytes=0,
            premium_bonus_bytes=0,
            regular_bonus_bytes=0,
            regular_unlimited_override=False,
            premium_unlimited_override=False,
            premium_is_limited=False,
            tariff_key=None,
            auto_renew_enabled=False,
            provider="trial",
            is_throttled=False,
        )

        payload = admin_common._serialize_subscription(sub)

        self.assertTrue(payload["is_trial"])
        self.assertEqual(payload["display_label"], "Trial")
        self.assertIsNone(payload["tariff_key"])

    def test_trial_summary_includes_usage_dates_and_reset_marker(self):
        first_at = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
        latest_at = datetime(2026, 2, 3, 4, 5, tzinfo=UTC)
        latest_end = datetime(2026, 2, 10, 4, 5, tzinfo=UTC)
        reset_at = datetime(2026, 3, 1, tzinfo=UTC)
        user = SimpleNamespace(trial_eligibility_reset_at=reset_at)
        trial_subs = [
            SimpleNamespace(
                start_date=first_at,
                end_date=datetime(2026, 1, 9, tzinfo=UTC),
            ),
            SimpleNamespace(start_date=latest_at, end_date=latest_end, is_active=True),
        ]

        payload = admin_users._serialize_trial_summary(user, trial_subs)

        self.assertTrue(payload["used"])
        self.assertTrue(payload["active"])
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["first_activated_at"], first_at.isoformat())
        self.assertEqual(payload["latest_activated_at"], latest_at.isoformat())
        self.assertEqual(payload["latest_end_date"], latest_end.isoformat())
        self.assertEqual(payload["last_reset_at"], reset_at.isoformat())


if __name__ == "__main__":
    unittest.main()
