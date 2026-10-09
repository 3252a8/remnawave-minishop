import asyncio
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.payment_providers.anore import AnoreConfig, AnoreService
from bot.payment_providers.anore import service as provider
from bot.payment_providers.shared import hosted_settlement


def make_service(**overrides):
    config = {"ENABLED": True, "API_KEY": "an_live_test", "WEBHOOK_SECRET": "test-secret"}
    config.update(overrides)
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
    return AnoreService(ctx, AnoreConfig(**config))


class Request:
    def __init__(self, data, *, signature=None):
        self.raw = json.dumps(data, separators=(",", ":")).encode()
        self.headers = {
            "Anore-Signature": signature
            if signature is not None
            else hmac.new(b"test-secret", self.raw, hashlib.sha256).hexdigest()
        }

    async def read(self):
        return self.raw


def test_create_contract_and_live_admin_configuration(monkeypatch):
    service = make_service(SHOP_ID=5, METHODS="sbp,crypto")
    post = AsyncMock(
        return_value=(True, {"id": "invoice", "paymentUrl": "https://pay.anore.cc/invoice"})
    )
    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=object()))
    monkeypatch.setattr(provider, "post_json_request", post)
    assert asyncio.run(
        service.create_payment(
            payment_db_id=9, amount=150.49, currency="USD", description="Subscription"
        )
    )[0]
    body = post.call_args.kwargs["body"]
    assert body == {
        "amount": 150.49,
        "currency": "USD",
        "orderId": "9",
        "description": "Subscription",
        "shopId": 5,
        "methods": "sbp,crypto",
        "getbackurl": "https://t.me/testbot",
        "callbackUrl": "https://shop.example/webhook/anore",
    }
    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer an_live_test"}
    service.config.ENABLED = False
    assert not service.configured
    service.config.ADMIN_ONLY_ENABLED = True
    assert service.configured


@pytest.mark.parametrize("signature", ["", "bad"])
def test_signature_is_required(monkeypatch, signature):
    settle = AsyncMock(side_effect=AssertionError("unauthenticated webhook"))
    monkeypatch.setattr(provider, "settle_hosted_payment", settle)
    response = asyncio.run(
        make_service().webhook_route(Request({"event": "payment.succeeded"}, signature=signature))
    )
    assert response.status == 403
    settle.assert_not_awaited()


def test_webhook_uses_original_invoice_currency_not_rub_settlement(monkeypatch):
    settle = AsyncMock(return_value=SimpleNamespace(status=200))
    monkeypatch.setattr(provider, "settle_hosted_payment", settle)
    data = {
        "event": "payment.succeeded",
        "status": "paid",
        "id": "invoice",
        "orderId": "9",
        "amount": 10,
        "rubAmount": 800,
        "currency": "usd",
    }
    assert asyncio.run(make_service().webhook_route(Request(data))).status == 200
    assert settle.call_args.kwargs["amount"] == 10
    assert settle.call_args.kwargs["currency"] == "usd"


class DbSession:
    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


@pytest.mark.parametrize(
    "order_id,provider_id,amount,currency",
    [
        ("10", "invoice", 10, "USD"),
        ("9", "other", 10, "USD"),
        ("9", "invoice", 1, "USD"),
        ("9", "invoice", 10, "RUB"),
    ],
)
def test_settlement_rejects_identity_amount_and_currency_mismatch(
    monkeypatch, order_id, provider_id, amount, currency
):
    service = make_service()
    service.async_session_factory = DbSession()
    payment = SimpleNamespace(
        payment_id=9,
        provider_payment_id="invoice",
        amount=10,
        currency="USD",
        status="pending_anore",
    )
    monkeypatch.setattr(
        hosted_settlement, "lookup_payment_by_order_or_provider_id", AsyncMock(return_value=payment)
    )
    claim = AsyncMock(side_effect=AssertionError("invalid payment must not activate"))
    monkeypatch.setattr(hosted_settlement.payment_dal, "claim_payment_finalization", claim)
    response = asyncio.run(
        hosted_settlement.settle_hosted_payment(
            service,
            provider="anore",
            provider_id=provider_id,
            order_id=order_id,
            state="succeeded",
            amount=amount,
            currency=currency,
        )
    )
    assert response.status == 400
    claim.assert_not_awaited()


@pytest.mark.parametrize("state", ["succeeded", "failed"])
def test_repeated_or_late_webhook_preserves_success(monkeypatch, state):
    service = make_service()
    service.async_session_factory = DbSession()
    payment = SimpleNamespace(
        payment_id=9, provider_payment_id="invoice", amount=10, currency="USD", status="succeeded"
    )
    monkeypatch.setattr(
        hosted_settlement, "lookup_payment_by_order_or_provider_id", AsyncMock(return_value=payment)
    )
    claim = AsyncMock(side_effect=AssertionError("already finalized"))
    monkeypatch.setattr(hosted_settlement.payment_dal, "claim_payment_finalization", claim)
    assert (
        asyncio.run(
            hosted_settlement.settle_hosted_payment(
                service,
                provider="anore",
                provider_id="invoice",
                order_id="9",
                state=state,
                amount=10,
                currency="USD",
            )
        ).status
        == 200
    )
    claim.assert_not_awaited()
