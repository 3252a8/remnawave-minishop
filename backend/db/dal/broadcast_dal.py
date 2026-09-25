# SQLAlchemy legacy Column declarations expose instance attributes as Column[T]
# to mypy; this DAL intentionally mutates loaded ORM instances.
# mypy: disable-error-code="assignment,arg-type,operator"

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.broadcast_models import AdminBroadcast, AdminBroadcastDelivery

ACTIVE_BROADCAST_STATUSES = ("scheduled", "queued", "running")
FINAL_DELIVERY_STATUSES = ("sent", "failed")


def utc_now() -> datetime:
    return datetime.now(UTC)


async def create_broadcast(
    session: AsyncSession,
    *,
    actor_id: int | None,
    target: str,
    channels: list[str],
    exclude_blocked_telegram: bool,
    texts: dict[str, str],
    email_subjects: dict[str, str],
    buttons: list[dict[str, Any]],
    scheduled_at: datetime,
    is_visible: bool = True,
    image_id: str | None = None,
) -> AdminBroadcast:
    status = "scheduled" if scheduled_at > utc_now() else "queued"
    item = AdminBroadcast(
        created_by_admin_id=actor_id,
        status=status,
        is_visible=is_visible,
        target=target,
        channels=list(channels),
        exclude_blocked_telegram=bool(exclude_blocked_telegram),
        texts=dict(texts),
        email_subjects=dict(email_subjects),
        buttons=list(buttons),
        image_id=image_id,
        scheduled_at=scheduled_at,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def get_broadcast(
    session: AsyncSession,
    broadcast_id: int,
    *,
    include_deleted: bool = False,
    for_update: bool = False,
) -> AdminBroadcast | None:
    stmt = select(AdminBroadcast).where(AdminBroadcast.broadcast_id == broadcast_id)
    if not include_deleted:
        stmt = stmt.where(AdminBroadcast.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_broadcasts(session: AsyncSession, *, limit: int = 60) -> list[AdminBroadcast]:
    stmt = (
        select(AdminBroadcast)
        .where(AdminBroadcast.deleted_at.is_(None), AdminBroadcast.is_visible == True)
        .order_by(AdminBroadcast.created_at.desc(), AdminBroadcast.broadcast_id.desc())
        .limit(max(1, min(int(limit), 100)))
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_failed_deliveries(
    session: AsyncSession,
    broadcast_id: int,
    *,
    limit: int,
    offset: int,
) -> tuple[int, list[AdminBroadcastDelivery]]:
    condition = (
        AdminBroadcastDelivery.broadcast_id == broadcast_id,
        AdminBroadcastDelivery.status == "failed",
    )
    total = int(
        (
            await session.execute(
                select(func.count(AdminBroadcastDelivery.delivery_id)).where(*condition)
            )
        ).scalar_one()
        or 0
    )
    rows = (
        (
            await session.execute(
                select(AdminBroadcastDelivery)
                .where(*condition)
                .order_by(AdminBroadcastDelivery.delivery_id.asc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return total, list(rows)


async def due_broadcast_ids(session: AsyncSession, *, limit: int = 3) -> list[int]:
    stmt = (
        select(AdminBroadcast.broadcast_id)
        .where(
            AdminBroadcast.deleted_at.is_(None),
            AdminBroadcast.status.in_(("scheduled", "queued")),
            AdminBroadcast.scheduled_at <= utc_now(),
        )
        .order_by(AdminBroadcast.scheduled_at.asc(), AdminBroadcast.broadcast_id.asc())
        .limit(max(1, int(limit)))
    )
    return [int(value) for value in (await session.execute(stmt)).scalars().all()]


async def running_broadcast_ids(session: AsyncSession, *, limit: int = 20) -> list[int]:
    stmt = (
        select(AdminBroadcast.broadcast_id)
        .where(
            AdminBroadcast.deleted_at.is_(None),
            AdminBroadcast.status == "running",
        )
        .order_by(AdminBroadcast.updated_at.asc())
        .limit(max(1, int(limit)))
    )
    return [int(value) for value in (await session.execute(stmt)).scalars().all()]


async def begin_broadcast(session: AsyncSession, broadcast_id: int) -> AdminBroadcast | None:
    item = await get_broadcast(session, broadcast_id, for_update=True)
    # Claim a broadcast exactly once. A second worker may have read the same
    # due id before this transaction committed, but it must not enqueue the
    # already-running delivery set again after waiting on the row lock.
    if item is None or item.status not in {"scheduled", "queued"}:
        return None
    if item.scheduled_at > utc_now():
        return None
    item.status = "running"
    item.started_at = item.started_at or utc_now()
    item.updated_at = utc_now()
    await session.commit()
    await session.refresh(item)
    return item


async def recover_interrupted_broadcasts(session: AsyncSession) -> int:
    """Requeue only deliveries whose in-memory sender vanished with the process."""

    recovered = int(
        (
            await session.execute(
                select(func.count(AdminBroadcastDelivery.delivery_id)).where(
                    AdminBroadcastDelivery.status == "queued"
                )
            )
        ).scalar_one()
        or 0
    )
    await session.execute(
        update(AdminBroadcastDelivery)
        .where(AdminBroadcastDelivery.status == "queued")
        .values(status="pending", queued_at=None)
    )
    await session.execute(
        update(AdminBroadcast)
        .where(
            AdminBroadcast.deleted_at.is_(None),
            AdminBroadcast.status == "running",
        )
        .values(status="queued", updated_at=utc_now())
    )
    await session.commit()
    return recovered


async def add_deliveries(
    session: AsyncSession,
    broadcast: AdminBroadcast,
    deliveries: Iterable[dict[str, Any]],
) -> list[AdminBroadcastDelivery]:
    existing_stmt = select(
        AdminBroadcastDelivery.user_id,
        AdminBroadcastDelivery.channel,
    ).where(AdminBroadcastDelivery.broadcast_id == broadcast.broadcast_id)
    existing = {(int(uid), str(channel)) for uid, channel in (await session.execute(existing_stmt))}
    for payload in deliveries:
        key = (int(payload["user_id"]), str(payload["channel"]))
        if key in existing:
            continue
        existing.add(key)
        session.add(
            AdminBroadcastDelivery(
                broadcast_id=broadcast.broadcast_id,
                user_id=key[0],
                channel=key[1],
                destination=str(payload["destination"]),
                language_code=payload.get("language_code"),
                status="pending",
            )
        )
    await session.flush()
    await refresh_broadcast_stats(session, int(broadcast.broadcast_id), commit=False)
    await session.commit()
    return await pending_deliveries(session, int(broadcast.broadcast_id))


async def pending_deliveries(
    session: AsyncSession,
    broadcast_id: int,
) -> list[AdminBroadcastDelivery]:
    stmt = (
        select(AdminBroadcastDelivery)
        .where(
            AdminBroadcastDelivery.broadcast_id == broadcast_id,
            AdminBroadcastDelivery.status == "pending",
        )
        .order_by(AdminBroadcastDelivery.delivery_id.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def mark_delivery_queued(session: AsyncSession, delivery_id: int) -> None:
    await session.execute(
        update(AdminBroadcastDelivery)
        .where(
            AdminBroadcastDelivery.delivery_id == delivery_id,
            AdminBroadcastDelivery.status == "pending",
        )
        .values(
            status="queued",
            attempts=AdminBroadcastDelivery.attempts + 1,
            queued_at=utc_now(),
            error=None,
        )
    )
    await session.commit()


async def mark_delivery_result(
    session: AsyncSession,
    delivery_id: int,
    *,
    success: bool,
    error: str | None = None,
) -> None:
    delivery = (
        await session.execute(
            select(AdminBroadcastDelivery)
            .where(AdminBroadcastDelivery.delivery_id == delivery_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if delivery is None or delivery.status in FINAL_DELIVERY_STATUSES:
        return
    delivery.status = "sent" if success else "failed"
    delivery.error = None if success else str(error or "delivery_failed")[:1000]
    delivery.finished_at = utc_now()
    await session.flush()
    await refresh_broadcast_stats(session, int(delivery.broadcast_id), commit=False)
    await session.commit()


async def refresh_broadcast_stats(
    session: AsyncSession,
    broadcast_id: int,
    *,
    commit: bool = True,
) -> AdminBroadcast | None:
    item = await get_broadcast(session, broadcast_id, include_deleted=True, for_update=True)
    if item is None:
        return None
    stmt = select(
        func.count(AdminBroadcastDelivery.delivery_id),
        func.count(func.distinct(AdminBroadcastDelivery.user_id)),
        func.coalesce(func.sum(case((AdminBroadcastDelivery.status == "sent", 1), else_=0)), 0),
        func.coalesce(func.sum(case((AdminBroadcastDelivery.status == "failed", 1), else_=0)), 0),
        func.coalesce(
            func.sum(
                case(
                    (
                        (AdminBroadcastDelivery.channel == "telegram")
                        & (AdminBroadcastDelivery.status == "sent"),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
        func.coalesce(
            func.sum(
                case(
                    (
                        (AdminBroadcastDelivery.channel == "telegram")
                        & (AdminBroadcastDelivery.status == "failed"),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
        func.coalesce(
            func.sum(
                case(
                    (
                        (AdminBroadcastDelivery.channel == "email")
                        & (AdminBroadcastDelivery.status == "sent"),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
        func.coalesce(
            func.sum(
                case(
                    (
                        (AdminBroadcastDelivery.channel == "email")
                        & (AdminBroadcastDelivery.status == "failed"),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
    ).where(AdminBroadcastDelivery.broadcast_id == broadcast_id)
    values = (await session.execute(stmt)).one()
    (
        item.total_deliveries,
        item.recipient_count,
        item.successful_deliveries,
        item.failed_deliveries,
        item.telegram_sent,
        item.telegram_failed,
        item.email_sent,
        item.email_failed,
    ) = (int(value or 0) for value in values)
    processed = int(item.successful_deliveries) + int(item.failed_deliveries)
    if item.status == "running" and processed >= int(item.total_deliveries):
        item.status = "completed" if int(item.failed_deliveries) == 0 else "completed_with_errors"
        item.finished_at = item.finished_at or utc_now()
    item.updated_at = utc_now()
    if commit:
        await session.commit()
        await session.refresh(item)
    return item


async def finish_empty_broadcast(session: AsyncSession, broadcast_id: int) -> None:
    item = await get_broadcast(session, broadcast_id, include_deleted=True, for_update=True)
    if item is None:
        return
    item.status = "completed"
    item.finished_at = utc_now()
    item.updated_at = utc_now()
    await session.commit()


async def fail_broadcast(session: AsyncSession, broadcast_id: int, error: str) -> None:
    item = await get_broadcast(session, broadcast_id, include_deleted=True, for_update=True)
    if item is None:
        return
    item.status = "failed"
    item.last_error = str(error or "broadcast_failed")[:2000]
    item.finished_at = utc_now()
    item.updated_at = utc_now()
    await session.commit()


async def reschedule_broadcast(
    session: AsyncSession,
    broadcast_id: int,
    scheduled_at: datetime,
) -> AdminBroadcast | None:
    item = await get_broadcast(session, broadcast_id, for_update=True)
    if item is None or item.status not in {"scheduled", "queued"} or item.started_at is not None:
        return None
    item.scheduled_at = scheduled_at
    item.status = "scheduled" if scheduled_at > utc_now() else "queued"
    item.updated_at = utc_now()
    await session.commit()
    await session.refresh(item)
    return item


async def delete_broadcast(session: AsyncSession, broadcast_id: int) -> AdminBroadcast | None:
    item = await get_broadcast(session, broadcast_id, for_update=True)
    if item is None:
        return None
    now = utc_now()
    item.deleted_at = now
    item.updated_at = now
    if item.status in ACTIVE_BROADCAST_STATUSES:
        item.status = "cancelled"
        item.finished_at = now
    await session.commit()
    return item
