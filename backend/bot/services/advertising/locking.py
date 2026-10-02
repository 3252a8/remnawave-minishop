"""Serialize namespace and offer changes within the existing transaction."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def lock_advertising(session: AsyncSession, key: str) -> None:
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "advertising:" + key},
        )
