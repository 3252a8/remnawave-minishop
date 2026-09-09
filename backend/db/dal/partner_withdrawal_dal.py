from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, delete, desc, func, or_, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.partner_models import PartnerAuditEvent, PartnerWithdrawal


async def get_withdrawal_by_id(
    session: AsyncSession,
    withdrawal_id: int,
    *,
    for_update: bool = False,
) -> PartnerWithdrawal | None:
    statement = select(PartnerWithdrawal).where(PartnerWithdrawal.withdrawal_id == withdrawal_id)
    if for_update:
        statement = statement.with_for_update()
    return (await session.execute(statement)).scalar_one_or_none()


async def get_withdrawal_by_idempotency_key(
    session: AsyncSession,
    key: str,
) -> PartnerWithdrawal | None:
    return (
        await session.execute(
            select(PartnerWithdrawal).where(PartnerWithdrawal.client_idempotency_key == key)
        )
    ).scalar_one_or_none()


async def latest_withdrawal_for_partner(
    session: AsyncSession,
    partner_id: int,
) -> PartnerWithdrawal | None:
    return (
        await session.execute(
            select(PartnerWithdrawal)
            .where(PartnerWithdrawal.partner_id == partner_id)
            .order_by(
                desc(PartnerWithdrawal.requested_at),
                desc(PartnerWithdrawal.withdrawal_id),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def active_withdrawal_count(session: AsyncSession, partner_id: int) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(PartnerWithdrawal)
                .where(
                    PartnerWithdrawal.partner_id == partner_id,
                    PartnerWithdrawal.status.in_(("requested", "processing")),
                )
            )
        ).scalar_one()
        or 0
    )


async def active_withdrawal_methods_in_use(
    session: AsyncSession,
    method_ids: set[str],
) -> set[str]:
    if not method_ids:
        return set()
    result = await session.execute(
        select(PartnerWithdrawal.method_id_snapshot)
        .where(
            PartnerWithdrawal.method_id_snapshot.in_(sorted(method_ids)),
            PartnerWithdrawal.status.in_(("requested", "processing", "failed")),
        )
        .distinct()
    )
    return {str(value) for value in result.scalars().all()}


async def create_withdrawal(session: AsyncSession, **values: Any) -> PartnerWithdrawal:
    withdrawal = PartnerWithdrawal(**values)
    session.add(withdrawal)
    await session.flush()
    return withdrawal


async def list_withdrawals(
    session: AsyncSession,
    *,
    partner_id: int | None = None,
    status: str | None = None,
    currency: str | None = None,
    search: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[PartnerWithdrawal], int]:
    conditions: list[Any] = []
    if partner_id is not None:
        conditions.append(PartnerWithdrawal.partner_id == partner_id)
    if status and status != "all":
        if status == "closed":
            conditions.append(
                PartnerWithdrawal.status.in_(("paid", "rejected", "canceled", "failed"))
            )
        else:
            conditions.append(PartnerWithdrawal.status == status)
    if currency:
        conditions.append(func.upper(PartnerWithdrawal.debit_currency) == currency.upper())
    normalized_search = str(search or "").strip()
    if normalized_search.isdigit():
        numeric = int(normalized_search)
        conditions.append(
            or_(
                PartnerWithdrawal.withdrawal_id == numeric,
                PartnerWithdrawal.partner_id == numeric,
            )
        )
    where = and_(*conditions) if conditions else true()
    total = int(
        (
            await session.execute(select(func.count()).select_from(PartnerWithdrawal).where(where))
        ).scalar_one()
        or 0
    )
    result = await session.execute(
        select(PartnerWithdrawal)
        .where(where)
        .order_by(desc(PartnerWithdrawal.requested_at), desc(PartnerWithdrawal.withdrawal_id))
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), total


async def create_audit_event(
    session: AsyncSession,
    *,
    event_type: str,
    actor_type: str,
    partner_id: int | None = None,
    application_id: int | None = None,
    withdrawal_id: int | None = None,
    actor_user_id: int | None = None,
    old_values_json: str | None = None,
    new_values_json: str | None = None,
    reason: str | None = None,
) -> PartnerAuditEvent:
    event = PartnerAuditEvent(
        partner_id=partner_id,
        application_id=application_id,
        withdrawal_id=withdrawal_id,
        event_type=event_type,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        old_values_json=old_values_json,
        new_values_json=new_values_json,
        reason=reason,
    )
    session.add(event)
    await session.flush()
    return event


async def purge_expired_partner_data(
    session: AsyncSession,
    *,
    audit_before: datetime | None,
    requisites_before: datetime,
) -> dict[str, int]:
    audit_count = 0
    if audit_before is not None:
        audit_result = await session.execute(
            delete(PartnerAuditEvent).where(PartnerAuditEvent.created_at < audit_before)
        )
        audit_count = int(getattr(audit_result, "rowcount", 0) or 0)
    requisites_result = await session.execute(
        update(PartnerWithdrawal)
        .where(
            PartnerWithdrawal.status.in_(("paid", "rejected", "canceled")),
            PartnerWithdrawal.decided_at.is_not(None),
            PartnerWithdrawal.decided_at < requisites_before,
            PartnerWithdrawal.requisites_ciphertext.is_not(None),
        )
        .values(requisites_ciphertext=None)
    )
    return {
        "audit": audit_count,
        "requisites": int(getattr(requisites_result, "rowcount", 0) or 0),
    }
