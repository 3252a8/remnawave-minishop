"""Regression coverage for amount checks in legacy signed gateway callbacks."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlencode

from bot.payment_providers.freekassa import service as freekassa_service
from bot.payment_providers.heleket import service as heleket_service


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
    def __init__(self, body: bytes, *, content_type: str = "application/json"):
        self._body = body
        self.content_type = content_type
        self.headers: dict[str, str] = {}
        self.remote = "127.0.0.1"

    async def read(self):
        return self._body


def _payment(**overrides):
    values = {
        "payment_id": 77,
        "status": "pending_gateway",
        "amount": 150.0,
        "currency": "RUB",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_freekassa_rejects_mismatched_amount_before_claim(monkeypatch):
    session = _FakeSession()
    claim_mock = AsyncMock(side_effect=AssertionError("mismatched payment must not be claimed"))
    monkeypatch.setattr(
        freekassa_service.payment_dal,
        "get_payment_by_db_id",
        AsyncMock(return_value=_payment()),
    )
    monkeypatch.setattr(freekassa_service.payment_dal, "claim_payment_finalization", claim_mock)

    service = SimpleNamespace(
        configured=True,
        config=SimpleNamespace(trusted_ips_list=["127.0.0.1"]),
        settings=SimpleNamespace(trusted_proxies=[]),
        shop_id="merchant",
        _validate_signature=lambda _body, _signature: True,
        async_session_factory=session,
    )
    body = urlencode(
        {
            "MERCHANT_ID": "merchant",
            "MERCHANT_ORDER_ID": "77",
            # This used to be rounded to the expected 150.00 and fulfilled.
            "AMOUNT": "150.001",
            "intid": "freekassa-77",
            "SIGN": "signed",
        }
    ).encode("utf-8")

    response = asyncio.run(
        freekassa_service.FreeKassaService.webhook_route(
            service,
            _FakeRequest(body, content_type="application/x-www-form-urlencoded"),
        )
    )

    assert response.status == 400
    assert response.text == "amount_mismatch"
    claim_mock.assert_not_awaited()


def test_freekassa_requires_provider_order_currency_before_claim(monkeypatch):
    session = _FakeSession()
    claim_mock = AsyncMock(side_effect=AssertionError("unverified payment must not be claimed"))
    monkeypatch.setattr(
        freekassa_service.payment_dal,
        "get_payment_by_db_id",
        AsyncMock(return_value=_payment()),
    )
    monkeypatch.setattr(freekassa_service.payment_dal, "claim_payment_finalization", claim_mock)

    service = SimpleNamespace(
        configured=True,
        config=SimpleNamespace(trusted_ips_list=["127.0.0.1"]),
        settings=SimpleNamespace(trusted_proxies=[]),
        shop_id="merchant",
        _validate_signature=lambda _body, _signature: True,
        _verify_paid_order=AsyncMock(return_value=(False, "currency_mismatch")),
        async_session_factory=session,
    )
    body = urlencode(
        {
            "MERCHANT_ID": "merchant",
            "MERCHANT_ORDER_ID": "77",
            "AMOUNT": "150.00",
            "intid": "freekassa-77",
            "SIGN": "signed",
        }
    ).encode("utf-8")

    response = asyncio.run(
        freekassa_service.FreeKassaService.webhook_route(
            service,
            _FakeRequest(body, content_type="application/x-www-form-urlencoded"),
        )
    )

    assert response.status == 400
    assert response.text == "currency_mismatch"
    claim_mock.assert_not_awaited()


def test_freekassa_orders_api_requires_matching_currency():
    service = SimpleNamespace(
        get_orders=AsyncMock(
            return_value=(
                True,
                {
                    "orders": [
                        {
                            "merchant_order_id": "77",
                            "status": 1,
                            "amount": "150.00",
                            "currency": "USD",
                        }
                    ]
                },
            )
        )
    )

    verified, error = asyncio.run(
        freekassa_service.FreeKassaService._verify_paid_order(service, _payment())
    )

    assert not verified
    assert error == "currency_mismatch"
    service.get_orders.assert_awaited_once_with(payment_id=77, order_status=1)


def test_heleket_rejects_missing_currency_before_claim(monkeypatch):
    session = _FakeSession()
    claim_mock = AsyncMock(side_effect=AssertionError("unverified payment must not be claimed"))
    finalize_mock = AsyncMock(side_effect=AssertionError("unverified payment must not finalize"))
    monkeypatch.setattr(
        heleket_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(return_value=_payment(status="pending_heleket")),
    )
    monkeypatch.setattr(heleket_service.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(heleket_service, "finalize_successful_payment", finalize_mock)

    service = SimpleNamespace(
        configured=True,
        config=SimpleNamespace(trusted_ips_list=[]),
        settings=SimpleNamespace(trusted_proxies=[], traffic_sale_mode=False),
        verify_webhook_signature=False,
        async_session_factory=session,
    )
    response = asyncio.run(
        heleket_service.HeleketService.webhook_route(
            service,
            _FakeRequest(
                json.dumps(
                    {
                        "uuid": "heleket-77",
                        "order_id": "77",
                        "status": "paid",
                        "is_final": True,
                        "amount": "150.00",
                    }
                ).encode("utf-8")
            ),
        )
    )

    assert response.status == 400
    assert response.text == "payment_mismatch"
    claim_mock.assert_not_awaited()
    finalize_mock.assert_not_awaited()
