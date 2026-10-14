"""Qualification history for invitation period accrual."""

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.gift_models import SubscriptionGift
from db.models import Payment


async def count_user_succeeded_payments(
    session: AsyncSession,
    user_id: int,
    exclude_payment_id: int | None = None,
    *,
    qualifying_subscription_only: bool = False,
    before_payment_id: int | None = None,
    include_gift_activations: bool = False,
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
                ~Payment.sale_mode.like("%|gift"),
                ~Payment.sale_mode.like("%|gift|%"),
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
    payment_count = select(func.count(Payment.payment_id)).where(and_(*conditions))
    if qualifying_subscription_only and include_gift_activations:
        gift_conditions = [
            SubscriptionGift.recipient_id == user_id,
            SubscriptionGift.referral_qualified.is_(True),
        ]
        if exclude_payment_id is not None:
            gift_conditions.append(SubscriptionGift.payment_id != exclude_payment_id)
        if before_payment_id is not None:
            gift_conditions.append(SubscriptionGift.activated_at < boundary)
        gift_count = select(func.count(SubscriptionGift.gift_id)).where(*gift_conditions)
        stmt = select(payment_count.scalar_subquery() + gift_count.scalar_subquery())
    else:
        stmt = payment_count
    result = await session.execute(stmt)
    return result.scalar() or 0
