import asyncio
import base64
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.payment_providers.cryptomus import CryptomusConfig, CryptomusService
from bot.payment_providers.cryptomus import service as provider
from bot.payment_providers.shared.managed_mandates import checkout_period_days


def make_service():
    ctx = SimpleNamespace(
        settings=SimpleNamespace(
            WEBHOOK_BASE_URL="https://shop.example", PAYMENT_REQUEST_TIMEOUT_SECONDS=20
        ),
        bot=None,
        i18n=None,
        async_session_factory=None,
        subscription_service=None,
        referral_service=None,
        bot_username_for_default_return="testbot",
    )
    return CryptomusService(
        ctx, CryptomusConfig(ENABLED=True, MERCHANT_ID="merchant", API_KEY="payment-key")
    )


class Response:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return {
            "state": 0,
            "result": {"uuid": "invoice", "url": "https://pay.cryptomus.com/invoice"},
        }


def test_request_signs_exact_utf8_bytes_and_invoice_limits(monkeypatch):
    service = make_service()
    captured = {}

    def post(url, *, data, headers):
        captured.update(url=url, data=data, headers=headers)
        return Response()

    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=SimpleNamespace(post=post)))
    success, data = asyncio.run(
        service.create_payment(
            payment_db_id=77, amount=150.49, currency="RUB", description="Subscription"
        )
    )
    assert success and data["id"] == "invoice"
    assert captured["headers"]["merchant"] == "merchant"
    assert (
        captured["headers"]["sign"]
        == hashlib.md5(
            base64.b64encode(captured["data"]) + b"payment-key", usedforsecurity=False
        ).hexdigest()
    )
    body = json.loads(captured["data"])
    assert body["amount"] == "150.49"
    assert body["order_id"] == "77"
    assert body["accuracy_payment_percent"] == 0
    assert body["is_payment_multiple"] is True
    assert body["url_callback"] == "https://shop.example/webhook/cryptomus"


class Request:
    def __init__(self, service, data, *, valid=True):
        unsigned = (
            json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("/", "\\/").encode()
        )
        data["sign"] = service.signature(unsigned) if valid else "invalid"
        # Deliberately use different JSON whitespace; verification follows PHP
        # JSON_UNESCAPED_UNICODE and slash escaping, not transport formatting.
        self.raw = json.dumps(data, ensure_ascii=False).encode()

    async def read(self):
        return self.raw


def test_webhook_php_unicode_and_slash_encoding(monkeypatch):
    service = make_service()
    settle = AsyncMock(return_value=SimpleNamespace(status=200))
    monkeypatch.setattr(provider, "settle_hosted_payment", settle)
    data = {
        "type": "payment",
        "uuid": "invoice",
        "order_id": "77",
        "status": "paid_over",
        "amount": "150.49",
        "payment_amount": "160",
        "currency": "RUB",
        "additional_data": "Пример/счёт",
    }
    assert asyncio.run(service.webhook_route(Request(service, data))).status == 200
    assert settle.call_args.kwargs["amount"] == "150.49"


@pytest.mark.parametrize(
    "amount,valid,status,final,expected",
    [
        ("1", True, "paid", True, 400),
        ("150.49", False, "paid", True, 403),
        ("1", True, "wrong_amount", False, 200),
    ],
)
def test_untrusted_partial_and_underpaid_payments_never_activate(
    monkeypatch, amount, valid, status, final, expected
):
    service = make_service()
    settle = AsyncMock(side_effect=AssertionError("must not fulfill"))
    monkeypatch.setattr(provider, "settle_hosted_payment", settle)
    data = {
        "type": "payment",
        "uuid": "invoice",
        "order_id": "77",
        "status": status,
        "amount": "150.49",
        "payment_amount": amount,
        "currency": "RUB",
        "is_final": final,
    }
    assert (
        asyncio.run(service.webhook_route(Request(service, data, valid=valid))).status == expected
    )
    settle.assert_not_awaited()


@pytest.mark.parametrize(
    "months,sale_mode,allowed",
    [
        (1, "subscription", True),
        (3, "subscription", True),
        (12, "subscription", False),
        (1, "gift", False),
        (1, "traffic", False),
        (1, "hwid_devices", False),
    ],
)
def test_recurring_checkout_restrictions(months, sale_mode, allowed):
    assert provider.SUBSCRIPTION_SPEC.payment_context_resolver(None, months, sale_mode) == allowed
    assert not provider.SUBSCRIPTION_SPEC.supports_recurring
    assert provider.SUBSCRIPTION_SPEC.manages_recurring
    assert not provider.SUBSCRIPTION_SPEC.supports_checkout_addons
    assert checkout_period_days(months, sale_mode) is None or sale_mode == "subscription"


def test_existing_recurrence_can_be_cancelled_when_checkout_disabled():
    service = make_service()
    service.config.ENABLED = False
    service.config.SUBSCRIPTION_ENABLED = False
    assert not service.configured
    assert service.manages_recurrence


def test_legacy_import_enables_crypto_without_creating_recurring_consent():
    from scripts.legacy_import.remnashop_env import remnashop_payment_gateway_overrides

    data = remnashop_payment_gateway_overrides(
        {
            "type": "CRYPTOMUS",
            "currency": "RUB",
            "is_active": True,
            "settings": {"merchant_id": "merchant", "api_key": "secret"},
        }
    )
    assert data["supported"] and data["provider_ids"] == ["cryptomus"]
    assert data["overrides"] == {
        "CRYPTOMUS_ENABLED": True,
        "CRYPTOMUS_MERCHANT_ID": "merchant",
        "CRYPTOMUS_API_KEY": "secret",
    }


def test_cancellation_requires_confirmed_terminal_status(monkeypatch):
    service = make_service()
    api = AsyncMock(return_value=(True, {"uuid": "mandate", "status": "wait_accept"}))
    monkeypatch.setattr(service, "api_request", api)
    assert not asyncio.run(service.stop_remote_subscription("mandate"))
    assert api.call_args.args == ("recurrence/info", {"uuid": "mandate"})
    api.return_value = (True, {"uuid": "mandate", "status": "cancel_by_merchant"})
    assert asyncio.run(service.stop_remote_subscription("mandate"))
