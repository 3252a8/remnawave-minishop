"""Contract tests for the Pally / PayPalych provider."""

import asyncio
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlencode

from bot.payment_providers.pally import PallyConfig, PallyService
from bot.payment_providers.pally import service as pally_service


def _md5_upper(value: str) -> str:
    try:
        digest = hashlib.md5(value.encode("utf-8"), usedforsecurity=False)
    except TypeError:  # pragma: no cover
        digest = hashlib.md5(value.encode("utf-8"))
    return digest.hexdigest().upper()


def _make_service(**config_overrides) -> PallyService:
    config_values = {
        "ENABLED": True,
        "API_TOKEN": "api-token",
        "SIGNATURE_TOKEN": "signature-token",
        "SHOP_ID": "shop-xyz",
    }
    config_values.update(config_overrides)
    service = object.__new__(PallyService)
    service.config = PallyConfig(**config_values)
    service.settings = SimpleNamespace(
        DEFAULT_CURRENCY_SYMBOL="RUB",
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
            else {
                "success": True,
                "bill_id": "bill-1",
                "link_page_url": "https://pally.info/transfer/bill-1",
                "status": "NEW",
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

    def post(url, data=None, headers=None):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        return response or _FakeResponse()

    def get(url, params=None, headers=None):
        captured["get_url"] = url
        captured["params"] = params
        captured["get_headers"] = headers
        return response or _FakeResponse(payload={"success": True, "id": "bill-1", "status": "NEW"})

    session.post = post
    session.get = get
    return session


class _FakeWebhookRequest:
    def __init__(self, fields):
        self._body = urlencode(fields).encode("utf-8")

    async def read(self):
        return self._body


class _FakeDbSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _payment(**overrides):
    values = {
        "payment_id": 77,
        "user_id": 42,
        "status": "pending_pally",
        "sale_mode": "subscription",
        "purchased_hwid_devices": None,
        "purchased_gb": None,
        "subscription_duration_months": 1,
        "amount": 100.0,
        "currency": "RUB",
        "user": None,
        "provider_payment_id": "bill-1",
        "provider_payment_url": "https://pally.info/transfer/bill-1",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_create_bill_posts_form_with_bearer_auth(monkeypatch):
    service = _make_service(PAYER_PAYS_COMMISSION=True, PAYMENT_METHOD="SBP", TTL_SECONDS=600)
    captured = {}
    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=_capture_session(captured)))

    success, data = asyncio.run(
        service.create_bill(
            payment_db_id=77,
            amount=100.0,
            currency="RUB",
            description="Subscription 1m",
            language="ru",
        )
    )

    assert success
    assert data["bill_id"] == "bill-1"
    assert captured["url"] == "https://pally.info/api/v1/bill/create"
    assert captured["headers"]["Authorization"] == "Bearer api-token"
    assert captured["data"]["amount"] == "100.00"
    assert captured["data"]["shop_id"] == "shop-xyz"
    assert captured["data"]["order_id"] == "77"
    assert captured["data"]["type"] == "normal"
    assert captured["data"]["currency_in"] == "RUB"
    assert captured["data"]["payer_pays_commission"] == "1"
    assert captured["data"]["payment_method"] == "SBP"
    assert captured["data"]["ttl"] == "600"
    assert captured["data"]["locale"] == "ru"


def test_create_bill_rejects_unsupported_currency(monkeypatch):
    service = _make_service()
    monkeypatch.setattr(
        service,
        "_get_session",
        AsyncMock(side_effect=AssertionError("must not reach API for unsupported currency")),
    )

    success, data = asyncio.run(service.create_bill(payment_db_id=1, amount=10.0, currency="JPY"))

    assert not success
    assert data["message"] == "unsupported_currency"


def test_signature_uses_outsum_invid_and_signature_token():
    service = _make_service()
    expected = _md5_upper("123.45:order-1:signature-token")

    assert service.calculate_signature("123.45", "order-1") == expected
    assert service.verify_signature("123.45", "order-1", expected.lower())


def test_webhook_success_accepts_commission_adjusted_amount(monkeypatch):
    session = _FakeDbSession()
    payment = _payment()
    service = _make_service()
    service.async_session_factory = session
    service.bot = SimpleNamespace()
    service.i18n = SimpleNamespace()
    service.subscription_service = SimpleNamespace()
    service.referral_service = SimpleNamespace()

    async def lookup_payment(_session, *, order_id_raw=None, provider_payment_id=None):
        assert _session is session
        assert order_id_raw == "77"
        assert provider_payment_id == "bill-1"
        return payment

    update_mock = AsyncMock()
    finalize_mock = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(pally_service, "lookup_payment_by_order_or_provider_id", lookup_payment)
    monkeypatch.setattr(
        pally_service.payment_dal, "update_provider_payment_and_status", update_mock
    )
    monkeypatch.setattr(pally_service, "finalize_successful_payment", finalize_mock)

    signature = service.calculate_signature("102.50", "77")
    response = asyncio.run(
        service.webhook_route(
            _FakeWebhookRequest(
                {
                    "InvId": "77",
                    "OutSum": "102.50",
                    "Commission": "2.50",
                    "CurrencyIn": "RUB",
                    "TrsId": "bill-1",
                    "Status": "SUCCESS",
                    "SignatureValue": signature,
                }
            )
        )
    )

    assert response.status == 200
    update_mock.assert_awaited_once_with(
        session,
        77,
        "bill-1",
        pally_service.PAYMENT_STATUS_PENDING_FINALIZATION,
    )
    finalize_mock.assert_awaited_once()


def test_webhook_rejects_wrong_signature(monkeypatch):
    service = _make_service()
    service.async_session_factory = _FakeDbSession()
    monkeypatch.setattr(
        pally_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(side_effect=AssertionError("invalid signature must stop before DB lookup")),
    )

    response = asyncio.run(
        service.webhook_route(
            _FakeWebhookRequest(
                {
                    "InvId": "77",
                    "OutSum": "100.00",
                    "TrsId": "bill-1",
                    "Status": "SUCCESS",
                    "SignatureValue": "bad",
                }
            )
        )
    )

    assert response.status == 403


def test_reuse_returns_url_for_pending_bill(monkeypatch):
    service = _make_service()
    monkeypatch.setattr(
        service,
        "get_bill_status",
        AsyncMock(return_value=(True, {"id": "bill-1", "order_id": "77", "status": "NEW"})),
    )

    assert (
        asyncio.run(service.try_reuse_pending_bill(_payment()))
        == "https://pally.info/transfer/bill-1"
    )


def test_reuse_rejects_terminal_or_foreign_bill(monkeypatch):
    service = _make_service()
    payment = _payment()

    monkeypatch.setattr(
        service,
        "get_bill_status",
        AsyncMock(return_value=(True, {"id": "bill-1", "order_id": "77", "status": "SUCCESS"})),
    )
    assert asyncio.run(service.try_reuse_pending_bill(payment)) is None

    monkeypatch.setattr(
        service,
        "get_bill_status",
        AsyncMock(return_value=(True, {"id": "other", "order_id": "77", "status": "NEW"})),
    )
    assert asyncio.run(service.try_reuse_pending_bill(payment)) is None

    monkeypatch.setattr(
        service,
        "get_bill_status",
        AsyncMock(return_value=(True, {"id": "bill-1", "order_id": "99", "status": "NEW"})),
    )
    assert asyncio.run(service.try_reuse_pending_bill(payment)) is None
