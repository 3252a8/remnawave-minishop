"""Contract tests for the LAVA Business provider.

The LAVA API accepts exactly one signature scheme for outgoing requests:
HMAC-SHA256 over the raw body bytes in the ``Signature`` HTTP header. A
body-embedded ``signature`` field (legacy PHP SDK style) is rejected with
401, so these tests pin the header form. Webhook verification is tolerant:
LAVA shops sign either the raw body or a sorted-keys re-serialization.
"""

import asyncio
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.payment_providers import lava
from bot.payment_providers.lava import LavaConfig, LavaService
from bot.payment_providers.lava import service as lava_service


def _hmac_hex(message: bytes, key: str) -> str:
    return hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _make_service(**config_overrides) -> LavaService:
    config_values = {
        "ENABLED": True,
        "SHOP_ID": "shop-xyz",
        "SECRET_KEY": "outgoing-secret",
        "WEBHOOK_SECRET": "webhook-secret",
    }
    config_values.update(config_overrides)
    service = object.__new__(LavaService)
    service.config = LavaConfig(**config_values)
    service.settings = SimpleNamespace(
        DEFAULT_CURRENCY_SYMBOL="RUB",
        WEBHOOK_BASE_URL="https://bot.example.com",
        PAYMENT_REQUEST_TIMEOUT_SECONDS=30,
    )
    service._default_return_url = "testbot"
    return service


class _FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status = status
        self._payload = (
            payload
            if payload is not None
            else {"status": "success", "data": {"id": "inv-1", "url": "https://pay.lava.ru/x"}}
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

    session.post = post
    return session


class _FakeWebhookRequest:
    def __init__(self, payload, signature=None, secret="webhook-secret"):
        self._body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.headers = {
            "Authorization": signature if signature is not None else _hmac_hex(self._body, secret)
        }

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


def test_create_payment_signs_raw_body_in_signature_header(monkeypatch):
    service = _make_service()
    captured = {}
    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=_capture_session(captured)))

    success, data = asyncio.run(
        service.create_payment(payment_db_id=77, amount=150.0, currency="RUB")
    )

    assert success
    assert data == {"id": "inv-1", "url": "https://pay.lava.ru/x"}
    assert captured["url"] == "https://api.lava.ru/business/invoice/create"
    # Signature travels in the header and matches the exact bytes sent.
    assert captured["headers"]["Signature"] == _hmac_hex(captured["data"], "outgoing-secret")
    body = json.loads(captured["data"])
    assert "signature" not in body
    assert body["sum"] == 150.0
    assert body["orderId"] == "77"
    assert body["shopId"] == "shop-xyz"
    assert body["hookUrl"] == "https://bot.example.com/webhook/lava"


def test_create_payment_keeps_payload_key_order(monkeypatch):
    # A sorted-keys re-serialization would diverge from the signed raw body,
    # so the wire format must preserve insertion order ("sum" before "hookUrl").
    service = _make_service()
    captured = {}
    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=_capture_session(captured)))

    asyncio.run(service.create_payment(payment_db_id=1, amount=10.0, currency="RUB"))

    text = captured["data"].decode("utf-8")
    assert text.find('"sum"') < text.find('"hookUrl"')


def test_create_payment_rejects_non_rub_currency(monkeypatch):
    service = _make_service()
    monkeypatch.setattr(
        service,
        "_get_session",
        AsyncMock(side_effect=AssertionError("must not reach the API for unsupported currency")),
    )

    success, data = asyncio.run(
        service.create_payment(payment_db_id=1, amount=10.0, currency="USD")
    )

    assert not success
    assert data["message"] == "unsupported_currency"


def test_create_payment_surfaces_api_error(monkeypatch):
    service = _make_service()
    captured = {}
    response = _FakeResponse(
        status=401, payload={"status": "error", "error": "Invalid signature", "code": 401}
    )
    monkeypatch.setattr(
        service,
        "_get_session",
        AsyncMock(return_value=_capture_session(captured, response=response)),
    )

    success, data = asyncio.run(
        service.create_payment(payment_db_id=1, amount=10.0, currency="RUB")
    )

    assert not success
    assert data["message"] == "Invalid signature"


def test_create_payment_passes_optional_invoice_fields(monkeypatch):
    service = _make_service(LIFETIME_MINUTES=90, INCLUDE_SERVICES="card, sbp")
    captured = {}
    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=_capture_session(captured)))

    asyncio.run(
        service.create_payment(
            payment_db_id=5, amount=10.0, currency="RUB", description="Subscription 1m"
        )
    )

    body = json.loads(captured["data"])
    assert body["expire"] == 90
    assert body["comment"] == "Subscription 1m"
    assert body["includeService"] == ["card", "sbp"]


def test_service_is_unconfigured_without_credentials():
    assert not _make_service(SHOP_ID=None).configured
    assert not _make_service(SECRET_KEY=None).configured
    assert not _make_service(ENABLED=False).configured
    assert _make_service().configured
    assert _make_service(ENABLED=False, ADMIN_ONLY_ENABLED=True).configured


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------


def test_webhook_signature_accepts_raw_body_hmac():
    service = _make_service()
    body = b'{"order_id":"1","status":"success"}'

    assert service.verify_webhook_signature(body, _hmac_hex(body, "webhook-secret"))


def test_webhook_signature_accepts_canonical_sorted_json_hmac():
    # Legacy PHP-SDK shops sign a sorted-keys re-serialization instead of the raw body.
    service = _make_service()
    body = b'{"status":"success","order_id":"1"}'
    canonical = json.dumps(
        {"order_id": "1", "status": "success"}, sort_keys=True, separators=(",", ":")
    )
    signature = _hmac_hex(canonical.encode("utf-8"), "webhook-secret")

    assert service.verify_webhook_signature(body, signature)


def test_webhook_signature_rejects_wrong_or_empty_signature():
    service = _make_service()
    body = b'{"order_id":"1","status":"success"}'

    assert not service.verify_webhook_signature(body, "deadbeef" * 8)
    assert not service.verify_webhook_signature(body, "")


def test_webhook_signature_falls_back_to_secret_key():
    service = _make_service(WEBHOOK_SECRET=None)
    body = b'{"order_id":"1"}'

    assert service.verify_webhook_signature(body, _hmac_hex(body, "outgoing-secret"))


def test_webhook_signature_fails_closed_without_any_secret():
    service = _make_service(SECRET_KEY=None, WEBHOOK_SECRET=None)
    body = b'{"order_id":"1"}'

    assert not service.verify_webhook_signature(body, _hmac_hex(body, ""))


# ---------------------------------------------------------------------------
# Webhook route behaviour
# ---------------------------------------------------------------------------


def _webhook_service(session, payment, monkeypatch, **overrides):
    monkeypatch.setattr(
        lava_service,
        "lookup_payment_by_order_or_provider_id",
        AsyncMock(return_value=payment),
    )
    service = SimpleNamespace(
        configured=True,
        verify_webhook_signature=lambda _raw, _sig: True,
        async_session_factory=session,
        settings=SimpleNamespace(traffic_sale_mode=False),
        bot=SimpleNamespace(),
        i18n=SimpleNamespace(),
        subscription_service=SimpleNamespace(),
        referral_service=SimpleNamespace(),
    )
    for key, value in overrides.items():
        setattr(service, key, value)
    return service


def test_webhook_invalid_signature_is_rejected():
    service = _make_service()
    request = _FakeWebhookRequest({"order_id": "1", "status": "success"}, signature="f" * 64)

    response = asyncio.run(service.webhook_route(request))

    assert response.status == 403


def test_webhook_duplicate_success_does_not_finalize_again(monkeypatch):
    session = _FakeDbSession()
    payment = SimpleNamespace(
        payment_id=88,
        user_id=42,
        status="succeeded",
        sale_mode="subscription",
        purchased_hwid_devices=None,
        purchased_gb=None,
        subscription_duration_months=1,
        amount=150.0,
        currency="RUB",
        user=None,
    )
    service = _webhook_service(session, payment, monkeypatch)
    monkeypatch.setattr(
        lava.payment_dal,
        "update_provider_payment_and_status",
        AsyncMock(side_effect=AssertionError("duplicate webhook must not update payment")),
    )
    monkeypatch.setattr(
        lava_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("duplicate webhook must not finalize")),
    )

    response = asyncio.run(
        LavaService.webhook_route(
            service,
            _FakeWebhookRequest({"invoice_id": "inv-1", "order_id": "88", "status": "success"}),
        )
    )

    assert response.status == 200


def test_webhook_success_finalizes_payment(monkeypatch):
    session = _FakeDbSession()
    payment = SimpleNamespace(
        payment_id=88,
        user_id=42,
        status="pending_lava",
        sale_mode="subscription",
        purchased_hwid_devices=None,
        purchased_gb=None,
        subscription_duration_months=1,
        amount=150.0,
        currency="RUB",
        user=None,
    )
    service = _webhook_service(session, payment, monkeypatch)
    update_mock = AsyncMock()
    finalize_mock = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(lava.payment_dal, "update_provider_payment_and_status", update_mock)
    monkeypatch.setattr(lava_service, "finalize_successful_payment", finalize_mock)

    response = asyncio.run(
        LavaService.webhook_route(
            service,
            _FakeWebhookRequest(
                {"invoice_id": "inv-1", "order_id": "88", "status": "success", "amount": 150.0}
            ),
        )
    )

    assert response.status == 200
    update_mock.assert_awaited_once_with(
        session,
        88,
        "inv-1",
        lava.PAYMENT_STATUS_PENDING_FINALIZATION,
    )
    finalize_mock.assert_awaited_once()


def test_webhook_success_with_amount_mismatch_is_rejected(monkeypatch):
    session = _FakeDbSession()
    payment = SimpleNamespace(
        payment_id=88,
        user_id=42,
        status="pending_lava",
        sale_mode="subscription",
        purchased_hwid_devices=None,
        purchased_gb=None,
        subscription_duration_months=1,
        amount=150.0,
        currency="RUB",
        user=None,
    )
    service = _webhook_service(session, payment, monkeypatch)
    monkeypatch.setattr(
        lava.payment_dal,
        "update_provider_payment_and_status",
        AsyncMock(side_effect=AssertionError("mismatched amount must not update payment")),
    )
    monkeypatch.setattr(
        lava_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("mismatched amount must not finalize")),
    )

    response = asyncio.run(
        LavaService.webhook_route(
            service,
            _FakeWebhookRequest(
                {"invoice_id": "inv-1", "order_id": "88", "status": "success", "amount": 9999}
            ),
        )
    )

    assert response.status == 400


def test_webhook_failed_status_marks_payment_failed(monkeypatch):
    session = _FakeDbSession()
    payment = SimpleNamespace(
        payment_id=88,
        user_id=42,
        status="pending_lava",
        sale_mode="subscription",
        purchased_hwid_devices=None,
        purchased_gb=None,
        subscription_duration_months=1,
        amount=150.0,
        currency="RUB",
        user=None,
    )
    service = _webhook_service(session, payment, monkeypatch)
    update_mock = AsyncMock()
    notify_mock = AsyncMock()
    monkeypatch.setattr(lava.payment_dal, "update_provider_payment_and_status", update_mock)
    monkeypatch.setattr(lava_service, "notify_user_payment_failed", notify_mock)
    monkeypatch.setattr(
        lava_service,
        "finalize_successful_payment",
        AsyncMock(side_effect=AssertionError("failed webhook must not finalize")),
    )

    response = asyncio.run(
        LavaService.webhook_route(
            service,
            _FakeWebhookRequest({"invoice_id": "inv-1", "order_id": "88", "status": "expired"}),
        )
    )

    assert response.status == 200
    update_mock.assert_awaited_once_with(session, 88, "inv-1", "failed")
    notify_mock.assert_awaited_once()


def test_webhook_unknown_payment_returns_404(monkeypatch):
    session = _FakeDbSession()
    service = _webhook_service(session, None, monkeypatch)

    response = asyncio.run(
        LavaService.webhook_route(
            service,
            _FakeWebhookRequest({"invoice_id": "inv-x", "order_id": "404", "status": "success"}),
        )
    )

    assert response.status == 404


# ---------------------------------------------------------------------------
# Pending payment reuse
# ---------------------------------------------------------------------------


def test_reuse_returns_url_for_pending_invoice(monkeypatch):
    service = _make_service()
    payment = SimpleNamespace(
        payment_id=88,
        provider_payment_id="inv-1",
        provider_payment_url="https://pay.lava.ru/x",
    )
    monkeypatch.setattr(
        service,
        "get_invoice_status",
        AsyncMock(return_value=(True, {"id": "inv-1", "order_id": "88", "status": "created"})),
    )

    assert asyncio.run(service.try_reuse_pending_payment(payment)) == "https://pay.lava.ru/x"


def test_reuse_rejects_terminal_or_foreign_invoices(monkeypatch):
    service = _make_service()
    payment = SimpleNamespace(
        payment_id=88,
        provider_payment_id="inv-1",
        provider_payment_url="https://pay.lava.ru/x",
    )

    monkeypatch.setattr(
        service,
        "get_invoice_status",
        AsyncMock(return_value=(True, {"id": "inv-1", "order_id": "88", "status": "expired"})),
    )
    assert asyncio.run(service.try_reuse_pending_payment(payment)) is None

    monkeypatch.setattr(
        service,
        "get_invoice_status",
        AsyncMock(return_value=(True, {"id": "other", "order_id": "88", "status": "created"})),
    )
    assert asyncio.run(service.try_reuse_pending_payment(payment)) is None

    monkeypatch.setattr(
        service,
        "get_invoice_status",
        AsyncMock(return_value=(True, {"id": "inv-1", "order_id": "99", "status": "created"})),
    )
    assert asyncio.run(service.try_reuse_pending_payment(payment)) is None


def test_reuse_requires_stored_url_and_id():
    service = _make_service()

    assert (
        asyncio.run(
            service.try_reuse_pending_payment(
                SimpleNamespace(payment_id=1, provider_payment_id="", provider_payment_url="")
            )
        )
        is None
    )
