import json
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import web

from bot.app.web.webapp import auth_email, auth_oauth, auth_referral
from bot.services.registration_invite_gate import (
    RegistrationInviteRequiredError,
    RegistrationInviteStatus,
)


class InviteOnlyRegistrationTests(unittest.IsolatedAsyncioTestCase):
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

    def _settings(self, *, invite_only: bool = True):
        return SimpleNamespace(
            DEFAULT_LANGUAGE="en",
            REGISTRATION_INVITE_ONLY_ENABLED=invite_only,
            LEGACY_REFS=True,
            compatibility_settings=SimpleNamespace(remnashop_referral_code_compat_enabled=False),
            WEBAPP_SESSION_SECRET="session-secret",
            WEBAPP_SESSION_TTL_SECONDS=3600,
            WEBAPP_AUTH_MAX_AGE_SECONDS=3600,
            REFERRAL_WELCOME_BONUS_DAYS=0,
            REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED=True,
            disposable_email_domains=[],
            DISPOSABLE_EMAIL_DOMAINS="",
            referral_settings=SimpleNamespace(welcome_bonus_days=0),
            tariffs_config=None,
        )

    def _request(self, settings, payload, query=None, **app_values):
        app = {
            "settings": settings,
            "async_session_factory": self._AsyncSessionFactory(),
            **app_values,
        }
        return SimpleNamespace(app=app, json=AsyncMock(return_value=payload), query=query or {})

    async def test_webapp_telegram_auth_requires_invite_for_new_user(self):
        settings = self._settings(invite_only=True)
        request = self._request(settings, {"auth_data": {"id": 42}})
        create_user = AsyncMock()

        with (
            patch.object(
                auth_oauth,
                "_validate_telegram_auth_payload",
                AsyncMock(return_value={"id": 42, "language_code": "en"}),
            ),
            patch.object(
                auth_oauth,
                "_enforce_webapp_rate_limit",
                AsyncMock(return_value=None),
            ),
            patch.object(
                auth_referral.user_dal,
                "get_user_by_telegram_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                auth_referral.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=None),
            ),
            patch.object(auth_referral.user_dal, "create_user", create_user),
        ):
            response = await auth_oauth.auth_token_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 403)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "registration_invite_required")
        create_user.assert_not_awaited()

    async def test_webapp_telegram_auth_creates_new_user_with_valid_invite(self):
        settings = self._settings(invite_only=True)
        request = self._request(settings, {"auth_data": {"id": 42}, "referral_code": "ABC123"})
        referrer = SimpleNamespace(user_id=7)
        created_user = SimpleNamespace(user_id=42, is_banned=False, referred_by_id=7)
        create_user = AsyncMock(return_value=(created_user, True))

        with (
            patch.object(
                auth_oauth,
                "_validate_telegram_auth_payload",
                AsyncMock(return_value={"id": 42, "language_code": "en"}),
            ),
            patch.object(
                auth_oauth,
                "_enforce_webapp_rate_limit",
                AsyncMock(return_value=None),
            ),
            patch.object(
                auth_referral.user_dal,
                "get_user_by_telegram_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                auth_referral.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.registration_invite_gate.user_dal.get_user_by_referral_code",
                AsyncMock(return_value=referrer),
            ),
            patch.object(auth_referral.user_dal, "create_user", create_user),
            patch.object(
                auth_referral.user_dal,
                "lock_user_by_id",
                AsyncMock(return_value=created_user),
            ),
            patch.object(
                auth_referral.subscription_dal,
                "has_any_subscription_for_user",
                AsyncMock(return_value=False),
            ),
            patch.object(auth_oauth, "_invalidate_webapp_user_caches", AsyncMock()),
            patch.object(
                auth_oauth,
                "_probe_telegram_notifications_for_user_id",
                AsyncMock(),
            ),
        ):
            response = await auth_oauth.auth_token_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["ok"])
        create_payload = create_user.await_args.args[1]
        self.assertEqual(create_payload["referred_by_id"], 7)

    async def test_oauth_callback_redirects_invite_required(self):
        settings = self._settings(invite_only=True)
        request = self._request(
            settings,
            {},
            query={"code": "code", "state": "state"},
        )

        with (
            patch.object(
                auth_oauth,
                "_read_telegram_oauth_state_payload",
                return_value={"purpose": "login", "nonce": "nonce", "code_verifier": "verifier"},
            ),
            patch.object(
                auth_oauth,
                "_telegram_oauth_callback_url",
                return_value="https://app.example.com/auth/telegram/callback",
            ),
            patch.object(auth_oauth, "_resolve_telegram_oauth_client_id", return_value=42),
            patch.object(
                auth_oauth,
                "_telegram_oauth_redirect_url",
                side_effect=lambda path="/", status=None: (
                    f"https://app.example.com{path}?telegram_auth={status}"
                ),
            ),
            patch.object(
                auth_oauth,
                "_exchange_telegram_oauth_code",
                AsyncMock(return_value={"id_token": "id-token"}),
            ),
            patch.object(
                auth_oauth,
                "validate_telegram_oauth_id_token",
                AsyncMock(return_value={"id": 42, "language_code": "en"}),
            ),
            patch.object(
                auth_oauth,
                "_ensure_user_from_telegram",
                AsyncMock(
                    side_effect=RegistrationInviteRequiredError(RegistrationInviteStatus.MISSING)
                ),
            ),
            self.assertRaises(web.HTTPFound) as raised,
        ):
            await auth_oauth.telegram_oauth_callback_route(request)

        self.assertIn("telegram_auth=invite_required", raised.exception.location)

    async def test_email_request_passes_referral_to_magic_link(self):
        settings = self._settings(invite_only=True)
        email_service = SimpleNamespace(
            request_code=AsyncMock(
                return_value=SimpleNamespace(
                    ok=True,
                    code=None,
                    magic_link="https://app.example.com/?login_token=token&ref=ABC123",
                )
            ),
        )
        request = self._request(
            settings,
            {"email": "new@example.com", "language": "en", "referral_code": "ABC123"},
            email_auth_service=email_service,
        )

        response = await auth_email.email_auth_request_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(
            email_service.request_code.await_args.kwargs["referral_param"],
            "ABC123",
        )

    async def test_email_verify_existing_user_without_ref_is_allowed(self):
        settings = self._settings(invite_only=True)
        email_service = SimpleNamespace(
            verify_code=AsyncMock(return_value=SimpleNamespace(ok=True)),
        )
        user = SimpleNamespace(
            user_id=42,
            email_verified_at=datetime.now(UTC),
            is_banned=False,
            telegram_id=None,
            referred_by_id=None,
        )
        request = self._request(
            settings,
            {"email": "user@example.com", "code": "123456"},
            email_auth_service=email_service,
        )

        with (
            patch.object(
                auth_email.user_dal,
                "get_user_by_email",
                AsyncMock(return_value=user),
            ),
            patch.object(auth_email.user_dal, "create_email_user", AsyncMock()) as create_user,
            patch.object(auth_email, "_invalidate_webapp_user_caches", AsyncMock()),
        ):
            response = await auth_email.email_auth_verify_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["ok"])
        create_user.assert_not_awaited()

    async def test_email_verify_requires_invite_for_new_user(self):
        settings = self._settings(invite_only=True)
        email_service = SimpleNamespace(
            verify_code=AsyncMock(return_value=SimpleNamespace(ok=True)),
        )
        request = self._request(
            settings,
            {"email": "new@example.com", "code": "123456"},
            email_auth_service=email_service,
        )

        with (
            patch.object(
                auth_email.user_dal,
                "get_user_by_email",
                AsyncMock(return_value=None),
            ),
            patch.object(auth_email.user_dal, "create_email_user", AsyncMock()) as create_user,
        ):
            response = await auth_email.email_auth_verify_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 403)
        self.assertEqual(payload["error"], "registration_invite_required")
        create_user.assert_not_awaited()

    async def test_email_verify_creates_new_user_with_valid_invite(self):
        settings = self._settings(invite_only=True)
        email_service = SimpleNamespace(
            verify_code=AsyncMock(return_value=SimpleNamespace(ok=True)),
        )
        created_user = SimpleNamespace(
            user_id=100,
            email="new@example.com",
            email_verified_at=datetime.now(UTC),
            is_banned=False,
            telegram_id=None,
            referred_by_id=7,
            referral_welcome_bonus_claimed_at=None,
        )
        request = self._request(
            settings,
            {"email": "new@example.com", "code": "123456", "referral_code": "ABC123"},
            email_auth_service=email_service,
        )

        with (
            patch.object(
                auth_email.user_dal,
                "get_user_by_email",
                AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.registration_invite_gate.user_dal.get_user_by_referral_code",
                AsyncMock(return_value=SimpleNamespace(user_id=7)),
            ),
            patch.object(
                auth_email.user_dal,
                "create_email_user",
                AsyncMock(return_value=(created_user, True)),
            ) as create_user,
            patch.object(
                auth_referral.user_dal,
                "lock_user_by_id",
                AsyncMock(return_value=created_user),
            ),
            patch.object(
                auth_referral.subscription_dal,
                "has_any_subscription_for_user",
                AsyncMock(return_value=False),
            ),
            patch.object(auth_email, "_invalidate_webapp_user_caches", AsyncMock()),
        ):
            response = await auth_email.email_auth_verify_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(
            create_user.await_args.kwargs["referred_by_id"],
            7,
        )

    async def test_email_magic_requires_invite_for_new_user(self):
        settings = self._settings(invite_only=True)
        email_service = SimpleNamespace(
            verify_magic_token=AsyncMock(
                return_value=SimpleNamespace(ok=True, email="new@example.com")
            ),
        )
        request = self._request(
            settings,
            {"token": "magic-token"},
            email_auth_service=email_service,
        )

        with (
            patch.object(
                auth_email.user_dal,
                "get_user_by_email",
                AsyncMock(return_value=None),
            ),
            patch.object(auth_email.user_dal, "create_email_user", AsyncMock()) as create_user,
        ):
            response = await auth_email.email_auth_magic_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 403)
        self.assertEqual(payload["error"], "registration_invite_required")
        create_user.assert_not_awaited()

    async def test_email_magic_creates_new_user_with_valid_invite(self):
        settings = self._settings(invite_only=True)
        email_service = SimpleNamespace(
            verify_magic_token=AsyncMock(
                return_value=SimpleNamespace(ok=True, email="new@example.com")
            ),
        )
        created_user = SimpleNamespace(
            user_id=100,
            email="new@example.com",
            email_verified_at=datetime.now(UTC),
            is_banned=False,
            telegram_id=None,
            referred_by_id=7,
            referral_welcome_bonus_claimed_at=None,
        )
        request = self._request(
            settings,
            {"token": "magic-token", "referral_code": "ABC123"},
            email_auth_service=email_service,
        )

        with (
            patch.object(
                auth_email.user_dal,
                "get_user_by_email",
                AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.registration_invite_gate.user_dal.get_user_by_referral_code",
                AsyncMock(return_value=SimpleNamespace(user_id=7)),
            ),
            patch.object(
                auth_email.user_dal,
                "create_email_user",
                AsyncMock(return_value=(created_user, True)),
            ) as create_user,
            patch.object(
                auth_referral.user_dal,
                "lock_user_by_id",
                AsyncMock(return_value=created_user),
            ),
            patch.object(
                auth_referral.subscription_dal,
                "has_any_subscription_for_user",
                AsyncMock(return_value=False),
            ),
            patch.object(auth_email, "_invalidate_webapp_user_caches", AsyncMock()),
        ):
            response = await auth_email.email_auth_magic_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(
            create_user.await_args.kwargs["referred_by_id"],
            7,
        )
