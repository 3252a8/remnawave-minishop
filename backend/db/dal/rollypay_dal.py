"""Persistence helpers for provider-managed RollyPay SBP subscriptions."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import RollyPaySubscription

LIVE_BILLING_STATUSES = (
    "consent_pending",
    "pending",
    "enabled",
    "review",
    "stop_pending",
)


async def get_subscription(
    session: AsyncSession,
    subscription_id: str,
    *,
    for_update: bool = False,
) -> RollyPaySubscription | None:
    remote_id = str(subscription_id or "").strip()
    if not remote_id:
        return None
    stmt = select(RollyPaySubscription).where(
        RollyPaySubscription.rollypay_subscription_id == remote_id
    )
    if for_update:
        stmt = stmt.execution_options(populate_existing=True).with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_by_anchor_payment(
    session: AsyncSession,
    payment_id: int,
    *,
    for_update: bool = False,
) -> RollyPaySubscription | None:
    stmt = select(RollyPaySubscription).where(
        RollyPaySubscription.anchor_payment_id == int(payment_id)
    )
    if for_update:
        stmt = stmt.execution_options(populate_existing=True).with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_or_update_subscription(
    session: AsyncSession,
    *,
    subscription_id: str,
    anchor_payment_id: int,
    user_id: int,
    provider_state: str,
    billing_status: str,
    plan_id: str,
    plan_code: str,
    plan_version: int,
    interval: str,
    max_cycles: int | None,
    amount: float,
    months: int,
    sale_mode: str | None,
    tariff_key: str | None,
    next_charge_at: datetime | None = None,
) -> RollyPaySubscription:
    """Create a mirror or refresh mutable state without repointing immutable terms."""

    remote_id = str(subscription_id or "").strip()
    if not remote_id:
        raise ValueError("subscription_id is required")
    record = await get_subscription(session, remote_id, for_update=True)
    if record is None:
        record = RollyPaySubscription(
            rollypay_subscription_id=remote_id,
            anchor_payment_id=int(anchor_payment_id),
            user_id=int(user_id),
            provider_state=str(provider_state),
            billing_status=str(billing_status),
            plan_id=str(plan_id),
            plan_code=str(plan_code),
            plan_version=int(plan_version),
            interval=str(interval),
            max_cycles=max_cycles,
            amount=float(amount),
            currency="RUB",
            months=int(months),
            sale_mode=sale_mode,
            tariff_key=tariff_key,
            next_charge_at=next_charge_at,
        )
        session.add(record)
    else:
        if int(record.anchor_payment_id) != int(anchor_payment_id) or int(record.user_id) != int(
            user_id
        ):
            raise ValueError("RollyPay subscription attribution mismatch")
        record.provider_state = str(provider_state)
        record.billing_status = str(billing_status)
        record.next_charge_at = next_charge_at
    await session.flush()
    return record


async def update_remote_state(
    session: AsyncSession,
    record: RollyPaySubscription,
    *,
    provider_state: str,
    billing_status: str,
    next_charge_at: datetime | None = None,
) -> None:
    record.provider_state = str(provider_state)
    record.billing_status = str(billing_status)
    record.next_charge_at = next_charge_at
    record.updated_at = func.now()
    if billing_status == "enabled" and record.activated_at is None:
        record.activated_at = datetime.now(UTC)
    if provider_state == "stop" or billing_status == "stopped":
        record.next_charge_at = None
        if record.stopped_at is None:
            record.stopped_at = datetime.now(UTC)
    await session.flush()


async def record_charge(
    session: AsyncSession,
    record: RollyPaySubscription,
    *,
    payment_id: str,
    charged_at: datetime | None = None,
    next_charge_at: datetime | None = None,
) -> None:
    record.charges_count = int(record.charges_count or 0) + 1
    record.last_charge_at = charged_at or datetime.now(UTC)
    record.next_charge_at = next_charge_at
    record.provider_state = "active"
    record.billing_status = "enabled"
    if record.first_provider_payment_id is None:
        record.first_provider_payment_id = str(payment_id)
    if record.activated_at is None:
        record.activated_at = datetime.now(UTC)
    await session.flush()


async def list_live_for_user(
    session: AsyncSession,
    user_id: int,
) -> list[RollyPaySubscription]:
    stmt = (
        select(RollyPaySubscription)
        .where(
            RollyPaySubscription.user_id == int(user_id),
            RollyPaySubscription.billing_status.in_(LIVE_BILLING_STATUSES),
        )
        .order_by(RollyPaySubscription.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_reconcilable(
    session: AsyncSession,
    *,
    limit: int,
) -> list[RollyPaySubscription]:
    stmt = (
        select(RollyPaySubscription)
        .where(RollyPaySubscription.billing_status.in_(LIVE_BILLING_STATUSES))
        .order_by(
            func.coalesce(RollyPaySubscription.updated_at, RollyPaySubscription.created_at).asc(),
            RollyPaySubscription.id.asc(),
        )
        .limit(max(1, int(limit)))
    )
    return list((await session.execute(stmt)).scalars().all())


__all__ = [
    "LIVE_BILLING_STATUSES",
    "create_or_update_subscription",
    "get_by_anchor_payment",
    "get_subscription",
    "list_live_for_user",
    "list_reconcilable",
    "record_charge",
    "update_remote_state",
]
