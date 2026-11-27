"""Use database leases so concurrent workers do not replace the same snapshot."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .sources import SourceError, fetch_source
from .storage import RefreshLease, claim_due_sources, record_refresh

_CONCURRENT_REFRESHES = 2


async def refresh_sources(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async def refresh(lease: RefreshLease) -> bool:
        try:
            snapshot = await fetch_source(lease.url, lease.content_sha256)
        except SourceError as exc:
            async with session_factory.begin() as session:
                return await record_refresh(session, lease, datetime.now(UTC), error=exc.code)
        async with session_factory.begin() as session:
            return await record_refresh(session, lease, datetime.now(UTC), snapshot=snapshot)

    completed = 0
    while True:
        async with session_factory.begin() as session:
            leases = await claim_due_sources(
                session, datetime.now(UTC), limit=_CONCURRENT_REFRESHES
            )
        async with asyncio.TaskGroup() as group:
            attempts = [group.create_task(refresh(lease)) for lease in leases]
        completed += sum(attempt.result() for attempt in attempts)
        if len(leases) < _CONCURRENT_REFRESHES:
            return completed
