import hashlib
import hmac
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

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


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
