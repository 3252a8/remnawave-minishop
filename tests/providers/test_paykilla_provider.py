import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.payment_providers.paykilla import service as paykilla_service


class _FakeSession:
    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def rollback(self):
        pass


class _FakeRequest:
    def __init__(self, payload):
        self._raw_body = json.dumps(payload).encode("utf-8")
        self.remote = "127.0.0.1"
        self.headers = {}

    async def read(self):
        return self._raw_body


def _payment(**overrides):
    values = {
        "payment_id": 42,
        "provider_payment_id": "invoice-42",
        "status": "pending_paykilla",
        "amount": 1000.0,
        "currency": "RUB",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _invoice_service(*, invoice_currencies: str, currency: str):
    service = object.__new__(paykilla_service.PaykillaService)
    service.config = SimpleNamespace(
        INVOICE_CURRENCIES=invoice_currencies,
        CURRENCY=currency,
        INVOICE_TYPE=None,
        PAYMENT_CURRENCIES="BTC,USD",
        USER_PAYS_SERVICE_FEE=True,
        USER_PAYS_NETWORK_FEE=True,
        LIFETIME_SECONDS=0,
    )
    service.settings = SimpleNamespace(WEBAPP_TITLE="Minishop")
    return service


def test_invoice_creation_preserves_crypto_amount_precision():
    service = _invoice_service(invoice_currencies="BTC", currency="BTC")

    invoice_amount, invoice_currency = asyncio.run(
        paykilla_service.PaykillaService._invoice_amount_and_currency(
            service,
            amount=1.2345,
            payment_currency="BTC",
        )
    )

    assert invoice_amount == Decimal("1.2345")
    assert invoice_currency == "BTC"
    assert (
        paykilla_service.PaykillaService._invoice_body(
            service,
            payment_db_id=42,
            amount=invoice_amount,
            currency=invoice_currency,
            description="ignored",
        )["totalPrice"]
        == "1.2345"
    )


def test_invoice_creation_keeps_two_places_for_fiat():
    service = _invoice_service(invoice_currencies="USD", currency="USD")

    invoice_amount, invoice_currency = asyncio.run(
        paykilla_service.PaykillaService._invoice_amount_and_currency(
            service,
            amount=1.2345,
            payment_currency="USD",
        )
    )

    assert invoice_amount == Decimal("1.23")
    assert invoice_currency == "USD"
    assert (
        paykilla_service.PaykillaService._invoice_body(
            service,
            payment_db_id=42,
            amount=invoice_amount,
            currency=invoice_currency,
            description="ignored",
        )["totalPrice"]
        == "1.23"
    )


def test_invoice_conversion_uses_full_source_crypto_amount_before_fiat_rounding():
    service = _invoice_service(invoice_currencies="USD", currency="USD")
    service._exchange_rate = AsyncMock(return_value=Decimal("60000"))

    invoice_amount, invoice_currency = asyncio.run(
        paykilla_service.PaykillaService._invoice_amount_and_currency(
            service,
            amount=1.2345,
            payment_currency="BTC",
        )
    )

    assert invoice_amount == Decimal("74070.00")
    assert invoice_currency == "USD"
    service._exchange_rate.assert_awaited_once_with("BTC", "USD")


def test_success_invoice_validation_uses_provider_invoice_after_currency_conversion():
    service = object.__new__(paykilla_service.PaykillaService)
    service.get_invoice_details = AsyncMock(
        return_value=(
            True,
            {
                "id": "invoice-42",
                "clientOrderId": "42",
                "totalPrice": "10.00",
                "currency": "USD",
            },
        )
    )

    verified, error = asyncio.run(
        paykilla_service.PaykillaService._verify_success_invoice(
            service,
            payment=_payment(),
            invoice_id="invoice-42",
            webhook_data={"amount": "10.00", "currency": "USD"},
        )
    )

    assert verified
    assert error == ""
    service.get_invoice_details.assert_awaited_once_with("invoice-42")


def test_success_invoice_validation_preserves_crypto_precision():
    service = object.__new__(paykilla_service.PaykillaService)
    service.get_invoice_details = AsyncMock(
        return_value=(
            True,
            {
                "id": "invoice-42",
                "clientOrderId": "42",
                "totalPrice": "1.2345",
                "currency": "BTC",
            },
        )
    )

    verified, error = asyncio.run(
        paykilla_service.PaykillaService._verify_success_invoice(
            service,
            payment=_payment(amount=1.2345, currency="BTC"),
            invoice_id="invoice-42",
            webhook_data={"amount": "1.2345", "currency": "BTC"},
        )
    )
    assert verified
    assert error == ""

    verified, error = asyncio.run(
        paykilla_service.PaykillaService._verify_success_invoice(
            service,
            payment=_payment(amount=1.2345, currency="BTC"),
            invoice_id="invoice-42",
            webhook_data={"amount": "1.23", "currency": "BTC"},
        )
    )
    assert not verified
    assert error == "amount_mismatch"


def test_success_invoice_validation_rejects_paid_amount_mismatch():
    service = object.__new__(paykilla_service.PaykillaService)
    service.get_invoice_details = AsyncMock(
        return_value=(
            True,
            {
                "id": "invoice-42",
                "clientOrderId": "42",
                "totalPrice": "10.00",
                "currency": "USD",
            },
        )
    )

    verified, error = asyncio.run(
        paykilla_service.PaykillaService._verify_success_invoice(
            service,
            payment=_payment(),
            invoice_id="invoice-42",
            webhook_data={"amount": "9.99", "currency": "USD"},
        )
    )

    assert not verified
    assert error == "amount_mismatch"


def test_success_webhook_mismatch_stops_before_finalization(monkeypatch):
    session = _FakeSession()
    payment = _payment()
    monkeypatch.setattr(
        paykilla_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(return_value=payment),
    )
    claim_mock = AsyncMock(side_effect=AssertionError("mismatch must not claim payment"))
    monkeypatch.setattr(paykilla_service.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(
        paykilla_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("mismatch must not finalize payment")),
    )
    service = SimpleNamespace(
        configured=True,
        config=SimpleNamespace(trusted_ips_list=[]),
        settings=SimpleNamespace(trusted_proxies=[]),
        verify_webhook_signature=False,
        async_session_factory=session,
        _verify_success_invoice=AsyncMock(return_value=(False, "amount_mismatch")),
    )

    response = asyncio.run(
        paykilla_service.PaykillaService.webhook_route(
            service,
            _FakeRequest(
                {
                    "eventType": "INVOICE_PAID",
                    "data": {
                        "id": "invoice-42",
                        "clientOrderId": "42",
                        "amount": "9.99",
                        "currency": "USD",
                    },
                }
            ),
        )
    )

    assert response.status == 400
    assert claim_mock.await_count == 0
