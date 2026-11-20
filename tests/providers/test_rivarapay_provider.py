import asyncio
import hmac
import json
import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from bot.payment_providers.base import ServiceFactoryContext
from bot.payment_providers.rivarapay import CRYPTO_SPEC, SBP_SPEC, RivaraPayConfig, RivaraPayService
from bot.payment_providers.rivarapay import provider as registry_entries
from bot.payment_providers.rivarapay import service as rivarapay
from bot.payment_providers.shared import CreatePaymentRequest, hosted_settlement
from db.models import Payment


def make_service(**overrides):
    config = {"API_KEY": "live_fixture", "WEBHOOK_SECRET": "fixture-secret", "SBP_ENABLED": True}
    ctx = ServiceFactoryContext(
        settings=SimpleNamespace(WEBHOOK_BASE_URL="https://shop.example"),
        bot=None,
        i18n=None,
        async_session_factory=None,
        subscription_service=None,
        referral_service=None,
        bot_username_for_default_return="fixture_bot",
    )
    return RivaraPayService(ctx, RivaraPayConfig(**(config | overrides)))


def intent(**overrides):
    return {
        "id": "pi_fixture",
        "merchantOrderId": "42",
        "livemode": True,
        "status": "CREATED",
        "amount": {"amount": "10005", "currency": "RUB"},
        "checkoutUrl": "https://pay.rivarapay.io/checkout/fixture",
    } | overrides


@pytest.mark.parametrize(
    ("descriptor", "method"),
    [
        (registry_entries._DESCRIPTOR, "SBP"),
        (registry_entries._CRYPTO_DESCRIPTOR, "CRYPTO"),
    ],
)
def test_create_intent_for_exact_method_and_minor_amount(monkeypatch, descriptor, method):
    service = make_service(SBP_ENABLED=method == "SBP", CRYPTO_ENABLED=method == "CRYPTO")
    monkeypatch.setattr(service, "_get_session", AsyncMock())
    post = AsyncMock(return_value=(True, intent()))
    monkeypatch.setattr(rivarapay, "post_json_request", post)
    request = CreatePaymentRequest(
        payment=Payment(payment_id=42),
        user_id=72,
        amount=Decimal("100.05"),
        currency="RUB",
        description="Subscription",
        months=1,
        sale_mode="subscription",
    )

    success, data = asyncio.run(descriptor.create(service, request))

    assert success
    assert descriptor.extract_url(data) == intent()["checkoutUrl"]
    assert descriptor.extract_provider_id(data) == "pi_fixture"
    assert post.call_args.args[1] == "https://api.rivarapay.io/api/v1/payment-intents"
    call = post.call_args.kwargs
    assert call["headers"]["X-API-Key"] == "live_fixture"
    assert UUID(call["headers"]["Idempotency-Key"]).version == 4
    assert call["body"] == {
        "amount": "10005",
        "currency": "RUB",
        "merchantOrderId": "42",
        "customerEmail": "72@telegram.org",
        "description": "Subscription",
        "allowedMethods": [method],
        "returnUrl": "https://t.me/fixture_bot",
    }
    assert call["is_success"](201, data)
    assert not call["is_success"](201, intent(merchantOrderId="43"))
    assert not call["is_success"](201, intent(livemode=False))
    assert not call["is_success"](201, intent(amount={"amount": "10006", "currency": "RUB"}))
    assert not call["is_success"](201, intent(checkoutUrl="http://example.test/checkout"))


def test_methods_are_independently_configured_and_share_one_webhook():
    config = make_service(CRYPTO_ADMIN_ONLY_ENABLED=True).config
    assert SBP_SPEC.enabled(config)
    assert not CRYPTO_SPEC.enabled(config)
    assert getattr(config, CRYPTO_SPEC.admin_only_config_attr)
    assert SBP_SPEC.service_key == CRYPTO_SPEC.service_key == "rivarapay_service"
    assert SBP_SPEC.webhook_path is not None
    assert SBP_SPEC.webhook_path(config) == "/webhook/rivarapay"
    assert CRYPTO_SPEC.webhook_route is None
    assert not make_service(API_KEY="test_fixture").configured


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, "https://pay.rivarapay.io/checkout/original"),
        ({"merchantOrderId": "43"}, None),
        ({"status": "EXPIRED"}, None),
        ({"status": "SUCCEEDED"}, None),
    ],
)
def test_only_reuses_matching_open_intents(monkeypatch, changes, expected):
    service = make_service()
    payment = Payment(
        payment_id=42,
        provider_payment_id="pi_fixture",
        provider_payment_url="https://pay.rivarapay.io/checkout/original",
        amount=Decimal("100.05"),
        currency="RUB",
    )
    session = MagicMock()
    response = session.get.return_value.__aenter__.return_value
    response.status = 200
    response.json = AsyncMock(return_value=intent(**changes))
    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=session))

    assert asyncio.run(service.try_reuse_pending_payment(payment)) == expected


def signed_request(*, age=0, valid_signature=True, **overrides):
    data = {
        "event_type": "payment.paid",
        "status": "paid",
        "payment_id": "pi_fixture",
        "order_id": "42",
        "amount": "100.05",
        "total": "101.05",
        "currency": "RUB",
        "test": False,
    } | overrides
    raw = json.dumps(data).encode()
    timestamp = str(int(time.time()) - age)
    signature = hmac.digest(b"fixture-secret", timestamp.encode() + b"." + raw, "sha256").hex()
    return SimpleNamespace(
        headers={
            "X-Timestamp": timestamp,
            "X-Signature": signature if valid_signature else "0" * 64,
            "X-Event-Type": "use-body-instead",
        },
        read=AsyncMock(return_value=raw),
    )


@pytest.mark.parametrize(
    ("changes", "expected_status"),
    [
        ({"valid_signature": False}, 400),
        ({"age": 301}, 400),
        ({"age": -301}, 400),
        ({"event_type": "payment.expired", "status": "expired"}, 200),
        ({"test": True}, 200),
        ({"test": None}, 400),
        ({"order_id": None}, 400),
        ({"status": "processing"}, 400),
        ({"currency": "USDT"}, 400),
    ],
)
def test_unverified_or_non_live_payment_never_settles(monkeypatch, changes, expected_status):
    settle = AsyncMock()
    monkeypatch.setattr(rivarapay, "settle_hosted_payment", settle)
    response = asyncio.run(make_service().webhook_route(signed_request(**changes)))
    assert response.status == expected_status
    settle.assert_not_awaited()


@pytest.mark.parametrize("provider", ["rivarapay_sbp", "rivarapay_crypto"])
def test_paid_webhook_settles_original_ruble_amount_once(monkeypatch, provider):
    service = make_service(SBP_ENABLED=False)
    service.async_session_factory = MagicMock()
    payment = Payment(
        payment_id=42,
        provider=provider,
        provider_payment_id="pi_fixture",
        amount=Decimal("100.05"),
        currency="RUB",
        status="pending_rivarapay",
        sale_mode="subscription",
        user_id=72,
        subscription_duration_months=1,
    )
    get_payment = AsyncMock(return_value=payment)
    claim = AsyncMock(side_effect=[payment, None])
    finalize = AsyncMock(return_value=object())
    monkeypatch.setattr(hosted_settlement.payment_dal, "get_payment_by_db_id", get_payment)
    monkeypatch.setattr(hosted_settlement.payment_dal, "claim_payment_finalization", claim)
    monkeypatch.setattr(hosted_settlement, "finalize_successful_payment", finalize)

    assert asyncio.run(service.webhook_route(signed_request(amount="101.05"))).status == 400
    assert asyncio.run(service.webhook_route(signed_request(payment_id="pi_other"))).status == 400
    claim.assert_not_awaited()

    assert asyncio.run(service.webhook_route(signed_request())).status == 200
    assert asyncio.run(service.webhook_route(signed_request())).status == 200
    finalize.assert_awaited_once()
    assert finalize.call_args.args[0].provider_notification == provider
