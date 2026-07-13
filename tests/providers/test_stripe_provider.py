"""Contract tests for the Stripe provider.

The integration uses Stripe Checkout Sessions for user-facing payments and
PaymentIntents with saved payment methods for app-managed auto-renewal.
Webhook signatures are verified with the Stripe-Signature timestamped HMAC.
"""

import asyncio
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.payment_providers import stripe
from bot.payment_providers.shared import RecurringChargeContext
from bot.payment_providers.stripe import StripeConfig, StripeService
from bot.payment_providers.stripe import service as stripe_service


def _stripe_signature(body: bytes, secret: str, timestamp: int | None = None) -> str:
    ts = int(time.time()) if timestamp is None else int(timestamp)
    digest = hmac.new(
        secret.encode("utf-8"),
        str(ts).encode("utf-8") + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return f"t={ts},v1={digest}"


def _make_service(**config_overrides) -> StripeService:
    config_values = {
        "ENABLED": True,
        "SECRET_KEY": "sk_test_secret",
        "WEBHOOK_SECRET": "whsec_test",
    }
    config_values.update(config_overrides)
    service = object.__new__(StripeService)
    service.config = StripeConfig(**config_values)
    service.settings = SimpleNamespace(
        DEFAULT_CURRENCY_SYMBOL="USD",
        WEBHOOK_BASE_URL="https://bot.example.com",
        PAYMENT_REQUEST_TIMEOUT_SECONDS=30,
        traffic_sale_mode=False,
    )
    service._default_return_url = "testbot"
    return service


class _FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status = status
        self._payload = (
            payload
            if payload is not None
            else {"id": "cs_test_1", "url": "https://checkout.stripe.com/c/pay/cs_test_1"}
        )

    async def text(self):
        return json.dumps(self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


def _capture_session(captured, response=None):
    session = SimpleNamespace()

    def post(url, data=None, headers=None):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        return response or _FakeResponse()

    def get(url, headers=None):
        captured["get_url"] = url
        captured["get_headers"] = headers
        return response or _FakeResponse(payload={"id": "pm_1"})

    session.post = post
    session.get = get
    return session


class _FakeWebhookRequest:
    def __init__(self, payload, *, secret="whsec_test", signature=True):
        self._body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.headers = (
            {"Stripe-Signature": _stripe_signature(self._body, secret)} if signature else {}
        )

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


def _payment(**overrides):
    base = {
        "payment_id": 88,
        "user_id": 42,
        "status": "pending_stripe",
        "sale_mode": "subscription",
        "purchased_hwid_devices": None,
        "purchased_gb": None,
        "subscription_duration_months": 1,
        "amount": 150.0,
        "currency": "USD",
        "user": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _webhook_service(session, payment, monkeypatch, **overrides):
    service = _make_service(RECURRING_ENABLED=True, VERIFY_WEBHOOK_SIGNATURE=False)
    service.async_session_factory = session
    service.bot = SimpleNamespace()
    service.i18n = SimpleNamespace()
    service.subscription_service = SimpleNamespace()
    service.referral_service = SimpleNamespace()
    monkeypatch.setattr(
        stripe_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(
        service,
        "retrieve_payment_method",
        AsyncMock(return_value={"type": "card", "card": {"last4": "4242", "brand": "visa"}}),
    )
    for key, value in overrides.items():
        setattr(service, key, value)
    return service


def test_create_checkout_session_uses_form_encoded_checkout_contract(monkeypatch):
    service = _make_service(RECURRING_ENABLED=True)
    captured = {}
    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=_capture_session(captured)))

    success, data = asyncio.run(
        service.create_checkout_session(
            payment_db_id=77,
            user_id=555,
            amount=10.99,
            currency="USD",
            description="Subscription 1m",
            metadata={"sale_mode": "subscription", "source": "webapp"},
        )
    )

    assert success
    assert data["id"] == "cs_test_1"
    assert captured["url"] == "https://api.stripe.com/v1/checkout/sessions"
    assert captured["headers"]["Authorization"] == "Bearer sk_test_secret"
    assert captured["headers"]["Idempotency-Key"] == "checkout:77"
    body = dict(captured["data"])
    assert body["mode"] == "payment"
    assert body["line_items[0][price_data][currency]"] == "usd"
    assert body["line_items[0][price_data][unit_amount]"] == "1099"
    assert body["payment_method_types[0]"] == "card"
    assert body["customer_creation"] == "always"
    assert body["payment_intent_data[setup_future_usage]"] == "off_session"
    assert body["metadata[payment_db_id]"] == "77"
    assert body["payment_intent_data[metadata][payment_db_id]"] == "77"


def test_amount_conversion_uses_minor_units_and_zero_decimal_currency():
    assert stripe._stripe_amount_to_minor_units(10.99, "USD") == 1099
    assert stripe._stripe_amount_to_minor_units(500, "JPY") == 500


def test_stripe_spec_supports_recurring():
    assert stripe.SPEC.supports_recurring


def test_signature_accepts_valid_stripe_signature():
    service = _make_service()
    body = b'{"id":"evt_1"}'

    assert service.verify_signature(body, _stripe_signature(body, "whsec_test"))


def test_signature_rejects_wrong_or_empty_signature():
    service = _make_service()
    body = b'{"id":"evt_1"}'

    assert not service.verify_signature(body, _stripe_signature(body, "wrong"))
    assert not service.verify_signature(body, "")


def test_webhook_success_finalizes_payment_and_saves_payment_method(monkeypatch):
    session = _FakeDbSession()
    payment = _payment()
    service = _webhook_service(session, payment, monkeypatch)
    claim_mock = AsyncMock(return_value=payment)
    finalize_mock = AsyncMock(return_value=SimpleNamespace())
    upsert_mock = AsyncMock()
    monkeypatch.setattr(stripe.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(stripe_service, "finalize_successful_payment", finalize_mock)
    monkeypatch.setattr(stripe.user_billing_dal, "upsert_user_payment_method", upsert_mock)

    payload = {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_1",
                "amount": 15000,
                "amount_received": 15000,
                "currency": "usd",
                "customer": "cus_1",
                "payment_method": "pm_1",
                "metadata": {"payment_db_id": "88", "sale_mode": "subscription"},
                "status": "succeeded",
            }
        },
    }
    response = asyncio.run(StripeService.webhook_route(service, _FakeWebhookRequest(payload)))

    assert response.status == 200
    claim_mock.assert_awaited_once_with(
        session,
        88,
        provider_payment_id="pi_1",
    )
    upsert_mock.assert_awaited_once_with(
        session,
        user_id=42,
        provider_payment_method_id="cus_1|pm_1",
        provider="stripe",
        card_last4="4242",
        card_network="visa",
        set_default=True,
    )
    finalize_mock.assert_awaited_once()


def test_webhook_duplicate_success_does_not_finalize_again(monkeypatch):
    session = _FakeDbSession()
    service = _webhook_service(session, _payment(status="succeeded"), monkeypatch)
    monkeypatch.setattr(
        stripe.payment_dal,
        "update_provider_payment_and_status",
        AsyncMock(side_effect=AssertionError("duplicate webhook must not update payment")),
    )
    monkeypatch.setattr(
        stripe_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("duplicate webhook must not finalize")),
    )

    payload = {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_1",
                "amount_received": 15000,
                "currency": "usd",
                "metadata": {"payment_db_id": "88"},
            }
        },
    }
    response = asyncio.run(StripeService.webhook_route(service, _FakeWebhookRequest(payload)))

    assert response.status == 200


def test_webhook_amount_mismatch_is_rejected(monkeypatch):
    session = _FakeDbSession()
    service = _webhook_service(session, _payment(), monkeypatch)
    monkeypatch.setattr(
        stripe.payment_dal,
        "update_provider_payment_and_status",
        AsyncMock(side_effect=AssertionError("mismatched amount must not update payment")),
    )
    monkeypatch.setattr(
        stripe_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("mismatched amount must not finalize")),
    )

    payload = {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_1",
                "amount_received": 999,
                "currency": "usd",
                "metadata": {"payment_db_id": "88"},
            }
        },
    }
    response = asyncio.run(StripeService.webhook_route(service, _FakeWebhookRequest(payload)))

    assert response.status == 400


def test_webhook_missing_amount_is_rejected_before_finalization(monkeypatch):
    session = _FakeDbSession()
    service = _webhook_service(session, _payment(), monkeypatch)
    claim_mock = AsyncMock(side_effect=AssertionError("missing amount must not claim payment"))
    finalize_mock = AsyncMock(side_effect=AssertionError("missing amount must not finalize"))
    monkeypatch.setattr(stripe.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(stripe_service, "finalize_successful_payment", finalize_mock)

    payload = {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_1",
                "currency": "usd",
                "metadata": {"payment_db_id": "88"},
            }
        },
    }
    response = asyncio.run(StripeService.webhook_route(service, _FakeWebhookRequest(payload)))

    assert response.status == 400
    assert response.body == b'{"error": "amount_mismatch"}'
    claim_mock.assert_not_awaited()
    finalize_mock.assert_not_awaited()


def test_webhook_missing_currency_is_rejected_before_finalization(monkeypatch):
    session = _FakeDbSession()
    service = _webhook_service(session, _payment(), monkeypatch)
    claim_mock = AsyncMock(side_effect=AssertionError("missing currency must not claim payment"))
    finalize_mock = AsyncMock(side_effect=AssertionError("missing currency must not finalize"))
    monkeypatch.setattr(stripe.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(stripe_service, "finalize_successful_payment", finalize_mock)

    payload = {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_1",
                "amount_received": 15000,
                "metadata": {"payment_db_id": "88"},
            }
        },
    }
    response = asyncio.run(StripeService.webhook_route(service, _FakeWebhookRequest(payload)))

    assert response.status == 400
    assert response.body == b'{"error": "currency_mismatch"}'
    claim_mock.assert_not_awaited()
    finalize_mock.assert_not_awaited()


def test_webhook_failed_status_marks_payment_failed(monkeypatch):
    session = _FakeDbSession()
    service = _webhook_service(session, _payment(), monkeypatch)
    update_mock = AsyncMock()
    notify_mock = AsyncMock()
    monkeypatch.setattr(stripe.payment_dal, "update_provider_payment_and_status", update_mock)
    monkeypatch.setattr(stripe_service, "notify_user_payment_failed", notify_mock)
    monkeypatch.setattr(
        stripe_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("failed webhook must not finalize")),
    )

    payload = {
        "type": "payment_intent.payment_failed",
        "data": {"object": {"id": "pi_1", "metadata": {"payment_db_id": "88"}}},
    }
    response = asyncio.run(StripeService.webhook_route(service, _FakeWebhookRequest(payload)))

    assert response.status == 200
    update_mock.assert_awaited_once_with(session, 88, "pi_1", "failed")
    notify_mock.assert_awaited_once()


def test_charge_saved_payment_method_creates_payment_intent_for_off_session_charge(monkeypatch):
    service = _make_service(RECURRING_ENABLED=True)
    session = SimpleNamespace()
    payment = SimpleNamespace(payment_id=123)
    create_mock = AsyncMock(return_value=payment)
    update_mock = AsyncMock()
    monkeypatch.setattr(stripe.payment_dal, "create_payment_record", create_mock)
    monkeypatch.setattr(stripe.payment_dal, "update_provider_payment_and_status", update_mock)
    monkeypatch.setattr(
        service,
        "create_off_session_payment_intent",
        AsyncMock(return_value=(True, {"id": "pi_auto", "status": "succeeded"})),
    )

    result = asyncio.run(
        service.charge_saved_payment_method(
            RecurringChargeContext(
                session=session,
                user_id=42,
                subscription_id=7,
                saved_method=SimpleNamespace(provider_payment_method_id="cus_1|pm_1"),
                amount=199.0,
                currency="USD",
                months=1,
                sale_mode="subscription@standard",
                description="Auto-renewal for 1 months",
                metadata={"auto_renew_for_subscription_id": "7"},
            )
        )
    )

    assert result.initiated
    assert result.provider_payment_id == "pi_auto"
    payload = create_mock.await_args.args[1]
    assert payload["status"] == "pending_stripe"
    assert payload["provider"] == "stripe"
    assert payload["user_id"] == 42
    assert payload["subscription_duration_months"] == 1
    assert payload["tariff_key"] == "standard"
    service.create_off_session_payment_intent.assert_awaited_once_with(
        payment_db_id=123,
        user_id=42,
        customer_id="cus_1",
        payment_method_id="pm_1",
        amount=199.0,
        currency="USD",
        description="Auto-renewal for 1 months",
        metadata={"auto_renew_for_subscription_id": "7"},
    )
    update_mock.assert_awaited_once_with(session, 123, "pi_auto", "pending_stripe")
