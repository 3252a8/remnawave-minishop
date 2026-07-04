import asyncio
import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

from bot.payment_providers.epay import EpayConfig, EpayService, calculate_signature
from bot.payment_providers.epay import service as epay_service


def _expected_signature(params, key):
    pairs = []
    for param_key in sorted(params):
        if param_key in {"sign", "sign_type"}:
            continue
        value = params[param_key]
        if value is None or value == "":
            continue
        pairs.append(f"{param_key}={value}")
    return hashlib.md5(("&".join(pairs) + key).encode("utf-8")).hexdigest()


def _make_service(**config_overrides):
    config_values = {
        "ENABLED": True,
        "API_BASE_URL": "https://pay.example.com",
        "PID": "1001",
        "KEY": "merchant-secret",
        "PAYMENT_TYPE": "alipay",
        "RETURN_URL": "https://app.example.com/payment-return",
    }
    config_values.update(config_overrides)
    service = object.__new__(EpayService)
    service.config = EpayConfig(**config_values)
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
    service._default_return_url = "bot"
    return service


class _FakeWebhookRequest:
    def __init__(self, payload):
        self.query = {}
        self._payload = payload
        self.can_read_body = True
        self.content_type = "application/x-www-form-urlencoded"

    async def post(self):
        return dict(self._payload)


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


def test_signature_sorts_non_empty_params_and_excludes_sign_fields():
    params = {
        "pid": "1001",
        "out_trade_no": "88",
        "money": "10.00",
        "return_url": "",
        "sign": "bad",
        "sign_type": "MD5",
    }

    assert calculate_signature(params, "merchant-secret") == _expected_signature(
        params,
        "merchant-secret",
    )


def test_create_payment_generates_signed_submit_url():
    service = _make_service()

    success, data = asyncio.run(
        service.create_payment(
            payment_db_id=77,
            amount=125.5,
            currency="CNY",
            description="Subscription 1 month",
        )
    )

    assert success
    parsed = urlparse(data["payment_url"])
    params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
    assert parsed.geturl().startswith("https://pay.example.com/submit.php?")
    assert params["pid"] == "1001"
    assert params["type"] == "alipay"
    assert params["out_trade_no"] == "77"
    assert params["money"] == "125.50"
    assert params["notify_url"] == "https://bot.example.com/webhook/epay"
    assert params["return_url"] == "https://app.example.com/payment-return"
    assert params["sign_type"] == "MD5"
    assert params["sign"] == _expected_signature(params, "merchant-secret")
    assert data["provider_payment_id"] == "77"


def test_create_payment_rejects_unsupported_currency():
    service = _make_service(SUPPORTED_CURRENCIES="CNY")

    success, data = asyncio.run(
        service.create_payment(payment_db_id=1, amount=10.0, currency="USD")
    )

    assert not success
    assert data["message"] == "unsupported_currency"


def _signed_webhook_payload(**overrides):
    payload = {
        "pid": "1001",
        "trade_no": "202607040001",
        "out_trade_no": "88",
        "type": "alipay",
        "name": "Subscription",
        "money": "150.00",
        "trade_status": "TRADE_SUCCESS",
    }
    payload.update(overrides)
    payload["sign"] = _expected_signature(payload, "merchant-secret")
    payload["sign_type"] = "MD5"
    return payload


def _webhook_service(session, payment, monkeypatch):
    monkeypatch.setattr(
        epay_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(return_value=payment),
    )
    service = _make_service()
    service.async_session_factory = session
    return service


def test_webhook_success_finalizes_payment(monkeypatch):
    session = _FakeDbSession()
    payment = SimpleNamespace(
        payment_id=88,
        user_id=42,
        status="pending_epay",
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
    monkeypatch.setattr(epay_service.payment_dal, "update_provider_payment_and_status", update_mock)
    monkeypatch.setattr(epay_service, "finalize_successful_payment", finalize_mock)

    response = asyncio.run(
        EpayService.webhook_route(service, _FakeWebhookRequest(_signed_webhook_payload()))
    )

    assert response.status == 200
    assert response.text == "success"
    update_mock.assert_awaited_once_with(
        session,
        88,
        "202607040001",
        epay_service.PAYMENT_STATUS_PENDING_FINALIZATION,
    )
    finalize_mock.assert_awaited_once()


def test_webhook_success_with_amount_mismatch_is_rejected(monkeypatch):
    session = _FakeDbSession()
    payment = SimpleNamespace(
        payment_id=88,
        user_id=42,
        status="pending_epay",
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
        epay_service.payment_dal,
        "update_provider_payment_and_status",
        AsyncMock(side_effect=AssertionError("mismatched amount must not update payment")),
    )
    monkeypatch.setattr(
        epay_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("mismatched amount must not finalize")),
    )

    response = asyncio.run(
        EpayService.webhook_route(
            service,
            _FakeWebhookRequest(_signed_webhook_payload(money="151.00")),
        )
    )

    assert response.status == 400


def test_webhook_returns_503_if_service_not_configured():
    service = _make_service(ENABLED=False)

    response = asyncio.run(
        EpayService.webhook_route(service, _FakeWebhookRequest(_signed_webhook_payload()))
    )

    assert response.status == 503
    assert response.text == "epay_disabled"


def test_create_payment_rejects_when_service_not_configured():
    service = _make_service(ENABLED=False)

    success, data = asyncio.run(
        service.create_payment(payment_db_id=99, amount=15.0, currency="CNY")
    )

    assert not success
    assert data["message"] == "service_not_configured"


def test_webhook_missing_payment_returns_404(monkeypatch):
    session = _FakeDbSession()
    service = _make_service()
    service.async_session_factory = session
    monkeypatch.setattr(
        epay_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(return_value=None),
    )

    response = asyncio.run(
        EpayService.webhook_route(service, _FakeWebhookRequest(_signed_webhook_payload()))
    )

    assert response.status == 404
    assert response.text == "payment_not_found"


def test_webhook_non_success_status_is_ignored(monkeypatch):
    session = _FakeDbSession()
    payment = SimpleNamespace(
        payment_id=88,
        user_id=42,
        status="pending_epay",
        sale_mode="subscription",
        purchased_hwid_devices=None,
        purchased_gb=None,
        subscription_duration_months=1,
        amount=150.0,
        currency="CNY",
        user=None,
    )
    service = _make_service()
    service.async_session_factory = session
    monkeypatch.setattr(
        epay_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(return_value=payment),
    )
    update_mock = AsyncMock()
    finalize_mock = AsyncMock()
    monkeypatch.setattr(epay_service.payment_dal, "update_provider_payment_and_status", update_mock)
    monkeypatch.setattr(epay_service, "finalize_successful_payment", finalize_mock)

    response = asyncio.run(
        EpayService.webhook_route(
            service,
            _FakeWebhookRequest(_signed_webhook_payload(trade_status="TRADE_WAIT")),
        )
    )

    assert response.status == 200
    assert response.text == "success"
    update_mock.assert_not_awaited()
    finalize_mock.assert_not_awaited()


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
    service = _make_service()
    service.async_session_factory = session
    monkeypatch.setattr(
        epay_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(return_value=payment),
    )
    update_mock = AsyncMock(side_effect=AssertionError("duplicate webhook must not update payment"))
    finalize_mock = AsyncMock(side_effect=AssertionError("duplicate webhook must not finalize"))
    monkeypatch.setattr(epay_service.payment_dal, "update_provider_payment_and_status", update_mock)
    monkeypatch.setattr(epay_service, "finalize_successful_payment", finalize_mock)

    response = asyncio.run(
        EpayService.webhook_route(service, _FakeWebhookRequest(_signed_webhook_payload()))
    )

    assert response.status == 200
    assert response.text == "success"
