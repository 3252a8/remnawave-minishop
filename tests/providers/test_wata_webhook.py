import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.payment_providers.shared import PAYMENT_STATUS_PENDING_FINALIZATION
from bot.payment_providers.wata import WataConfig, WataService
from bot.payment_providers.wata import service as wata_service
from bot.payment_providers.wata.config import _parse_wata_datetime


class _FakeRequest:
    def __init__(self, payload):
        self.headers = {}
        self.remote = "127.0.0.1"
        self._raw_body = json.dumps(payload).encode("utf-8")

    async def read(self):
        return self._raw_body


class _FakeSession:
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
        "payment_id": 465,
        "user_id": 748116183,
        "status": "pending_wata",
        "amount": 100.0,
        "currency": "RUB",
        "provider_payment_id": "link-id",
        "purchased_gb": None,
        "purchased_hwid_devices": None,
        "subscription_duration_months": 1,
        "sale_mode": "subscription",
        "user": None,
        "created_at": datetime.now(UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _service(session, **config_overrides):
    settings = SimpleNamespace(
        DEFAULT_CURRENCY_SYMBOL="RUB",
        DEFAULT_LANGUAGE="ru",
        PAYMENT_REQUEST_TIMEOUT_SECONDS=15,
        traffic_sale_mode=False,
        trusted_proxies=[],
    )
    config_values = {
        "ENABLED": True,
        "API_TOKEN": "token",
        "WEBHOOK_VERIFY_SIGNATURE": False,
        "TRUSTED_IPS": "",
    }
    config_values.update(config_overrides)
    return WataService(
        bot=SimpleNamespace(),
        settings=settings,
        config=WataConfig(**config_values),
        i18n=SimpleNamespace(),
        async_session_factory=session,
        subscription_service=SimpleNamespace(),
        referral_service=SimpleNamespace(),
        default_return_url="test_bot",
    )


async def _run_and_close(service, awaitable):
    try:
        return await awaitable
    finally:
        await service.close()


def test_wata_created_webhook_returns_ok_and_persists_transaction_id(monkeypatch):
    session = _FakeSession()
    payment = _payment()
    updates = []

    async def lookup_payment(
        _session, *, providers=None, order_id_raw=None, provider_payment_id=None
    ):
        assert _session is session
        assert order_id_raw == "465"
        assert provider_payment_id == "tx-1"
        return payment

    async def update_provider_payment_and_status(
        _session,
        payment_id,
        provider_payment_id,
        status,
    ):
        updates.append((payment_id, provider_payment_id, status))

    monkeypatch.setattr(wata_service, "lookup_payment_by_order_or_provider_id", lookup_payment)
    monkeypatch.setattr(
        wata_service.payment_dal,
        "update_provider_payment_and_status",
        update_provider_payment_and_status,
    )

    response = asyncio.run(
        _service(session).webhook_route(
            _FakeRequest(
                {
                    "transactionStatus": "Created",
                    "transactionId": "tx-1",
                    "orderId": "465",
                    "amount": 100,
                    "currency": "RUB",
                }
            )
        )
    )

    assert response.status == 200
    assert updates == [(465, "tx-1", "pending_wata")]
    assert session.commits == 1
    assert session.rollbacks == 0


def test_wata_created_webhook_can_find_payment_by_payment_link_id(monkeypatch):
    session = _FakeSession()
    payment = _payment()
    lookup_calls = []
    updates = []

    async def lookup_payment(
        _session, *, providers=None, order_id_raw=None, provider_payment_id=None
    ):
        lookup_calls.append((order_id_raw, provider_payment_id))
        if provider_payment_id == "link-id":
            return payment
        return None

    async def update_provider_payment_and_status(
        _session,
        payment_id,
        provider_payment_id,
        status,
    ):
        updates.append((payment_id, provider_payment_id, status))

    monkeypatch.setattr(wata_service, "lookup_payment_by_order_or_provider_id", lookup_payment)
    monkeypatch.setattr(
        wata_service.payment_dal,
        "update_provider_payment_and_status",
        update_provider_payment_and_status,
    )

    response = asyncio.run(
        _service(session).webhook_route(
            _FakeRequest(
                {
                    "transactionStatus": "Created",
                    "transactionId": "tx-1",
                    "paymentLinkId": "link-id",
                    "amount": 100,
                    "currency": "RUB",
                }
            )
        )
    )

    assert response.status == 200
    assert lookup_calls == [(None, "tx-1"), (None, "link-id")]
    assert updates == [(465, "tx-1", "pending_wata")]
    assert session.commits == 1


def test_wata_known_payment_with_unknown_status_still_acknowledges_webhook(monkeypatch):
    session = _FakeSession()
    payment = _payment(provider_payment_id="tx-1")

    async def lookup_payment(
        _session, *, providers=None, order_id_raw=None, provider_payment_id=None
    ):
        return payment

    async def update_provider_payment_and_status(*args, **kwargs):
        raise AssertionError("unknown statuses must not mutate payment state")

    monkeypatch.setattr(wata_service, "lookup_payment_by_order_or_provider_id", lookup_payment)
    monkeypatch.setattr(
        wata_service.payment_dal,
        "update_provider_payment_and_status",
        update_provider_payment_and_status,
    )

    response = asyncio.run(
        _service(session).webhook_route(
            _FakeRequest(
                {
                    "transactionStatus": "WaitingForBank",
                    "transactionId": "tx-1",
                    "orderId": "465",
                }
            )
        )
    )

    assert response.status == 200
    assert session.commits == 0


def test_wata_refresh_finds_paid_transaction_by_order_id_and_finalizes(monkeypatch):
    session = _FakeSession()
    payment = _payment(provider="wata", provider_payment_id="link-id")
    claims = []
    finalized = []
    service = _service(session)

    async def search_transactions(
        *,
        order_id=None,
        payment_link_id=None,
        status=None,
        limit=5,
        profile=None,
    ):
        assert order_id == "465"
        assert payment_link_id is None
        assert status == "Paid"
        assert limit == 5
        return True, {
            "items": [
                {
                    "id": "tx-paid",
                    "status": "Paid",
                    "orderId": "465",
                    "amount": 100,
                    "currency": "RUB",
                    "paymentLinkId": "link-id",
                }
            ]
        }

    async def get_payment_by_db_id(_session, payment_id):
        assert _session is session
        assert payment_id == 465
        return payment

    async def claim_payment_finalization(
        _session,
        payment_id,
        *,
        provider_payment_id=None,
        provider_payment_url=None,
    ):
        claims.append((payment_id, provider_payment_id))
        payment.provider_payment_id = provider_payment_id
        payment.status = PAYMENT_STATUS_PENDING_FINALIZATION
        return payment

    async def finalize_successful_payment(request):
        assert session.commits == 0
        finalized.append(
            (
                request.payment.payment_id,
                request.provider_subscription,
                request.provider_notification,
            )
        )
        await request.session.commit()
        return SimpleNamespace()

    service.search_transactions = search_transactions
    monkeypatch.setattr(wata_service.payment_dal, "get_payment_by_db_id", get_payment_by_db_id)
    monkeypatch.setattr(
        wata_service.payment_dal,
        "claim_payment_finalization",
        claim_payment_finalization,
    )
    monkeypatch.setattr(wata_service, "finalize_successful_payment", finalize_successful_payment)

    result = asyncio.run(service.refresh_payment_status(session, payment))

    assert result is payment
    assert claims == [(465, "tx-paid")]
    assert finalized == [(465, "wata", "wata")]
    assert session.commits == 1


def test_wata_webhook_rejects_paid_amount_mismatch_before_finalization(monkeypatch):
    session = _FakeSession()
    payment = _payment(provider="wata", provider_payment_id="link-id")
    service = _service(session)
    claim_mock = AsyncMock(side_effect=AssertionError("mismatched payment must not be claimed"))
    finalize_mock = AsyncMock(side_effect=AssertionError("mismatched payment must not finalize"))

    async def lookup_payment(
        _session, *, providers=None, order_id_raw=None, provider_payment_id=None
    ):
        assert _session is session
        assert order_id_raw == "465"
        assert provider_payment_id == "tx-paid"
        return payment

    monkeypatch.setattr(wata_service, "lookup_payment_by_order_or_provider_id", lookup_payment)
    monkeypatch.setattr(
        wata_service.payment_dal,
        "get_payment_by_db_id",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(wata_service.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(wata_service, "finalize_successful_payment", finalize_mock)

    response = asyncio.run(
        service.webhook_route(
            _FakeRequest(
                {
                    "transactionStatus": "Paid",
                    "transactionId": "tx-paid",
                    "orderId": "465",
                    "amount": 99,
                    "currency": "RUB",
                }
            )
        )
    )

    assert response.status == 400
    assert response.text == "amount_mismatch"
    claim_mock.assert_not_awaited()
    finalize_mock.assert_not_awaited()


def test_wata_status_refresh_skips_paid_transaction_without_currency(monkeypatch):
    session = _FakeSession()
    payment = _payment(provider="wata", provider_payment_id="link-id")
    service = _service(session)
    claim_mock = AsyncMock(side_effect=AssertionError("missing currency must not be claimed"))
    finalize_mock = AsyncMock(side_effect=AssertionError("missing currency must not finalize"))

    async def search_transactions(**_kwargs):
        return True, {
            "items": [
                {
                    "id": "tx-paid",
                    "status": "Paid",
                    "orderId": "465",
                    "amount": 100,
                    "paymentLinkId": "link-id",
                }
            ]
        }

    service.search_transactions = search_transactions
    monkeypatch.setattr(
        wata_service.payment_dal,
        "get_payment_by_db_id",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(wata_service.payment_dal, "claim_payment_finalization", claim_mock)
    monkeypatch.setattr(wata_service, "finalize_successful_payment", finalize_mock)

    result = asyncio.run(service.refresh_payment_status(session, payment))

    assert result is payment
    claim_mock.assert_not_awaited()
    finalize_mock.assert_not_awaited()


def test_wata_duplicate_paid_refresh_returns_fresh_payment(monkeypatch):
    session = _FakeSession()
    payment = _payment(status="pending_wata")
    refreshed_payment = _payment(status="succeeded", provider_payment_id="tx-paid")
    service = _service(session)
    fresh_loads = []

    async def get_payment_by_db_id(_session, payment_id, *, fresh=False):
        assert _session is session
        assert payment_id == 465
        if fresh:
            fresh_loads.append(payment_id)
            return refreshed_payment
        return payment

    monkeypatch.setattr(wata_service.payment_dal, "get_payment_by_db_id", get_payment_by_db_id)
    claim = AsyncMock(return_value=None)
    finalize = AsyncMock(side_effect=AssertionError("duplicate payment must not finalize"))
    monkeypatch.setattr(wata_service.payment_dal, "claim_payment_finalization", claim)
    monkeypatch.setattr(wata_service, "finalize_successful_payment", finalize)

    result = asyncio.run(
        service._mark_paid_from_payload(
            session,
            payment,
            {"transactionId": "tx-paid", "amount": 100, "currency": "RUB"},
            log_prefix="Wata refresh",
        )
    )

    assert result is refreshed_payment
    assert fresh_loads == [465]
    claim.assert_awaited_once_with(session, 465, provider_payment_id="tx-paid")
    finalize.assert_not_awaited()


def test_wata_hwid_payment_finalizes_purchased_device_count(monkeypatch):
    session = _FakeSession()
    payment = _payment(
        provider="wata",
        provider_payment_id="link-id",
        sale_mode="hwid_devices@standard",
        subscription_duration_months=None,
        purchased_hwid_devices=3,
    )
    finalized = []
    service = _service(session)

    async def search_transactions(
        *,
        order_id=None,
        payment_link_id=None,
        status=None,
        limit=5,
        profile=None,
    ):
        return True, {
            "items": [
                {
                    "id": "tx-paid",
                    "status": "Paid",
                    "orderId": "465",
                    "amount": 100,
                    "currency": "RUB",
                    "paymentLinkId": "link-id",
                }
            ]
        }

    async def get_payment_by_db_id(_session, payment_id):
        assert payment_id == 465
        return payment

    async def claim_payment_finalization(
        _session,
        payment_id,
        *,
        provider_payment_id=None,
        provider_payment_url=None,
    ):
        payment.provider_payment_id = provider_payment_id
        payment.status = PAYMENT_STATUS_PENDING_FINALIZATION
        return payment

    async def finalize_successful_payment(request):
        finalized.append((request.months, request.traffic_amount, request.sale_mode))
        return SimpleNamespace()

    service.search_transactions = search_transactions
    monkeypatch.setattr(wata_service.payment_dal, "get_payment_by_db_id", get_payment_by_db_id)
    monkeypatch.setattr(
        wata_service.payment_dal,
        "claim_payment_finalization",
        claim_payment_finalization,
    )
    monkeypatch.setattr(wata_service, "finalize_successful_payment", finalize_successful_payment)

    result = asyncio.run(service.refresh_payment_status(session, payment))

    assert result is payment
    assert finalized == [(3, 3.0, "hwid_devices@standard")]


def test_try_reuse_pending_link_returns_url_for_opened_link():
    service = _service(_FakeSession())
    payment = _payment(provider_payment_id="link-id")

    future_iso = "2099-01-01T00:00:00Z"

    async def fake_get_payment_link(payment_link_id, *, profile=None):
        assert payment_link_id == "link-id"
        return True, {
            "id": "link-id",
            "status": "Opened",
            "url": "https://wata.pro/p/link-id",
            "expirationDateTime": future_iso,
        }

    service.get_payment_link = fake_get_payment_link

    url = asyncio.run(service.try_reuse_pending_link(payment))
    assert url == "https://wata.pro/p/link-id"


def test_try_reuse_pending_link_returns_none_for_other_link_id():
    service = _service(_FakeSession())
    payment = _payment(provider_payment_id="link-id")

    async def fake_get_payment_link(payment_link_id, *, profile=None):
        assert payment_link_id == "link-id"
        return True, {
            "id": "other-link-id",
            "status": "Opened",
            "url": "https://wata.pro/p/other-link-id",
            "expirationDateTime": "2099-01-01T00:00:00Z",
        }

    service.get_payment_link = fake_get_payment_link

    url = asyncio.run(service.try_reuse_pending_link(payment))
    assert url is None


def test_try_reuse_pending_link_returns_none_for_other_order_id():
    service = _service(_FakeSession())
    payment = _payment(provider_payment_id="link-id")

    async def fake_get_payment_link(payment_link_id, *, profile=None):
        assert payment_link_id == "link-id"
        return True, {
            "id": "link-id",
            "orderId": "999",
            "status": "Opened",
            "url": "https://wata.pro/p/link-id",
            "expirationDateTime": "2099-01-01T00:00:00Z",
        }

    service.get_payment_link = fake_get_payment_link

    url = asyncio.run(service.try_reuse_pending_link(payment))
    assert url is None


def test_try_reuse_pending_link_returns_none_for_closed_link():
    service = _service(_FakeSession())
    payment = _payment(provider_payment_id="link-id")

    async def fake_get_payment_link(payment_link_id, *, profile=None):
        return True, {
            "id": "link-id",
            "status": "Closed",
            "url": "https://wata.pro/p/link-id",
            "expirationDateTime": "2099-01-01T00:00:00Z",
        }

    service.get_payment_link = fake_get_payment_link

    url = asyncio.run(service.try_reuse_pending_link(payment))
    assert url is None


def test_try_reuse_pending_link_returns_none_for_expired_link():
    service = _service(_FakeSession())
    payment = _payment(provider_payment_id="link-id")

    async def fake_get_payment_link(payment_link_id, *, profile=None):
        return True, {
            "id": "link-id",
            "status": "Opened",
            "url": "https://wata.pro/p/link-id",
            "expirationDateTime": "2000-01-01T00:00:00Z",
        }

    service.get_payment_link = fake_get_payment_link

    url = asyncio.run(service.try_reuse_pending_link(payment))
    assert url is None


def test_try_reuse_pending_link_returns_none_when_no_provider_payment_id():
    service = _service(_FakeSession())
    payment = _payment(provider_payment_id=None)

    async def fake_get_payment_link(payment_link_id, *, profile=None):
        raise AssertionError("get_payment_link must not be called without provider id")

    service.get_payment_link = fake_get_payment_link

    url = asyncio.run(service.try_reuse_pending_link(payment))
    assert url is None


def test_try_reuse_pending_link_returns_none_when_get_fails():
    service = _service(_FakeSession())
    payment = _payment(provider_payment_id="link-id")

    async def fake_get_payment_link(payment_link_id, *, profile=None):
        return False, {"status": 429, "message": "rate_limited"}

    service.get_payment_link = fake_get_payment_link

    url = asyncio.run(service.try_reuse_pending_link(payment))
    assert url is None


def test_create_payment_link_uses_clean_iso_expiration_without_microseconds(monkeypatch):
    captured = {}

    async def fake_post_json_request(session, url, *, body, headers, log_prefix, is_success):
        captured["body"] = body
        return True, {"id": "link-1", "url": "https://wata.pro/p/link-1"}

    monkeypatch.setattr(wata_service, "post_json_request", fake_post_json_request)

    service = _service(_FakeSession())

    success, _ = asyncio.run(
        _run_and_close(
            service,
            service.create_payment_link(
                payment_db_id=465,
                amount=199.5,
                currency="RUB",
                description="Оплата подписки на 1 мес.",
            ),
        )
    )
    assert success is True

    expiration = captured["body"]["expirationDateTime"]
    assert expiration.endswith("Z"), expiration
    assert "." not in expiration, expiration
    assert "+" not in expiration, expiration
    expiration_dt = _parse_wata_datetime(expiration)
    assert expiration_dt is not None
    ttl_delta = expiration_dt - datetime.now(UTC)
    assert timedelta(minutes=14, seconds=30) <= ttl_delta <= timedelta(minutes=15, seconds=30)


def test_create_crypto_payment_link_uses_crypto_terminal_credentials(monkeypatch):
    captured = {}

    async def fake_post_json_request(session, url, *, body, headers, log_prefix, is_success):
        captured["body"] = body
        captured["headers"] = headers
        captured["log_prefix"] = log_prefix
        return True, {"id": "crypto-link", "url": "https://wata.pro/p/crypto-link"}

    monkeypatch.setattr(wata_service, "post_json_request", fake_post_json_request)

    service = _service(
        _FakeSession(),
        CRYPTO_ENABLED=True,
        CRYPTO_API_TOKEN="crypto-token",
        CRYPTO_RETURN_URL="https://example.com/ok",
        CRYPTO_FAILED_URL="https://example.com/fail",
        CRYPTO_LINK_TTL_MINUTES=45,
    )

    success, _ = asyncio.run(
        _run_and_close(
            service,
            service.create_payment_link(
                payment_db_id=465,
                amount=199.5,
                currency="RUB",
                description="Crypto payment",
                method="wata_crypto",
            ),
        )
    )

    assert success is True
    assert captured["headers"]["Authorization"] == "Bearer crypto-token"
    assert captured["body"]["successRedirectUrl"] == "https://example.com/ok"
    assert captured["body"]["failRedirectUrl"] == "https://example.com/fail"
    assert captured["log_prefix"] == "Wata crypto create_payment_link"
    expiration = _parse_wata_datetime(captured["body"]["expirationDateTime"])
    assert expiration is not None
    ttl_delta = expiration - datetime.now(UTC)
    assert timedelta(minutes=44, seconds=30) <= ttl_delta <= timedelta(minutes=45, seconds=30)


def test_wata_link_ttl_uses_minutes_with_default_and_minimum():
    default_config = WataConfig(ENABLED=True, API_TOKEN="token")
    assert default_config.LINK_TTL_MINUTES == 15

    too_short_config = WataConfig(ENABLED=True, API_TOKEN="token", LINK_TTL_MINUTES=10)
    assert too_short_config.LINK_TTL_MINUTES == 15

    custom_config = WataConfig(ENABLED=True, API_TOKEN="token", LINK_TTL_MINUTES=45)
    assert custom_config.LINK_TTL_MINUTES == 45


def test_try_reuse_pending_link_uses_crypto_profile():
    service = _service(
        _FakeSession(),
        CRYPTO_ENABLED=True,
        CRYPTO_API_TOKEN="crypto-token",
    )
    payment = _payment(provider="wata_crypto", provider_payment_id="crypto-link")

    async def fake_get_payment_link(payment_link_id, *, profile=None):
        assert payment_link_id == "crypto-link"
        assert profile is not None
        assert profile.provider == "wata_crypto"
        assert profile.api_token == "crypto-token"
        return True, {
            "id": "crypto-link",
            "status": "Opened",
            "url": "https://wata.pro/p/crypto-link",
            "expirationDateTime": "2099-01-01T00:00:00Z",
        }

    service.get_payment_link = fake_get_payment_link

    url = asyncio.run(service.try_reuse_pending_link(payment))
    assert url == "https://wata.pro/p/crypto-link"


def test_wata_webhook_rejects_mismatched_terminal_public_id(monkeypatch):
    session = _FakeSession()
    payment = _payment(provider="wata")

    async def lookup_payment(
        _session, *, providers=None, order_id_raw=None, provider_payment_id=None
    ):
        return payment

    async def update_provider_payment_and_status(*args, **kwargs):
        raise AssertionError("terminal mismatch must not mutate payment state")

    monkeypatch.setattr(wata_service, "lookup_payment_by_order_or_provider_id", lookup_payment)
    monkeypatch.setattr(
        wata_service.payment_dal,
        "update_provider_payment_and_status",
        update_provider_payment_and_status,
    )

    response = asyncio.run(
        _service(session, TERMINAL_PUBLIC_ID="fiat-public").webhook_route(
            _FakeRequest(
                {
                    "transactionStatus": "Created",
                    "transactionId": "tx-1",
                    "orderId": "465",
                    "terminalPublicId": "other-public",
                }
            )
        )
    )

    assert response.status == 403
    assert response.text == "terminal_mismatch"
    assert session.commits == 0


def test_wata_crypto_webhook_accepts_matching_terminal_public_id(monkeypatch):
    session = _FakeSession()
    payment = _payment(provider="wata_crypto")
    updates = []

    async def lookup_payment(
        _session, *, providers=None, order_id_raw=None, provider_payment_id=None
    ):
        return payment

    async def update_provider_payment_and_status(
        _session,
        payment_id,
        provider_payment_id,
        status,
    ):
        updates.append((payment_id, provider_payment_id, status))

    monkeypatch.setattr(wata_service, "lookup_payment_by_order_or_provider_id", lookup_payment)
    monkeypatch.setattr(
        wata_service.payment_dal,
        "update_provider_payment_and_status",
        update_provider_payment_and_status,
    )

    response = asyncio.run(
        _service(
            session,
            CRYPTO_ENABLED=True,
            CRYPTO_API_TOKEN="crypto-token",
            CRYPTO_TERMINAL_PUBLIC_ID="crypto-public",
        ).webhook_route(
            _FakeRequest(
                {
                    "transactionStatus": "Created",
                    "transactionId": "tx-crypto",
                    "orderId": "465",
                    "terminalPublicId": "crypto-public",
                }
            )
        )
    )

    assert response.status == 200
    assert updates == [(465, "tx-crypto", "pending_wata")]
    assert session.commits == 1


def test_wata_webhook_without_terminal_hint_rechecks_signature_with_payment_profile(monkeypatch):
    session = _FakeSession()
    payment = _payment(provider="wata_crypto")
    updates = []

    async def lookup_payment(
        _session, *, providers=None, order_id_raw=None, provider_payment_id=None
    ):
        return payment

    async def update_provider_payment_and_status(
        _session,
        payment_id,
        provider_payment_id,
        status,
    ):
        updates.append((payment_id, provider_payment_id, status))

    monkeypatch.setattr(wata_service, "lookup_payment_by_order_or_provider_id", lookup_payment)
    monkeypatch.setattr(
        wata_service.payment_dal,
        "update_provider_payment_and_status",
        update_provider_payment_and_status,
    )

    service = _service(
        session,
        WEBHOOK_VERIFY_SIGNATURE=True,
        CRYPTO_ENABLED=True,
        CRYPTO_API_TOKEN="crypto-token",
    )
    verified_profiles = []

    async def verify_signature(raw_body, signature_header, *, profile=None):
        verified_profiles.append(None if profile is None else profile.provider)
        return True

    service._verify_signature = verify_signature

    response = asyncio.run(
        service.webhook_route(
            _FakeRequest(
                {
                    "transactionStatus": "Created",
                    "transactionId": "tx-crypto",
                    "orderId": "465",
                }
            )
        )
    )

    assert response.status == 200
    assert verified_profiles == [None, "wata_crypto"]
    assert updates == [(465, "tx-crypto", "pending_wata")]


def test_refresh_marks_expired_wata_link_as_canceled(monkeypatch):
    session = _FakeSession()
    service = _service(session)
    payment = _payment(
        provider="wata",
        provider_payment_id="link-id",
        created_at=datetime.now(UTC) - timedelta(minutes=16),
    )
    updates = []

    async def find_transaction_for_payment(_payment, *, status):
        return None

    async def get_payment_link(payment_link_id, *, profile=None):
        assert payment_link_id == "link-id"
        return True, {
            "id": "link-id",
            "status": "Opened",
            "expirationDateTime": "2000-01-01T00:00:00Z",
        }

    async def update_provider_payment_and_status(
        _session,
        payment_id,
        provider_payment_id,
        status,
    ):
        updates.append((payment_id, provider_payment_id, status))
        payment.provider_payment_id = provider_payment_id
        payment.status = status

    async def get_payment_by_db_id(_session, payment_id):
        assert payment_id == payment.payment_id
        return payment

    service._find_transaction_for_payment = find_transaction_for_payment
    service.get_payment_link = get_payment_link
    monkeypatch.setattr(
        wata_service.payment_dal,
        "update_provider_payment_and_status",
        update_provider_payment_and_status,
    )
    monkeypatch.setattr(wata_service.payment_dal, "get_payment_by_db_id", get_payment_by_db_id)

    result = asyncio.run(service.refresh_payment_status(session, payment))

    assert result is payment
    assert updates == [(465, "link-id", "canceled")]
    assert session.commits == 1
