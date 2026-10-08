from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.context import SETTINGS
from bot.app.web.webapp import payment_history
from bot.app.web.webapp.payment_history_schemas import PaymentHistoryItemOut
from db.dal.payment_history_dal import list_user_payments, payment_history_filter
from db.models import Payment
from db.payment_history import payment_history_state
from tests.support.settings_stub import settings_stub


def _payment() -> Payment:
    return Payment(
        payment_id=17,
        user_id=42,
        provider="wata",
        amount=120,
        currency="RUB",
        status="succeeded",
        description="Traffic top-up",
        sale_mode="topup@standard",
        purchased_gb=12.5,
        purchased_hwid_devices=2,
        checkout_discount_amount=30,
        created_at=datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
        provider_payment_id="private-provider-id",
        provider_payment_url="https://pay.example.test/private-link",
        idempotence_key="private-key",
        fulfillment_note="Internal fulfillment note",
    )


def test_history_requires_authentication_before_database_access() -> None:
    app = web.Application()
    app[SETTINGS] = settings_stub()
    request = make_mocked_request("GET", "/api/payments/history", app=app)
    with (
        patch.object(payment_history, "get_session_factory") as factory,
        pytest.raises(web.HTTPUnauthorized),
    ):
        asyncio.run(payment_history.payment_history_route(request))
    factory.assert_not_called()


@pytest.mark.parametrize("query", ["limit=oops", "offset=oops", "limit=", "offset="])
def test_history_rejects_invalid_pagination(query: str) -> None:
    request = make_mocked_request("GET", f"/api/payments/history?{query}")
    with (
        patch.object(payment_history, "_require_user_id", return_value=42),
        patch.object(payment_history, "get_session_factory") as factory,
    ):
        response = asyncio.run(payment_history.payment_history_route(request))
    assert response.status == 400
    assert json.loads(response.text)["error"] == "invalid_pagination"
    factory.assert_not_called()


@pytest.mark.parametrize(
    ("query", "limit", "offset"),
    [("", 10, 0), ("limit=999&offset=10", 100, 10), ("limit=-1&offset=-2", 1, 0)],
)
def test_history_uses_current_account_and_bounded_pagination(
    query: str, limit: int, offset: int
) -> None:
    request = make_mocked_request("GET", f"/api/payments/history?user_id=999&{query}")
    session = AsyncMock(spec=AsyncSession)
    session_manager = MagicMock()
    session_manager.__aenter__ = AsyncMock(return_value=session)
    session_manager.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=session_manager)
    listing = AsyncMock(return_value=([_payment()], 23))
    with (
        patch.object(payment_history, "_require_user_id", return_value=42),
        patch.object(payment_history, "get_session_factory", return_value=factory),
        patch.object(payment_history, "list_user_payments", listing),
    ):
        response = asyncio.run(payment_history.payment_history_route(request))
    listing.assert_awaited_once_with(session, 42, limit=limit, offset=offset)
    payload = json.loads(response.text)
    assert payload["ok"] is True
    assert (payload["total"], payload["limit"], payload["offset"]) == (23, limit, offset)
    assert payload["items"][0]["payment_id"] == 17
    assert payload["items"][0]["created_at"] == "2026-01-02T03:04:00+00:00"


def test_empty_history_preserves_total_and_requested_offset() -> None:
    request = make_mocked_request("GET", "/api/payments/history?offset=100")
    manager = MagicMock()
    manager.__aenter__ = AsyncMock()
    manager.__aexit__ = AsyncMock(return_value=False)
    with (
        patch.object(payment_history, "_require_user_id", return_value=42),
        patch.object(payment_history, "get_session_factory", return_value=lambda: manager),
        patch.object(payment_history, "list_user_payments", AsyncMock(return_value=([], 3))),
    ):
        response = asyncio.run(payment_history.payment_history_route(request))
    assert json.loads(response.text) == {
        "ok": True,
        "items": [],
        "total": 3,
        "limit": 10,
        "offset": 100,
    }


def test_history_serialization_keeps_purchase_data_without_private_fields() -> None:
    payment = _payment()
    payload = PaymentHistoryItemOut.from_orm_payment(payment).model_dump(mode="json")
    assert payload["traffic_regular_gb"] == 12.5
    assert payload["traffic_premium_gb"] is None
    assert payload["checkout_discount_amount"] == 30
    assert payload["history_state"] == "completed"
    assert payload["checkout_url"] is None
    assert [(item["kind"], item["amount"]) for item in payload["purchases"]] == [
        ("traffic", 12.5),
        ("hwid_devices", 2),
    ]
    for key in (
        "user_id",
        "user_label",
        "telegram_id",
        "provider_payment_id",
        "provider_payment_url",
        "idempotence_key",
        "fulfillment_note",
    ):
        assert key not in payload


@pytest.mark.parametrize("naive_expiry", [False, True])
def test_history_exposes_active_checkout_only_for_awaiting_payment(naive_expiry: bool) -> None:
    payment = _payment()
    payment.status = "pending_wata"
    expiry = datetime.now(UTC) + timedelta(hours=1)
    payment.checkout_expires_at = expiry.replace(tzinfo=None) if naive_expiry else expiry
    assert (
        PaymentHistoryItemOut.from_orm_payment(payment).checkout_url == payment.provider_payment_url
    )


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        " ",
        "javascript:alert(1)",
        "data:text/html,checkout",
        "//pay.example.test",
        "https://",
        "https://[broken",
        "https://user:password@pay.example.test",
        "https://pay.example.test/\ncheckout",
    ],
)
def test_history_does_not_expose_invalid_checkout_urls(url: str | None) -> None:
    payment = _payment()
    payment.status = "pending_wata"
    payment.checkout_expires_at = datetime.now(UTC) + timedelta(hours=1)
    payment.provider_payment_url = url
    assert PaymentHistoryItemOut.from_orm_payment(payment).checkout_url is None


@pytest.mark.parametrize("expired", [False, True])
def test_history_does_not_expose_missing_or_expired_checkout(expired: bool) -> None:
    payment = _payment()
    payment.status = "pending_wata"
    payment.checkout_expires_at = datetime.now(UTC) - timedelta(hours=1) if expired else None
    assert PaymentHistoryItemOut.from_orm_payment(payment).checkout_url is None


@pytest.mark.parametrize(
    "status",
    [
        "succeeded",
        "processing",
        "succeeded_pending_finalization",
        "succeeded_pending_review",
        "refunded",
        "failed",
    ],
)
def test_history_does_not_reopen_checkout_after_payment_started(status: str) -> None:
    payment = _payment()
    payment.status = status
    payment.checkout_expires_at = datetime.now(UTC) + timedelta(hours=1)
    assert PaymentHistoryItemOut.from_orm_payment(payment).checkout_url is None


@pytest.mark.parametrize("marker", ["fulfilled_at", "reversed_at"])
def test_history_does_not_reopen_checkout_with_purchase_or_refund_evidence(marker: str) -> None:
    payment = _payment()
    payment.status = "pending_wata"
    payment.checkout_expires_at = datetime.now(UTC) + timedelta(hours=1)
    setattr(payment, marker, datetime.now(UTC))
    assert PaymentHistoryItemOut.from_orm_payment(payment).checkout_url is None


def test_history_filters_both_count_and_page_and_orders_ties_consistently() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = 23
    result = MagicMock()
    result.scalars.return_value.all.return_value = [_payment()]
    session.execute.return_value = result
    payments, total = asyncio.run(list_user_payments(session, 42, limit=10, offset=20))
    assert len(payments) == 1
    assert total == 23
    count_statement = session.scalar.await_args.args[0]
    page_statement = session.execute.await_args.args[0]
    for statement in (count_statement, page_statement):
        sql = str(
            statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        )
        assert "WHERE payments.user_id = 42" in sql
    page_sql = str(
        page_statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "ORDER BY payments.created_at DESC NULLS LAST, payments.payment_id DESC" in page_sql
    assert "LIMIT 10 OFFSET 20" in page_sql


@pytest.mark.parametrize(
    ("status", "state"),
    [
        ("pending_yookassa", "awaiting_payment"),
        ("waiting_for_capture", "processing"),
        ("PROCESSING", "processing"),
        ("underpaid", "processing"),
        ("succeeded_pending_finalization", "crediting"),
        ("succeeded_pending_review", "review"),
        ("succeeded", "completed"),
        ("refunded", "refunded"),
        ("reversed", "refunded"),
        ("failed", "failed"),
    ],
)
def test_history_distinguishes_provider_processing_from_purchase_crediting(
    status: str, state: str
) -> None:
    payment = _payment()
    payment.status = status
    assert payment_history_state(payment) == state


def test_visibility_keeps_paid_and_processing_rows_and_hides_abandoned_checkouts() -> None:
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    metadata = MetaData()
    table = Table(
        "payments",
        metadata,
        Column("payment_id", Integer, primary_key=True),
        Column("user_id", Integer),
        Column("status", String),
        Column("provider_payment_url", String),
        Column("checkout_expires_at", DateTime(timezone=True)),
        Column("fulfilled_at", DateTime(timezone=True)),
        Column("reversed_at", DateTime(timezone=True)),
    )
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    statuses = [
        "succeeded",
        "succeeded_pending_finalization",
        "succeeded_pending_review",
        "refunded",
        "reversed",
        "processing",
        "waiting_for_capture",
        "underpaid",
        "pending_yookassa",
        "pending_pally",
        "pending_lava",
        "pending_paykilla",
        "canceled",
        "failed_creation",
        "failed",
        "succeeded",
    ]
    rows = [
        {
            "payment_id": index,
            "user_id": 42 if index != 16 else 999,
            "status": status,
            "provider_payment_url": "https://pay.example.test/link",
            "checkout_expires_at": now - timedelta(hours=1),
            "fulfilled_at": now if index == 15 else None,
            "reversed_at": None,
        }
        for index, status in enumerate(statuses, start=1)
    ]
    rows[8]["checkout_expires_at"] = now + timedelta(hours=1)
    rows[10]["checkout_expires_at"] = None
    rows[11]["checkout_expires_at"] = now + timedelta(hours=1)
    rows[11]["provider_payment_url"] = " "
    try:
        with engine.begin() as connection:
            connection.execute(table.insert(), rows)
            visible = connection.scalars(
                select(Payment.payment_id)
                .where(payment_history_filter(42, now))
                .order_by(Payment.payment_id)
            ).all()
        assert visible == [1, 2, 3, 4, 5, 6, 7, 8, 9, 15]
    finally:
        engine.dispose()
