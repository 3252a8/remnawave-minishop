import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import ANY, AsyncMock, Mock, call, patch

from aiohttp import web

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp import email_change as email_change_module
from config.settings import Settings
from db.dal.user_email_dal import EmailAddressConflictError


class _SessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _settings(**overrides):
    values = {
        "EMAIL_ADDRESS_CHANGE_ENABLED": True,
        "email_auth_configured": True,
        "DEFAULT_LANGUAGE": "en",
        "qa_auth_enabled": False,
        "WEBAPP_LOGIN_TOKEN_TTL_SECONDS": 600,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _user(**overrides):
    values = {
        "user_id": 42,
        "email": "old@example.com",
        "email_verified_at": object(),
        "notification_email": "old@example.com",
        "language_code": "en",
        "is_banned": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class WebAppEmailChangeTests(IsolatedAsyncioTestCase):
    def test_email_address_change_is_enabled_by_default(self):
        assert Settings.model_fields["EMAIL_ADDRESS_CHANGE_ENABLED"].default is True

    async def test_disabled_setting_blocks_an_already_started_flow(self):
        settings = _settings(EMAIL_ADDRESS_CHANGE_ENABLED=False)
        parse_payload = AsyncMock()

        with (
            patch.object(email_change_module, "_require_user_id", return_value=42),
            patch.object(email_change_module, "get_settings", return_value=settings),
            patch.object(email_change_module, "_parse_model_payload", parse_payload),
        ):
            response = await email_change_module.account_email_change_current_verify_route(
                SimpleNamespace(app={})
            )

        self.assertEqual(response.status, 403)
        self.assertEqual(json.loads(response.text)["error"], "email_change_disabled")
        parse_payload.assert_not_awaited()

    async def test_new_email_request_rejects_an_address_owned_by_another_account(self):
        settings = _settings()
        session = SimpleNamespace()
        payload = SimpleNamespace(email="taken@example.com", change_token="change-token")
        other_user = SimpleNamespace(user_id=77)

        with (
            patch.object(email_change_module, "_require_user_id", return_value=42),
            patch.object(email_change_module, "get_settings", return_value=settings),
            patch.object(
                email_change_module,
                "_parse_model_payload",
                AsyncMock(return_value=payload),
            ),
            patch.object(
                email_change_module,
                "get_session_factory",
                return_value=_SessionFactory(session),
            ),
            patch.object(
                email_change_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=_user()),
            ),
            patch.object(
                email_change_module.user_dal,
                "get_user_by_email",
                AsyncMock(return_value=other_user),
            ),
            patch.object(email_change_module, "_verify_change_token", return_value=True),
            patch.object(email_change_module, "_request_email_code", AsyncMock()) as request_code,
        ):
            response = await email_change_module.account_email_change_new_request_route(
                SimpleNamespace(app={})
            )

        self.assertEqual(response.status, 409)
        self.assertEqual(json.loads(response.text)["error"], "email_already_in_use")
        request_code.assert_not_awaited()

    async def test_expired_new_email_code_does_not_change_the_account(self):
        settings = _settings()
        session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
        user = _user()
        payload = SimpleNamespace(
            email="new@example.com",
            code="123456",
            change_token="change-token",
        )
        email_service = SimpleNamespace(
            verify_code=AsyncMock(
                return_value=SimpleNamespace(
                    ok=False,
                    error="expired_code",
                    retry_after=None,
                )
            )
        )

        with (
            patch.object(email_change_module, "_require_user_id", return_value=42),
            patch.object(email_change_module, "get_settings", return_value=settings),
            patch.object(
                email_change_module,
                "_parse_model_payload",
                AsyncMock(return_value=payload),
            ),
            patch.object(
                email_change_module,
                "get_email_auth_service",
                return_value=email_service,
            ),
            patch.object(
                email_change_module,
                "get_session_factory",
                return_value=_SessionFactory(session),
            ),
            patch.object(
                email_change_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=user),
            ),
            patch.object(
                email_change_module.user_dal,
                "get_user_by_email",
                AsyncMock(return_value=None),
            ),
            patch.object(
                email_change_module.user_email_dal,
                "get_user_by_verified_email_address",
                AsyncMock(return_value=None),
            ),
            patch.object(email_change_module, "_verify_change_token", return_value=True),
            patch.object(
                email_change_module.user_email_dal,
                "upsert_user_email_address",
                AsyncMock(),
            ) as upsert_email,
        ):
            response = await email_change_module.account_email_change_confirm_route(
                SimpleNamespace(app={})
            )

        self.assertEqual(response.status, 400)
        self.assertEqual(json.loads(response.text)["error"], "expired_code")
        self.assertEqual(user.email, "old@example.com")
        session.commit.assert_awaited_once()
        upsert_email.assert_not_awaited()

    async def test_confirmation_handles_a_concurrent_unique_email_conflict(self):
        settings = _settings()
        session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
        payload = SimpleNamespace(
            email="new@example.com",
            code="123456",
            change_token="change-token",
        )
        email_service = SimpleNamespace(
            verify_code=AsyncMock(
                return_value=SimpleNamespace(ok=True, error=None, retry_after=None)
            )
        )
        sync_panel = AsyncMock()

        with (
            patch.object(email_change_module, "_require_user_id", return_value=42),
            patch.object(email_change_module, "get_settings", return_value=settings),
            patch.object(
                email_change_module,
                "_parse_model_payload",
                AsyncMock(return_value=payload),
            ),
            patch.object(
                email_change_module,
                "get_email_auth_service",
                return_value=email_service,
            ),
            patch.object(
                email_change_module,
                "get_session_factory",
                return_value=_SessionFactory(session),
            ),
            patch.object(
                email_change_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=_user()),
            ),
            patch.object(
                email_change_module.user_dal,
                "get_user_by_email",
                AsyncMock(return_value=None),
            ),
            patch.object(
                email_change_module.user_email_dal,
                "get_user_by_verified_email_address",
                AsyncMock(return_value=None),
            ),
            patch.object(email_change_module, "_verify_change_token", return_value=True),
            patch.object(
                email_change_module.user_email_dal,
                "upsert_user_email_address",
                AsyncMock(side_effect=EmailAddressConflictError),
            ),
            patch.object(email_change_module, "_sync_panel_identity_for_user", sync_panel),
        ):
            response = await email_change_module.account_email_change_confirm_route(
                SimpleNamespace(app={})
            )

        self.assertEqual(response.status, 409)
        self.assertEqual(json.loads(response.text)["error"], "email_already_in_use")
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()
        sync_panel.assert_not_awaited()

    async def test_success_updates_primary_email_and_notifies_both_addresses(self):
        settings = _settings()
        session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
        user = _user()
        payload = SimpleNamespace(
            email="new@example.com",
            code="123456",
            change_token="change-token",
        )
        email_service = SimpleNamespace(
            verify_code=AsyncMock(
                return_value=SimpleNamespace(ok=True, error=None, retry_after=None)
            ),
            send_custom_email=AsyncMock(return_value=True),
        )
        upsert_email = AsyncMock()
        sync_panel = AsyncMock(return_value=True)
        invalidate_cache = AsyncMock()
        i18n = SimpleNamespace(gettext=Mock(side_effect=lambda _lang, key, **_kwargs: key))

        with (
            patch.object(email_change_module, "_require_user_id", return_value=42),
            patch.object(email_change_module, "get_settings", return_value=settings),
            patch.object(
                email_change_module,
                "_parse_model_payload",
                AsyncMock(return_value=payload),
            ),
            patch.object(
                email_change_module,
                "get_email_auth_service",
                return_value=email_service,
            ),
            patch.object(
                email_change_module,
                "get_session_factory",
                return_value=_SessionFactory(session),
            ),
            patch.object(
                email_change_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=user),
            ),
            patch.object(
                email_change_module.user_dal,
                "get_user_by_email",
                AsyncMock(return_value=None),
            ),
            patch.object(
                email_change_module.user_email_dal,
                "get_user_by_verified_email_address",
                AsyncMock(return_value=None),
            ),
            patch.object(email_change_module, "_verify_change_token", return_value=True),
            patch.object(
                email_change_module.user_email_dal,
                "upsert_user_email_address",
                upsert_email,
            ),
            patch.object(email_change_module, "_sync_panel_identity_for_user", sync_panel),
            patch.object(email_change_module, "get_i18n", return_value=i18n),
            patch.object(
                email_change_module,
                "_invalidate_webapp_user_caches",
                invalidate_cache,
            ),
            patch.object(
                email_change_module,
                "create_webapp_session_token",
                return_value="session-token",
            ),
            patch.object(
                email_change_module,
                "_build_webapp_auth_response",
                side_effect=lambda _settings, payload, **_kwargs: web.json_response(payload),
            ),
        ):
            response = await email_change_module.account_email_change_confirm_route(
                SimpleNamespace(app={})
            )

        self.assertEqual(response.status, 200)
        self.assertEqual(user.email, "new@example.com")
        self.assertEqual(user.notification_email, "new@example.com")
        self.assertIsNotNone(user.email_verified_at)
        upsert_email.assert_awaited_once()
        self.assertEqual(upsert_email.await_args.kwargs["email"], "new@example.com")
        self.assertTrue(upsert_email.await_args.kwargs["is_primary"])
        self.assertTrue(upsert_email.await_args.kwargs["is_notification"])
        sync_panel.assert_awaited_once_with(ANY, user)
        session.commit.assert_awaited_once()
        email_service.send_custom_email.assert_has_awaits(
            [
                call(
                    email="old@example.com",
                    subject="email_change_notice_subject",
                    body="email_change_notice_body",
                ),
                call(
                    email="new@example.com",
                    subject="email_change_success_subject",
                    body="email_change_success_body",
                ),
            ]
        )
        invalidate_cache.assert_awaited_once_with(settings, 42, include_devices=True)
