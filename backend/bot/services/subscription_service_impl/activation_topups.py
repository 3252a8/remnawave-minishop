from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from . import entitlement_helpers


async def record_activation_topups(
    session: AsyncSession,
    *,
    subscription_id: int,
    payment_id: int,
    promo_regular_bytes: int,
    promo_premium_bytes: int,
    checkout_regular_bytes: int,
    checkout_premium_bytes: int,
) -> None:
    topups = (
        (promo_regular_bytes, "promo_topup"),
        (promo_premium_bytes, "promo_premium_topup"),
        (checkout_regular_bytes, "checkout_topup"),
        (checkout_premium_bytes, "checkout_premium_topup"),
    )
    for purchased_bytes, kind in topups:
        if purchased_bytes <= 0:
            continue
        await entitlement_helpers.record_traffic_topup_best_effort(
            session,
            subscription_id=subscription_id,
            payment_id=payment_id,
            purchased_bytes=purchased_bytes,
            kind=kind,
        )
