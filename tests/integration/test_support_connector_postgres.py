"""Support reply races on disposable PostgreSQL schemas with real row locks."""

import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.services.support_connector_contracts import SupportConnectorConflict
from bot.services.support_service import SupportService
from db.activity_models import SupportChangeClock
from db.dal import support_dal
from db.models import Base, User
from tests.support.settings_stub import settings_stub

DATABASE_URL = os.environ.get("CORE_PERFORMANCE_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="Disposable PostgreSQL URL is required")


def scenario(run: Callable[[Any, SupportService, int], Awaitable[None]]) -> None:
    async def execute() -> None:
        schema = "support_connector_test_" + uuid.uuid4().hex
        admin = create_async_engine(DATABASE_URL)
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(
            DATABASE_URL, connect_args={"server_settings": {"search_path": schema}}
        )
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
            async with factory() as session:
                session.add(User(user_id=1))
                session.add(SupportChangeClock(id=1, cursor=0))
                await session.flush()
                ticket = await support_dal.create_ticket(
                    session, 1, "Help", "other", "normal", "Question"
                )
                await session.commit()
            service = SupportService(
                factory, settings_stub(SUPPORT_TICKETS_ENABLED=True), None, None
            )
            service._schedule_notification = lambda coroutine, *_args: coroutine.close()
            await run(factory, service, int(ticket.ticket_id))
        finally:
            await engine.dispose()
            async with admin.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin.dispose()

    asyncio.run(execute())


async def send(service: SupportService, ticket_id: int):
    return await service.reply_from_connector(
        ticket_id,
        "Approved answer",
        expected_user_id=1,
        expected_revision=1,
        idempotency_key="job",
        source="example",
        author_label="Automated support",
    )


def test_parallel_retries_commit_one_reply() -> None:
    async def run(_factory: Any, service: SupportService, ticket_id: int) -> None:
        first, second = await asyncio.gather(send(service, ticket_id), send(service, ticket_id))
        assert first.message_id == second.message_id
        assert {first.duplicate, second.duplicate} == {False, True}

    scenario(run)


def test_new_user_message_between_generation_and_send_is_rejected_under_ticket_lock() -> None:
    async def run(factory: Any, service: SupportService, ticket_id: int) -> None:
        async with factory() as session:
            await support_dal.add_message(session, ticket_id, "user", 1, "Another question")
            pending = asyncio.create_task(send(service, ticket_id))
            await asyncio.sleep(0.05)
            assert not pending.done()
            await session.commit()
        with pytest.raises(SupportConnectorConflict, match="stale_revision"):
            await pending

    scenario(run)


def test_ban_committing_during_generation_is_checked_under_owner_lock() -> None:
    async def run(factory: Any, service: SupportService, ticket_id: int) -> None:
        async with factory() as session:
            user = await session.get(User, 1)
            assert user is not None
            user.is_banned = True
            await session.flush()
            pending = asyncio.create_task(send(service, ticket_id))
            await asyncio.sleep(0.05)
            assert not pending.done()
            await session.commit()
        with pytest.raises(SupportConnectorConflict, match="owner_unavailable"):
            await pending

    scenario(run)


def test_change_cursor_cannot_skip_an_earlier_uncommitted_ticket() -> None:
    async def run(factory: Any, _service: SupportService, ticket_id: int) -> None:
        async def create_second() -> int:
            async with factory() as session:
                second = await support_dal.create_ticket(
                    session, 1, "Second", "other", "normal", "Question"
                )
                await session.commit()
                return int(second.change_cursor)

        async with factory() as session:
            await support_dal.add_message(session, ticket_id, "user", 1, "Uncommitted")
            pending = asyncio.create_task(create_second())
            await asyncio.sleep(0.05)
            assert not pending.done()
            async with factory() as reader:
                assert await support_dal.get_change_cursor(reader) == 1
            await session.commit()
        assert await pending == 3
        async with factory() as reader:
            assert [
                change.cursor
                for change in await support_dal.list_changed_tickets(reader, after_cursor=1)
            ] == [2, 3]

    scenario(run)
