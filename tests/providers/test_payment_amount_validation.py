"""Regression coverage for fail-closed payment confirmation validation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.payment_providers.base import ProviderWebhookPayload
from bot.payment_providers.platega import service as platega_service
from bot.payment_providers.qa import service as qa_service
from bot.payment_providers.severpay import service as severpay_service
from bot.payment_providers.shared import payment_amount_and_currency_match
from bot.payment_providers.stars import service as stars_service


class _FakeSession:
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


class _FakeJsonRequest:
    def __init__(self, payload, *, headers=None):
        self._payload = payload
        self.headers = headers or {}

    async def json(self):
        return self._payload


def _payment(*, provider: str, **overrides):
    values = {
        "payment_id": 88,
        "user_id": 42,
        "provider": provider,
        "status": f"pending_{provider}",
        "sale_mode": "subscription",
        "subscription_duration_months": 1,
        "purchased_gb": None,
        "purchased_hwid_devices": None,
        "amount": 150.0,
        "currency": "RUB",
        "user": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    ("received_amount", "received_currency"),
    [
        (149.99, "RUB"),
        (149.995, "RUB"),
        (150.0, None),
        (None, "RUB"),
        (150.0, "USD"),
    ],
)
def test_payment_amount_and_currency_match_fails_closed(
    received_amount,
    received_currency,
):
    assert not payment_amount_and_currency_match(
        expected_amount=150.0,
        expected_currency="RUB",
        received_amount=received_amount,
        received_currency=received_currency,
    )


def test_payment_amount_and_currency_match_accepts_equivalent_currency_code():
    assert payment_amount_and_currency_match(
        expected_amount=150.0,
        expected_currency="RUB",
        received_amount="150.00",
        received_currency="RUR",
    )


def test_payment_amount_and_currency_match_uses_invoiced_precision_for_expected_amount():
    assert payment_amount_and_currency_match(
        expected_amount=1.234,
        expected_currency="RUB",
        received_amount="1.23",
        received_currency="RUB",
    )


def test_payment_amount_and_currency_match_uses_half_up_invoice_precision():
    assert payment_amount_and_currency_match(
        expected_amount=1.125,
        expected_currency="RUB",
        received_amount="1.13",
        received_currency="RUB",
    )


def test_payment_amount_and_currency_match_preserves_raw_invoice_precision():
    assert payment_amount_and_currency_match(
        expected_amount=1.234,
        expected_currency="RUB",
        received_amount="1.2340",
        received_currency="RUB",
        places=None,
    )
    assert not payment_amount_and_currency_match(
        expected_amount=1.234,
        expected_currency="RUB",
        received_amount="1.23",
        received_currency="RUB",
        places=None,
    )


@pytest.mark.parametrize(
    ("received_amount", "received_currency"),
    [(149.99, "RUB"), (150.0, None)],
)
def test_platega_confirmation_rejects_unverified_payment_before_claim(
    monkeypatch,
    received_amount,
    received_currency,
):
    session = _FakeSession()
    payment = _payment(provider="platega")
    claim_mock = AsyncMock(side_effect=AssertionError("unverified payment must not be claimed"))
    finalize_mock = AsyncMock(side_effect=AssertionError("unverified payment must not finalize"))
    monkeypatch.setattr(
        platega_service.payment_dal,
        "get_payment_by_provider_payment_id",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(platega_service.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(platega_service, "finalize_successful_payment", finalize_mock)

    service = SimpleNamespace(
        configured=True,
        merchant_id="merchant",
        secret="secret",
        async_session_factory=session,
        settings=SimpleNamespace(traffic_sale_mode=False),
        bot=SimpleNamespace(),
        i18n=SimpleNamespace(),
        subscription_service=SimpleNamespace(),
        referral_service=SimpleNamespace(),
    )
    response = asyncio.run(
        platega_service.PlategaService.webhook_route(
            service,
            _FakeJsonRequest(
                {
                    "id": "platega-1",
                    "status": "CONFIRMED",
                    "amount": received_amount,
                    "currency": received_currency,
                },
                headers={"X-MerchantId": "merchant", "X-Secret": "secret"},
            ),
        )
    )

    assert response.status == 400
    assert response.text == "amount_mismatch"
    claim_mock.assert_not_awaited()
    finalize_mock.assert_not_awaited()


@pytest.mark.parametrize(
    ("received_amount", "received_currency"),
    [(149.99, "RUB"), (150.0, None)],
)
def test_qa_confirmation_rejects_unverified_payment_before_claim(
    monkeypatch,
    received_amount,
    received_currency,
):
    session = _FakeSession()
    payment = _payment(provider="qa")
    claim_mock = AsyncMock(side_effect=AssertionError("unverified payment must not be claimed"))
    finalize_mock = AsyncMock(side_effect=AssertionError("unverified payment must not finalize"))
    monkeypatch.setattr(
        qa_service.payment_dal,
        "get_payment_by_db_id",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(qa_service.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(qa_service, "finalize_successful_payment", finalize_mock)

    service = SimpleNamespace(
        async_session_factory=session,
        bot=SimpleNamespace(),
        settings=SimpleNamespace(),
        i18n=SimpleNamespace(),
        subscription_service=SimpleNamespace(),
        referral_service=SimpleNamespace(),
    )
    response = asyncio.run(
        qa_service.QaPaymentService.handle_verified_webhook(
            service,
            SimpleNamespace(),
            ProviderWebhookPayload(
                raw_body=b"{}",
                data={
                    "payment_id": payment.payment_id,
                    "status": "succeeded",
                    "amount": received_amount,
                    "currency": received_currency,
                },
                signature="",
            ),
        )
    )

    assert response.status == 400
    assert response.body == b'{"ok": false, "error": "amount_mismatch"}'
    claim_mock.assert_not_awaited()
    finalize_mock.assert_not_awaited()


def test_qa_confirmation_preserves_local_amount_precision(monkeypatch):
    session = _FakeSession()
    payment = _payment(provider="qa", amount=1.234)
    claim_mock = AsyncMock(return_value=payment)
    finalize_mock = AsyncMock(return_value=SimpleNamespace(final_end_date=None))
    monkeypatch.setattr(
        qa_service.payment_dal,
        "get_payment_by_db_id",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(qa_service.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(qa_service, "finalize_successful_payment", finalize_mock)

    service = SimpleNamespace(
        async_session_factory=session,
        bot=SimpleNamespace(),
        settings=SimpleNamespace(),
        i18n=SimpleNamespace(),
        subscription_service=SimpleNamespace(),
        referral_service=SimpleNamespace(),
    )
    response = asyncio.run(
        qa_service.QaPaymentService.handle_verified_webhook(
            service,
            SimpleNamespace(),
            ProviderWebhookPayload(
                raw_body=b"{}",
                data={
                    "payment_id": payment.payment_id,
                    "status": "succeeded",
                    "amount": 1.234,
                    "currency": "RUB",
                },
                signature="",
            ),
        )
    )

    assert response.status == 200
    claim_mock.assert_awaited_once_with(
        session,
        payment.payment_id,
        provider_payment_id=f"qa:{payment.payment_id}",
    )
    finalize_mock.assert_awaited_once()


@pytest.mark.parametrize(
    ("received_amount", "received_currency"),
    [(149.99, "RUB"), (150.0, None)],
)
def test_severpay_confirmation_rejects_unverified_payment_before_claim(
    monkeypatch,
    received_amount,
    received_currency,
):
    session = _FakeSession()
    payment = _payment(provider="severpay")
    claim_mock = AsyncMock(side_effect=AssertionError("unverified payment must not be claimed"))
    finalize_mock = AsyncMock(side_effect=AssertionError("unverified payment must not finalize"))
    monkeypatch.setattr(
        severpay_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(severpay_service.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(severpay_service, "finalize_successful_payment", finalize_mock)

    service = SimpleNamespace(
        configured=True,
        _validate_signature=lambda _payload: True,
        async_session_factory=session,
        settings=SimpleNamespace(traffic_sale_mode=False),
        bot=SimpleNamespace(),
        i18n=SimpleNamespace(),
        subscription_service=SimpleNamespace(),
        referral_service=SimpleNamespace(),
    )
    response = asyncio.run(
        severpay_service.SeverPayService.webhook_route(
            service,
            _FakeJsonRequest(
                {
                    "type": "payin",
                    "data": {
                        "id": "severpay-1",
                        "order_id": str(payment.payment_id),
                        "status": "success",
                        "amount": received_amount,
                        "currency": received_currency,
                    },
                }
            ),
        )
    )

    assert response.status == 400
    assert response.body == b'{"status": false, "msg": "amount_mismatch"}'
    claim_mock.assert_not_awaited()
    finalize_mock.assert_not_awaited()


@pytest.mark.parametrize(
    ("received_amount", "received_currency"),
    [(149, "XTR"), (150, None)],
)
def test_stars_confirmation_rejects_unverified_payment_before_claim(
    monkeypatch,
    received_amount,
    received_currency,
):
    session = _FakeSession()
    payment = _payment(provider="telegram_stars", currency="XTR")
    claim_mock = AsyncMock(side_effect=AssertionError("unverified payment must not be claimed"))
    finalize_mock = AsyncMock(side_effect=AssertionError("unverified payment must not finalize"))
    monkeypatch.setattr(
        stars_service.payment_dal,
        "get_payment_by_db_id",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(stars_service.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(stars_service, "finalize_successful_payment", finalize_mock)

    service = SimpleNamespace(
        bot=SimpleNamespace(),
        settings=SimpleNamespace(),
        i18n=SimpleNamespace(),
        subscription_service=SimpleNamespace(),
        referral_service=SimpleNamespace(),
    )
    message = SimpleNamespace(
        successful_payment=SimpleNamespace(
            provider_payment_charge_id="stars-charge-1",
            total_amount=received_amount,
            currency=received_currency,
        ),
        from_user=SimpleNamespace(id=payment.user_id),
    )
    asyncio.run(
        stars_service.StarsService.process_successful_payment(
            service,
            session=session,
            message=message,
            payment_db_id=payment.payment_id,
            months=1,
            stars_amount=received_amount or 0,
            i18n_data={},
            sale_mode="subscription",
        )
    )

    claim_mock.assert_not_awaited()
    finalize_mock.assert_not_awaited()
