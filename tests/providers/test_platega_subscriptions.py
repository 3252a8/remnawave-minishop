"""Contract coverage for Platega provider-managed recurring subscriptions.

Platega owns the renewal schedule, which makes two invariants load-bearing:
the local renewal worker must never try to charge Platega, and a debit the
provider reports must be credited exactly once.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.infra.auto_renew import auto_renew_toggle_allowed
from bot.payment_providers import provider_manages_recurring, provider_supports_recurring
from bot.payment_providers.platega import service as platega_service
from bot.payment_providers.platega import subscriptions as platega_subscriptions
from bot.payment_providers.shared import service_manages_recurrence, service_supports_recurring


class _FakeSession:
    def __init__(self):
        self.committed = 0
        self.rolled_back = 0

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        self.rolled_back += 1

    async def flush(self):
        pass


class _FakeJsonRequest:
    def __init__(self, payload, *, headers=None):
        self._payload = payload
        self.headers = headers or {}

    async def json(self):
        return self._payload


def _service(session=None, **overrides):
    service = object.__new__(platega_service.PlategaService)
    service.config = platega_service.PlategaConfig(
        ENABLED=True,
        MERCHANT_ID="merchant",
        SECRET="secret",
        SUBSCRIPTION_ENABLED=True,
    )
    service.settings = SimpleNamespace(
        traffic_sale_mode=False,
        DEFAULT_LANGUAGE="en",
        DEFAULT_CURRENCY_SYMBOL="RUB",
    )
    service.bot = SimpleNamespace()
    service.i18n = SimpleNamespace(gettext=lambda lang, key, **kw: key)
    service.async_session_factory = session or _FakeSession()
    service.subscription_service = SimpleNamespace()
    service.referral_service = SimpleNamespace()
    service._default_return_url = "shopbot"
    for name, value in overrides.items():
        setattr(service, name, value)
    return service


def _mandate(**overrides):
    values = {
        "platega_subscription_id": "sub-1",
        "user_id": 42,
        "status": "active",
        "amount": 150.0,
        "currency": "RUB",
        "interval_code": 3,
        "months": 1,
        "sale_mode": "subscription@base",
        "tariff_key": "base",
        "charges_count": 1,
        "next_charge_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _anchor(**overrides):
    values = {
        "payment_id": 88,
        "user_id": 42,
        "provider": "platega",
        "status": "pending_platega",
        "sale_mode": "subscription@base",
        "tariff_key": "base",
        "subscription_duration_months": 1,
        "amount": 150.0,
        "currency": "RUB",
        "idempotence_key": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


# --------------------------------------------------------------- gating


@pytest.mark.parametrize(
    ("months", "expected"),
    [(1, platega_subscriptions.INTERVAL_MONTH), (12, platega_subscriptions.INTERVAL_YEAR)],
)
def test_supported_periods_map_to_a_platega_interval(months, expected):
    assert platega_subscriptions.subscription_interval_for_months(months) == expected


@pytest.mark.parametrize("months", [0, 2, 3, 6, 24, None, "abc"])
def test_unrepresentable_periods_have_no_interval(months):
    assert platega_subscriptions.subscription_interval_for_months(months) is None


@pytest.mark.parametrize(
    ("months", "sale_mode", "expected"),
    [
        (1, "subscription", True),
        (12, "subscription@premium", True),
        (3, "subscription", False),
        (1, "traffic", False),
        (1, "hwid_devices", False),
        (1, "tariff_upgrade", False),
    ],
)
def test_only_representable_period_subscriptions_offer_the_button(months, sale_mode, expected):
    spec = platega_service.SUBSCRIPTION_SPEC
    assert spec.is_usable_for_payment_context(None, months, sale_mode) is expected


def test_promo_checkout_never_creates_a_mandate():
    spec = platega_service.SUBSCRIPTION_SPEC
    promo = SimpleNamespace(discount_amount=50)
    assert spec.is_checkout_promo_supported(None, 1, "subscription", promo) is False
    # No promo at all stays supported — the guard is about repeating a one-off
    # discount forever, not about disabling the button.
    assert spec.is_checkout_promo_supported(None, 1, "subscription", None) is True


# ----------------------------------------------------- recurrence wiring


def test_platega_never_enters_the_saved_method_renewal_path():
    # Enabling supports_recurring would make the renewal worker look for a
    # saved payment method that no Platega customer can ever have.
    assert provider_supports_recurring("platega") is False
    assert platega_service.SUBSCRIPTION_SPEC.supports_recurring is False


def test_platega_declares_provider_managed_recurrence():
    assert platega_service.SUBSCRIPTION_SPEC.manages_recurring is True
    # Resolution goes through provider_key: Subscription.provider is "platega"
    # for every Platega button, including the one-off SBP one.
    assert provider_manages_recurring("platega") is True
    assert provider_manages_recurring("platega_sbp") is True


def test_service_reports_managed_recurrence_only_when_enabled():
    service = _service()
    assert service_manages_recurrence(service) is True
    assert service_supports_recurring(service) is False

    service.config = platega_service.PlategaConfig(
        ENABLED=True,
        MERCHANT_ID="merchant",
        SECRET="secret",
        SUBSCRIPTION_ENABLED=False,
    )
    assert service_manages_recurrence(service) is False


@pytest.mark.parametrize(
    ("provider", "enable", "expected"),
    [
        ("platega", False, True),
        ("platega", True, False),
        ("yookassa", True, True),
        ("yookassa", False, True),
        ("heleket", False, False),
    ],
)
def test_provider_managed_recurrence_can_only_be_stopped(provider, enable, expected):
    assert auto_renew_toggle_allowed(provider, enable=enable) is expected


# ------------------------------------------------------------ API shape


def test_create_subscription_sends_the_interval_and_method(monkeypatch):
    service = _service()
    captured: dict = {}

    async def _fake_post(session, url, *, body, headers, log_prefix, **kwargs):
        captured["url"] = url
        captured["body"] = body
        return True, {"transactionId": "sub-1", "redirect": "https://pay.platega.io/s/1"}

    monkeypatch.setattr(platega_service, "post_json_request", _fake_post)
    monkeypatch.setattr(
        platega_service.PlategaService,
        "_get_session",
        AsyncMock(return_value=SimpleNamespace()),
    )

    success, data = asyncio.run(
        service.create_subscription(
            amount=150.0,
            currency="RUB",
            description="Subscription",
            months=12,
            payload=json.dumps({"user_id": 42}),
        )
    )

    assert success
    assert data["transactionId"] == "sub-1"
    assert captured["url"].endswith("/transaction/process")
    assert captured["body"]["paymentMethod"] == platega_subscriptions.DEFAULT_SUBSCRIPTION_METHOD
    assert captured["body"]["paymentDetails"] == {
        "amount": 150.0,
        "currency": "RUB",
        "interval": platega_subscriptions.INTERVAL_YEAR,
    }


def test_create_subscription_refuses_an_unrepresentable_period():
    service = _service()
    success, data = asyncio.run(
        service.create_subscription(
            amount=150.0,
            currency="RUB",
            description="Subscription",
            months=3,
        )
    )
    assert success is False
    assert data["message"] == "unsupported_subscription_interval"


def test_one_off_transactions_still_omit_the_interval(monkeypatch):
    service = _service()
    captured: dict = {}

    async def _fake_post(session, url, *, body, headers, log_prefix, **kwargs):
        captured["body"] = body
        return True, {"transactionId": "tx-1", "redirect": "https://pay.platega.io/t/1"}

    monkeypatch.setattr(platega_service, "post_json_request", _fake_post)
    monkeypatch.setattr(
        platega_service.PlategaService,
        "_get_session",
        AsyncMock(return_value=SimpleNamespace()),
    )

    asyncio.run(service.create_transaction(amount=150.0, currency="RUB", description="One-off"))
    assert "interval" not in captured["body"]["paymentDetails"]


# ------------------------------------------------------- callback shapes


def test_callback_fields_are_read_regardless_of_casing():
    payload = {"Id": "charge-1", "SubscriptionId": "sub-1", "Status": "CONFIRMED"}
    assert platega_subscriptions.callback_value(payload, "id") == "charge-1"
    assert platega_subscriptions.callback_value(payload, "subscriptionid") == "sub-1"
    assert platega_subscriptions.callback_value({"status": "ok"}, "Status") == "ok"
    assert platega_subscriptions.callback_value({"Payload": ""}, "Payload") is None


def test_next_charge_at_parses_platega_timestamps():
    parsed = platega_subscriptions.parse_callback_datetime("2026-08-09T09:10:00Z")
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert platega_subscriptions.parse_callback_datetime(None) is None
    assert platega_subscriptions.parse_callback_datetime("not-a-date") is None


def _run_webhook(service, payload):
    return asyncio.run(
        platega_service.PlategaService.webhook_route(
            service,
            _FakeJsonRequest(
                payload,
                headers={"X-MerchantId": "merchant", "X-Secret": "secret"},
            ),
        )
    )


def test_subscription_status_callbacks_are_routed_away_from_the_one_off_flow(monkeypatch):
    service = _service()
    status_handler = AsyncMock(return_value=SimpleNamespace(status=200, text="ok"))
    monkeypatch.setattr(
        platega_service.PlategaService,
        "handle_subscription_status_callback",
        status_handler,
    )
    _run_webhook(service, {"Id": "sub-1", "Status": "SUBSCRIPTION_ACTIVATED"})
    status_handler.assert_awaited_once()


def test_charge_callbacks_are_routed_by_their_subscription_id(monkeypatch):
    service = _service()
    charge_handler = AsyncMock(return_value=SimpleNamespace(status=200, text="ok"))
    monkeypatch.setattr(
        platega_service.PlategaService,
        "handle_subscription_charge_callback",
        charge_handler,
    )
    _run_webhook(
        service,
        {"Id": "charge-1", "SubscriptionId": "sub-1", "Status": "CONFIRMED"},
    )
    charge_handler.assert_awaited_once()


def test_plain_transaction_callbacks_keep_the_existing_flow(monkeypatch):
    service = _service()
    status_handler = AsyncMock()
    charge_handler = AsyncMock()
    monkeypatch.setattr(
        platega_service.PlategaService,
        "handle_subscription_status_callback",
        status_handler,
    )
    monkeypatch.setattr(
        platega_service.PlategaService,
        "handle_subscription_charge_callback",
        charge_handler,
    )
    monkeypatch.setattr(
        platega_service.payment_dal,
        "get_payment_by_provider_payment_id",
        AsyncMock(return_value=None),
    )

    response = _run_webhook(service, {"id": "tx-1", "status": "CONFIRMED", "amount": 150.0})

    assert response.status == 404
    status_handler.assert_not_awaited()
    charge_handler.assert_not_awaited()


# --------------------------------------------------------- charge settling


def test_replayed_charge_callback_is_not_credited_twice(monkeypatch):
    session = _FakeSession()
    service = _service(session)
    settled = SimpleNamespace(status="succeeded")
    monkeypatch.setattr(
        platega_subscriptions.platega_dal,
        "get_subscription",
        AsyncMock(return_value=_mandate()),
    )
    monkeypatch.setattr(
        platega_subscriptions.payment_dal,
        "get_payment_by_provider_payment_id",
        AsyncMock(return_value=_anchor(status="succeeded")),
    )
    monkeypatch.setattr(
        platega_subscriptions.payment_dal,
        "get_payment_by_idempotence_key",
        AsyncMock(return_value=settled),
    )
    create_mock = AsyncMock(side_effect=AssertionError("replay must not open a second order"))
    monkeypatch.setattr(
        platega_subscriptions.payment_dal,
        "create_or_get_payment_record_by_idempotence_key",
        create_mock,
    )

    response = asyncio.run(
        service.handle_subscription_charge_callback(
            {
                "Id": "charge-1",
                "SubscriptionId": "sub-1",
                "Status": "CONFIRMED",
                "Amount": 150.0,
                "Currency": "RUB",
            }
        )
    )

    assert response.status == 200
    create_mock.assert_not_awaited()


def test_renewal_charge_opens_an_order_from_the_mandate(monkeypatch):
    session = _FakeSession()
    service = _service(session)
    mandate = _mandate(charges_count=1)
    renewal_payment = _anchor(payment_id=99, status="pending_platega")

    created: dict = {}

    async def _create(_session, payload):
        created.update(payload)
        return renewal_payment, True

    monkeypatch.setattr(
        platega_subscriptions.platega_dal, "get_subscription", AsyncMock(return_value=mandate)
    )
    monkeypatch.setattr(
        platega_subscriptions.platega_dal, "record_charge", AsyncMock(return_value=mandate)
    )
    monkeypatch.setattr(
        platega_subscriptions.payment_dal,
        "get_payment_by_provider_payment_id",
        AsyncMock(return_value=_anchor(status="succeeded")),
    )
    monkeypatch.setattr(
        platega_subscriptions.payment_dal,
        "get_payment_by_idempotence_key",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        platega_subscriptions.payment_dal,
        "create_or_get_payment_record_by_idempotence_key",
        _create,
    )
    monkeypatch.setattr(
        platega_subscriptions.payment_dal,
        "claim_payment_finalization",
        AsyncMock(return_value=renewal_payment),
    )
    monkeypatch.setattr(
        platega_subscriptions.user_dal, "get_user_by_id", AsyncMock(return_value=SimpleNamespace())
    )
    monkeypatch.setattr(
        platega_subscriptions.subscription_dal,
        "get_active_subscription_by_user_id",
        AsyncMock(return_value=SimpleNamespace(subscription_id=7, provider="platega")),
    )
    finalize = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(platega_subscriptions, "finalize_successful_payment", finalize)

    response = asyncio.run(
        service.handle_subscription_charge_callback(
            {
                "Id": "charge-2",
                "SubscriptionId": "sub-1",
                "Status": "CONFIRMED",
                "Amount": 150.0,
                "Currency": "RUB",
                "NextChargeAt": "2026-09-09T09:10:00Z",
            }
        )
    )

    assert response.status == 200
    assert created["idempotence_key"] == "platega-sub:sub-1:charge-2"
    assert created["provider_payment_id"] == "charge-2"
    assert created["is_auto_renew"] is True
    assert created["renewal_subscription_id"] == 7
    # The mandate, not the callback, is the source of truth for what was sold.
    assert created["amount"] == 150.0
    assert created["subscription_duration_months"] == 1
    finalize.assert_awaited_once()


def test_renewal_charge_with_a_different_amount_is_refused(monkeypatch):
    session = _FakeSession()
    service = _service(session)
    monkeypatch.setattr(
        platega_subscriptions.platega_dal,
        "get_subscription",
        AsyncMock(return_value=_mandate(charges_count=1)),
    )
    monkeypatch.setattr(
        platega_subscriptions.payment_dal,
        "get_payment_by_provider_payment_id",
        AsyncMock(return_value=_anchor(status="succeeded")),
    )
    monkeypatch.setattr(
        platega_subscriptions.payment_dal,
        "get_payment_by_idempotence_key",
        AsyncMock(return_value=None),
    )
    create_mock = AsyncMock(side_effect=AssertionError("mismatched charge must not be credited"))
    monkeypatch.setattr(
        platega_subscriptions.payment_dal,
        "create_or_get_payment_record_by_idempotence_key",
        create_mock,
    )

    response = asyncio.run(
        service.handle_subscription_charge_callback(
            {
                "Id": "charge-3",
                "SubscriptionId": "sub-1",
                "Status": "CONFIRMED",
                "Amount": 10.0,
                "Currency": "RUB",
            }
        )
    )

    assert response.status == 400
    assert response.text == "amount_mismatch"
    create_mock.assert_not_awaited()


def test_unknown_mandate_is_cancelled_upstream(monkeypatch):
    session = _FakeSession()
    service = _service(session)
    monkeypatch.setattr(
        platega_subscriptions.platega_dal, "get_subscription", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        platega_subscriptions.payment_dal,
        "get_payment_by_provider_payment_id",
        AsyncMock(return_value=None),
    )
    cancel = AsyncMock(return_value=True)
    monkeypatch.setattr(platega_service.PlategaService, "cancel_remote_subscription", cancel)

    response = asyncio.run(
        service.handle_subscription_charge_callback(
            {
                "Id": "charge-4",
                "SubscriptionId": "ghost",
                "Status": "CONFIRMED",
                "Amount": 150.0,
                "Currency": "RUB",
            }
        )
    )

    assert response.status == 404
    cancel.assert_awaited_once_with("ghost")


def test_terminal_failure_stops_local_auto_renew(monkeypatch):
    session = _FakeSession()
    service = _service(session)
    mandate = _mandate(charges_count=1)
    subscription = SimpleNamespace(subscription_id=7, provider="platega", auto_renew_enabled=True)
    set_auto_renew = AsyncMock(return_value=subscription)

    monkeypatch.setattr(
        platega_subscriptions.platega_dal, "get_subscription", AsyncMock(return_value=mandate)
    )
    monkeypatch.setattr(
        platega_subscriptions.platega_dal, "mark_status", AsyncMock(return_value=mandate)
    )
    monkeypatch.setattr(
        platega_subscriptions.payment_dal,
        "get_payment_by_provider_payment_id",
        AsyncMock(return_value=_anchor(status="succeeded")),
    )
    monkeypatch.setattr(
        platega_subscriptions.subscription_dal,
        "get_active_subscription_by_user_id",
        AsyncMock(return_value=subscription),
    )
    monkeypatch.setattr(platega_subscriptions.subscription_dal, "set_auto_renew", set_auto_renew)
    monkeypatch.setattr(platega_subscriptions, "notify_user_payment_failed", AsyncMock())

    response = asyncio.run(
        service.handle_subscription_charge_callback(
            {
                "Id": "charge-5",
                "SubscriptionId": "sub-1",
                "Status": "CANCELED",
                "Amount": 150.0,
                "Currency": "RUB",
                "NextChargeAt": None,
            }
        )
    )

    assert response.status == 200
    set_auto_renew.assert_awaited_once()
    assert set_auto_renew.await_args.args[2] is False


def test_retryable_failure_keeps_the_mandate_past_due(monkeypatch):
    session = _FakeSession()
    service = _service(session)
    mandate = _mandate(charges_count=1)
    mark_status = AsyncMock(return_value=mandate)
    set_auto_renew = AsyncMock()

    monkeypatch.setattr(
        platega_subscriptions.platega_dal, "get_subscription", AsyncMock(return_value=mandate)
    )
    monkeypatch.setattr(platega_subscriptions.platega_dal, "mark_status", mark_status)
    monkeypatch.setattr(
        platega_subscriptions.payment_dal,
        "get_payment_by_provider_payment_id",
        AsyncMock(return_value=_anchor(status="succeeded")),
    )
    monkeypatch.setattr(platega_subscriptions.subscription_dal, "set_auto_renew", set_auto_renew)
    monkeypatch.setattr(platega_subscriptions, "notify_user_payment_failed", AsyncMock())

    asyncio.run(
        service.handle_subscription_charge_callback(
            {
                "Id": "charge-6",
                "SubscriptionId": "sub-1",
                "Status": "CANCELED",
                "Amount": 150.0,
                "Currency": "RUB",
                "NextChargeAt": "2026-09-09T09:10:00Z",
            }
        )
    )

    assert mark_status.await_args.args[2] == "past_due"
    set_auto_renew.assert_not_awaited()


def test_cancelling_recurrence_only_clears_confirmed_mandates(monkeypatch):
    session = _FakeSession()
    service = _service(session)
    live = [_mandate(platega_subscription_id="sub-1"), _mandate(platega_subscription_id="sub-2")]
    marked: list[str] = []

    async def _mark(_session, record, status, **_kwargs):
        marked.append(f"{record.platega_subscription_id}:{status}")
        return record

    monkeypatch.setattr(
        platega_subscriptions.platega_dal,
        "list_live_subscriptions_for_user",
        AsyncMock(return_value=live),
    )
    monkeypatch.setattr(platega_subscriptions.platega_dal, "mark_status", _mark)
    monkeypatch.setattr(
        platega_service.PlategaService,
        "cancel_remote_subscription",
        AsyncMock(side_effect=[True, False]),
    )

    all_cancelled = asyncio.run(service.cancel_provider_recurrence(session, user_id=42))

    assert all_cancelled is False
    assert marked == ["sub-1:cancelled"]
