"""Persistent connector behavior, including retry after a committed send."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.services.support_connector_contracts import SupportConnectorConflict
from bot.services.support_service import SupportService, TicketNotFound
from db.activity_models import SupportChangeClock
from db.dal import support_dal
from db.models import Base, SupportTicket, SupportTicketMessage, User
from tests.support.settings_stub import settings_stub


def scenario(run: Callable[[Any, SupportService, int], Awaitable[None]]) -> None:
    async def execute() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
            async with factory() as session:
                session.add_all([User(user_id=1, email="private@example.test"), User(user_id=2)])
                session.add(SupportChangeClock(id=1, cursor=0))
                await session.flush()
                ticket = await support_dal.create_ticket(
                    session, 1, "Help", "other", "normal", "Question"
                )
                await session.commit()
            service = SupportService(
                factory, settings_stub(SUPPORT_TICKETS_ENABLED=True), None, None
            )
            service.notification_service.notify_support_admin_reply = AsyncMock()
            service._schedule_notification = lambda coroutine, *_args: coroutine.close()
            await run(factory, service, int(ticket.ticket_id))
        finally:
            await engine.dispose()

    asyncio.run(execute())


async def send(service: SupportService, ticket_id: int, revision: int = 1):
    return await service.reply_from_connector(
        ticket_id,
        "Approved answer",
        expected_user_id=1,
        expected_revision=revision,
        idempotency_key="job-1",
        source="example.connector",
        author_label="Automated support",
    )


def test_context_is_owner_scoped_and_excludes_notes_contacts_and_admin_read_side_effects() -> None:
    async def run(factory: Any, service: SupportService, ticket_id: int) -> None:
        async with factory() as session:
            await support_dal.add_message(
                session, ticket_id, "admin", 2, "Private note", is_internal_note=True
            )
            await session.commit()
        context = await service.get_ticket_context(ticket_id, expected_user_id=1)
        assert [message.body for message in context.messages] == ["Question"]
        assert context.revision == 2
        assert not {"user_id", "name", "email", "username", "telegram_id"} & context.facts.keys()
        async with factory() as session:
            ticket = await session.get(SupportTicket, ticket_id)
            assert ticket is not None and ticket.unread_admin_count == 1
        with pytest.raises(TicketNotFound):
            await service.get_ticket_context(ticket_id, expected_user_id=2)

    scenario(run)


def test_committed_retry_keeps_original_reply_and_operator_unread() -> None:
    async def run(factory: Any, service: SupportService, ticket_id: int) -> None:
        first = await send(service, ticket_id)
        second = await send(service, ticket_id)
        assert first.message_id == second.message_id and second.duplicate
        assert not first.duplicate and first.revision == 2
        async with factory() as session:
            ticket = await session.get(SupportTicket, ticket_id)
            message = await session.get(SupportTicketMessage, first.message_id)
            assert ticket is not None and ticket.unread_admin_count == 1
            assert ticket.unread_user_count == 1
            assert message is not None and message.author_user_id is None
            assert message.author_role == "connector"
            assert message.connector_source == "example.connector"
            count = await session.scalar(select(func.count()).select_from(SupportTicketMessage))
            assert count == 2
        with pytest.raises(SupportConnectorConflict, match="idempotency_mismatch"):
            await service.reply_from_connector(
                ticket_id,
                "Different answer",
                expected_user_id=1,
                expected_revision=1,
                idempotency_key="job-1",
                source="example.connector",
                author_label="Automated support",
            )

    scenario(run)


@pytest.mark.parametrize(
    "mutation", ["user_message", "admin_message", "internal_note", "closed", "assigned"]
)
def test_every_competing_conversation_write_invalidates_pending_reply(mutation: str) -> None:
    async def run(factory: Any, service: SupportService, ticket_id: int) -> None:
        async with factory() as session:
            if mutation in {"closed", "assigned"}:
                await support_dal.update_ticket(
                    session,
                    ticket_id,
                    **({"status": "closed"} if mutation == "closed" else {"assigned_admin_id": 2}),
                )
            else:
                await support_dal.add_message(
                    session,
                    ticket_id,
                    "user" if mutation == "user_message" else "admin",
                    1 if mutation == "user_message" else 2,
                    "Changed",
                    is_internal_note=mutation == "internal_note",
                )
            await session.commit()
        with pytest.raises(SupportConnectorConflict, match="stale_revision"):
            await send(service, ticket_id)

    scenario(run)


def test_banned_owner_is_rejected_before_any_external_reply() -> None:
    async def run(factory: Any, service: SupportService, ticket_id: int) -> None:
        async with factory() as session:
            user = await session.get(User, 1)
            assert user is not None
            user.is_banned = True
            await session.commit()
        with pytest.raises(SupportConnectorConflict, match="owner_unavailable"):
            await send(service, ticket_id)

    scenario(run)


def test_reconciliation_has_bounded_pages_and_rollback_does_not_advance_watermark() -> None:
    async def run(factory: Any, _service: SupportService, ticket_id: int) -> None:
        async with factory() as session:
            assert await support_dal.get_change_cursor(session) == 1
            await support_dal.add_message(session, ticket_id, "user", 1, "Rolled back")
            await session.rollback()
            assert await support_dal.get_change_cursor(session) == 1
            second = await support_dal.create_ticket(
                session, 2, "Help", "other", "normal", "Second"
            )
            await session.commit()
            page = await support_dal.list_changed_tickets(session, limit=1)
            assert len(page) == 1 and page[0].cursor == 1
            following = await support_dal.list_changed_tickets(session, after_cursor=page[0].cursor)
            assert len(following) == 1 and following[0].ticket_id == second.ticket_id
            assert following[0].last_message_id > 0
            with pytest.raises(ValueError):
                await support_dal.list_changed_tickets(session, limit=501)

    scenario(run)
