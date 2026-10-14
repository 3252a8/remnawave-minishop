import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra.event_payloads import AccountMergedPayload
from db.transaction_events import defer_event_until_commit


def payload(source: int = -1) -> AccountMergedPayload:
    return AccountMergedPayload(
        source_user_id=source,
        target_user_id=2,
        reason="admin_manual_merge",
        send_user_email=False,
    )


class TransactionEventTests(IsolatedAsyncioTestCase):
    async def test_commit_awaits_delivery_and_session_reuse_does_not_repeat(self):
        delivered = []

        async def deliver(value):
            await asyncio.sleep(0)
            delivered.append(value.source_user_id)

        async with AsyncSession() as session:
            with patch("db.transaction_events.events.emit_model", side_effect=deliver):
                await session.begin()
                defer_event_until_commit(session, payload())
                self.assertEqual(delivered, [])
                await session.commit()
                self.assertEqual(delivered, [-1])
                await session.begin()
                await session.commit()
                self.assertEqual(delivered, [-1])

    async def test_rollback_and_close_discard_events(self):
        with patch("db.transaction_events.events.emit_model", AsyncMock()) as emit:
            async with AsyncSession() as session:
                await session.begin()
                defer_event_until_commit(session, payload())
                await session.rollback()
                await session.begin()
                await session.commit()
            async with AsyncSession() as session:
                await session.begin()
                defer_event_until_commit(session, payload())
            emit.assert_not_awaited()

    async def test_savepoint_release_waits_for_outer_commit(self):
        with patch("db.transaction_events.events.emit_model", AsyncMock()) as emit:
            async with AsyncSession() as session:
                async with session.begin():
                    async with session.begin_nested():
                        defer_event_until_commit(session, payload())
                    emit.assert_not_awaited()
                emit.assert_awaited_once()

    async def test_savepoint_rollback_preserves_only_outer_events(self):
        with patch("db.transaction_events.events.emit_model", AsyncMock()) as emit:
            async with AsyncSession() as session:
                async with session.begin():
                    defer_event_until_commit(session, payload(-1))
                    savepoint = await session.begin_nested()
                    defer_event_until_commit(session, payload(-3))
                    await savepoint.rollback()
                    emit.assert_not_awaited()
                self.assertEqual(emit.await_count, 1)
                self.assertEqual(emit.await_args.args[0].source_user_id, -1)

    async def test_outer_rollback_discards_released_savepoint_events(self):
        with patch("db.transaction_events.events.emit_model", AsyncMock()) as emit:
            async with AsyncSession() as session:
                await session.begin()
                async with session.begin_nested():
                    defer_event_until_commit(session, payload())
                await session.rollback()
                await session.begin()
                await session.commit()
                emit.assert_not_awaited()

    async def test_event_requires_a_transaction(self):
        async with AsyncSession() as session:
            with self.assertRaisesRegex(RuntimeError, "active transaction"):
                defer_event_until_commit(session, payload())
