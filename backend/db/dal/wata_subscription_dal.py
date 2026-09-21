"""Persistence helpers for provider-managed Wata subscriptions."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Payment, WataSubscription

LIVE_STATUSES = ("active",)


async def get_subscription(
    session: AsyncSession,
    subscription_id: str,
    *,
    for_update: bool = False,
) -> WataSubscription | None:
    remote_id = str(subscription_id or "").strip()
    if not remote_id:
        return None
    stmt = select(WataSubscription).where(WataSubscription.wata_subscription_id == remote_id)
    if for_update:
        stmt = stmt.execution_options(populate_existing=True).with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_by_anchor_payment(
    session: AsyncSession,
    payment_id: int,
    *,
    for_update: bool = False,
) -> WataSubscription | None:
    stmt = select(WataSubscription).where(WataSubscription.anchor_payment_id == int(payment_id))
    if for_update:
        stmt = stmt.execution_options(populate_existing=True).with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_from_anchor(
    session: AsyncSession,
    *,
    subscription_id: str,
    anchor: Payment,
    interval: str,
    period: int,
    max_periods: int,
    status: str = "active",
) -> WataSubscription:
    """Freeze attribution and recurring checkout terms from the authorized payment."""

    remote_id = str(subscription_id or "").strip()
    if not remote_id:
        raise ValueError("subscription_id is required")
    record = await get_subscription(session, remote_id, for_update=True)
    if record is None:
        record = WataSubscription(
            wata_subscription_id=remote_id,
            anchor_payment_id=int(anchor.payment_id),
            user_id=int(anchor.user_id),
            status=str(status).lower(),
            interval=str(interval),
            period=int(period),
            max_periods=int(max_periods),
            amount=float(anchor.amount),
            currency=str(anchor.currency),
            months=int(anchor.subscription_duration_months or 0),
            duration_days=anchor.subscription_duration_days,
            subscription_terms_snapshot=anchor.subscription_terms_snapshot,
            checkout_bundle_snapshot=anchor.checkout_bundle_snapshot,
            period_semantics="provider_managed",
            sale_mode=anchor.sale_mode,
            tariff_key=anchor.tariff_key,
        )
        session.add(record)
    elif int(record.anchor_payment_id) != int(anchor.payment_id) or int(record.user_id) != int(
        anchor.user_id
    ):
        raise ValueError("Wata subscription attribution mismatch")
    else:
        record.status = str(status).lower()
    await session.flush()
    return record


async def mark_status(
    session: AsyncSession,
    record: WataSubscription,
    status: str,
) -> None:
    normalized = str(status or "").strip().lower()
    record.status = normalized
    record.updated_at = func.now()
    if normalized in {"completed", "failed"} and record.completed_at is None:
        record.completed_at = datetime.now(UTC)
    await session.flush()


async def record_charge(
    session: AsyncSession,
    record: WataSubscription,
    *,
    payment_id: str,
    charged_at: datetime | None = None,
) -> None:
    record.charges_count = int(record.charges_count or 0) + 1
    record.last_charge_at = charged_at or datetime.now(UTC)
    record.status = "active"
    record.updated_at = func.now()
    if record.first_provider_payment_id is None:
        record.first_provider_payment_id = str(payment_id)
    await session.flush()


async def list_live_for_user(
    session: AsyncSession,
    user_id: int,
) -> list[WataSubscription]:
    stmt = (
        select(WataSubscription)
        .where(
            WataSubscription.user_id == int(user_id),
            WataSubscription.status.in_(LIVE_STATUSES),
        )
        .order_by(WataSubscription.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


__all__ = [
    "LIVE_STATUSES",
    "create_from_anchor",
    "get_by_anchor_payment",
    "get_subscription",
    "list_live_for_user",
    "mark_status",
    "record_charge",
]
