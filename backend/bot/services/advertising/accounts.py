"""Advertising cleanup through the existing account-deletion transaction."""

from datetime import UTC, datetime

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.advertising_models import AdOfferActivation, AdPurchaseAttribution, AdTouchpoint, AdVisit
from db.models import AdCampaign, Payment, PromoCodeActivation


async def delete_account_evidence(session: AsyncSession, user_id: int) -> None:
    payments = select(Payment.payment_id).where(Payment.user_id == user_id)
    activations = select(PromoCodeActivation.activation_id).where(
        or_(PromoCodeActivation.user_id == user_id, PromoCodeActivation.payment_id.in_(payments))
    )
    await session.execute(
        delete(AdOfferActivation).where(
            or_(
                AdOfferActivation.user_id == user_id,
                AdOfferActivation.activation_id.in_(activations),
            )
        )
    )
    await session.execute(
        update(AdCampaign).where(AdCampaign.advertiser_id == user_id).values(advertiser_id=None)
    )
    await session.execute(
        update(AdTouchpoint)
        .where(AdTouchpoint.user_id == user_id)
        .values(user_id=None, original_user_id=None, visit_id=None)
    )
    await session.execute(
        update(AdTouchpoint)
        .where(AdTouchpoint.original_user_id == user_id)
        .values(original_user_id=None)
    )
    await session.execute(
        update(AdVisit)
        .where(AdVisit.user_id == user_id)
        .values(user_id=None, expires_at=datetime.now(UTC))
    )
    await session.execute(
        delete(AdPurchaseAttribution).where(AdPurchaseAttribution.user_id == user_id)
    )
