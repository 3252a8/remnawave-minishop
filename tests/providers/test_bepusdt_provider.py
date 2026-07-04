import asyncio
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.payment_providers.bepusdt import BepusdtConfig, BepusdtService, calculate_signature
from bot.payment_providers.bepusdt import service as bepusdt_service


def _expected_signature(params, token):
    pairs = []
    for key in sorted(params):
        if key == "signature":
            continue
        value = params[key]
        if value is None or value == "":
            continue
        pairs.append(f"{key}={value}")
    return hashlib.md5(("&".join(pairs) + token).encode("utf-8")).hexdigest()


def _make_service(**config_overrides):
    config_values = {
        "ENABLED": True,
        "API_BASE_URL": "https://bepusdt.example.com",
        "API_TOKEN": "secret-token",
        "TRADE_TYPE": "usdt.trc20",
        "FIAT": "CNY",
        "RETURN_URL": "https://app.example.com/payment-return",
    }
    config_values.update(config_overrides)
    service = object.__new__(BepusdtService)
    service.config = BepusdtConfig(**config_values)
    service.settings = SimpleNamespace(
        WEBHOOK_BASE_URL="https://bot.example.com",
        SUBSCRIPTION_MINI_APP_URL="https://app.example.com/",
        DEFAULT_CURRENCY_SYMBOL="CNY",
        PAYMENT_REQUEST_TIMEOUT_SECONDS=30,
        traffic_sale_mode=False,
    )
    service.bot = SimpleNamespace()
    service.i18n = SimpleNamespace()
    service.subscription_service = SimpleNamespace()
    service.referral_service = SimpleNamespace()
    return service


class _FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status = status
        self._payload = payload if payload is not None else {}

    async def text(self):
        return json.dumps(self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


def _capture_session(captured, response=None):
    session = SimpleNamespace()

    def post(url, data=None, json=None, headers=None):
        captured["url"] = url
        captured["data"] = data
        captured["json"] = json
        captured["headers"] = headers
        return response or _FakeResponse(
            payload={
                "status_code": 200,
                "data": {
                    "trade_id": "trade-1",
                    "order_id": "77",
                    "payment_url": "https://bepusdt.example.com/pay/trade-1",
                },
            }
        )

    session.post = post
    return session


class _FakeWebhookRequest:
    def __init__(self, payload):
        self._body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.headers = {"Content-Type": "application/json"}
        self.query = {}

    async def read(self):
        return self._body


class _FakeDbSession:
    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        pass

    async def rollback(self):
        pass


def test_signature_sorts_non_empty_params_and_appends_token():
    params = {
        "order_id": "CL202607030001",
        "amount": "10.00",
        "notify_url": "https://bot.example.com/webhook/bepusdt",
        "redirect_url": "",
        "signature": "bad-signature",
        "empty": None,
    }

    assert calculate_signature(params, "secret-token") == _expected_signature(
        params, "secret-token"
    )


def test_create_payment_posts_signed_transaction(monkeypatch):
    service = _make_service()
    captured = {}
    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=_capture_session(captured)))

    success, data = asyncio.run(
        service.create_payment(
            payment_db_id=77,
            amount=125.5,
            currency="CNY",
            description="Subscription 1 month",
        )
    )

    assert success
    assert data["trade_id"] == "trade-1"
    assert data["payment_url"] == "https://bepusdt.example.com/pay/trade-1"
    assert captured["url"] == "https://bepusdt.example.com/api/v1/order/create-transaction"
    body = captured["json"] or json.loads(captured["data"].decode("utf-8"))
    assert body["order_id"] == "77"
    assert body["amount"] == "125.50"
    assert body["trade_type"] == "usdt.trc20"
    assert body["fiat"] == "CNY"
    assert body["notify_url"] == "https://bot.example.com/webhook/bepusdt"
    assert body["redirect_url"] == "https://app.example.com/payment-return"
    assert body["signature"] == _expected_signature(body, "secret-token")


def test_create_payment_rejects_unsupported_currency(monkeypatch):
    service = _make_service(SUPPORTED_CURRENCIES="CNY,USDT")
    monkeypatch.setattr(
        service,
        "_get_session",
        AsyncMock(side_effect=AssertionError("unsupported currency must not reach API")),
    )

    success, data = asyncio.run(
        service.create_payment(payment_db_id=1, amount=10.0, currency="RUB")
    )

    assert not success
    assert data["message"] == "unsupported_currency"


def _signed_webhook_payload(**overrides):
    payload = {
        "trade_id": "trade-1",
        "order_id": "88",
        "amount": "150.00",
        "actual_amount": "150.00",
        "token": "USDT",
        "block_transaction_id": "0xabc",
        "status": 2,
    }
    payload.update(overrides)
    payload["signature"] = _expected_signature(payload, "secret-token")
    return payload


def _webhook_service(session, payment, monkeypatch, **overrides):
    monkeypatch.setattr(
        bepusdt_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(return_value=payment),
    )
    service = _make_service()
    service.async_session_factory = session
    for key, value in overrides.items():
        setattr(service, key, value)
    return service


def test_webhook_success_finalizes_payment(monkeypatch):
    session = _FakeDbSession()
    payment = SimpleNamespace(
        payment_id=88,
        user_id=42,
        status="pending_bepusdt",
        sale_mode="subscription",
        purchased_hwid_devices=None,
        purchased_gb=None,
        subscription_duration_months=1,
        amount=150.0,
        currency="CNY",
        user=None,
    )
    service = _webhook_service(session, payment, monkeypatch)
    update_mock = AsyncMock()
    finalize_mock = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(
        bepusdt_service.payment_dal, "update_provider_payment_and_status", update_mock
    )
    monkeypatch.setattr(bepusdt_service, "finalize_successful_payment", finalize_mock)

    response = asyncio.run(
        BepusdtService.webhook_route(service, _FakeWebhookRequest(_signed_webhook_payload()))
    )

    assert response.status == 200
    assert response.text == "success"
    update_mock.assert_awaited_once_with(
        session,
        88,
        "trade-1",
        bepusdt_service.PAYMENT_STATUS_PENDING_FINALIZATION,
    )
    finalize_mock.assert_awaited_once()


def test_webhook_success_with_amount_mismatch_is_rejected(monkeypatch):
    session = _FakeDbSession()
    payment = SimpleNamespace(
        payment_id=88,
        user_id=42,
        status="pending_bepusdt",
        sale_mode="subscription",
        purchased_hwid_devices=None,
        purchased_gb=None,
        subscription_duration_months=1,
        amount=150.0,
        currency="CNY",
        user=None,
    )
    service = _webhook_service(session, payment, monkeypatch)
    monkeypatch.setattr(
        bepusdt_service.payment_dal,
        "update_provider_payment_and_status",
        AsyncMock(side_effect=AssertionError("mismatched amount must not update payment")),
    )
    monkeypatch.setattr(
        bepusdt_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("mismatched amount must not finalize")),
    )

    response = asyncio.run(
        BepusdtService.webhook_route(
            service, _FakeWebhookRequest(_signed_webhook_payload(amount="151.00"))
        )
    )

    assert response.status == 400


def test_webhook_duplicate_success_does_not_finalize_again(monkeypatch):
    session = _FakeDbSession()
    payment = SimpleNamespace(
        payment_id=88,
        user_id=42,
        status="succeeded",
        sale_mode="subscription",
        purchased_hwid_devices=None,
        purchased_gb=None,
        subscription_duration_months=1,
        amount=150.0,
        currency="CNY",
        user=None,
    )
    service = _webhook_service(session, payment, monkeypatch)
    monkeypatch.setattr(
        bepusdt_service.payment_dal,
        "update_provider_payment_and_status",
        AsyncMock(side_effect=AssertionError("duplicate webhook must not update payment")),
    )
    monkeypatch.setattr(
        bepusdt_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("duplicate webhook must not finalize")),
    )

    response = asyncio.run(
        BepusdtService.webhook_route(service, _FakeWebhookRequest(_signed_webhook_payload()))
    )

    assert response.status == 200
    assert response.text == "success"


def test_webhook_invalid_signature_is_rejected():
    service = _make_service()
    payload = _signed_webhook_payload()
    payload["signature"] = "bad"

    response = asyncio.run(BepusdtService.webhook_route(service, _FakeWebhookRequest(payload)))

    assert response.status == 403
