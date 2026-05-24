import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.app.web import subscription_webapp  # noqa: F401
from bot.app.web.webapp import account as account_routes
from bot.app.web.webapp.auth import (
    _link_telegram_to_user,
    _panel_description_for_user,
    _sync_merged_panel_identity_for_user,
    _sync_panel_identity_for_user,
)


class AccountLinkingPanelTests(unittest.IsolatedAsyncioTestCase):
    class _AsyncSessionFactory:
        def __init__(self):
            self.session = SimpleNamespace(
                commit=AsyncMock(),
                rollback=AsyncMock(),
                flush=AsyncMock(),
            )

        def __call__(self):
            return self

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def test_panel_identity_sync_reports_failed_update_response(self):
        user = SimpleNamespace(
            user_id=42,
            panel_user_uuid="panel-42",
            email="linked@example.com",
            telegram_id=42,
            username="alice",
            first_name=None,
            last_name=None,
        )
        panel_service = SimpleNamespace(update_user_details_on_panel=AsyncMock(return_value=None))
        request = SimpleNamespace(
            app={"subscription_service": SimpleNamespace(panel_service=panel_service)}
        )

        result = await _sync_panel_identity_for_user(request, user)

        self.assertFalse(result)
        panel_service.update_user_details_on_panel.assert_awaited_once()

    async def test_panel_identity_sync_reports_successful_update_response(self):
        user = SimpleNamespace(
            user_id=42,
            panel_user_uuid="panel-42",
            email="linked@example.com",
            telegram_id=42,
            username="alice",
            first_name=None,
            last_name=None,
        )
        panel_service = SimpleNamespace(
            update_user_details_on_panel=AsyncMock(return_value={"uuid": "panel-42"})
        )
        request = SimpleNamespace(
            app={"subscription_service": SimpleNamespace(panel_service=panel_service)}
        )

        result = await _sync_panel_identity_for_user(request, user)

        self.assertTrue(result)
        panel_service.update_user_details_on_panel.assert_awaited_once()
        _, payload = panel_service.update_user_details_on_panel.await_args.args[:2]
        self.assertNotIn("description", payload)
        self.assertEqual(payload["email"], "linked@example.com")

    def test_panel_description_for_user_excludes_email(self):
        user = SimpleNamespace(
            email="linked@example.com",
            username="alice",
            first_name="Alice",
            last_name=None,
        )

        self.assertEqual(_panel_description_for_user(user), "alice\nAlice")

    def test_panel_description_for_user_filters_broken_lines(self):
        user = SimpleNamespace(
            email="linked@example.com",
            username="alice??",
            first_name="????",
            last_name="Smith",
        )

        self.assertEqual(_panel_description_for_user(user), "alice??\nSmith")

    async def test_merged_panel_identity_deletes_source_before_updating_target(self):
        calls = []

        async def delete_source(*args, **kwargs):
            calls.append("delete")
            return True

        async def update_target(*args, **kwargs):
            calls.append("update")
            return {"uuid": "panel-target"}

        panel_service = SimpleNamespace(
            delete_user_from_panel=AsyncMock(side_effect=delete_source),
            update_user_details_on_panel=AsyncMock(side_effect=update_target),
        )
        request = SimpleNamespace(
            app={"subscription_service": SimpleNamespace(panel_service=panel_service)}
        )
        user = SimpleNamespace(
            user_id=42,
            panel_user_uuid="panel-target",
            telegram_id=42,
            email="linked@example.com",
            username="alice",
            first_name="Alice",
            last_name=None,
        )

        result = await _sync_merged_panel_identity_for_user(
            request,
            user,
            source_panel_uuid="panel-source",
            final_panel_uuid="panel-target",
        )

        self.assertTrue(result)
        self.assertEqual(calls, ["delete", "update"])
        panel_service.delete_user_from_panel.assert_awaited_once_with(
            "panel-source",
            log_response=False,
        )
        panel_service.update_user_details_on_panel.assert_awaited_once()
        update_uuid, payload = panel_service.update_user_details_on_panel.await_args.args[:2]
        self.assertEqual(update_uuid, "panel-target")
        self.assertEqual(payload["email"], "linked@example.com")
        self.assertEqual(payload["telegramId"], 42)

    async def test_merged_panel_identity_reactivates_expired_target_with_transferred_time(self):
        expire_at = datetime.now(timezone.utc) + timedelta(days=30)
        panel_service = SimpleNamespace(
            delete_user_from_panel=AsyncMock(return_value=True),
            update_user_details_on_panel=AsyncMock(return_value={"uuid": "panel-target"}),
        )
        request = SimpleNamespace(
            app={"subscription_service": SimpleNamespace(panel_service=panel_service)}
        )
        user = SimpleNamespace(
            user_id=42,
            panel_user_uuid="panel-target",
            telegram_id=42,
            email="linked@example.com",
            username="alice",
            first_name="Alice",
            last_name=None,
        )

        result = await _sync_merged_panel_identity_for_user(
            request,
            user,
            source_panel_uuid="panel-email",
            final_panel_uuid="panel-target",
            expire_at=expire_at,
        )

        self.assertTrue(result)
        panel_service.delete_user_from_panel.assert_awaited_once_with(
            "panel-email",
            log_response=False,
        )
        _, payload = panel_service.update_user_details_on_panel.await_args.args[:2]
        expected_expire_at = expire_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        self.assertEqual(payload["expireAt"], expected_expire_at)
        self.assertEqual(payload["status"], "ACTIVE")

    async def test_telegram_merge_defers_panel_sync_until_source_cleanup(self):
        current_user = SimpleNamespace(
            user_id=-100,
            email="linked@example.com",
            email_verified_at=None,
            panel_user_uuid="panel-source",
            telegram_id=None,
            username=None,
            first_name=None,
            last_name=None,
            language_code="ru",
            telegram_photo_url=None,
        )
        existing_telegram_user = SimpleNamespace(
            user_id=42,
            email=None,
            email_verified_at=None,
            panel_user_uuid="panel-target",
            telegram_id=42,
            username="old",
            first_name=None,
            last_name=None,
            language_code="ru",
            telegram_photo_url=None,
        )
        merged_user = SimpleNamespace(
            user_id=42,
            email="linked@example.com",
            email_verified_at=None,
            panel_user_uuid="panel-target",
            telegram_id=42,
            username="old",
            first_name=None,
            last_name=None,
            language_code="ru",
            telegram_photo_url=None,
        )
        panel_service = SimpleNamespace(update_user_details_on_panel=AsyncMock())
        request = SimpleNamespace(
            app={"subscription_service": SimpleNamespace(panel_service=panel_service)}
        )
        session = SimpleNamespace(flush=AsyncMock())
        telegram_user = {
            "id": 42,
            "username": "alice",
            "first_name": "Alice",
            "last_name": "",
            "language_code": "ru",
        }

        with (
            patch(
                "bot.app.web.webapp.auth.user_dal.get_user_by_id",
                AsyncMock(return_value=current_user),
            ),
            patch(
                "bot.app.web.webapp.auth.user_dal.get_user_by_telegram_id",
                AsyncMock(return_value=existing_telegram_user),
            ),
            patch(
                "bot.app.web.webapp.auth.user_dal.merge_users",
                AsyncMock(return_value=merged_user),
            ),
        ):
            result = await _link_telegram_to_user(
                request,
                session,
                current_user_id=-100,
                telegram_user=telegram_user,
                settings=SimpleNamespace(DEFAULT_LANGUAGE="ru"),
            )

        self.assertIs(result, merged_user)
        panel_service.update_user_details_on_panel.assert_not_awaited()
        self.assertEqual(merged_user.username, "alice")

    async def test_email_only_session_can_link_existing_telegram_only_account(self):
        email_user = SimpleNamespace(
            user_id=-100,
            email="linked@example.com",
            email_verified_at=object(),
            panel_user_uuid="panel-email",
            telegram_id=None,
            username=None,
            first_name=None,
            last_name=None,
            language_code="ru",
            telegram_photo_url=None,
            is_banned=False,
        )
        telegram_user_record = SimpleNamespace(
            user_id=42,
            email=None,
            email_verified_at=None,
            panel_user_uuid="panel-telegram",
            telegram_id=42,
            username="old",
            first_name=None,
            last_name=None,
            language_code="ru",
            telegram_photo_url=None,
            is_banned=False,
        )
        merged_user = SimpleNamespace(
            user_id=42,
            email="linked@example.com",
            email_verified_at=object(),
            panel_user_uuid="panel-telegram",
            telegram_id=42,
            username="old",
            first_name=None,
            last_name=None,
            language_code="ru",
            telegram_photo_url=None,
            is_banned=False,
        )
        panel_calls = []

        async def delete_source(*args, **kwargs):
            panel_calls.append("delete")
            return True

        async def update_target(*args, **kwargs):
            panel_calls.append("update")
            return {"uuid": "panel-telegram"}

        panel_service = SimpleNamespace(
            delete_user_from_panel=AsyncMock(side_effect=delete_source),
            update_user_details_on_panel=AsyncMock(side_effect=update_target),
        )
        settings = SimpleNamespace(
            WEBAPP_SESSION_SECRET="session-secret",
            WEBAPP_SESSION_TTL_SECONDS=3600,
            REDIS_URL=None,
            REDIS_KEY_PREFIX="test",
            DEFAULT_LANGUAGE="ru",
        )
        request = SimpleNamespace(
            app={
                "settings": settings,
                "async_session_factory": self._AsyncSessionFactory(),
                "subscription_service": SimpleNamespace(panel_service=panel_service),
                "email_auth_service": None,
                "i18n": None,
                "bot": SimpleNamespace(),
            },
            json=AsyncMock(return_value={"init_data": "telegram-init-data"}),
        )
        telegram_auth_payload = {
            "id": 42,
            "username": "alice",
            "first_name": "Alice",
            "last_name": "",
            "language_code": "ru",
        }
        notification_service = SimpleNamespace(
            notify_account_telegram_linked=AsyncMock(),
            notify_account_merged=AsyncMock(),
        )

        with (
            patch.object(account_routes, "_require_user_id", return_value=-100),
            patch.object(
                account_routes,
                "_validate_telegram_auth_payload",
                AsyncMock(return_value=telegram_auth_payload),
            ),
            patch.object(
                account_routes.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=email_user),
            ),
            patch.object(
                account_routes.user_dal,
                "get_user_by_telegram_id",
                AsyncMock(return_value=telegram_user_record),
            ),
            patch.object(
                account_routes.user_dal,
                "merge_users",
                AsyncMock(return_value=merged_user),
            ) as merge_users,
            patch.object(
                account_routes.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.notification_service.NotificationService",
                return_value=notification_service,
            ),
        ):
            response = await account_routes.account_telegram_link_route(request)

        self.assertEqual(response.status, 200)
        payload = json.loads(response.text)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["user_id"], 42)
        self.assertEqual(payload["telegram_id"], 42)
        self.assertEqual(payload["account_merge"]["removed_user_id"], -100)
        self.assertEqual(payload["account_merge"]["primary_user_id"], 42)
        merge_users.assert_awaited_once_with(
            request.app["async_session_factory"].session,
            source_user_id=-100,
            target_user_id=42,
        )
        self.assertEqual(panel_calls, ["delete", "update"])
        panel_service.delete_user_from_panel.assert_awaited_once_with(
            "panel-email",
            log_response=False,
        )
        update_uuid, update_payload = panel_service.update_user_details_on_panel.await_args.args[:2]
        self.assertEqual(update_uuid, "panel-telegram")
        self.assertEqual(update_payload["email"], "linked@example.com")
        self.assertEqual(update_payload["telegramId"], 42)
        notification_service.notify_account_merged.assert_awaited_once_with(
            primary_user_id=42,
            removed_user_id=-100,
            email="linked@example.com",
            telegram_id=42,
            username="alice",
            first_name="Alice",
            final_end_date_text="",
            primary_panel_user_uuid="panel-telegram",
            removed_panel_user_uuid="panel-email",
        )
        self.assertIn("rw_webapp_session", response.cookies)
