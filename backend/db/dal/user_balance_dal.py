from __future__ import annotations

from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.balance_models import UserBalanceLedgerEntry


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
