"""Payment candidates from the account history for billing support requests."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from db.dal.payment_history_dal import payment_history_filter
from db.models import Payment

SUPPORT_PAYMENT_RECENT_DAYS = 7


def support_payment_filter(user_id: int, now: datetime) -> ColumnElement[bool]:
    status = func.lower(func.trim(func.coalesce(Payment.status, "")))
    return and_(
        payment_history_filter(user_id, now),
        Payment.created_at >= now - timedelta(days=SUPPORT_PAYMENT_RECENT_DAYS),
        Payment.created_at <= now,
        status.not_in({"succeeded", "refunded", "reversed"}),
        Payment.fulfilled_at.is_(None),
        Payment.reversed_at.is_(None),
    )


async def list_support_payments(session: AsyncSession, user_id: int) -> list[Payment]:
    result = await session.execute(
        select(Payment)
        .where(support_payment_filter(user_id, datetime.now(UTC)))
        .order_by(Payment.created_at.desc(), Payment.payment_id.desc())
        .limit(100)
    )
    return list(result.scalars().all())


async def lock_support_payment(
    session: AsyncSession, user_id: int, payment_id: int
) -> Payment | None:
    return await session.scalar(
        select(Payment)
        .where(support_payment_filter(user_id, datetime.now(UTC)), Payment.payment_id == payment_id)
        .with_for_update()
    )
