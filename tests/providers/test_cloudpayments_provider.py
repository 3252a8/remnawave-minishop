"""Contract tests for the CloudPayments provider.

Outgoing Orders API requests authenticate with HTTP Basic auth (Public ID as
username, API Secret as password). Pay/Fail notifications arrive as
``application/x-www-form-urlencoded`` bodies signed with a base64-encoded
HMAC-SHA256 digest of the raw body under the API Secret, carried in the
``Content-HMAC`` header. These tests pin both contracts.
"""

import asyncio
import base64
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import unquote_plus, urlencode

from bot.payment_providers import cloudpayments
from bot.payment_providers.cloudpayments import CloudPaymentsConfig, CloudPaymentsService
from bot.payment_providers.cloudpayments import service as cloudpayments_service
from bot.payment_providers.shared import RecurringChargeContext


def _hmac_b64(message: bytes, key: str) -> str:
    return base64.b64encode(hmac.new(key.encode("utf-8"), message, hashlib.sha256).digest()).decode(
        "ascii"
    )


def _make_service(**config_overrides) -> CloudPaymentsService:
    config_values = {
        "ENABLED": True,
        "PUBLIC_ID": "pk_test",
        "API_SECRET": "api-secret",
    }
    config_values.update(config_overrides)
    service = object.__new__(CloudPaymentsService)
    service.config = CloudPaymentsConfig(**config_values)
    service.settings = SimpleNamespace(
        DEFAULT_CURRENCY_SYMBOL="RUB",
        WEBHOOK_BASE_URL="https://bot.example.com",
        PAYMENT_REQUEST_TIMEOUT_SECONDS=30,
        trusted_proxies=[],
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
            else {
                "Success": True,
                "Model": {
                    "Id": "ord-1",
                    "Number": 42,
                    "Url": "https://orders.cloudpayments.ru/d/x",
                },
            }
        )

    async def text(self):
        return json.dumps(self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


def _capture_session(captured, response=None):
    session = SimpleNamespace()

    def post(url, json=None, headers=None, trace_request_ctx=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return response or _FakeResponse()

    session.post = post
    return session


class _FakeWebhookRequest:
    def __init__(self, fields, signature=None, secret="api-secret", remote="127.0.0.1"):
        self._body = urlencode(fields).encode("utf-8")
        if signature is None:
            signature = _hmac_b64(self._body, secret)
        self.headers = {"Content-HMAC": signature} if signature else {}
        self.remote = remote
        self.content_type = "application/x-www-form-urlencoded"

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


# ---------------------------------------------------------------------------
# Outgoing request contract
# ---------------------------------------------------------------------------


def test_create_order_uses_basic_auth_and_orders_endpoint(monkeypatch):
    service = _make_service()
    captured = {}
    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=_capture_session(captured)))

    success, data = asyncio.run(
        service.create_order(
            payment_db_id=77,
            user_id=555,
            amount=150.0,
            currency="RUB",
            description="Subscription 1m",
        )
    )

    assert success
    assert data == {"Id": "ord-1", "Number": 42, "Url": "https://orders.cloudpayments.ru/d/x"}
    assert captured["url"] == "https://api.cloudpayments.ru/orders/create"
    expected_token = base64.b64encode(b"pk_test:api-secret").decode("ascii")
    assert captured["headers"]["Authorization"] == f"Basic {expected_token}"
    body = captured["json"]
    assert body["Amount"] == 150.0
    assert body["Currency"] == "RUB"
    assert body["InvoiceId"] == "77"
    assert body["AccountId"] == "555"
    assert body["RequireConfirmation"] is False


def test_cloudpayments_spec_supports_recurring():
    assert cloudpayments.SPEC.supports_recurring


def test_token_charge_marks_merchant_initiated_scheduled_payment(monkeypatch):
    service = _make_service(RECURRING_ENABLED=True)
    captured = {}
    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=_capture_session(captured)))

    success, data = asyncio.run(
        service.charge_token(
            payment_db_id=99,
            user_id=555,
            token="cp-token",
            amount=150.0,
            currency="RUB",
            description="Auto-renewal",
            metadata={"subscription_id": "10"},
        )
    )

    assert success
    assert data == {"Id": "ord-1", "Number": 42, "Url": "https://orders.cloudpayments.ru/d/x"}
    assert captured["url"] == "https://api.cloudpayments.ru/payments/tokens/charge"
    body = captured["json"]
    assert body["Token"] == "cp-token"
    assert body["InvoiceId"] == "99"
    assert body["AccountId"] == "555"
    assert body["TrInitiatorCode"] == 0
    assert body["PaymentScheduled"] == 1
    assert body["JsonData"] == {"cloudpayments": {"subscription_id": "10"}}


def test_create_order_rejects_unsupported_currency(monkeypatch):
    service = _make_service()
    monkeypatch.setattr(
        service,
        "_get_session",
        AsyncMock(side_effect=AssertionError("must not reach the API for unsupported currency")),
    )

    success, data = asyncio.run(
        service.create_order(
            payment_db_id=1, user_id=1, amount=10.0, currency="JPY", description="x"
        )
    )

    assert not success
    assert data["message"] == "unsupported_currency"


def test_create_order_surfaces_api_error(monkeypatch):
    service = _make_service()
    captured = {}
    response = _FakeResponse(status=200, payload={"Success": False, "Message": "Invalid public id"})
    monkeypatch.setattr(
        service,
        "_get_session",
        AsyncMock(return_value=_capture_session(captured, response=response)),
    )

    success, _data = asyncio.run(
        service.create_order(
            payment_db_id=1, user_id=1, amount=10.0, currency="RUB", description="x"
        )
    )

    assert not success


def test_service_is_unconfigured_without_credentials():
    assert not _make_service(PUBLIC_ID=None).configured
    assert not _make_service(API_SECRET=None).configured
    assert not _make_service(ENABLED=False).configured
    assert _make_service().configured
    assert _make_service(ENABLED=False, ADMIN_ONLY_ENABLED=True).configured


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------


def test_signature_accepts_valid_base64_hmac():
    service = _make_service()
    body = b"TransactionId=1&Status=Completed"

    assert service.verify_signature(body, _hmac_b64(body, "api-secret"))


def test_signature_accepts_url_decoded_hmac_variant():
    service = _make_service()
    body = b"InvoiceId=1&Description=Auto+renewal+%D1%82%D0%B5%D1%81%D1%82"
    decoded = unquote_plus(body.decode("utf-8")).encode("utf-8")

    assert service.verify_signature(body, _hmac_b64(decoded, "api-secret"))


def test_signature_rejects_wrong_or_empty_signature():
    service = _make_service()
    body = b"TransactionId=1&Status=Completed"

    assert not service.verify_signature(body, base64.b64encode(b"nope").decode("ascii"))
    assert not service.verify_signature(body, "")


def test_signature_fails_closed_without_secret():
    service = _make_service(API_SECRET=None)
    body = b"TransactionId=1"

    assert not service.verify_signature(body, _hmac_b64(body, ""))


# ---------------------------------------------------------------------------
# Webhook route behaviour
# ---------------------------------------------------------------------------


def _webhook_service(session, payment, monkeypatch, **overrides):
    monkeypatch.setattr(
        cloudpayments_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(return_value=payment),
    )
    service = SimpleNamespace(
        configured=True,
        verify_webhook_signature=False,
        verify_signature=lambda _raw, _sig: True,
        async_session_factory=session,
        config=SimpleNamespace(trusted_ips_list=[]),
        settings=SimpleNamespace(trusted_proxies=[], traffic_sale_mode=False),
        bot=SimpleNamespace(),
        i18n=SimpleNamespace(),
        subscription_service=SimpleNamespace(),
        referral_service=SimpleNamespace(),
        recurring_active=False,
    )
    service._persist_recurring_payment_method = (
        CloudPaymentsService._persist_recurring_payment_method.__get__(
            service,
            CloudPaymentsService,
        )
    )
    for key, value in overrides.items():
        setattr(service, key, value)
    return service


def _payment(**overrides):
    base = {
        "payment_id": 88,
        "user_id": 42,
        "status": "pending_cloudpayments",
        "sale_mode": "subscription",
        "purchased_hwid_devices": None,
        "purchased_gb": None,
        "subscription_duration_months": 1,
        "amount": 150.0,
        "currency": "RUB",
        "user": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_webhook_invalid_signature_is_rejected():
    service = _make_service()
    request = _FakeWebhookRequest({"InvoiceId": "88", "Status": "Completed"}, signature="not-valid")

    response = asyncio.run(service.webhook_route(request))

    assert response.status == 403


def test_webhook_duplicate_success_does_not_finalize_again(monkeypatch):
    session = _FakeDbSession()
    service = _webhook_service(session, _payment(status="succeeded"), monkeypatch)
    monkeypatch.setattr(
        cloudpayments_service.payment_dal,
        "update_provider_payment_and_status",
        AsyncMock(side_effect=AssertionError("duplicate webhook must not update payment")),
    )
    monkeypatch.setattr(
        cloudpayments_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("duplicate webhook must not finalize")),
    )

    response = asyncio.run(
        CloudPaymentsService.webhook_route(
            service,
            _FakeWebhookRequest(
                {"InvoiceId": "88", "TransactionId": "tx-1", "Status": "Completed"}
            ),
        )
    )

    assert response.status == 200
    assert json.loads(response.body) == {"code": 0}


def test_webhook_success_finalizes_payment(monkeypatch):
    session = _FakeDbSession()
    payment = _payment()
    service = _webhook_service(session, payment, monkeypatch)
    claim_mock = AsyncMock(return_value=payment)
    finalize_mock = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(cloudpayments_service.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(cloudpayments_service, "finalize_successful_payment", finalize_mock)

    response = asyncio.run(
        CloudPaymentsService.webhook_route(
            service,
            _FakeWebhookRequest(
                {
                    "InvoiceId": "88",
                    "TransactionId": "tx-1",
                    "Status": "Completed",
                    "Amount": "150.00",
                    "Currency": "RUB",
                }
            ),
        )
    )

    assert response.status == 200
    assert json.loads(response.body) == {"code": 0}
    claim_mock.assert_awaited_once_with(
        session,
        88,
        provider_payment_id="tx-1",
    )
    finalize_mock.assert_awaited_once()


def test_webhook_success_saves_token_when_recurring_enabled(monkeypatch):
    session = _FakeDbSession()
    payment = _payment()
    service = _webhook_service(session, payment, monkeypatch, recurring_active=True)
    claim_mock = AsyncMock(return_value=payment)
    finalize_mock = AsyncMock(return_value=SimpleNamespace())
    upsert_mock = AsyncMock()
    monkeypatch.setattr(cloudpayments_service.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(cloudpayments_service, "finalize_successful_payment", finalize_mock)
    monkeypatch.setattr(
        cloudpayments_service.user_billing_dal, "upsert_user_payment_method", upsert_mock
    )

    response = asyncio.run(
        CloudPaymentsService.webhook_route(
            service,
            _FakeWebhookRequest(
                {
                    "InvoiceId": "88",
                    "TransactionId": "tx-1",
                    "Status": "Completed",
                    "Amount": "150.00",
                    "Currency": "RUB",
                    "Token": "cp-token-1",
                    "CardLastFour": "4242",
                    "CardType": "Visa",
                }
            ),
        )
    )

    assert response.status == 200
    claim_mock.assert_awaited_once_with(session, 88, provider_payment_id="tx-1")
    upsert_mock.assert_awaited_once_with(
        session,
        user_id=42,
        provider_payment_method_id="cp-token-1",
        provider="cloudpayments",
        card_last4="4242",
        card_network="Visa",
        set_default=True,
    )


def test_webhook_payment_details_mismatch_is_rejected(monkeypatch):
    session = _FakeDbSession()
    service = _webhook_service(session, _payment(), monkeypatch)
    claim_mock = AsyncMock(side_effect=AssertionError("mismatched payment must not claim"))
    monkeypatch.setattr(cloudpayments_service.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(
        cloudpayments_service.payment_dal,
        "update_provider_payment_and_status",
        AsyncMock(side_effect=AssertionError("mismatched amount must not update payment")),
    )
    monkeypatch.setattr(
        cloudpayments_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("mismatched amount must not finalize")),
    )

    response = asyncio.run(
        CloudPaymentsService.webhook_route(
            service,
            _FakeWebhookRequest(
                {
                    "InvoiceId": "88",
                    "TransactionId": "tx-1",
                    "Status": "Completed",
                    "Amount": "149.99",
                    "Currency": "RUB",
                }
            ),
        )
    )

    assert response.status == 200
    assert json.loads(response.body) == {"code": 12}
    claim_mock.assert_not_awaited()


def test_webhook_missing_or_invalid_payment_details_are_rejected(monkeypatch):
    invalid_details = (
        {"Currency": "RUB"},
        {"Amount": "not-a-number", "Currency": "RUB"},
        {"Amount": "150.00", "Currency": "USD"},
        {"Amount": "150.00"},
    )

    for details in invalid_details:
        session = _FakeDbSession()
        service = _webhook_service(session, _payment(), monkeypatch)
        claim_mock = AsyncMock(side_effect=AssertionError("invalid payment must not claim"))
        finalize_mock = AsyncMock(side_effect=AssertionError("invalid payment must not finalize"))
        monkeypatch.setattr(
            cloudpayments_service.payment_dal,
            "claim_payment_finalization",
            claim_mock,
        )
        monkeypatch.setattr(cloudpayments_service, "finalize_successful_payment", finalize_mock)

        response = asyncio.run(
            CloudPaymentsService.webhook_route(
                service,
                _FakeWebhookRequest(
                    {
                        "InvoiceId": "88",
                        "TransactionId": "tx-1",
                        "Status": "Completed",
                        **details,
                    }
                ),
            )
        )

        assert response.status == 200
        assert json.loads(response.body) == {"code": 12}
        claim_mock.assert_not_awaited()
        finalize_mock.assert_not_awaited()


def test_webhook_failed_status_marks_payment_failed(monkeypatch):
    session = _FakeDbSession()
    service = _webhook_service(session, _payment(), monkeypatch)
    update_mock = AsyncMock()
    notify_mock = AsyncMock()
    monkeypatch.setattr(
        cloudpayments_service.payment_dal, "update_provider_payment_and_status", update_mock
    )
    monkeypatch.setattr(cloudpayments_service, "notify_user_payment_failed", notify_mock)
    monkeypatch.setattr(
        cloudpayments_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("failed webhook must not finalize")),
    )

    response = asyncio.run(
        CloudPaymentsService.webhook_route(
            service,
            _FakeWebhookRequest({"InvoiceId": "88", "TransactionId": "tx-1", "Status": "Declined"}),
        )
    )

    assert response.status == 200
    assert json.loads(response.body) == {"code": 0}
    update_mock.assert_awaited_once_with(session, 88, "tx-1", "failed")
    notify_mock.assert_awaited_once()


def test_webhook_unknown_payment_returns_404(monkeypatch):
    session = _FakeDbSession()
    service = _webhook_service(session, None, monkeypatch)

    response = asyncio.run(
        CloudPaymentsService.webhook_route(
            service,
            _FakeWebhookRequest({"InvoiceId": "404", "Status": "Completed"}),
        )
    )

    assert response.status == 404


# ---------------------------------------------------------------------------
# Pending payment reuse
# ---------------------------------------------------------------------------


def test_reuse_returns_stored_url_for_pending_payment():
    service = _make_service()
    payment = SimpleNamespace(
        payment_id=88,
        provider_payment_id="ord-1",
        provider_payment_url="https://orders.cloudpayments.ru/d/x",
    )

    assert (
        asyncio.run(service.try_reuse_pending_payment(payment))
        == "https://orders.cloudpayments.ru/d/x"
    )


def test_reuse_requires_stored_url():
    service = _make_service()

    assert (
        asyncio.run(
            service.try_reuse_pending_payment(
                SimpleNamespace(payment_id=1, provider_payment_id="ord-1", provider_payment_url="")
            )
        )
        is None
    )


def test_charge_saved_payment_method_creates_local_record_before_token_charge(monkeypatch):
    service = _make_service(RECURRING_ENABLED=True)
    session = SimpleNamespace()
    payment = SimpleNamespace(payment_id=123)
    create_mock = AsyncMock(return_value=payment)
    update_mock = AsyncMock()
    monkeypatch.setattr(cloudpayments_service.payment_dal, "create_payment_record", create_mock)
    monkeypatch.setattr(
        cloudpayments_service.payment_dal,
        "update_provider_payment_and_status",
        update_mock,
    )
    monkeypatch.setattr(
        service,
        "charge_token",
        AsyncMock(return_value=(True, {"TransactionId": "tx-auto", "Status": "Completed"})),
    )

    result = asyncio.run(
        service.charge_saved_payment_method(
            RecurringChargeContext(
                session=session,
                user_id=42,
                subscription_id=7,
                saved_method=SimpleNamespace(provider_payment_method_id="cp-token"),
                amount=199.0,
                currency="RUB",
                months=1,
                sale_mode="subscription@standard",
                description="Auto-renewal for 1 months",
                metadata={"auto_renew_for_subscription_id": "7"},
            )
        )
    )

    assert result.initiated
    assert result.provider_payment_id == "tx-auto"
    create_mock.assert_awaited_once()
    payload = create_mock.await_args.args[1]
    assert payload["status"] == "pending_cloudpayments"
    assert payload["provider"] == "cloudpayments"
    assert payload["user_id"] == 42
    assert payload["subscription_duration_months"] == 1
    assert payload["tariff_key"] == "standard"
    service.charge_token.assert_awaited_once_with(
        payment_db_id=123,
        user_id=42,
        token="cp-token",
        amount=199.0,
        currency="RUB",
        description="Auto-renewal for 1 months",
        metadata={"auto_renew_for_subscription_id": "7"},
    )
    update_mock.assert_awaited_once_with(session, 123, "tx-auto", "pending_cloudpayments")
