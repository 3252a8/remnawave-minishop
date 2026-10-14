import asyncio
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.payment_providers.cispay import CisPayConfig, CisPayService
from bot.payment_providers.cispay import service as provider


def make_service():
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
    return CisPayService(ctx, CisPayConfig(ENABLED=True, SHOP_ID="shop", API_KEY="secret"))


def test_checkout_uses_minor_units_and_owner(monkeypatch):
    service = make_service()
    api = AsyncMock(return_value=(True, {"id": "invoice", "payment_url": "https://pay.example"}))
    monkeypatch.setattr(service, "api_request", api)
    success, _ = asyncio.run(
        service.create_payment(
            payment_db_id=77, user_id=42, amount=150.49, currency="RUB", description="Subscription"
        )
    )
    assert success
    assert api.call_args.args == ("POST", "/payments")
    body = api.call_args.kwargs["body"]
    assert body["amount"] == 15049
    assert body["order_id"] == "77"
    assert body["customer_id"] == "42"
    assert "payment_method" not in body


@pytest.mark.parametrize(
    "data,amount,currency",
    [
        ({"amount": 15049, "charged_amount": 16000, "currency": "RUB"}, "150.49", "RUB"),
        (
            {"amount": 200, "currency": "USD", "source_amount": 15049, "source_currency": "RUB"},
            "150.49",
            "RUB",
        ),
        ({"amount": "15049", "currency": "RUB"}, None, "RUB"),
        ({"amount": True, "currency": "RUB"}, None, "RUB"),
    ],
)
def test_invoice_price_excludes_client_fees_and_preserves_original_currency(data, amount, currency):
    normalized = CisPayService.normalize_payment(data)
    assert normalized["amount"] == amount
    assert normalized["currency"] == currency


class Request:
    def __init__(self, data, *, signature=None):
        self.raw = json.dumps(data, ensure_ascii=False).encode()
        self.headers = {
            "X-Signature": signature
            if signature is not None
            else hmac.new(b"secret", self.raw, hashlib.sha256).hexdigest()
        }

    async def read(self):
        return self.raw


@pytest.mark.parametrize(
    "change,signature,expected",
    [
        ({}, "invalid", 403),
        ({}, "подпись", 403),
        ({"store_id": "other"}, None, 403),
        ({"is_sandbox": True}, None, 400),
        ({"is_sandbox": None}, None, 400),
    ],
)
def test_webhook_rejects_untrusted_shop_signature_and_sandbox(
    monkeypatch, change, signature, expected
):
    service = make_service()
    settle = AsyncMock(side_effect=AssertionError("untrusted payment"))
    monkeypatch.setattr(provider, "settle_hosted_payment", settle)
    payload = {
        "id": "invoice",
        "order_id": "77",
        "store_id": "shop",
        "status": "PAID",
        "is_sandbox": False,
        **change,
    }
    assert (
        asyncio.run(service.webhook_route(Request(payload, signature=signature))).status == expected
    )
    settle.assert_not_awaited()


def test_paid_webhook_requires_matching_read_api_invoice(monkeypatch):
    service = make_service()
    monkeypatch.setattr(
        service,
        "get_payment",
        AsyncMock(return_value=(True, {"id": "other", "order_id": "77", "status": "PAID"})),
    )
    settle = AsyncMock(side_effect=AssertionError("wrong invoice"))
    monkeypatch.setattr(provider, "settle_hosted_payment", settle)
    payload = {
        "id": "invoice",
        "order_id": "77",
        "store_id": "shop",
        "status": "PAID",
        "is_sandbox": False,
    }
    assert asyncio.run(service.webhook_route(Request(payload))).status == 500
    settle.assert_not_awaited()


def test_signed_recurring_event_confirms_remote_history(monkeypatch):
    service = make_service()

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    service.async_session_factory = Session
    monkeypatch.setattr(
        provider.provider_mandate_dal, "get_mandate", AsyncMock(return_value=object())
    )
    reconcile = AsyncMock(return_value=True)
    monkeypatch.setattr(service, "reconcile_remote_mandate", reconcile)
    payload = {
        "id": "charge",
        "subscription_id": "mandate",
        "store_id": "shop",
        "status": "PAID",
        "is_sandbox": False,
    }
    assert asyncio.run(service.webhook_route(Request(payload))).status == 200
    reconcile.assert_awaited_once_with(provider="cispay_subscription_card", remote_id="mandate")


@pytest.mark.parametrize("spec", [provider.CARD_SUBSCRIPTION_SPEC, provider.SBP_SUBSCRIPTION_SPEC])
def test_recurring_supports_only_documented_periods_and_rub(spec):
    assert spec.supported_currencies == ("RUB",)
    assert spec.manages_recurring and not spec.supports_recurring
    assert spec.payment_context_resolver(None, 1, "subscription")
    assert not spec.payment_context_resolver(None, 12, "subscription")
    assert not spec.payment_context_resolver(None, 1, "gift")
    assert not spec.supports_checkout_addons


def test_remote_cancel_must_confirm_identity_and_state(monkeypatch):
    service = make_service()
    api = AsyncMock(return_value=(True, {"id": "mandate", "status": "ACTIVE"}))
    monkeypatch.setattr(service, "api_request", api)
    assert not asyncio.run(service.stop_remote_subscription("mandate"))
    api.return_value = (True, {"id": "mandate", "status": "CANCELLED"})
    assert asyncio.run(service.stop_remote_subscription("mandate"))
    service.config.ENABLED = False
    assert not service.configured
    assert service.manages_recurrence


def test_history_reconciles_only_new_charges_after_account_merge(monkeypatch):
    service = make_service()

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    service.async_session_factory = Session
    data = {
        "id": "mandate",
        "customer_id": "42",
        "payment_method": "SBP",
        "interval_days": 30,
        "status": "ACTIVE",
        "charges": [
            {"id": "first", "status": "PAID", "created_at": "2026-09-01T00:00:00Z"},
            {"id": "second", "status": "PAID", "created_at": "2026-10-01T00:00:00Z"},
        ],
    }
    monkeypatch.setattr(service, "api_request", AsyncMock(return_value=(True, data)))
    monkeypatch.setattr(
        provider.provider_mandate_dal,
        "get_mandate",
        AsyncMock(
            return_value=SimpleNamespace(user_id=99, provider_customer_id="42", period_days=30)
        ),
    )
    monkeypatch.setattr(
        provider.payment_dal,
        "get_payment_by_idempotence_key",
        AsyncMock(side_effect=[SimpleNamespace(status="succeeded"), None]),
    )
    read = AsyncMock(
        return_value=(True, {"id": "second", "status": "PAID", "amount": "150", "currency": "RUB"})
    )
    monkeypatch.setattr(service, "get_payment", read)
    settle = AsyncMock(return_value=True)
    monkeypatch.setattr(provider, "settle_managed_charge", settle)
    monkeypatch.setattr(provider, "update_mandate_state", AsyncMock())
    assert asyncio.run(
        service.reconcile_remote_mandate(provider="cispay_subscription_sbp", remote_id="mandate")
    )
    read.assert_awaited_once_with("second")
    assert settle.call_args.kwargs["charge_id"] == "second"


def test_missing_credentials_cannot_forge_webhook_or_claim_remote_cancellation(monkeypatch):
    from bot.infra.auto_renew import stop_provider_managed_recurrence

    service = make_service()
    service.config.API_KEY = ""
    assert not service.can_reconcile_payments
    assert asyncio.run(service.webhook_route(Request({}))).status == 503
    monkeypatch.setattr(
        provider.provider_mandate_dal,
        "list_mandates",
        AsyncMock(return_value=[SimpleNamespace(remote_id="live", status="active")]),
    )
    owner = SimpleNamespace(
        managed_recurring_provider_services={"cispay_subscription_card": service}
    )
    assert not asyncio.run(
        stop_provider_managed_recurrence(
            owner, SimpleNamespace(), user_id=42, provider="cispay_subscription_card"
        )
    )
