"""Qualification history for invitation period accrual."""

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Payment


async def count_user_succeeded_payments(
    session: AsyncSession,
    user_id: int,
    exclude_payment_id: int | None = None,
    *,
    qualifying_subscription_only: bool = False,
    before_payment_id: int | None = None,
) -> int:
    """Count succeeded payments for a specific user.

    If exclude_payment_id is provided, that specific payment will be excluded
    from the count. Useful to check "prior" payments while processing the
    current payment in the same transaction.
    """
    conditions = [Payment.user_id == user_id, Payment.status == "succeeded"]
    if qualifying_subscription_only:
        # Refunds do not undo a previously committed qualification decision.
        conditions[1] = or_(
            Payment.status == "succeeded",
            and_(
                Payment.referral_accrual_processed.is_(True),
                Payment.status.in_(["refunded", "reversed"]),
            ),
        )
        conditions.extend(
            [
                or_(
                    Payment.sale_mode == "subscription",
                    Payment.sale_mode.like("subscription@%"),
                    Payment.sale_mode.like("subscription|%"),
                ),
                Payment.amount > 0,
            ]
        )
    if exclude_payment_id is not None:
        conditions.append(Payment.payment_id != exclude_payment_id)
    if before_payment_id is not None:
        boundary = (
            select(func.coalesce(Payment.updated_at, Payment.created_at))
            .where(Payment.payment_id == before_payment_id)
            .scalar_subquery()
        )
        time = func.coalesce(Payment.updated_at, Payment.created_at)
        conditions.append(
            or_(time < boundary, and_(time == boundary, Payment.payment_id < before_payment_id))
        )
    stmt = select(func.count(Payment.payment_id)).where(and_(*conditions))
    result = await session.execute(stmt)
    return result.scalar() or 0
