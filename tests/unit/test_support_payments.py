import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, select

from bot.app.web.context import SETTINGS
from bot.app.web.support_schemas import SupportPaymentOut
from bot.app.web.webapp import support
from bot.app.web.webapp.payloads import CreateTicketPayload
from bot.middlewares.i18n import JsonI18n
from bot.services import support_service as service_module
from bot.services.support_message_body import support_body_plain_text
from bot.services.support_payment_body import SupportPaymentUnavailable, attach_payment_summary
from bot.services.support_service import SupportService
from db.dal.support_payment_dal import support_payment_filter
from db.models import Payment, User
from tests.support.settings_stub import settings_stub


def payment():
    return Payment(
        payment_id=17,
        user_id=42,
        provider="wata",
        amount=120,
        currency="RUB",
        status="failed",
        created_at=datetime.now(UTC),
        provider_payment_id="private-id",
        provider_payment_url="https://private.test/key",
        fulfillment_note="private-note",
    )


def test_candidates_enforce_ownership_recency_and_unresolved_state():
    now = datetime(2026, 10, 30, 12, tzinfo=UTC)
    metadata = MetaData()
    table = Table(
        "payments",
        metadata,
        Column("payment_id", Integer, primary_key=True),
        Column("user_id", Integer),
        Column("status", String),
        Column("created_at", DateTime(timezone=True)),
        Column("provider_payment_url", String),
        Column("checkout_expires_at", DateTime(timezone=True)),
        Column("fulfilled_at", DateTime(timezone=True)),
        Column("reversed_at", DateTime(timezone=True)),
    )
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    cases = [
        {},
        {"status": "processing"},
        {"status": "succeeded_pending_finalization"},
        {"status": "succeeded_pending_review"},
        {
            "status": "pending",
            "checkout_expires_at": now + timedelta(hours=1),
            "provider_payment_url": "https://pay.test",
        },
        {"created_at": now - timedelta(days=7)},
        {"user_id": 99},
        {"created_at": now - timedelta(days=7, seconds=1)},
        {"created_at": now + timedelta(seconds=1)},
        {"status": "succeeded"},
        {"status": "refunded"},
        {"status": "reversed"},
        {"fulfilled_at": now},
        {"reversed_at": now},
        {"status": "pending"},
    ]
    with engine.begin() as connection:
        for index, changes in enumerate(cases):
            connection.execute(
                table.insert().values(
                    payment_id=index + 1,
                    **{"user_id": 42, "status": "failed", "created_at": now, **changes},
                )
            )
        ids = (
            connection.execute(
                select(Payment.payment_id)
                .where(support_payment_filter(42, now))
                .order_by(Payment.payment_id)
            )
            .scalars()
            .all()
        )
    engine.dispose()
    assert ids == [1, 2, 3, 4, 5, 6]


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("body_format", ["text", "html"])
def test_payment_summary_freezes_safe_public_fields(lang, body_format):
    item = payment()
    item.provider = '<a href="https://evil.test">provider</a>'
    i18n = JsonI18n(path="locales", default="en")
    body, stored_format = attach_payment_summary(
        "<b>Help</b>", body_format, item, lang=lang, i18n=i18n
    )
    assert stored_format == "html"
    assert "120.00 RUB" in body
    assert "17" in body
    assert "&lt;a href=" in body
    assert "private-id" not in body and "private-note" not in body and "private.test" not in body
    assert i18n.gettext(lang, "wa_payment_history_state_failed") in body
    assert "Help" in support_body_plain_text(body, stored_format)
    item.status = "succeeded"
    assert i18n.gettext(lang, "wa_payment_history_state_failed") in body


@pytest.mark.parametrize("choice", [None, 17])
def test_create_ticket_persists_selected_payment_summary_or_original_body(choice, monkeypatch):
    lock_order = []

    def lock_user(*_args):
        lock_order.append("user")
        return User(user_id=42, language_code="en")

    def lock_payment(*_args):
        lock_order.append("payment")
        return payment()

    session = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    service = object.__new__(SupportService)
    service.session_factory = factory
    service.settings = settings_stub(SUPPORT_TICKET_RATE_LIMIT_PER_HOUR=0)
    service.i18n = JsonI18n(path="locales", default="en")
    service.notification_service = SimpleNamespace(notify_new_support_ticket=AsyncMock())
    service._ensure_user_allowed = AsyncMock(side_effect=lock_user)
    service._enforce_user_message_limits = AsyncMock()
    service.build_user_snapshot = AsyncMock(return_value={})
    ticket = SimpleNamespace(ticket_id=8, user_id=42)
    create = AsyncMock(return_value=ticket)
    lock = AsyncMock(side_effect=lock_payment)
    monkeypatch.setattr(service_module, "lock_support_payment", lock)
    monkeypatch.setattr(service_module, "persist_message_image", AsyncMock(return_value=None))
    monkeypatch.setattr(service_module.support_dal, "create_ticket", create)
    monkeypatch.setattr(
        service_module.support_dal, "get_ticket", AsyncMock(return_value=(ticket, []))
    )
    monkeypatch.setattr(service_module.events, "emit_model", AsyncMock())
    asyncio.run(
        service.create_ticket(42, "Help", "billing", "normal", "Question", payment_id=choice)
    )
    stored_body = create.call_args.args[5]
    if choice:
        lock.assert_awaited_once_with(session, 42, 17)
        assert "Attached payment #17" in stored_body
        assert create.call_args.kwargs["first_message_format"] == "html"
    else:
        lock.assert_not_awaited()
        assert stored_body == "Question"
    session.commit.assert_awaited_once()
    assert lock_order == (["payment", "user"] if choice else ["user"])


@pytest.mark.parametrize("category", ["billing", "technical"])
def test_unavailable_or_wrong_category_payment_creates_no_ticket(category, monkeypatch):
    session = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    service = object.__new__(SupportService)
    service.session_factory = factory
    service.settings = settings_stub()
    service._ensure_user_allowed = AsyncMock(return_value=User(user_id=42))
    monkeypatch.setattr(service_module, "lock_support_payment", AsyncMock(return_value=None))
    create = AsyncMock()
    monkeypatch.setattr(service_module.support_dal, "create_ticket", create)
    with pytest.raises(SupportPaymentUnavailable):
        asyncio.run(
            service.create_ticket(42, "Help", category, "normal", "Question", payment_id=17)
        )
    create.assert_not_awaited()
    session.commit.assert_not_awaited()


def test_payment_options_require_authentication_before_database_access():
    app = web.Application()
    app[SETTINGS] = settings_stub()
    request = make_mocked_request("GET", "/api/support/payment-options", app=app)
    with (
        patch.object(support, "get_session_factory") as factory,
        pytest.raises(web.HTTPUnauthorized),
    ):
        asyncio.run(support.support_payment_options_route(request))
    factory.assert_not_called()


def test_payment_options_are_public_summaries_without_provider_secrets():
    data = SupportPaymentOut.from_orm_payment(payment()).model_dump()
    assert set(data) == {
        "payment_id",
        "amount",
        "currency",
        "provider",
        "created_at",
        "history_state",
    }


def test_create_route_passes_payment_id_and_returns_stale_selection_error():
    request = make_mocked_request("POST", "/api/support/tickets")
    payload = CreateTicketPayload(
        subject="Help", body="Question", category="billing", payment_id=17
    )
    service = SimpleNamespace(create_ticket=AsyncMock(side_effect=SupportPaymentUnavailable()))
    with (
        patch.object(support, "_require_user_id", return_value=42),
        patch.object(
            support,
            "parse_body_with_optional_image_or_400",
            AsyncMock(return_value=(payload, None)),
        ),
        patch.object(support, "prepare_message_image", AsyncMock(return_value=None)),
        patch.object(support, "get_support_service", return_value=service),
    ):
        response = asyncio.run(support.support_create_ticket_route(request))
    assert response.status == 400
    assert json.loads(response.text)["error"] == "support_payment_unavailable"
    assert service.create_ticket.call_args.kwargs["payment_id"] == 17
