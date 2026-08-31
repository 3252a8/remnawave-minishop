from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import String, and_, cast, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from db.balance_models import UserBalanceLedgerEntry
from db.models import Payment


async def create_ledger_entry(
    session: AsyncSession,
    **values: Any,
) -> UserBalanceLedgerEntry:
    entry = UserBalanceLedgerEntry(**values)
    session.add(entry)
    await session.flush()
    return entry


async def get_ledger_entry_by_key(
    session: AsyncSession,
    idempotency_key: str,
) -> UserBalanceLedgerEntry | None:
    return (
        await session.execute(
            select(UserBalanceLedgerEntry).where(
                UserBalanceLedgerEntry.idempotency_key == idempotency_key
            )
        )
    ).scalar_one_or_none()


async def balance_minor(
    session: AsyncSession,
    user_id: int,
    currency: str,
) -> int:
    value = await session.scalar(
        select(func.coalesce(func.sum(UserBalanceLedgerEntry.amount_minor), 0)).where(
            UserBalanceLedgerEntry.user_id == user_id,
            func.upper(UserBalanceLedgerEntry.currency) == currency.upper(),
            UserBalanceLedgerEntry.state == "posted",
        )
    )
    return int(value or 0)


async def balance_minor_by_user_ids(
    session: AsyncSession,
    user_ids: list[int],
    currency: str,
) -> dict[int, int]:
    unique_ids = sorted({int(user_id) for user_id in user_ids})
    if not unique_ids:
        return {}
    rows = (
        await session.execute(
            select(
                UserBalanceLedgerEntry.user_id,
                func.coalesce(func.sum(UserBalanceLedgerEntry.amount_minor), 0).label("amount"),
            )
            .where(
                UserBalanceLedgerEntry.user_id.in_(unique_ids),
                func.upper(UserBalanceLedgerEntry.currency) == currency.upper(),
                UserBalanceLedgerEntry.state == "posted",
            )
            .group_by(UserBalanceLedgerEntry.user_id)
        )
    ).all()
    return {int(row.user_id): int(row.amount or 0) for row in rows}


async def list_terminal_checkout_payments(
    session: AsyncSession,
    *,
    statuses: set[str] | frozenset[str],
    limit: int,
) -> list[Payment]:
    spend = aliased(UserBalanceLedgerEntry, name="user_checkout_spend")
    release = aliased(UserBalanceLedgerEntry, name="user_checkout_spend_release")
    normalized_status = func.lower(func.trim(Payment.status))
    result = await session.execute(
        select(Payment)
        .join(
            spend,
            and_(
                spend.reference_type == "payment",
                spend.reference_id == cast(Payment.payment_id, String),
                spend.kind == "checkout_spend",
            ),
        )
        .outerjoin(
            release,
            and_(
                release.reference_type == "payment",
                release.reference_id == cast(Payment.payment_id, String),
                release.kind == "checkout_spend_release",
                release.state == "posted",
            ),
        )
        .where(
            normalized_status.in_(tuple(sorted(statuses))),
            release.entry_id.is_(None),
        )
        .order_by(Payment.payment_id)
        .limit(limit)
        .with_for_update(skip_locked=True, of=Payment)
    )
    return list(result.scalars().all())


async def list_stale_checkout_payments(
    session: AsyncSession,
    *,
    older_than: datetime,
    limit: int,
) -> list[Payment]:
    last_activity = func.coalesce(Payment.updated_at, Payment.created_at)
    spend = aliased(UserBalanceLedgerEntry, name="stale_user_checkout_spend")
    release = aliased(UserBalanceLedgerEntry, name="stale_user_checkout_spend_release")
    result = await session.execute(
        select(Payment)
        .join(
            spend,
            and_(
                spend.reference_type == "payment",
                spend.reference_id == cast(Payment.payment_id, String),
                spend.kind == "checkout_spend",
            ),
        )
        .outerjoin(
            release,
            and_(
                release.reference_type == "payment",
                release.reference_id == cast(Payment.payment_id, String),
                release.kind == "checkout_spend_release",
                release.state == "posted",
            ),
        )
        .where(
            Payment.status == "succeeded_pending_finalization",
            last_activity < older_than,
            release.entry_id.is_(None),
        )
        .order_by(last_activity, Payment.payment_id)
        .limit(limit)
        .with_for_update(skip_locked=True, of=Payment)
    )
    return list(result.scalars().all())


async def balance_summaries(
    session: AsyncSession,
    user_id: int,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(
                UserBalanceLedgerEntry.currency,
                UserBalanceLedgerEntry.currency_scale,
                func.coalesce(func.sum(UserBalanceLedgerEntry.amount_minor), 0).label("amount"),
            )
            .where(
                UserBalanceLedgerEntry.user_id == user_id,
                UserBalanceLedgerEntry.state == "posted",
            )
            .group_by(
                UserBalanceLedgerEntry.currency,
                UserBalanceLedgerEntry.currency_scale,
            )
            .order_by(UserBalanceLedgerEntry.currency)
        )
    ).all()
    return [
        {
            "currency": str(row.currency).upper(),
            "currency_scale": int(row.currency_scale),
            "amount_minor": int(row.amount or 0),
        }
        for row in rows
    ]


async def list_ledger_entries(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None = None,
    limit: int = 100,
) -> list[UserBalanceLedgerEntry]:
    conditions = [UserBalanceLedgerEntry.user_id == user_id]
    if currency:
        conditions.append(func.upper(UserBalanceLedgerEntry.currency) == currency.upper())
    return list(
        (
            await session.execute(
                select(UserBalanceLedgerEntry)
                .where(*conditions)
                .order_by(
                    desc(UserBalanceLedgerEntry.created_at),
                    desc(UserBalanceLedgerEntry.entry_id),
                )
                .limit(max(1, min(int(limit), 500)))
            )
        ).scalars()
    )
