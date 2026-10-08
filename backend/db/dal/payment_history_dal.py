"""Read-only payment history scoped to the authenticated account."""

from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from db.models import Payment
from db.payment_history import (
    AWAITING_PAYMENT_STATUSES,
    CONFIRMED_PAYMENT_STATUSES,
    PROCESSING_PAYMENT_STATUSES,
)


def payment_history_filter(user_id: int, now: datetime) -> ColumnElement[bool]:
    status = func.lower(func.trim(func.coalesce(Payment.status, "")))
    active_checkout = and_(
        or_(status.in_(AWAITING_PAYMENT_STATUSES), status.startswith("pending_", autoescape=True)),
        Payment.checkout_expires_at > now,
        func.length(func.trim(func.coalesce(Payment.provider_payment_url, ""))) > 0,
    )
    return and_(
        Payment.user_id == user_id,
        or_(
            status.in_(CONFIRMED_PAYMENT_STATUSES),
            status.in_(PROCESSING_PAYMENT_STATUSES),
            Payment.fulfilled_at.is_not(None),
            Payment.reversed_at.is_not(None),
            active_checkout,
        ),
    )


async def list_user_payments(
    session: AsyncSession,
    user_id: int,
    *,
    limit: int,
    offset: int,
) -> tuple[list[Payment], int]:
    account_filter = payment_history_filter(user_id, datetime.now(UTC))
    total = int(
        await session.scalar(select(func.count(Payment.payment_id)).where(account_filter)) or 0
    )
    result = await session.execute(
        select(Payment)
        .where(account_filter)
        .order_by(Payment.created_at.desc().nullslast(), Payment.payment_id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), total
