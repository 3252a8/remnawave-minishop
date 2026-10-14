"""Publish database events only after the enclosing transaction is committed."""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction
from sqlalchemy.util.concurrency import await_only

from bot.infra import events
from bot.infra.event_payloads import EventPayload

_QUEUE = "minishop_committed_events"
_REGISTERED = "minishop_committed_event_listeners"


def defer_event_until_commit(session: AsyncSession, payload: EventPayload) -> None:
    """Savepoint release defers delivery; rollback discards its own events."""
    sync_session = session.sync_session
    transaction = sync_session.get_nested_transaction() or sync_session.get_transaction()
    if transaction is None:
        raise RuntimeError("A database event requires an active transaction")
    if not sync_session.info.get(_REGISTERED):
        event.listen(sync_session, "after_commit", _after_commit)
        event.listen(sync_session, "after_soft_rollback", _after_rollback)
        event.listen(sync_session, "after_transaction_end", _after_end)
        sync_session.info[_REGISTERED] = True
    sync_session.info.setdefault(_QUEUE, []).append((transaction, payload))


def _after_commit(session: Session) -> None:
    if session.in_nested_transaction():
        return
    queued: list[tuple[SessionTransaction, EventPayload]] = session.info.pop(_QUEUE, [])
    for _, payload in queued:
        # AsyncSession invokes SQLAlchemy callbacks inside its IO greenlet.
        # Await delivery here so callers observe committed plugin state.
        await_only(events.emit_model(payload))


def _belongs_to(transaction: SessionTransaction, ancestor: SessionTransaction) -> bool:
    current: SessionTransaction | None = transaction
    while current is not None:
        if current is ancestor:
            return True
        current = current.parent
    return False


def _after_rollback(session: Session, transaction: SessionTransaction) -> None:
    queued: list[tuple[SessionTransaction, EventPayload]] = session.info.get(_QUEUE, [])
    session.info[_QUEUE] = [item for item in queued if not _belongs_to(item[0], transaction)]


def _after_end(session: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is None:
        session.info.pop(_QUEUE, None)
