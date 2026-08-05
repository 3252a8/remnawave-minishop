"""Local mirror of Platega SBP subscription mandates.

Platega owns the renewal schedule, so these rows are written from the webhook
(never from checkout) and read whenever a charge has to be attributed to a
customer or a mandate has to be stopped.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PlategaSubscription

# Statuses that still bill the customer. ``past_due`` is included on purpose:
# Platega keeps retrying such a mandate, so it is not a free slot for a second
# one and it must still be cancellable.
LIVE_STATUSES = ("active", "past_due")


async def get_subscription(
    session: AsyncSession,
    platega_subscription_id: str,
    *,
    for_update: bool = False,
) -> PlategaSubscription | None:
    remote_id = str(platega_subscription_id or "").strip()
    if not remote_id:
        return None
    stmt = select(PlategaSubscription).where(
        PlategaSubscription.platega_subscription_id == remote_id
    )
    if for_update:
        stmt = stmt.execution_options(populate_existing=True).with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_subscription(
    session: AsyncSession,
    *,
    platega_subscription_id: str,
    user_id: int,
    amount: float,
    currency: str,
    interval_code: int,
    months: int,
    sale_mode: str | None = None,
    tariff_key: str | None = None,
    status: str = "active",
    next_charge_at: datetime | None = None,
) -> PlategaSubscription:
    """Create or refresh the local mirror of one mandate.

    ``user_id`` and the billing terms are frozen on first write: they come from
    the anchor payment the customer actually authorized, and a later callback
    must never be able to repoint an existing mandate at another account.
    """
    remote_id = str(platega_subscription_id or "").strip()
    if not remote_id:
        raise ValueError("platega_subscription_id is required")

    record = await get_subscription(session, remote_id, for_update=True)
    if record is None:
        record = PlategaSubscription(
            platega_subscription_id=remote_id,
            user_id=int(user_id),
            amount=float(amount),
            currency=str(currency),
            interval_code=int(interval_code),
            months=int(months),
            sale_mode=sale_mode,
            tariff_key=tariff_key,
            status=status,
            next_charge_at=next_charge_at,
        )
        session.add(record)
        await session.flush()
        await session.refresh(record)
        return record

    record.status = status
    if next_charge_at is not None:
        record.next_charge_at = next_charge_at
    if status == "cancelled" and record.cancelled_at is None:
        record.cancelled_at = datetime.now(UTC)
    await session.flush()
    return record


async def mark_status(
    session: AsyncSession,
    record: PlategaSubscription,
    status: str,
    *,
    next_charge_at: datetime | None = None,
) -> PlategaSubscription:
    record.status = status
    if next_charge_at is not None:
        record.next_charge_at = next_charge_at
    if status in {"cancelled", "failed"}:
        record.next_charge_at = None
        if record.cancelled_at is None:
            record.cancelled_at = datetime.now(UTC)
    await session.flush()
    return record


async def record_charge(
    session: AsyncSession,
    record: PlategaSubscription,
    *,
    charged_at: datetime | None = None,
    next_charge_at: datetime | None = None,
) -> PlategaSubscription:
    record.charges_count = int(record.charges_count or 0) + 1
    record.last_charge_at = charged_at or datetime.now(UTC)
    record.next_charge_at = next_charge_at
    record.status = "active"
    await session.flush()
    return record


async def list_live_subscriptions_for_user(
    session: AsyncSession,
    user_id: int,
) -> list[PlategaSubscription]:
    stmt = (
        select(PlategaSubscription)
        .where(
            PlategaSubscription.user_id == int(user_id),
            PlategaSubscription.status.in_(LIVE_STATUSES),
        )
        .order_by(PlategaSubscription.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def user_has_live_subscription(session: AsyncSession, user_id: int) -> bool:
    return bool(await list_live_subscriptions_for_user(session, user_id))


def subscription_snapshot(record: PlategaSubscription) -> dict[str, Any]:
    """Detached view used for logging after the session is gone."""
    return {
        "platega_subscription_id": str(record.platega_subscription_id),
        "user_id": int(record.user_id),
        "status": str(record.status),
        "months": int(record.months),
        "amount": float(record.amount),
        "currency": str(record.currency),
    }
