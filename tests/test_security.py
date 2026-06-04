import hashlib
import hmac
import json
import time
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

from aiohttp import web

from bot.app.web import admin_api, subscription_webapp
from bot.app.web.admin_api_impl import settings as admin_settings_routes
from bot.app.web.webapp import account as account_routes
from bot.app.web.webapp_auth import (
    create_telegram_oauth_nonce,
    create_webapp_session_token,
    verify_telegram_oauth_nonce,
)
from bot.payment_providers.cryptopay import CryptoPayService
from bot.payment_providers.freekassa import FreeKassaService
from bot.payment_providers.heleket import HeleketConfig, HeleketService, _compute_signature
from bot.payment_providers.paykilla import (
    PaykillaConfig,
    PaykillaService,
    _clean_paykilla_text,
    _sign_query,
    _webhook_signature,
)
from bot.payment_providers.yookassa import yookassa_webhook_route
from bot.services.email_templates import render_login_code
from bot.utils.request_security import request_client_ip
from config.settings import Settings
from db.dal import security_dal
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


class HeleketServiceTests(unittest.TestCase):
    def _make_service(self, api_key: str = " payment-api-key ") -> HeleketService:
        service = HeleketService.__new__(HeleketService)
        service.config = HeleketConfig(ENABLED=True, MERCHANT_ID="merchant", API_KEY=api_key)
        return service

    def test_verify_signature_accepts_php_style_webhook_with_unicode_and_nested_payload(self):
        payload = {
            "type": "payment",
            "uuid": "1467f384-b053-42db-9066-d8a445cc52d3",
            "order_id": "435",
            "amount": "190.00000000",
            "payment_amount": "2.61000000",
            "payment_amount_usd": "2.61",
            "merchant_amount": "2.55780000",
            "commission": "0.05220000",
            "is_final": True,
            "status": "paid",
            "from": "0x7876fa0152a8eceb847154297b4ffdc85e3c4bd1",
            "wallet_address_uuid": None,
            "network": "polygon",
            "currency": "RUB",
            "payer_currency": "USDT",
            "payer_amount": "2.61000000",
            "payer_amount_exchange_rate": "72.72073217",
            "additional_data": "Подписка на 1 месяц",
            "transfer_id": None,
            "convert": {
                "to_currency": "USDC",
                "commission": "0.00000000",
                "rate": "0.99870036",
                "amount": "2.55447580",
            },
            "txid": "0x91f2a28213bf79fba51675f92a741c820ee321babe6ec48a3ae9301d31977f83",
        }
        payload["sign"] = _compute_signature(payload, "payment-api-key")

        self.assertTrue(self._make_service()._verify_signature(payload))

    def test_verify_signature_accepts_escaped_unicode_webhook_variant(self):
        payload = {
            "order_id": "435",
            "status": "paid",
            "additional_data": "Подписка на 1 месяц",
        }
        payload["sign"] = _compute_signature(payload, "payment-api-key", ensure_ascii=True)

        self.assertTrue(self._make_service()._verify_signature(payload))

    def test_verify_signature_rejects_invalid_signature(self):
        service = self._make_service("payment-api-key")

        self.assertFalse(service._verify_signature({"order_id": "435", "sign": "bad"}))


class PaykillaServiceTests(unittest.TestCase):
    def _make_service(self, *, webhook_url: str = "https://shop.example/webhook/paykilla"):
        service = PaykillaService.__new__(PaykillaService)
        service.config = PaykillaConfig(
            ENABLED=True,
            API_KEY="public-key",
            SECRET_KEY="secret-key",
            WEBHOOK_URL=webhook_url,
        )
        service.settings = SimpleNamespace(
            WEBHOOK_BASE_URL="https://shop.example",
            WEBAPP_TITLE="/minishop",
            trusted_proxies=["127.0.0.1"],
        )
        service._default_return_url = "test_bot"
        return service

    def test_sign_query_uses_timestamp_and_recv_window_only(self):
        query, signature = _sign_query(1738800000000, 5000, "secret-key")
        expected = hmac.new(
            b"secret-key",
            b"timestamp=1738800000000&recvWindow=5000",
            hashlib.sha256,
        ).hexdigest()

        self.assertEqual(query, "timestamp=1738800000000&recvWindow=5000")
        self.assertEqual(signature, expected)

    def test_clean_text_transliterates_russian_description_for_invoice_fields(self):
        text = _clean_paykilla_text(
            "Оплата подписки на 1 мес. - тариф «Базовый» ✅",
            fallback="Payment 556",
        )

        self.assertEqual(text, "Oplata podpiski na 1 mes. tarif Bazovyy")
        self.assertRegex(text, r"^[A-Za-z0-9_\s.,]+$")

    def test_invoice_body_uses_english_purpose_and_description(self):
        service = self._make_service()
        service.settings.WEBAPP_TITLE = "Tunnel Shop"

        body = service._invoice_body(
            payment_db_id=556,
            amount=100,
            currency="RUB",
            description="Оплата подписки на 1 мес. - тариф «Базовый» ✅",
        )

        self.assertEqual(body["purpose"], "Tunnel Shop payment 556")
        self.assertRegex(body["purpose"], r"^[A-Za-z0-9_\s.,]+$")
        self.assertEqual(body["paymentCurrencies"], ["USDTTRC"])
        self.assertEqual(body["description"], body["purpose"])
        self.assertTrue(body["expiredAt"].endswith("Z"))
        self.assertTrue(body["userPaysNetworkFee"])
        self.assertTrue(body["userPaysServiceFee"])
        self.assertNotIn("urls", body)

    def test_invoice_body_uses_payment_currency_before_configured_fallback(self):
        service = self._make_service()
        service.config.CURRENCY = "USD"

        body = service._invoice_body(
            payment_db_id=556,
            amount=100,
            currency="RUB",
            description="ignored",
        )

        self.assertEqual(body["currency"], "RUB")
        self.assertEqual(body["type"], "FIAT_BASED")

    def test_invoice_body_uses_configured_currency_as_fallback(self):
        service = self._make_service()
        service.config.CURRENCY = "USD"

        body = service._invoice_body(
            payment_db_id=556,
            amount=100,
            currency=None,
            description="ignored",
        )

        self.assertEqual(body["currency"], "USD")
        self.assertEqual(body["type"], "FIAT_BASED")

    def test_invoice_amount_converts_unsupported_tariff_currency_to_fallback(self):
        service = self._make_service()
        service.config.CURRENCY = "USD"
        service.config.INVOICE_CURRENCIES = "USD,EUR"

        with patch.object(
            service,
            "_exchange_rate",
            AsyncMock(return_value=Decimal("0.013586")),
        ) as exchange_rate:
            amount, currency = asyncio_run(
                service._invoice_amount_and_currency(
                    amount=190,
                    payment_currency="RUB",
                )
            )

        self.assertEqual(currency, "USD")
        self.assertEqual(amount, Decimal("2.58"))
        exchange_rate.assert_awaited_once_with("RUB", "USD")

    def test_invoice_amount_keeps_enabled_paykilla_invoice_currency(self):
        service = self._make_service()
        service.config.CURRENCY = "USD"
        service.config.INVOICE_CURRENCIES = "RUB,USD"

        with patch.object(
            service,
            "_exchange_rate",
            AsyncMock(side_effect=AssertionError("conversion must not run")),
        ):
            amount, currency = asyncio_run(
                service._invoice_amount_and_currency(
                    amount=190,
                    payment_currency="RUB",
                )
            )

        self.assertEqual(currency, "RUB")
        self.assertEqual(amount, Decimal("190.00"))

    def test_invoice_amount_bounds_detects_paykilla_minimum(self):
        service = self._make_service()

        with patch.object(
            service,
            "_currency_info_for",
            AsyncMock(return_value={"invoiceMin": "10", "invoiceMax": "500000"}),
        ):
            error = asyncio_run(
                service._invoice_amount_bounds_error(
                    amount=Decimal("2.58"),
                    currency="USD",
                )
            )

        self.assertEqual(error["message"], "invoice_amount_below_minimum")
        self.assertEqual(error["currency"], "USD")
        self.assertEqual(error["minimum"], "10.00")

    def test_invoice_body_omits_redirect_urls(self):
        service = self._make_service()

        body = service._invoice_body(
            payment_db_id=556,
            amount=100,
            currency="RUB",
            description="ignored",
        )

        self.assertNotIn("urls", body)

    def test_verify_webhook_signature_accepts_raw_body_signature(self):
        service = self._make_service()
        raw_body = (
            b'{"id":"evt_1","priority":"HIGH","eventType":"INVOICE_PAID",'
            b'"data":{"id":"inv_1","clientOrderId":"42"}}'
        )
        timestamp = str(int(time.time() * 1000))
        signature = _webhook_signature(
            timestamp=timestamp,
            method="POST",
            url="https://shop.example/webhook/paykilla",
            raw_body=raw_body,
            secret_key="secret-key",
        )
        request = SimpleNamespace(
            headers={
                "X-API-KEY": "public-key",
                "X-API-TIMESTAMP": timestamp,
                "X-API-RECV-WINDOW": "5000",
                "X-API-SIGN": signature,
            },
            method="POST",
            scheme="https",
            host="shop.example",
            path_qs="/webhook/paykilla",
        )

        self.assertTrue(service._verify_webhook_signature(request, raw_body))

    def test_verify_webhook_signature_rejects_invalid_signature(self):
        service = self._make_service()
        request = SimpleNamespace(
            headers={
                "X-API-KEY": "public-key",
                "X-API-TIMESTAMP": str(int(time.time() * 1000)),
                "X-API-RECV-WINDOW": "5000",
                "X-API-SIGN": "bad",
            },
            method="POST",
            scheme="https",
            host="shop.example",
            path_qs="/webhook/paykilla",
        )

        self.assertFalse(service._verify_webhook_signature(request, b"{}"))


class WebAppSecurityTests(unittest.IsolatedAsyncioTestCase):
    class _AsyncSessionFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def commit(self):
            return None

        async def rollback(self):
            return None

        async def flush(self):
            return None

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

    def test_email_password_hash_round_trips_without_plaintext(self):
        password = "correct horse battery staple"

        stored_hash = subscription_webapp._hash_email_password(password)

        self.assertNotIn(password, stored_hash)
        self.assertTrue(subscription_webapp._verify_email_password(password, stored_hash))
        self.assertFalse(subscription_webapp._verify_email_password("wrong-password", stored_hash))

    def test_set_password_email_code_copy_mentions_password_creation(self):
        settings = SimpleNamespace(
            DEFAULT_LANGUAGE="ru",
            EMAIL_CODE_TTL_SECONDS=600,
            WEBAPP_LOGO_URL="",
            WEBAPP_PRIMARY_COLOR="#00fe7a",
            WEBAPP_TITLE="Remnawave",
        )

        content = render_login_code(
            settings,
            code="123456",
            language_code="ru",
            magic_link="https://example.com/login",
            purpose="set_password",
        )

        self.assertIn("создания пароля", content.subject)
        self.assertIn("создание пароля", content.html)
        self.assertIn("код для создания пароля", content.text)
        self.assertNotIn("Подтвердите вход", content.html)
        self.assertNotIn("https://example.com/login", content.text)

    async def test_email_password_login_success_sets_session_cookie(self):
        settings = SimpleNamespace(
            WEBAPP_SESSION_SECRET="session-secret",
            WEBAPP_SESSION_TTL_SECONDS=3600,
            email_auth_configured=True,
            BRUTE_FORCE_MAX_FAILURES=5,
            BRUTE_FORCE_WINDOW_SECONDS=60,
            BRUTE_FORCE_LOCK_SECONDS=300,
        )
        stored_hash = subscription_webapp._hash_email_password("secret-password")
        db_user = SimpleNamespace(
            user_id=42,
            email_verified_at=object(),
            password_hash=stored_hash,
            is_banned=False,
            telegram_id=None,
        )
        request = SimpleNamespace(
            app={"settings": settings, "async_session_factory": self._AsyncSessionFactory()},
            json=AsyncMock(
                return_value={"email": "user@example.com", "password": "secret-password"}
            ),
        )

        with (
            patch.object(
                subscription_webapp.security_dal,
                "check_throttle",
                AsyncMock(return_value=security_dal.ThrottleDecision(locked=False)),
            ),
            patch.object(
                subscription_webapp.security_dal,
                "clear_throttle_state",
                AsyncMock(return_value=None),
            ),
            patch.object(
                subscription_webapp.user_dal,
                "get_user_by_email",
                AsyncMock(return_value=db_user),
            ),
        ):
            response = await subscription_webapp.email_password_auth_route(request)

        payload = json.loads(response.text)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["user_id"], 42)
        self.assertIn("rw_webapp_session", response.cookies)

    async def test_email_password_login_failures_use_same_fallback_error(self):
        settings = SimpleNamespace(
            email_auth_configured=True,
            BRUTE_FORCE_MAX_FAILURES=5,
            BRUTE_FORCE_WINDOW_SECONDS=60,
            BRUTE_FORCE_LOCK_SECONDS=300,
        )
        cases = [
            None,
            SimpleNamespace(
                user_id=42,
                email_verified_at=object(),
                password_hash=None,
                is_banned=False,
            ),
            SimpleNamespace(
                user_id=42,
                email_verified_at=object(),
                password_hash=subscription_webapp._hash_email_password("other-password"),
                is_banned=False,
            ),
        ]

        for db_user in cases:
            request = SimpleNamespace(
                app={"settings": settings, "async_session_factory": self._AsyncSessionFactory()},
                json=AsyncMock(
                    return_value={"email": "user@example.com", "password": "secret-password"}
                ),
            )
            with (
                patch.object(
                    subscription_webapp.security_dal,
                    "check_throttle",
                    AsyncMock(return_value=security_dal.ThrottleDecision(locked=False)),
                ),
                patch.object(
                    subscription_webapp.security_dal,
                    "record_throttle_failure",
                    AsyncMock(return_value=security_dal.ThrottleDecision(locked=False)),
                ),
                patch.object(
                    subscription_webapp.user_dal,
                    "get_user_by_email",
                    AsyncMock(return_value=db_user),
                ),
            ):
                response = await subscription_webapp.email_password_auth_route(request)

            payload = json.loads(response.text)
            self.assertEqual(response.status, 401)
            self.assertEqual(payload["error"], "password_login_failed")
            self.assertEqual(payload["fallback"], "email_code")

    async def test_account_password_confirm_requires_matching_passwords(self):
        request = SimpleNamespace(
            app={},
            json=AsyncMock(
                return_value={
                    "password": "secret-password",
                    "password_confirm": "other-password",
                    "code": "123456",
                }
            ),
        )

        with patch.object(account_routes, "_require_user_id", return_value=42):
            response = await account_routes.account_password_confirm_route(request)

        self.assertEqual(response.status, 400)
        self.assertIn("password_mismatch", response.text)

    async def test_account_password_confirm_sets_hash_after_email_code(self):
        settings = SimpleNamespace(
            REDIS_URL=None,
            REDIS_KEY_PREFIX="test",
        )
        db_user = SimpleNamespace(
            user_id=42,
            email="user@example.com",
            email_verified_at=object(),
            is_banned=False,
            password_hash=None,
            password_set_at=None,
        )
        email_service = SimpleNamespace(
            verify_code=AsyncMock(
                return_value=SimpleNamespace(ok=True, error=None, retry_after=None)
            )
        )
        request = SimpleNamespace(
            app={
                "settings": settings,
                "email_auth_service": email_service,
                "async_session_factory": self._AsyncSessionFactory(),
            },
            json=AsyncMock(
                return_value={
                    "password": "secret-password",
                    "password_confirm": "secret-password",
                    "code": "123456",
                }
            ),
        )

        with (
            patch.object(account_routes, "_require_user_id", return_value=42),
            patch.object(
                account_routes.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=db_user),
            ),
        ):
            response = await account_routes.account_password_confirm_route(request)

        self.assertEqual(response.status, 200)
        self.assertTrue(
            subscription_webapp._verify_email_password("secret-password", db_user.password_hash)
        )
        self.assertIsNotNone(db_user.password_set_at)

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
        self.assertEqual(response.headers["X-Robots-Tag"], "noindex, nofollow, noarchive")


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

    async def test_admin_settings_exposes_payment_webhook_urls(self):
        class AsyncSessionFactory:
            def __call__(self):
                return self

            async def __aenter__(self):
                return object()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            SHOP_NAME="Visible shop",
            WEBHOOK_BASE_URL="https://web.tnnl.cc/",
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
        section_ids = [section["id"] for section in payload["sections"]]
        fields = {
            field["key"]: field for section in payload["sections"] for field in section["fields"]
        }

        self.assertLess(section_ids.index("general"), section_ids.index("remnawave"))
        self.assertLess(section_ids.index("remnawave"), section_ids.index("payments"))
        self.assertEqual(
            fields["FREEKASSA_ENABLED"]["webhook_url"],
            "https://web.tnnl.cc/webhook/freekassa",
        )
        self.assertTrue(fields["FREEKASSA_ENABLED"]["webhook_base_url_configured"])
        self.assertEqual(
            fields["PAYMENT_PLATEGA_CRYPTO_WEBAPP_LABEL_RU"]["webhook_url"],
            "https://web.tnnl.cc/webhook/platega",
        )
        self.assertEqual(
            fields["PANEL_WEBHOOK_SECRET"]["webhook_url"],
            "https://web.tnnl.cc/webhook/panel",
        )
        self.assertTrue(fields["PANEL_WEBHOOK_SECRET"]["webhook_requires_base_url"])
        self.assertNotIn("webhook_url", fields["PAYMENT_STARS_WEBAPP_LABEL_RU"])


class DatabaseLoggingSecurityTests(unittest.TestCase):
    def test_database_url_redaction_hides_password(self):
        raw_url = "postgresql+asyncpg://user:raw-password@db.example.com:5432/app"

        redacted = redacted_database_url(raw_url)

        self.assertIn("user:***@", redacted)
        self.assertNotIn("raw-password", redacted)


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
