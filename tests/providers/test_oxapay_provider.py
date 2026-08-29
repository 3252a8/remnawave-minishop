"""Contract tests for the OxaPay Generate Invoice integration."""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.payment_providers.oxapay import OxaPayConfig, OxaPayService
from bot.payment_providers.oxapay import service as oxapay_service


def _make_service(**config_overrides) -> OxaPayService:
    config_values = {
        "ENABLED": True,
        "MERCHANT_API_KEY": "merchant-key",
    }
    config_values.update(config_overrides)
    service = object.__new__(OxaPayService)
    service.config = OxaPayConfig(**config_values)
    service.settings = SimpleNamespace(
        DEFAULT_CURRENCY_SYMBOL="USD",
        WEBHOOK_BASE_URL="https://bot.example.com",
        PAYMENT_REQUEST_TIMEOUT_SECONDS=30,
        trusted_proxies=[],
        traffic_sale_mode=False,
    )
    service._default_return_url = "testbot"
    service.bot = object()
    service.i18n = object()
    service.subscription_service = object()
    service.referral_service = object()
    return service


class _FakeResponse:
    def __init__(self, status=200, payload=None, raw_text=None):
        self.status = status
        self._payload = payload if payload is not None else {}
        self._raw_text = raw_text

    async def text(self):
        if self._raw_text is not None:
            return self._raw_text
        return json.dumps(self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


def _capture_session(captured, *, post_response=None, get_response=None):
    session = SimpleNamespace()

    def post(url, json=None, headers=None, trace_request_ctx=None):
        captured["post_url"] = url
        captured["post_json"] = json
        captured["post_headers"] = headers
        captured["trace_request_ctx"] = trace_request_ctx
        return post_response or _FakeResponse()

    def get(url, headers=None):
        captured["get_url"] = url
        captured["get_headers"] = headers
        return get_response or _FakeResponse()

    session.post = post
    session.get = get
    return session


class _FakeWebhookRequest:
    def __init__(self, raw_body: bytes, signature: str, *, remote="127.0.0.1"):
        self._raw_body = raw_body
        self.headers = {"HMAC": signature}
        self.remote = remote

    async def read(self):
        return self._raw_body


class _FakeDbSession:
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


def _payment(*, status="pending_oxapay") -> SimpleNamespace:
    return SimpleNamespace(
        payment_id=77,
        user_id=1001,
        amount=15.5,
        currency="USD",
        status=status,
        provider="oxapay",
        provider_payment_id="184747701",
        provider_payment_url="https://pay.oxapay.com/merchant/184747701",
        sale_mode="subscription",
        subscription_duration_months=1,
        purchased_gb=None,
        purchased_hwid_devices=None,
        user=SimpleNamespace(user_id=1001),
    )


def _signed_request(service: OxaPayService, payload: dict) -> _FakeWebhookRequest:
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = oxapay_service._compute_webhook_signature(raw_body, service.merchant_api_key)
    return _FakeWebhookRequest(raw_body, signature)


def test_create_invoice_uses_current_v1_contract(monkeypatch):
    service = _make_service(
        FEE_PAID_BY_PAYER=True,
        UNDER_PAID_COVERAGE=2.5,
        TO_CURRENCY="usdt",
        AUTO_WITHDRAWAL=False,
        MIXED_PAYMENT=True,
        SANDBOX=True,
    )
    captured = {}
    response = _FakeResponse(
        payload={
            "data": {
                "track_id": "184747701",
                "payment_url": "https://pay.oxapay.com/merchant/184747701",
                "expired_at": 1_900_000_000,
            },
            "message": "Operation completed successfully!",
            "error": {},
            "status": 200,
            "version": "1.0.0",
        }
    )
    monkeypatch.setattr(
        service,
        "_get_session",
        AsyncMock(return_value=_capture_session(captured, post_response=response)),
    )

    success, data = asyncio.run(
        service.create_invoice(
            payment_db_id=77,
            amount=15.5,
            currency="usd",
            description="Subscription 1 month",
        )
    )

    assert success
    assert data["track_id"] == "184747701"
    assert captured["post_url"] == "https://api.oxapay.com/v1/payment/invoice"
    assert captured["post_headers"] == {
        "merchant_api_key": "merchant-key",
        "Content-Type": "application/json",
    }
    assert captured["post_json"] == {
        "amount": 15.5,
        "currency": "USD",
        "lifetime": 60,
        "return_url": "https://t.me/testbot",
        "order_id": "77",
        "sandbox": True,
        "callback_url": "https://bot.example.com/webhook/oxapay",
        "description": "Subscription 1 month",
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 2.5,
        "to_currency": "USDT",
        "auto_withdrawal": False,
        "mixed_payment": True,
    }


def test_create_invoice_rejects_incomplete_success_response(monkeypatch):
    service = _make_service()
    response = _FakeResponse(payload={"data": {}, "error": {}, "status": 200})
    monkeypatch.setattr(
        service,
        "_get_session",
        AsyncMock(return_value=_capture_session({}, post_response=response)),
    )

    success, data = asyncio.run(
        service.create_invoice(payment_db_id=77, amount=15, currency="USD", description="")
    )

    assert not success
    assert data["message"] == "invalid_response"


def test_payment_info_and_reuse_require_matching_live_invoice(monkeypatch):
    service = _make_service()
    captured = {}
    response = _FakeResponse(
        payload={
            "data": {
                "track_id": "184747701",
                "order_id": "77",
                "status": "waiting",
                "amount": 15.5,
                "currency": "USD",
                "expired_at": int(time.time()) + 900,
            },
            "error": {},
            "status": 200,
        }
    )
    monkeypatch.setattr(
        service,
        "_get_session",
        AsyncMock(return_value=_capture_session(captured, get_response=response)),
    )

    url = asyncio.run(service.try_reuse_pending_payment(_payment()))

    assert url == "https://pay.oxapay.com/merchant/184747701"
    assert captured["get_url"] == "https://api.oxapay.com/v1/payment/184747701"
    assert captured["get_headers"]["merchant_api_key"] == "merchant-key"


def test_paying_invoice_is_not_reused(monkeypatch):
    service = _make_service()
    service.get_payment_info = AsyncMock(
        return_value=(
            True,
            {
                "track_id": "184747701",
                "order_id": "77",
                "status": "paying",
                "expired_at": int(time.time()) + 900,
            },
        )
    )

    assert asyncio.run(service.try_reuse_pending_payment(_payment())) is None


def test_webhook_rejects_invalid_hmac_before_database_access(monkeypatch):
    service = _make_service()
    lookup = AsyncMock()
    monkeypatch.setattr(oxapay_service, "lookup_payment_by_order_or_provider_id", lookup)
    request = _FakeWebhookRequest(b'{"status":"Paid"}', "not-valid")

    response = asyncio.run(service.webhook_route(request))

    assert response.status == 403
    assert response.text == "invalid_signature"
    lookup.assert_not_awaited()


def test_paid_webhook_finalizes_verified_invoice(monkeypatch):
    service = _make_service()
    service.async_session_factory = _FakeDbSession()
    payment = _payment()
    lookup = AsyncMock(return_value=payment)
    claim = AsyncMock(return_value=payment)
    finalize = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(oxapay_service, "lookup_payment_by_order_or_provider_id", lookup)
    monkeypatch.setattr(oxapay_service.payment_dal, "claim_payment_finalization", claim)
    monkeypatch.setattr(oxapay_service, "finalize_successful_payment", finalize)
    request = _signed_request(
        service,
        {
            "track_id": "184747701",
            "status": "Paid",
            "type": "invoice",
            "amount": 15.5,
            "currency": "USD",
            "order_id": "77",
        },
    )

    response = asyncio.run(service.webhook_route(request))

    assert response.status == 200
    assert response.text == "ok"
    lookup.assert_awaited_once()
    claim.assert_awaited_once_with(
        service.async_session_factory,
        77,
        provider_payment_id="184747701",
    )
    finalize.assert_awaited_once()


def test_paid_webhook_rejects_monetary_mismatch(monkeypatch):
    service = _make_service()
    service.async_session_factory = _FakeDbSession()
    claim = AsyncMock()
    monkeypatch.setattr(
        oxapay_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(return_value=_payment()),
    )
    monkeypatch.setattr(oxapay_service.payment_dal, "claim_payment_finalization", claim)
    request = _signed_request(
        service,
        {
            "track_id": "184747701",
            "status": "Paid",
            "type": "invoice",
            "amount": 14.5,
            "currency": "USD",
            "order_id": "77",
        },
    )

    response = asyncio.run(service.webhook_route(request))

    assert response.status == 400
    assert response.text == "payment_mismatch"
    claim.assert_not_awaited()


def test_paying_webhook_is_acknowledged_without_finalization(monkeypatch):
    service = _make_service()
    service.async_session_factory = _FakeDbSession()
    update = AsyncMock()
    finalize = AsyncMock(side_effect=AssertionError("paying must not finalize"))
    monkeypatch.setattr(
        oxapay_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(return_value=_payment()),
    )
    monkeypatch.setattr(oxapay_service.payment_dal, "update_provider_payment_and_status", update)
    monkeypatch.setattr(oxapay_service, "finalize_successful_payment", finalize)
    request = _signed_request(
        service,
        {
            "track_id": "184747701",
            "status": "Paying",
            "type": "invoice",
            "amount": 15.5,
            "currency": "USD",
            "order_id": "77",
        },
    )

    response = asyncio.run(service.webhook_route(request))

    assert response.status == 200
    assert response.text == "ok"
    update.assert_awaited_once_with(
        service.async_session_factory,
        77,
        "184747701",
        "pending_oxapay",
    )
    finalize.assert_not_awaited()


def test_duplicate_paid_webhook_returns_required_ack(monkeypatch):
    service = _make_service()
    service.async_session_factory = _FakeDbSession()
    claim = AsyncMock(side_effect=AssertionError("duplicate payment must not be claimed"))
    monkeypatch.setattr(
        oxapay_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(return_value=_payment(status="succeeded")),
    )
    monkeypatch.setattr(oxapay_service.payment_dal, "claim_payment_finalization", claim)
    request = _signed_request(
        service,
        {
            "track_id": "184747701",
            "status": "Paid",
            "type": "invoice",
            "amount": 15.5,
            "currency": "USD",
            "order_id": "77",
        },
    )

    response = asyncio.run(service.webhook_route(request))

    assert response.status == 200
    assert response.text == "ok"
    claim.assert_not_awaited()
