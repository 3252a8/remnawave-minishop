"""Regression tests for high-precision crypto invoice amounts."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.payment_providers.heleket import HeleketConfig, HeleketService
from bot.payment_providers.heleket import service as heleket_service
from bot.payment_providers.shared import payment_amount_and_currency_match


class _FakeResponse:
    status = 200

    async def text(self):
        return json.dumps({"state": 0, "result": {"url": "https://pay.example/invoice"}})

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


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


class _FakeWebhookRequest:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")
        self.headers = {}
        self.remote = "127.0.0.1"

    async def read(self):
        return self._body


def _make_heleket_service() -> HeleketService:
    service = object.__new__(HeleketService)
    service.config = HeleketConfig(
        ENABLED=True,
        MERCHANT_ID="merchant",
        API_KEY="secret",
        VERIFY_WEBHOOK_SIGNATURE=False,
        TRUSTED_IPS="",
    )
    service.settings = SimpleNamespace(
        PAYMENT_REQUEST_TIMEOUT_SECONDS=30,
        trusted_proxies=[],
        traffic_sale_mode=False,
    )
    service._default_return_url = "testbot"
    return service


def _crypto_payment(*, amount=0.0001):
    return SimpleNamespace(
        payment_id=77,
        user_id=42,
        status="pending_heleket",
        sale_mode="subscription",
        subscription_duration_months=1,
        purchased_gb=None,
        purchased_hwid_devices=None,
        amount=amount,
        currency="BTC",
        user=None,
    )


def test_exact_amount_matching_accepts_equivalent_scale_but_rejects_other_crypto_value():
    assert payment_amount_and_currency_match(
        expected_amount=0.0001,
        expected_currency="BTC",
        received_amount="0.00010000",
        received_currency="BTC",
        places=None,
    )
    assert not payment_amount_and_currency_match(
        expected_amount=0.0001,
        expected_currency="BTC",
        received_amount="0.00010001",
        received_currency="BTC",
        places=None,
    )


def test_heleket_create_payment_link_preserves_crypto_amount_precision(monkeypatch):
    service = _make_heleket_service()
    captured = {}

    session = SimpleNamespace()

    def post(url, data=None, headers=None):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        return _FakeResponse()

    session.post = post
    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=session))

    success, _result = asyncio.run(
        service.create_payment_link(
            payment_db_id=77,
            amount=0.0001,
            currency="BTC",
            description="Subscription",
            url_callback=None,
        )
    )

    assert success
    assert json.loads(captured["data"])["amount"] == "0.0001"


def test_heleket_webhook_accepts_exact_high_precision_crypto_invoice(monkeypatch):
    session = _FakeDbSession()
    service = _make_heleket_service()
    service.async_session_factory = session
    service.bot = SimpleNamespace()
    service.i18n = SimpleNamespace()
    service.subscription_service = SimpleNamespace()
    service.referral_service = SimpleNamespace()
    payment = _crypto_payment()
    claim_mock = AsyncMock(return_value=payment)
    finalize_mock = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(
        heleket_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(heleket_service.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(heleket_service, "finalize_successful_payment", finalize_mock)

    response = asyncio.run(
        service.webhook_route(
            _FakeWebhookRequest(
                {
                    "uuid": "invoice-77",
                    "order_id": "77",
                    "status": "paid",
                    "is_final": True,
                    "amount": "0.00010000",
                    "currency": "BTC",
                }
            )
        )
    )

    assert response.status == 200
    assert response.text == "ok"
    claim_mock.assert_awaited_once_with(session, 77, provider_payment_id="invoice-77")
    assert finalize_mock.await_args.args[0].amount == 0.0001
    assert finalize_mock.await_args.args[0].currency == "BTC"


def test_heleket_webhook_rejects_underpaid_high_precision_crypto_invoice(monkeypatch):
    session = _FakeDbSession()
    service = _make_heleket_service()
    service.async_session_factory = session
    payment = _crypto_payment()
    claim_mock = AsyncMock(side_effect=AssertionError("mismatched invoice must not be claimed"))
    finalize_mock = AsyncMock(side_effect=AssertionError("mismatched invoice must not finalize"))
    monkeypatch.setattr(
        heleket_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(heleket_service.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(heleket_service, "finalize_successful_payment", finalize_mock)

    response = asyncio.run(
        service.webhook_route(
            _FakeWebhookRequest(
                {
                    "uuid": "invoice-77",
                    "order_id": "77",
                    "status": "paid",
                    "is_final": True,
                    "amount": "0.00009999",
                    "currency": "BTC",
                }
            )
        )
    )

    assert response.status == 400
    assert response.text == "payment_mismatch"
    claim_mock.assert_not_awaited()
    finalize_mock.assert_not_awaited()


def test_heleket_webhook_does_not_finalize_non_final_success(monkeypatch):
    session = _FakeDbSession()
    service = _make_heleket_service()
    service.async_session_factory = session
    payment = _crypto_payment()
    claim_mock = AsyncMock(side_effect=AssertionError("non-final invoice must not be claimed"))
    finalize_mock = AsyncMock(side_effect=AssertionError("non-final invoice must not finalize"))
    monkeypatch.setattr(
        heleket_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(heleket_service.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(heleket_service, "finalize_successful_payment", finalize_mock)

    response = asyncio.run(
        service.webhook_route(
            _FakeWebhookRequest(
                {
                    "uuid": "invoice-77",
                    "order_id": "77",
                    "status": "paid",
                    "is_final": False,
                    "amount": "0.00010000",
                    "currency": "BTC",
                }
            )
        )
    )

    assert response.status == 202
    assert response.text == "payment_not_final"
    claim_mock.assert_not_awaited()
    finalize_mock.assert_not_awaited()
