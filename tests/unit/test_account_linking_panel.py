import json
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bot.app.web import subscription_webapp  # noqa: F401
from bot.app.web.webapp import account as account_routes
from bot.app.web.webapp import auth as auth_routes
from bot.app.web.webapp.auth import (
    _apply_telegram_profile_to_user,
    _build_account_merge_notice,
    _ensure_user_from_telegram,
    _link_telegram_to_user,
    _merge_users_for_web,
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

    def test_duplicate_promo_merge_conflict_is_localized(self):
        i18n = SimpleNamespace(gettext=Mock(return_value="localized conflict"))
        request = SimpleNamespace(app={"i18n": i18n})
        settings = SimpleNamespace(DEFAULT_LANGUAGE="en")
        error = account_routes.UserMergeConflictError(
            "fallback",
            message_key="account_merge_duplicate_promo_conflict",
        )

        message = account_routes._merge_conflict_message(request, settings, error, "ru")

        self.assertEqual(message, "localized conflict")
        i18n.gettext.assert_called_once_with("ru", "account_merge_duplicate_promo_conflict")

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

    def test_telegram_profile_update_preserves_existing_language(self):
        user = SimpleNamespace(
            telegram_id=None,
            username=None,
            first_name=None,
            last_name=None,
            language_code="ru",
            telegram_photo_url=None,
        )

        _apply_telegram_profile_to_user(
            user,
            {
                "id": 42,
                "username": "alice",
                "first_name": "Alice",
                "last_name": "",
                "language_code": "en",
            },
            SimpleNamespace(DEFAULT_LANGUAGE="en"),
        )

        self.assertEqual(user.language_code, "ru")
        self.assertEqual(user.username, "alice")

    async def test_telegram_login_preserves_existing_language(self):
        user = SimpleNamespace(
            user_id=42,
            telegram_id=42,
            username="old",
            first_name="Old",
            last_name=None,
            language_code="ru",
            telegram_photo_url=None,
        )
        update_user = AsyncMock(return_value=user)

        with (
            patch(
                "bot.app.web.webapp.auth.user_dal.get_user_by_telegram_id",
                AsyncMock(return_value=user),
            ),
            patch(
                "bot.app.web.webapp.auth.user_dal.get_user_by_id",
                AsyncMock(return_value=None),
            ),
            patch("bot.app.web.webapp.auth.user_dal.update_user", update_user),
        ):
            result = await _ensure_user_from_telegram(
                SimpleNamespace(),
                {
                    "id": 42,
                    "username": "alice",
                    "first_name": "Alice",
                    "last_name": "",
                    "language_code": "en",
                },
                SimpleNamespace(DEFAULT_LANGUAGE="en"),
            )

        self.assertIs(result, user)
        changed = update_user.await_args.args[2]
        self.assertNotEqual(changed.get("language_code"), "en")

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

    async def test_merged_panel_identity_keeps_shared_panel_user(self):
        panel_service = SimpleNamespace(
            delete_user_from_panel=AsyncMock(return_value=True),
            update_user_details_on_panel=AsyncMock(return_value={"uuid": "shared-panel"}),
        )
        request = SimpleNamespace(
            app={"subscription_service": SimpleNamespace(panel_service=panel_service)}
        )
        user = SimpleNamespace(
            user_id=42,
            panel_user_uuid="shared-panel",
            telegram_id=42,
            email="linked@example.com",
        )

        result = await _sync_merged_panel_identity_for_user(
            request,
            user,
            source_panel_uuid="shared-panel",
            final_panel_uuid="shared-panel",
        )

        self.assertTrue(result)
        panel_service.delete_user_from_panel.assert_not_awaited()
        panel_service.update_user_details_on_panel.assert_awaited_once_with(
            "shared-panel",
            {"telegramId": 42, "email": "linked@example.com"},
            log_response=False,
        )

    async def test_merge_notice_does_not_report_shared_panel_user_as_removed(self):
        merged_user = SimpleNamespace(
            user_id=42,
            panel_user_uuid="shared-panel",
            language_code="ru",
        )
        settings = SimpleNamespace(DEFAULT_LANGUAGE="en")

        with patch.object(
            auth_routes.subscription_dal,
            "get_active_subscription_by_user_id",
            AsyncMock(return_value=None),
        ):
            notice = await _build_account_merge_notice(
                SimpleNamespace(),
                merged_user=merged_user,
                source_user_id=-100,
                source_panel_uuid="shared-panel",
                settings=settings,
            )

        self.assertEqual(notice["primary_panel_user_uuid"], "shared-panel")
        self.assertIsNone(notice["removed_panel_user_uuid"])

    async def test_merged_panel_identity_reactivates_expired_target_with_transferred_time(self):
        expire_at = datetime.now(UTC) + timedelta(days=30)
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

    async def test_merged_panel_identity_recomputes_entitlements_after_cleanup(self):
        panel_service = SimpleNamespace(delete_user_from_panel=AsyncMock(return_value=True))
        sync_entitlements = AsyncMock(return_value=True)
        request = SimpleNamespace(
            app={
                "subscription_service": SimpleNamespace(
                    panel_service=panel_service,
                    sync_main_traffic_limit_to_panel=sync_entitlements,
                )
            }
        )
        session = SimpleNamespace(commit=AsyncMock())
        user = SimpleNamespace(user_id=42, panel_user_uuid="panel-target")

        result = await _sync_merged_panel_identity_for_user(
            request,
            user,
            source_panel_uuid="panel-source",
            final_panel_uuid="panel-target",
            session=session,
        )

        self.assertTrue(result)
        sync_entitlements.assert_awaited_once_with(session, 42)
        session.commit.assert_awaited_once()

    async def test_web_merge_cancels_secondary_managed_and_local_recurrence(self):
        provider_service = SimpleNamespace(
            manages_recurrence=True,
            cancel_provider_recurrence=AsyncMock(return_value=True),
        )
        subscription_service = SimpleNamespace(
            managed_recurring_provider_services={"platega": provider_service}
        )
        request = SimpleNamespace(app={"subscription_service": subscription_service})
        session = SimpleNamespace()
        subscription = SimpleNamespace(subscription_id=17)
        merged = SimpleNamespace(user_id=42)

        async def exercise_cancellation(*args, **kwargs):
            cancel = kwargs["cancel_source_recurring"]
            self.assertTrue(await cancel(session, -10, subscription, ("platega",)))
            return merged

        with (
            patch.object(auth_routes.user_dal, "merge_users", side_effect=exercise_cancellation),
            patch.object(
                auth_routes.subscription_dal,
                "set_auto_renew",
                AsyncMock(),
            ) as set_auto_renew,
        ):
            result = await _merge_users_for_web(
                request,
                session,
                source_user_id=-10,
                target_user_id=42,
                reason="email_link",
                send_user_email=True,
            )

        self.assertIs(result, merged)
        provider_service.cancel_provider_recurrence.assert_awaited_once_with(
            session,
            user_id=-10,
        )
        set_auto_renew.assert_awaited_once_with(
            session,
            17,
            False,
            stop_reason="account_merged",
        )

    async def test_telegram_link_rejects_identity_owned_by_another_account(self):
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
                "bot.app.web.webapp.auth.user_dal.lock_user_by_id",
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
            self.assertRaisesRegex(Exception, "explicit merge is required"),
        ):
            await _link_telegram_to_user(
                request,
                session,
                current_user_id=-100,
                telegram_user=telegram_user,
                settings=SimpleNamespace(DEFAULT_LANGUAGE="ru"),
            )

        panel_service.update_user_details_on_panel.assert_not_awaited()
        self.assertEqual(merged_user.username, "old")

    async def test_email_only_session_cannot_take_existing_telegram_account(self):
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
                "lock_user_by_id",
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
                auth_routes.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                account_routes,
                "_probe_telegram_notifications_for_user_id",
                AsyncMock(),
            ) as probe_telegram_notifications,
            patch.object(
                account_routes,
                "_grant_deferred_referral_welcome_bonus_after_telegram_link",
                AsyncMock(),
            ) as grant_deferred_welcome_bonus,
        ):
            response = await account_routes.account_telegram_link_route(request)

        self.assertEqual(response.status, 409)
        payload = json.loads(response.text)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "account_merge_conflict")
        merge_users.assert_not_awaited()
        probe_telegram_notifications.assert_not_awaited()
        grant_deferred_welcome_bonus.assert_not_awaited()
        self.assertEqual(panel_calls, [])
        self.assertNotIn("rw_webapp_session", response.cookies)
