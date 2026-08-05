from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from config.settings import Settings

logger = logging.getLogger(__name__)

# Runtime transactions take the shared form of this lock. A database restore
# takes the exclusive form, waits for active transactions to finish, and keeps
# new application transactions fenced until the restore and its integrity
# checks are complete.
# Keep this distinct from every application-level advisory lock. In particular,
# the subscription background sync uses ``817512404897421338`` exclusively;
# reusing that value here would make its restore-aware transaction take the
# shared and exclusive forms of the same lock and fence every other request.
DB_RESTORE_ADVISORY_LOCK_ID = 817512404897421339


class RestoreAwareSession(Session):
    """Synchronous session used underneath restore-aware async sessions."""


class RestoreAwareAsyncSession(AsyncSession):
    """Async session whose transactions cooperate with database restores."""

    sync_session_class = RestoreAwareSession


@event.listens_for(RestoreAwareSession, "after_begin")
def _acquire_restore_shared_lock(
    _session: Session,
    _transaction: object,
    connection: Connection,
) -> None:
    if connection.dialect.name != "postgresql":
        return
    connection.exec_driver_sql(
        f"SELECT pg_advisory_xact_lock_shared({DB_RESTORE_ADVISORY_LOCK_ID})"
    )


@asynccontextmanager
async def database_restore_fence(settings: Settings) -> AsyncIterator[None]:
    """Block application DB transactions while a restore is in progress."""

    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        poolclass=NullPool,
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT pg_advisory_lock(:lock_id)"),
                {"lock_id": DB_RESTORE_ADVISORY_LOCK_ID},
            )
            logger.warning("Database restore write fence acquired")
            try:
                yield
            finally:
                try:
                    await connection.execute(
                        text("SELECT pg_advisory_unlock(:lock_id)"),
                        {"lock_id": DB_RESTORE_ADVISORY_LOCK_ID},
                    )
                finally:
                    logger.warning("Database restore write fence released")
    finally:
        await engine.dispose()
