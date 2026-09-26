"""Preserve external order ownership across account merges and fence active work."""

import hashlib
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.extension_models import ExtensionOperation, ExtensionOrder


async def assert_idle(session: AsyncSession, user_ids: tuple[int, ...]) -> None:
    active = (
        await session.execute(
            select(ExtensionOperation.id)
            .where(
                ExtensionOperation.user_id.in_(user_ids),
                ExtensionOperation.state == "running",
                ExtensionOperation.lease_until > datetime.now(UTC),
            )
            .with_for_update()
            .limit(1)
        )
    ).scalar_one_or_none()
    if active is not None:
        raise ValueError("extension_operation_in_progress")


async def merge(session: AsyncSession, source: int, target: int) -> None:
    await assert_idle(session, (source, target))
    rows = (
        (
            await session.execute(
                select(ExtensionOrder)
                .where(
                    ExtensionOrder.user_id == source,
                )
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        collision = (
            await session.execute(
                select(ExtensionOrder.id).where(
                    ExtensionOrder.user_id == target,
                    ExtensionOrder.idempotency_key == row.idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if collision is not None:
            # Retain every purchase, without confusing a target account's replay key.
            row.idempotency_key = (
                "merged:"
                + hashlib.sha256(f"{source}:{row.id}:{row.idempotency_key}".encode()).hexdigest()
            )
        row.user_id = target
    await session.execute(
        update(ExtensionOperation)
        .where(
            ExtensionOperation.user_id == source,
        )
        .values(user_id=target)
    )
    await session.flush()


async def delete_for_user(session: AsyncSession, user_id: int) -> None:
    await assert_idle(session, (user_id,))
    await session.execute(delete(ExtensionOperation).where(ExtensionOperation.user_id == user_id))
    await session.execute(delete(ExtensionOrder).where(ExtensionOrder.user_id == user_id))
