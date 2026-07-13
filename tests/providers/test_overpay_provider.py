"""Contract tests for the Overpay provider.

Outgoing checkout / gateway requests authenticate with HTTP Basic auth (Shop ID
as username, Secret Key as password) and transmit amounts in minimal currency
units. Notifications arrive as JSON POSTs authenticated with the same HTTP Basic
credentials. These tests pin both contracts and the saved-token auto-renew flow.
"""

import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.payment_providers import overpay
from bot.payment_providers.overpay import OverpayConfig, OverpayService
from bot.payment_providers.overpay import service as overpay_service
from bot.payment_providers.shared import RecurringChargeContext


def _make_service(**config_overrides) -> OverpayService:
    config_values = {
        "ENABLED": True,
        "SHOP_ID": "361",
        "SECRET_KEY": "shop-secret",
    }
    config_values.update(config_overrides)
    service = object.__new__(OverpayService)
    service.config = OverpayConfig(**config_values)
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
        self._payload = payload if payload is not None else {}

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
    def __init__(self, body, *, shop_id="361", secret="shop-secret", remote="127.0.0.1"):
        self._body = json.dumps(body).encode("utf-8")
        token = base64.b64encode(f"{shop_id}:{secret}".encode()).decode("ascii")
        self.headers = {"Authorization": f"Basic {token}"} if secret is not None else {}
        self.remote = remote
        self.content_type = "application/json"

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


def test_create_checkout_uses_basic_auth_and_checkout_endpoint(monkeypatch):
    service = _make_service()
    captured = {}
    response = _FakeResponse(
        payload={"checkout": {"token": "tok-1", "redirect_url": "https://checkout.overpay.io/v2/x"}}
    )
    monkeypatch.setattr(
        service, "_get_session", AsyncMock(return_value=_capture_session(captured, response))
    )

    success, data = asyncio.run(
        service.create_checkout(
            payment_db_id=77,
            amount=32.45,
            currency="USD",
            description="Subscription 1m",
            language="ru",
        )
    )

    assert success
    assert data == {"token": "tok-1", "redirect_url": "https://checkout.overpay.io/v2/x"}
    assert captured["url"] == "https://checkout.overpay.io/ctp/api/checkouts"
    expected_token = base64.b64encode(b"361:shop-secret").decode("ascii")
    assert captured["headers"]["Authorization"] == f"Basic {expected_token}"
    checkout = captured["json"]["checkout"]
    assert checkout["order"]["amount"] == 3245  # minor units
    assert checkout["order"]["currency"] == "USD"
    assert checkout["order"]["tracking_id"] == "77"
    assert checkout["settings"]["notification_url"] == "https://bot.example.com/webhook/overpay"
    assert checkout["settings"]["language"] == "ru"
    assert "additional_data" not in checkout  # recurring off by default


def test_create_checkout_requests_recurring_token_when_enabled(monkeypatch):
    service = _make_service(RECURRING_ENABLED=True)
    captured = {}
    response = _FakeResponse(
        payload={"checkout": {"token": "tok-1", "redirect_url": "https://checkout.overpay.io/v2/x"}}
    )
    monkeypatch.setattr(
        service, "_get_session", AsyncMock(return_value=_capture_session(captured, response))
    )

    success, _data = asyncio.run(
        service.create_checkout(payment_db_id=1, amount=10.0, currency="USD", description="x")
    )

    assert success
    assert captured["json"]["checkout"]["additional_data"] == {"contract": ["recurring"]}


def test_overpay_spec_supports_recurring():
    assert overpay.SPEC.supports_recurring


def test_token_charge_uses_gateway_endpoint_and_contract(monkeypatch):
    service = _make_service(RECURRING_ENABLED=True)
    captured = {}
    response = _FakeResponse(payload={"transaction": {"uid": "tx-auto", "status": "successful"}})
    monkeypatch.setattr(
        service, "_get_session", AsyncMock(return_value=_capture_session(captured, response))
    )

    success, data = asyncio.run(
        service.charge_token(
            payment_db_id=99,
            token="card-token",
            amount=150.0,
            currency="RUB",
            description="Auto-renewal",
        )
    )

    assert success
    assert data == {"uid": "tx-auto", "status": "successful"}
    assert captured["url"] == "https://gateway.overpay.io/transactions/payments"
    request = captured["json"]["request"]
    assert request["credit_card"] == {"token": "card-token"}
    assert request["amount"] == 15000
    assert request["tracking_id"] == "99"
    assert request["additional_data"] == {"contract": ["recurring"]}
    assert request["notification_url"] == "https://bot.example.com/webhook/overpay"


def test_create_checkout_rejects_unsupported_currency(monkeypatch):
    service = _make_service()
    monkeypatch.setattr(
        service,
        "_get_session",
        AsyncMock(side_effect=AssertionError("must not reach the API for unsupported currency")),
    )

    success, data = asyncio.run(
        service.create_checkout(payment_db_id=1, amount=10.0, currency="JPYX", description="x")
    )

    assert not success
    assert data["message"] == "unsupported_currency"


def test_service_is_unconfigured_without_credentials():
    assert not _make_service(SHOP_ID=None).configured
    assert not _make_service(SECRET_KEY=None).configured
    assert not _make_service(ENABLED=False).configured
    assert _make_service().configured
    assert _make_service(ENABLED=False, ADMIN_ONLY_ENABLED=True).configured


def test_recurring_active_requires_flag():
    assert not _make_service().recurring_active
    assert _make_service(RECURRING_ENABLED=True).recurring_active
    assert not _make_service(RECURRING_ENABLED=True, SECRET_KEY=None).recurring_active


# ---------------------------------------------------------------------------
# Webhook authentication
# ---------------------------------------------------------------------------


def test_webhook_auth_accepts_matching_basic_credentials():
    service = _make_service()
    request = _FakeWebhookRequest({"transaction": {}})

    assert service.verify_webhook_auth(request)


def test_webhook_auth_rejects_wrong_secret():
    service = _make_service()
    request = _FakeWebhookRequest({"transaction": {}}, secret="wrong-secret")

    assert not service.verify_webhook_auth(request)


def test_webhook_auth_rejects_missing_header():
    service = _make_service()
    request = _FakeWebhookRequest({"transaction": {}}, secret=None)

    assert not service.verify_webhook_auth(request)


def test_webhook_invalid_auth_is_rejected():
    service = _make_service()
    request = _FakeWebhookRequest(
        {"transaction": {"tracking_id": "88", "status": "successful"}}, secret="nope"
    )

    response = asyncio.run(service.webhook_route(request))

    assert response.status == 403


# ---------------------------------------------------------------------------
# Webhook route behaviour
# ---------------------------------------------------------------------------


def _webhook_service(session, payment, monkeypatch, **overrides):
    monkeypatch.setattr(
        overpay_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(return_value=payment),
    )
    service = SimpleNamespace(
        configured=True,
        shop_id="361",
        secret_key="shop-secret",
        verify_webhook_auth=lambda _request: True,
        async_session_factory=session,
        config=SimpleNamespace(trusted_ips_list=[], VERIFY_WEBHOOK_SIGNATURE=True),
        settings=SimpleNamespace(trusted_proxies=[], traffic_sale_mode=False),
        bot=SimpleNamespace(),
        i18n=SimpleNamespace(),
        subscription_service=SimpleNamespace(),
        referral_service=SimpleNamespace(),
        recurring_active=False,
    )
    service._parse_webhook_payload = OverpayService._parse_webhook_payload.__get__(
        service, OverpayService
    )
    service._amount_matches_payment = OverpayService._amount_matches_payment.__get__(
        service, OverpayService
    )
    service._persist_recurring_payment_method = (
        OverpayService._persist_recurring_payment_method.__get__(service, OverpayService)
    )
    for key, value in overrides.items():
        setattr(service, key, value)
    return service


def _payment(**overrides):
    base = {
        "payment_id": 88,
        "user_id": 42,
        "status": "pending_overpay",
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


def test_webhook_success_finalizes_payment(monkeypatch):
    session = _FakeDbSession()
    payment = _payment()
    service = _webhook_service(session, payment, monkeypatch)
    claim_mock = AsyncMock(return_value=payment)
    finalize_mock = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(overpay_service.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(overpay_service, "finalize_successful_payment", finalize_mock)

    response = asyncio.run(
        OverpayService.webhook_route(
            service,
            _FakeWebhookRequest(
                {
                    "transaction": {
                        "uid": "tx-1",
                        "status": "successful",
                        "amount": 15000,
                        "currency": "RUB",
                        "tracking_id": "88",
                    }
                }
            ),
        )
    )

    assert response.status == 200
    claim_mock.assert_awaited_once_with(session, 88, provider_payment_id="tx-1")
    finalize_mock.assert_awaited_once()


def test_webhook_success_saves_token_when_recurring_enabled(monkeypatch):
    session = _FakeDbSession()
    payment = _payment()
    service = _webhook_service(session, payment, monkeypatch, recurring_active=True)
    claim_mock = AsyncMock(return_value=payment)
    monkeypatch.setattr(overpay_service.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(
        overpay_service, "finalize_successful_payment", AsyncMock(return_value=SimpleNamespace())
    )
    upsert_mock = AsyncMock()
    monkeypatch.setattr(overpay_service.user_billing_dal, "upsert_user_payment_method", upsert_mock)

    response = asyncio.run(
        OverpayService.webhook_route(
            service,
            _FakeWebhookRequest(
                {
                    "transaction": {
                        "uid": "tx-1",
                        "status": "successful",
                        "amount": 15000,
                        "currency": "RUB",
                        "tracking_id": "88",
                        "credit_card": {
                            "token": "card-token-1",
                            "last_4": "4242",
                            "brand": "visa",
                        },
                    }
                }
            ),
        )
    )

    assert response.status == 200
    claim_mock.assert_awaited_once_with(session, 88, provider_payment_id="tx-1")
    upsert_mock.assert_awaited_once_with(
        session,
        user_id=42,
        provider_payment_method_id="card-token-1",
        provider="overpay",
        card_last4="4242",
        card_network="visa",
        set_default=True,
    )


def test_webhook_amount_mismatch_is_rejected(monkeypatch):
    session = _FakeDbSession()
    service = _webhook_service(session, _payment(), monkeypatch)
    monkeypatch.setattr(
        overpay_service.payment_dal,
        "update_provider_payment_and_status",
        AsyncMock(side_effect=AssertionError("mismatched amount must not update payment")),
    )
    monkeypatch.setattr(
        overpay_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("mismatched amount must not finalize")),
    )

    response = asyncio.run(
        OverpayService.webhook_route(
            service,
            _FakeWebhookRequest(
                {
                    "transaction": {
                        "uid": "tx-1",
                        "status": "successful",
                        "amount": 999999,
                        "tracking_id": "88",
                    }
                }
            ),
        )
    )

    assert response.status == 400


def test_webhook_failed_status_marks_payment_failed(monkeypatch):
    session = _FakeDbSession()
    service = _webhook_service(session, _payment(), monkeypatch)
    update_mock = AsyncMock()
    notify_mock = AsyncMock()
    monkeypatch.setattr(
        overpay_service.payment_dal, "update_provider_payment_and_status", update_mock
    )
    monkeypatch.setattr(overpay_service, "notify_user_payment_failed", notify_mock)
    monkeypatch.setattr(
        overpay_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("failed webhook must not finalize")),
    )

    response = asyncio.run(
        OverpayService.webhook_route(
            service,
            _FakeWebhookRequest(
                {"transaction": {"uid": "tx-1", "status": "failed", "tracking_id": "88"}}
            ),
        )
    )

    assert response.status == 200
    update_mock.assert_awaited_once_with(session, 88, "tx-1", "failed")
    notify_mock.assert_awaited_once()


def test_webhook_duplicate_success_does_not_finalize_again(monkeypatch):
    session = _FakeDbSession()
    service = _webhook_service(session, _payment(status="succeeded"), monkeypatch)
    monkeypatch.setattr(
        overpay_service.payment_dal,
        "update_provider_payment_and_status",
        AsyncMock(side_effect=AssertionError("duplicate webhook must not update payment")),
    )
    monkeypatch.setattr(
        overpay_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("duplicate webhook must not finalize")),
    )

    response = asyncio.run(
        OverpayService.webhook_route(
            service,
            _FakeWebhookRequest(
                {"transaction": {"uid": "tx-1", "status": "successful", "tracking_id": "88"}}
            ),
        )
    )

    assert response.status == 200


def test_webhook_unknown_payment_returns_404(monkeypatch):
    session = _FakeDbSession()
    service = _webhook_service(session, None, monkeypatch)

    response = asyncio.run(
        OverpayService.webhook_route(
            service,
            _FakeWebhookRequest(
                {"transaction": {"uid": "tx-1", "status": "successful", "tracking_id": "404"}}
            ),
        )
    )

    assert response.status == 404


# ---------------------------------------------------------------------------
# Pending payment reuse & auto-renew
# ---------------------------------------------------------------------------


def test_reuse_returns_stored_url_for_pending_payment():
    service = _make_service()
    payment = SimpleNamespace(
        payment_id=88,
        provider_payment_id="tok-1",
        provider_payment_url="https://checkout.overpay.io/v2/x",
    )

    assert (
        asyncio.run(service.try_reuse_pending_payment(payment))
        == "https://checkout.overpay.io/v2/x"
    )


def test_charge_saved_payment_method_creates_local_record_before_token_charge(monkeypatch):
    service = _make_service(RECURRING_ENABLED=True)
    session = SimpleNamespace()
    payment = SimpleNamespace(payment_id=123)
    create_mock = AsyncMock(return_value=payment)
    update_mock = AsyncMock()
    monkeypatch.setattr(overpay_service.payment_dal, "create_payment_record", create_mock)
    monkeypatch.setattr(
        overpay_service.payment_dal, "update_provider_payment_and_status", update_mock
    )
    monkeypatch.setattr(
        service,
        "charge_token",
        AsyncMock(return_value=(True, {"uid": "tx-auto", "status": "successful"})),
    )

    result = asyncio.run(
        service.charge_saved_payment_method(
            RecurringChargeContext(
                session=session,
                user_id=42,
                subscription_id=7,
                saved_method=SimpleNamespace(provider_payment_method_id="card-token"),
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
    assert payload["status"] == "pending_overpay"
    assert payload["provider"] == "overpay"
    assert payload["user_id"] == 42
    service.charge_token.assert_awaited_once_with(
        payment_db_id=123,
        token="card-token",
        amount=199.0,
        currency="RUB",
        description="Auto-renewal for 1 months",
    )
    update_mock.assert_awaited_once_with(session, 123, "tx-auto", "pending_overpay")


def test_charge_saved_payment_method_marks_failed_on_decline(monkeypatch):
    service = _make_service(RECURRING_ENABLED=True)
    session = SimpleNamespace()
    payment = SimpleNamespace(payment_id=123)
    monkeypatch.setattr(
        overpay_service.payment_dal, "create_payment_record", AsyncMock(return_value=payment)
    )
    monkeypatch.setattr(
        overpay_service.payment_dal, "update_provider_payment_and_status", AsyncMock()
    )
    failed_mock = AsyncMock()
    monkeypatch.setattr(overpay_service.payment_dal, "update_payment_status_by_db_id", failed_mock)
    monkeypatch.setattr(
        service,
        "charge_token",
        AsyncMock(return_value=(True, {"uid": "tx-auto", "status": "failed"})),
    )

    result = asyncio.run(
        service.charge_saved_payment_method(
            RecurringChargeContext(
                session=session,
                user_id=42,
                subscription_id=7,
                saved_method=SimpleNamespace(provider_payment_method_id="card-token"),
                amount=199.0,
                currency="RUB",
                months=1,
                sale_mode="subscription",
                description="Auto-renewal for 1 months",
            )
        )
    )

    assert not result.initiated
    failed_mock.assert_awaited_once_with(session, 123, "failed_creation")
