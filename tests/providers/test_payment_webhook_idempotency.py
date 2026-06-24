import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.payment_providers import severpay
from bot.payment_providers.cryptopay import service as cryptopay_service
from bot.payment_providers.severpay import service as severpay_service
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
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


def test_cryptopay_duplicate_success_webhook_does_not_finalize_again(monkeypatch):
    session = _FakeSession()
    payment = SimpleNamespace(payment_id=77, status="succeeded")
    update = SimpleNamespace(
        payload=SimpleNamespace(
            payload=json.dumps(
                {
                    "user_id": "42",
                    "subscription_months": "0",
                    "payment_db_id": "77",
                    "sale_mode": "hwid_devices@standard",
                }
            ),
            invoice_id=9001,
            amount=100,
            asset="USDT",
        )
    )
    app = {
        "async_session_factory": session,
        "bot": SimpleNamespace(),
        "settings": SimpleNamespace(traffic_sale_mode=False, DEFAULT_CURRENCY_SYMBOL="RUB"),
        "i18n": SimpleNamespace(),
        "subscription_service": SimpleNamespace(),
        "referral_service": SimpleNamespace(),
    }

    monkeypatch.setattr(
        cryptopay_service.payment_dal,
        "get_payment_by_db_id",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(
        cryptopay_service.payment_dal,
        "update_provider_payment_and_status",
        AsyncMock(side_effect=AssertionError("duplicate webhook must not update payment")),
    )
    monkeypatch.setattr(
        cryptopay_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("duplicate webhook must not finalize")),
    )

    service = SimpleNamespace(settings=SimpleNamespace(traffic_sale_mode=False))
    asyncio.run(cryptopay_service.CryptoPayService._invoice_paid_handler(service, update, app))


def test_severpay_duplicate_success_webhook_does_not_finalize_again(monkeypatch):
    session = _FakeSession()
    payment = SimpleNamespace(
        payment_id=88,
        user_id=42,
        status="succeeded",
        sale_mode="hwid_devices@standard",
        purchased_hwid_devices=3,
        purchased_gb=None,
        subscription_duration_months=None,
        amount=150.0,
        currency="RUB",
        user=None,
    )

    async def lookup_payment(_session, *, order_id_raw=None, provider_payment_id=None):
        assert _session is session
        assert order_id_raw == "88"
        assert provider_payment_id == "sev-1"
        return payment

    monkeypatch.setattr(severpay_service, "lookup_payment_by_order_or_provider_id", lookup_payment)
    monkeypatch.setattr(
        severpay_service.payment_dal,
        "update_provider_payment_and_status",
        AsyncMock(side_effect=AssertionError("duplicate webhook must not update payment")),
    )
    monkeypatch.setattr(
        severpay_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("duplicate webhook must not finalize")),
    )

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
        severpay.SeverPayService.webhook_route(
            service,
            _FakeJsonRequest(
                {
                    "type": "payin",
                    "data": {
                        "id": "sev-1",
                        "order_id": "88",
                        "status": "success",
                    },
                }
            ),
        )
    )

    assert response.status == 200


def test_stars_duplicate_success_message_does_not_finalize_again(monkeypatch):
    session = _FakeSession()
    payment = SimpleNamespace(payment_id=99, status="succeeded")
    message = SimpleNamespace(
        successful_payment=SimpleNamespace(provider_payment_charge_id="stars-charge-1"),
        from_user=SimpleNamespace(id=42),
    )

    monkeypatch.setattr(
        stars_service.payment_dal,
        "get_payment_by_db_id",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(
        stars_service.payment_dal,
        "update_provider_payment_and_status",
        AsyncMock(side_effect=AssertionError("duplicate stars payment must not update")),
    )
    monkeypatch.setattr(
        stars_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("duplicate stars payment must not finalize")),
    )

    service = SimpleNamespace()
    asyncio.run(
        stars_service.StarsService.process_successful_payment(
            service,
            session=session,
            message=message,
            payment_db_id=99,
            months=3,
            stars_amount=150,
            i18n_data={},
            sale_mode="hwid_devices@standard",
        )
    )
