import hashlib
import hmac
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

from aiohttp import web

from bot.app.web import admin_api, subscription_webapp
from bot.app.web.admin_api_impl import settings as admin_settings_routes
from bot.app.web.webapp_auth import (
    create_telegram_oauth_nonce,
    create_webapp_session_token,
    verify_telegram_oauth_nonce,
)
from bot.payment_providers.cryptopay import CryptoPayService
from bot.payment_providers.freekassa import FreeKassaService
from bot.payment_providers.yookassa import yookassa_webhook_route
from bot.utils.request_security import request_client_ip
from config.settings import Settings
from db.database_setup import redacted_database_url


class RequestSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_client_ip_uses_last_forwarded_for_value_for_trusted_proxy(self):
        request = SimpleNamespace(
            remote="127.0.0.1",
            headers={"X-Forwarded-For": "203.0.113.10, 198.51.100.7"},
        )

        self.assertEqual(
            request_client_ip(request, trusted_proxies=["127.0.0.1"]),
            "198.51.100.7",
        )

    async def test_yookassa_webhook_rejects_untrusted_ip_before_reading_body(self):
        request = SimpleNamespace(
            app={
                "bot": object(),
                "i18n": object(),
                "settings": SimpleNamespace(trusted_proxies=["127.0.0.1"]),
                "panel_service": object(),
                "subscription_service": object(),
                "referral_service": object(),
                "lknpd_service": None,
                "async_session_factory": object(),
            },
            headers={},
            remote="203.0.113.50",
            json=AsyncMock(side_effect=AssertionError("request.json() must not be called")),
        )

        response = await yookassa_webhook_route(request)

        self.assertEqual(response.status, 403)
        request.json.assert_not_awaited()


class FreeKassaServiceTests(unittest.TestCase):
    def _make_service(self) -> FreeKassaService:
        from bot.payment_providers.freekassa import FreeKassaConfig

        settings = SimpleNamespace(
            DEFAULT_CURRENCY_SYMBOL="RUB",
            trusted_proxies=["127.0.0.1"],
        )
        config = FreeKassaConfig(
            ENABLED=True,
            MERCHANT_ID="123456",
            API_KEY="api-key",
            SECOND_SECRET="second-secret",
            PAYMENT_IP="203.0.113.10",
            PAYMENT_METHOD_ID=44,
            TRUSTED_IPS="127.0.0.1,203.0.113.0/24",
        )
        return FreeKassaService(
            bot=object(),
            settings=settings,
            config=config,
            i18n=object(),
            async_session_factory=object(),
            subscription_service=object(),
            referral_service=object(),
        )

    def test_validate_signature_accepts_hmac_sha256_raw_body(self):
        service = self._make_service()
        raw_body = b'{"amount":"199.00","o":"42"}'
        expected_signature = hmac.new(
            service.second_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        self.assertTrue(service._validate_signature(raw_body, expected_signature))

    def test_validate_signature_rejects_wrong_signature(self):
        service = self._make_service()

        self.assertFalse(service._validate_signature(b"payload", "not-a-signature"))

    def test_webhook_rejects_unauthorized_ip_before_body_read(self):
        service = self._make_service()
        request = SimpleNamespace(
            remote="198.51.100.250",
            headers={},
            read=AsyncMock(side_effect=AssertionError("request.read() must not be called")),
        )

        response = asyncio_run(service.webhook_route(request))

        self.assertEqual(response.status, 403)
        request.read.assert_not_awaited()


class CryptoPayServiceTests(unittest.TestCase):
    def _make_service(self) -> CryptoPayService:
        from bot.payment_providers.cryptopay import CryptoPayConfig

        service = CryptoPayService.__new__(CryptoPayService)
        service.config = CryptoPayConfig(TOKEN="cryptopay-token")
        return service

    def test_validate_webhook_signature_accepts_valid_signature(self):
        service = self._make_service()
        raw_body = b'{"payload":"42"}'
        expected_signature = hmac.new(
            hashlib.sha256(service.token.encode("utf-8")).digest(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        self.assertTrue(service._validate_webhook_signature(raw_body, expected_signature))

    def test_validate_webhook_signature_rejects_invalid_signature(self):
        service = self._make_service()

        self.assertFalse(service._validate_webhook_signature(b"payload", "not-a-signature"))


class WebAppSecurityTests(unittest.IsolatedAsyncioTestCase):
    def test_auth_response_sets_cookies_and_does_not_return_session_token(self):
        settings = SimpleNamespace(
            WEBAPP_SESSION_SECRET="session-secret",
            WEBAPP_SESSION_TTL_SECONDS=3600,
        )

        response = subscription_webapp._build_webapp_auth_response(
            settings,
            {"user_id": 321},
            token="raw-session-token",
            csrf_token="csrf-token",
        )
        payload = json.loads(response.text)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["csrf_token"], "csrf-token")
        self.assertNotIn("token", payload)
        self.assertEqual(response.cookies["rw_webapp_session"].value, "raw-session-token")
        self.assertTrue(response.cookies["rw_webapp_session"]["httponly"])
        self.assertEqual(response.cookies["rw_webapp_csrf"].value, "csrf-token")
        self.assertFalse(response.cookies["rw_webapp_csrf"]["httponly"])

    def test_require_user_id_falls_back_to_cookie_session(self):
        settings = SimpleNamespace(
            WEBAPP_SESSION_SECRET="session-secret",
            WEBAPP_SESSION_TTL_SECONDS=3600,
        )
        token = create_webapp_session_token(settings, 321)
        request = SimpleNamespace(
            app={"settings": settings},
            headers={},
            cookies={"rw_webapp_session": token},
        )

        self.assertEqual(subscription_webapp._require_user_id(request), 321)

    async def test_csrf_middleware_rejects_mismatched_token_when_cookie_session_exists(self):
        settings = SimpleNamespace(
            WEBAPP_SESSION_SECRET="session-secret",
            WEBAPP_SESSION_TTL_SECONDS=3600,
        )
        request = SimpleNamespace(
            method="POST",
            path="/api/payments",
            headers={"X-CSRF-Token": "bad-token"},
            cookies={"rw_webapp_session": "session-cookie", "rw_webapp_csrf": "good-token"},
            app={"settings": settings},
        )
        handler = AsyncMock(return_value=web.Response(text="ok"))

        response = await subscription_webapp._csrf_protection_middleware(request, handler)

        self.assertEqual(response.status, 403)
        handler.assert_not_awaited()

    async def test_csrf_middleware_allows_matching_token_when_cookie_session_exists(self):
        settings = SimpleNamespace(
            WEBAPP_SESSION_SECRET="session-secret",
            WEBAPP_SESSION_TTL_SECONDS=3600,
        )
        request = SimpleNamespace(
            method="POST",
            path="/api/payments",
            headers={"X-CSRF-Token": "good-token"},
            cookies={"rw_webapp_session": "session-cookie", "rw_webapp_csrf": "good-token"},
            app={"settings": settings},
        )
        handler = AsyncMock(return_value=web.Response(text="ok"))

        response = await subscription_webapp._csrf_protection_middleware(request, handler)

        self.assertEqual(response.text, "ok")
        handler.assert_awaited_once()

    async def test_csrf_middleware_allows_valid_bearer_authorization_for_compatibility(self):
        settings = SimpleNamespace(
            WEBAPP_SESSION_SECRET="session-secret",
            WEBAPP_SESSION_TTL_SECONDS=3600,
        )
        token = create_webapp_session_token(settings, 321)
        request = SimpleNamespace(
            method="POST",
            path="/api/payments",
            headers={
                "Authorization": f"Bearer {token}",
                "X-CSRF-Token": "bad-token",
            },
            cookies={"rw_webapp_session": "session-cookie", "rw_webapp_csrf": "good-token"},
            app={"settings": settings},
        )
        handler = AsyncMock(return_value=web.Response(text="ok"))

        response = await subscription_webapp._csrf_protection_middleware(request, handler)

        self.assertEqual(response.text, "ok")
        handler.assert_awaited_once()

    def test_email_payload_rejects_overlong_email(self):
        long_email = ("a" * 245) + "@example.com"

        model, response = subscription_webapp._validate_model_payload(
            subscription_webapp.WebAppEmailPayload,
            {"email": long_email},
        )

        self.assertIsNone(model)
        self.assertEqual(response.status, 400)
        self.assertIn("email_too_long", response.text)

    def test_payment_payload_rejects_overlong_description(self):
        model, response = subscription_webapp._validate_model_payload(
            subscription_webapp.WebAppPaymentCreatePayload,
            {
                "method": "platega",
                "months": 3,
                "description": "x" * 4097,
            },
        )

        self.assertIsNone(model)
        self.assertEqual(response.status, 400)
        self.assertIn("description_too_long", response.text)

    def test_telegram_oauth_nonce_round_trips(self):
        settings = SimpleNamespace(
            WEBAPP_SESSION_SECRET="session-secret",
            WEBAPP_SESSION_TTL_SECONDS=3600,
        )
        nonce = create_telegram_oauth_nonce(settings, ttl_seconds=60)

        self.assertTrue(verify_telegram_oauth_nonce(settings, nonce))
        self.assertFalse(verify_telegram_oauth_nonce(settings, nonce + "tampered"))

    async def test_telegram_oauth_start_uses_short_public_state(self):
        settings = SimpleNamespace(
            WEBAPP_ENABLED=True,
            BOT_TOKEN="123456789:secret",
            TELEGRAM_OAUTH_CLIENT_ID=None,
            TELEGRAM_OAUTH_CLIENT_SECRET="client-secret",
            TELEGRAM_OAUTH_REQUEST_ACCESS="write",
            WEBAPP_LOGIN_TOKEN_TTL_SECONDS=600,
            WEBAPP_SESSION_SECRET="session-secret",
            WEBAPP_SESSION_TTL_SECONDS=3600,
            SUBSCRIPTION_MINI_APP_URL="https://app.example.com/home",
        )
        request = SimpleNamespace(
            app={"settings": settings},
            query={"purpose": "login", "referral_code": "x" * 128},
            headers={},
            cookies={},
        )

        with self.assertRaises(web.HTTPFound) as raised:
            await subscription_webapp.telegram_oauth_start_route(request)

        redirect = raised.exception
        query = parse_qs(urlsplit(redirect.headers["Location"]).query)
        state = query["state"][0]
        self.assertLessEqual(len(state), 64)

        cookie_name = subscription_webapp.WEBAPP_TELEGRAM_OAUTH_STATE_COOKIE_NAME
        signed_state = redirect.cookies[cookie_name].value
        callback_request = SimpleNamespace(
            app={"settings": settings},
            cookies={cookie_name: signed_state},
        )
        payload = subscription_webapp._read_telegram_oauth_state_payload(callback_request, state)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["referral_code"], "x" * 128)
        self.assertEqual(len(payload["code_verifier"]), 43)
        self.assertIsNone(
            subscription_webapp._read_telegram_oauth_state_payload(callback_request, state + "x")
        )

    def test_telegram_oauth_client_id_defaults_to_bot_id(self):
        settings = SimpleNamespace(
            BOT_TOKEN="123456789:secret",
            TELEGRAM_OAUTH_CLIENT_ID=None,
            TELEGRAM_OAUTH_REQUEST_ACCESS="write, phone, unknown, write",
        )

        self.assertEqual(subscription_webapp._resolve_telegram_oauth_client_id(settings), 123456789)
        self.assertEqual(
            subscription_webapp._resolve_telegram_oauth_request_access(settings),
            ["write", "phone"],
        )

    def test_public_webapp_base_url_ignores_forwarded_headers_from_untrusted_remote(self):
        settings = SimpleNamespace(
            SUBSCRIPTION_MINI_APP_URL="",
            trusted_proxies=["127.0.0.1"],
        )
        request = SimpleNamespace(
            remote="203.0.113.10",
            scheme="http",
            host="internal.local",
            headers={
                "Host": "internal.local",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "evil.example.com",
            },
        )

        self.assertEqual(
            subscription_webapp._public_webapp_base_url(settings, request),
            "http://internal.local",
        )

    def test_public_webapp_base_url_accepts_forwarded_headers_from_trusted_proxy(self):
        settings = SimpleNamespace(
            SUBSCRIPTION_MINI_APP_URL="",
            trusted_proxies=["127.0.0.1"],
        )
        request = SimpleNamespace(
            remote="127.0.0.1",
            scheme="http",
            host="internal.local",
            headers={
                "Host": "internal.local",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "app.example.com",
            },
        )

        self.assertEqual(
            subscription_webapp._public_webapp_base_url(settings, request),
            "https://app.example.com",
        )

    async def test_security_headers_csp_excludes_unsafe_eval_and_plain_http_images(self):
        request = {"settings": SimpleNamespace()}
        handler = AsyncMock(return_value=web.Response(text="ok"))

        response = await subscription_webapp._security_headers_middleware(request, handler)
        csp = response.headers["Content-Security-Policy"]

        self.assertNotIn("'unsafe-eval'", csp)
        self.assertIn("img-src 'self' data: blob: https:;", csp)
        self.assertNotIn("img-src 'self' data: https: http:;", csp)


class AdminSettingsSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_settings_masks_secret_values_and_exposes_has_value(self):
        class AsyncSessionFactory:
            def __call__(self):
                return self

            async def __aenter__(self):
                return object()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        from bot.payment_providers import (
            build_provider_configs,
            get_provider_bundle,
        )

        build_provider_configs(force=True)
        bundle = get_provider_bundle("yookassa_service")
        if bundle and bundle.config is not None:
            bundle.config.SECRET_KEY = "super-secret"

        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            SHOP_NAME="Visible shop",
        )
        request = SimpleNamespace(
            app={"settings": settings, "async_session_factory": AsyncSessionFactory()},
            headers={},
            cookies={},
            admin_telegram_id=1,
        )
        request.get = lambda key, default=None: getattr(request, key, default)

        with (
            patch.object(admin_settings_routes, "_require_admin_user_id", return_value=1),
            patch.object(
                admin_api.app_settings_dal,
                "get_overrides_with_meta",
                AsyncMock(return_value=[]),
            ),
        ):
            response = await admin_api.admin_settings_get_route(request)

        payload = json.loads(response.text)
        secret_field = next(
            field
            for section in payload["sections"]
            for field in section["fields"]
            if field["key"] == "YOOKASSA_SECRET_KEY"
        )

        self.assertEqual(secret_field["value"], "")
        self.assertTrue(secret_field["has_value"])
        self.assertNotIn("super-secret", response.text)


class DatabaseLoggingSecurityTests(unittest.TestCase):
    def test_database_url_redaction_hides_password(self):
        raw_url = "postgresql+asyncpg://user:raw-password@db.example.com:5432/app"

        redacted = redacted_database_url(raw_url)

        self.assertIn("user:***@", redacted)
        self.assertNotIn("raw-password", redacted)


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
