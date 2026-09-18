import asyncio
from unittest.mock import AsyncMock, call

from db.advisory_locks import (
    SUBSCRIPTION_BACKGROUND_SYNC_LOCK_ID,
    commit_subscription_background_sync_batch,
)


def test_background_sync_batch_commit_reacquires_transaction_lock() -> None:
    session = AsyncMock()

    asyncio.run(commit_subscription_background_sync_batch(session))

    session.commit.assert_awaited_once_with()
    session.execute.assert_awaited_once()
    assert session.method_calls[0] == call.commit()
    assert session.method_calls[1].args[1] == {"lock_id": SUBSCRIPTION_BACKGROUND_SYNC_LOCK_ID}
    assert str(session.method_calls[1].args[0]) == ("SELECT pg_advisory_xact_lock(:lock_id)")
