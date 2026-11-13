import asyncio
import hmac
import json
import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web

from bot.payment_providers.payhot import PayHotConfig, PayHotService
from bot.payment_providers.payhot import service as payhot
from bot.payment_providers.shared.reconciliation import _inspect_provider_payment

_SECRET = "whsec_v2_test"
_ORDER = "minishop-123-9"
_INVOICE = {
    "id": "invoice",
    "merchant_order_reference": _ORDER,
    "amount_minor": "1050",
    "currency": "RUB",
    "status": "succeeded",
}
_URL = "https://checkout.pay.hot/checkout#one-time-token"


def make_service(**overrides):
    config = {
        "ENABLED": True,
        "API_KEY": "phk_live_v2_test",
        "WEBHOOK_SECRET": _SECRET,
        **overrides,
    }
    ctx = SimpleNamespace(
        settings=SimpleNamespace(PAYMENT_REQUEST_TIMEOUT_SECONDS=20),
        bot=SimpleNamespace(id=123),
        i18n=None,
        async_session_factory=None,
        subscription_service=None,
        referral_service=None,
    )
    return PayHotService(ctx, PayHotConfig(**config))


class Request:
    def __init__(self, *, timestamp=None, signature=None, event=None, **overrides):
        body = {
            "api_version": "v2",
            "event_type": "payment.succeeded",
            "data": {
                **_INVOICE,
                "object": "payment",
                "captured_amount_minor": "1050",
                **overrides,
            },
            **(event or {}),
        }
        self.raw = json.dumps(body).encode() + b"\n"
        timestamp = int(time.time()) if timestamp is None else timestamp
        signed_body = str(timestamp).encode() + b"." + self.raw
        digest = hmac.digest(_SECRET.encode(), signed_body, "sha256").hex()
        self.headers = {
            "PayHot-Signature": signature if signature is not None else f"t={timestamp},v2={digest}"
        }

    async def read(self):
        return self.raw


def test_payhot_retries_same_order_and_reissues_checkout(monkeypatch):
    service = make_service(PAYMENT_METHOD="sbp")
    request = AsyncMock(
        side_effect=[
            (False, {"message": "request_failed"}),
            (True, {"payment": _INVOICE, "checkout": {"reissue_required": True}}),
            (True, {"checkout": {"url": _URL, "expires_at": "2026-11-10T11:00:00Z"}}),
        ]
    )
    monkeypatch.setattr(service, "_request", request)

    ok, result = asyncio.run(service.create_payment(payment_db_id=9, amount=10.5, currency="RUB"))

    assert ok
    assert result == {"id": "invoice", "url": _URL, "expires_at": "2026-11-10T11:00:00Z"}
    create, retry, reissue = request.await_args_list
    assert create == retry
    assert create.args == ("POST", "https://app.pay.hot/api/v2/payments")
    assert create.kwargs == {
        "body": {
            "merchant_order_reference": _ORDER,
            "amount_minor": "1050",
            "currency": "RUB",
            "payment_method": "sbp",
        },
        "idempotency_key": f"payhot-create-{_ORDER}",
    }
    assert reissue.args == ("POST", "https://app.pay.hot/api/v2/payments/invoice/checkout-sessions")
    assert reissue.kwargs == {}


@pytest.mark.parametrize(
    "config,currency",
    [
        ({"API_KEY": "phk_test_v2_sandbox"}, "RUB"),
        ({"WEBHOOK_SECRET": ""}, "RUB"),
        ({"PAYMENT_METHOD": "sbp"}, "EUR"),
    ],
)
def test_payhot_rejects_unsupported_checkout_before_api_call(monkeypatch, config, currency):
    service = make_service(**config)
    request = AsyncMock()
    monkeypatch.setattr(service, "_request", request)
    ok, _ = asyncio.run(service.create_payment(payment_db_id=9, amount=10.5, currency=currency))
    assert not ok
    request.assert_not_awaited()


@pytest.mark.parametrize(
    "request_kwargs,status",
    [
        ({"signature": "t=1,v2=bad"}, 403),
        ({"timestamp": 1}, 403),
        ({"amount_minor": 1050}, 400),
        ({"captured_amount_minor": "1049"}, 400),
        ({"currency": "USDT.TRON"}, 400),
        ({"merchant_order_reference": "minishop-124-9"}, 400),
        ({"status": "partially_captured"}, 400),
        ({"event": {"environment": "sandbox"}}, 200),
        ({"event": {"event_type": "sandbox.payment.succeeded"}}, 200),
        ({"origin": "recurring"}, 200),
    ],
)
def test_payhot_webhook_rejects_unverified_payments(monkeypatch, request_kwargs, status):
    settle = AsyncMock()
    monkeypatch.setattr(payhot, "settle_hosted_payment", settle)
    response = asyncio.run(make_service().webhook_route(Request(**request_kwargs)))
    assert response.status == status
    settle.assert_not_awaited()


def test_payhot_webhook_settles_signed_original_order_amount(monkeypatch):
    settle = AsyncMock(return_value=web.Response(text="ok"))
    monkeypatch.setattr(payhot, "settle_hosted_payment", settle)
    service = make_service(ENABLED=False)
    response = asyncio.run(service.webhook_route(Request(captured_amount_minor="1150")))
    assert response.status == 200
    settle.assert_awaited_once_with(
        service,
        provider="payhot",
        provider_id="invoice",
        order_id="9",
        state="succeeded",
        amount=Decimal("10.50"),
        currency="RUB",
    )


def test_payhot_keeps_existing_checkout_while_payment_is_processing(monkeypatch):
    service = make_service()
    remote = {**_INVOICE, "status": "processing"}
    monkeypatch.setattr(service, "_request", AsyncMock(return_value=(True, {"payment": remote})))
    payment = SimpleNamespace(
        provider_payment_id="invoice",
        payment_id=9,
        amount=10.5,
        currency="RUB",
        provider_payment_url=_URL,
    )
    assert asyncio.run(service.try_reuse_pending_payment(payment)) == _URL


@pytest.mark.parametrize(
    "changes,expected_state,verified",
    [
        ({}, "succeeded", True),
        ({"id": "other"}, "unknown", False),
        ({"merchant_order_reference": "minishop-123-10"}, "unknown", False),
        ({"currency": "EUR"}, "succeeded", False),
        ({"amount_minor": "1049"}, "succeeded", False),
        ({"status": "manual_reconciliation"}, "pending", False),
        ({"status": "partially_captured"}, "pending", False),
    ],
)
def test_payhot_reconciliation_checks_status_and_order(
    monkeypatch, changes, expected_state, verified
):
    service = make_service()
    monkeypatch.setattr(
        service, "_request", AsyncMock(return_value=(True, {"payment": {**_INVOICE, **changes}}))
    )
    payment = SimpleNamespace(
        provider="payhot", provider_payment_id="invoice", payment_id=9, amount=10.5, currency="RUB"
    )
    result = asyncio.run(_inspect_provider_payment(service, payment))
    assert result.state == expected_state
    assert result.payment_verified is verified
