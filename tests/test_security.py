import hashlib
import hmac
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp import web

from bot.app.web import subscription_webapp
from bot.app.web.webapp_auth import (
    create_telegram_oauth_nonce,
    create_webapp_session_token,
    verify_telegram_oauth_nonce,
)
from bot.services.crypto_pay_service import CryptoPayService
from bot.handlers.user.payment import yookassa_webhook_route
from bot.services.freekassa_service import FreeKassaService
from bot.utils.request_security import request_client_ip


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
        settings = SimpleNamespace(
            FREEKASSA_ENABLED=True,
            FREEKASSA_MERCHANT_ID="123456",
            FREEKASSA_API_KEY="api-key",
            FREEKASSA_SECOND_SECRET="second-secret",
            DEFAULT_CURRENCY_SYMBOL="RUB",
            FREEKASSA_PAYMENT_IP="203.0.113.10",
            FREEKASSA_PAYMENT_METHOD_ID=44,
            FREEKASSA_TRUSTED_IPS="127.0.0.1,203.0.113.0/24",
            trusted_proxies=["127.0.0.1"],
            freekassa_trusted_ips=["127.0.0.1", "203.0.113.0/24"],
        )
        return FreeKassaService(
            bot=object(),
            settings=settings,
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
        service = CryptoPayService.__new__(CryptoPayService)
        service.token = "cryptopay-token"
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


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
