import logging
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra.performance import current_scope

logger = logging.getLogger(__name__)

# Serializes background jobs that rewrite subscription rows from panel state.
SUBSCRIPTION_BACKGROUND_SYNC_LOCK_ID = 817512404897421338


async def acquire_subscription_background_sync_lock(session: AsyncSession) -> None:
    started = time.monotonic()
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": SUBSCRIPTION_BACKGROUND_SYNC_LOCK_ID},
    )
    elapsed = time.monotonic() - started
    scope = current_scope.get()
    if scope is not None:
        scope.lock_wait_seconds += elapsed
    logger.info("metric subscription_sync_lock_wait_seconds=%.4f", elapsed)


async def commit_subscription_background_sync_batch(session: AsyncSession) -> None:
    """Commit one bounded worker batch and serialize the next transaction.

    Long-running panel and tariff workers must not retain row locks for their
    entire scan. Committing between batches releases those locks for web
    requests, while immediately reacquiring the shared transaction advisory
    lock keeps background subscription writers serialized.
    """

    await session.commit()
    await acquire_subscription_background_sync_lock(session)
