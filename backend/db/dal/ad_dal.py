import logging
from typing import Any

from sqlalchemy import and_, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models import AdAttribution, AdCampaign, Payment
from ._sqlalchemy import rowcount

logger = logging.getLogger(__name__)


async def create_campaign(
    session: AsyncSession,
    *,
    source: str,
    start_param: str,
    cost: float,
    advertiser_id: int | None = None,
) -> AdCampaign:
    existing = await get_campaign_by_start_param(session, start_param)
    if existing:
        raise ValueError("ad_campaign_start_param_exists")

    campaign = AdCampaign(
        source=source,
        start_param=start_param,
        cost=float(cost),
        advertiser_id=advertiser_id,
    )
    session.add(campaign)
    await session.flush()
    await session.refresh(campaign)
    logger.info(
        "AdCampaign created id=%s, source=%s, start=%s, cost=%s, advertiser_id=%s",
        campaign.ad_campaign_id,
        source,
        start_param,
        cost,
        advertiser_id,
    )
    return campaign


async def get_campaign_by_id(session: AsyncSession, campaign_id: int) -> AdCampaign | None:
    stmt = select(AdCampaign).where(AdCampaign.ad_campaign_id == campaign_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_campaign_by_start_param(session: AsyncSession, start_param: str) -> AdCampaign | None:
    clean = start_param.strip()
    stmt = select(AdCampaign).where(AdCampaign.start_param == clean)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_campaigns(
    session: AsyncSession,
    *,
    only_active: bool = False,
    advertiser_id: int | None = None,
) -> list[AdCampaign]:
    stmt = select(AdCampaign).order_by(AdCampaign.created_at.desc())
    if only_active:
        stmt = stmt.where(AdCampaign.is_active == True)
    if advertiser_id is not None:
        stmt = stmt.where(AdCampaign.advertiser_id == advertiser_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def toggle_campaign_active(session: AsyncSession, campaign_id: int, is_active: bool) -> bool:
    stmt = (
        update(AdCampaign)
        .where(AdCampaign.ad_campaign_id == campaign_id)
        .values(is_active=is_active)
    )
    result = await session.execute(stmt)
    return rowcount(result) > 0


async def ensure_attribution(
    session: AsyncSession, *, user_id: int, campaign_id: int
) -> AdAttribution:
    existing = await get_attribution_for_user(session, user_id)
    if existing:
        return existing
    attrib = AdAttribution(user_id=user_id, ad_campaign_id=campaign_id)
    session.add(attrib)
    await session.flush()
    await session.refresh(attrib)
    logger.info("AdAttribution created for user %s -> campaign %s", user_id, campaign_id)
    return attrib


async def get_attribution_for_user(session: AsyncSession, user_id: int) -> AdAttribution | None:
    stmt = select(AdAttribution).where(AdAttribution.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def mark_trial_activated(session: AsyncSession, user_id: int) -> bool:
    stmt = (
        update(AdAttribution)
        .where(and_(AdAttribution.user_id == user_id, AdAttribution.trial_activated_at.is_(None)))
        .values(trial_activated_at=func.now())
    )
    result = await session.execute(stmt)
    return rowcount(result) > 0


async def get_campaign_stats(session: AsyncSession, campaign_id: int) -> dict[str, Any]:
    campaign = await session.get(AdCampaign, campaign_id)
    if not campaign:
        return {"starts": 0, "trials": 0, "payers": 0, "revenue": 0.0}
    reset_at = campaign.stats_reset_at

    # Starts (attributed users)
    starts_stmt = select(func.count(AdAttribution.user_id)).where(
        AdAttribution.ad_campaign_id == campaign_id
    )
    if reset_at:
        starts_stmt = starts_stmt.where(AdAttribution.first_start_at >= reset_at)
    starts = (await session.execute(starts_stmt)).scalar() or 0

    # Trials
    trials_stmt = select(func.count(AdAttribution.user_id)).where(
        and_(
            AdAttribution.ad_campaign_id == campaign_id,
            AdAttribution.trial_activated_at.is_not(None),
        )
    )
    if reset_at:
        trials_stmt = trials_stmt.where(AdAttribution.trial_activated_at >= reset_at)
    trials = (await session.execute(trials_stmt)).scalar() or 0

    # Payers (unique users with succeeded first payments)
    attrib_subq = (
        select(
            AdAttribution.user_id.label("user_id"),
            AdAttribution.first_start_at.label("first_start_at"),
        )
        .where(AdAttribution.ad_campaign_id == campaign_id)
        .subquery()
    )

    first_payment_subq = (
        select(func.min(Payment.payment_id).label("payment_id"))
        .where(
            Payment.status == "succeeded",
            Payment.funding_source == "external",
        )
        .group_by(Payment.user_id)
        .subquery()
    )

    payers_conditions = [
        Payment.payment_id == first_payment_subq.c.payment_id,
        Payment.created_at >= attrib_subq.c.first_start_at,
    ]
    if reset_at:
        payers_conditions.append(Payment.created_at >= reset_at)

    payers_stmt = (
        select(func.count(func.distinct(Payment.user_id)))
        .select_from(Payment)
        .join(attrib_subq, Payment.user_id == attrib_subq.c.user_id)
        .join(first_payment_subq, Payment.payment_id == first_payment_subq.c.payment_id)
        .where(and_(*payers_conditions))
    )
    payers = (await session.execute(payers_stmt)).scalar() or 0

    # Revenue sum (only first successful payments)
    revenue_stmt = (
        select(func.coalesce(func.sum(Payment.amount), 0.0))
        .select_from(Payment)
        .join(attrib_subq, Payment.user_id == attrib_subq.c.user_id)
        .join(first_payment_subq, Payment.payment_id == first_payment_subq.c.payment_id)
        .where(and_(*payers_conditions))
    )
    revenue = float((await session.execute(revenue_stmt)).scalar() or 0.0)

    return {
        "starts": int(starts),
        "trials": int(trials),
        "payers": int(payers),
        "revenue": revenue,
    }


async def reset_campaign_stats(session: AsyncSession, campaign_id: int) -> bool:
    stmt = (
        update(AdCampaign)
        .where(AdCampaign.ad_campaign_id == campaign_id)
        .values(stats_reset_at=func.now())
    )
    result = await session.execute(stmt)
    return rowcount(result) > 0


async def list_campaign_purchases(
    session: AsyncSession,
    campaign_id: int,
    *,
    page: int = 0,
    page_size: int = 50,
) -> list[dict[str, Any]]:
    campaign = await session.get(AdCampaign, campaign_id)
    if not campaign:
        return []
    reset_at = campaign.stats_reset_at

    attrib_subq = (
        select(
            AdAttribution.user_id.label("user_id"),
            AdAttribution.first_start_at.label("first_start_at"),
        )
        .where(AdAttribution.ad_campaign_id == campaign_id)
        .subquery()
    )

    first_payment_subq = (
        select(func.min(Payment.payment_id).label("payment_id"))
        .where(
            Payment.status == "succeeded",
            Payment.funding_source == "external",
        )
        .group_by(Payment.user_id)
        .subquery()
    )

    conditions = [
        Payment.payment_id == first_payment_subq.c.payment_id,
        Payment.created_at >= attrib_subq.c.first_start_at,
    ]
    if reset_at:
        conditions.append(Payment.created_at >= reset_at)

    from ..models import User

    stmt = (
        select(Payment, User.username, User.user_id)
        .select_from(Payment)
        .join(attrib_subq, Payment.user_id == attrib_subq.c.user_id)
        .join(first_payment_subq, Payment.payment_id == first_payment_subq.c.payment_id)
        .join(User, Payment.user_id == User.user_id)
        .where(and_(*conditions))
        .order_by(Payment.created_at.desc())
        .offset(max(0, page) * max(1, page_size))
        .limit(page_size)
    )

    result = await session.execute(stmt)
    rows = result.all()

    out = []
    for p, username, uid in rows:
        out.append(
            {
                "payment_id": p.payment_id,
                "user_id": uid,
                "username": username,
                "amount": float(p.amount),
                "currency": p.currency,
                "description": p.description,
                "created_at": p.created_at,
            }
        )
    return out


async def count_campaigns(session: AsyncSession, *, only_active: bool = False) -> int:
    stmt = select(func.count(AdCampaign.ad_campaign_id))
    if only_active:
        stmt = stmt.where(AdCampaign.is_active == True)
    return int((await session.execute(stmt)).scalar() or 0)


async def list_campaigns_paged(
    session: AsyncSession, *, page: int, page_size: int, only_active: bool = False
) -> list[AdCampaign]:
    offset = max(0, page) * max(1, page_size)
    stmt = select(AdCampaign).order_by(AdCampaign.created_at.desc()).offset(offset).limit(page_size)
    if only_active:
        stmt = stmt.where(AdCampaign.is_active == True)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_totals(session: AsyncSession) -> dict[str, float]:
    # Total cost across all campaigns
    total_cost_stmt = select(func.coalesce(func.sum(AdCampaign.cost), 0.0))
    total_cost = float((await session.execute(total_cost_stmt)).scalar() or 0.0)

    # Total revenue from all attributed users (only first successful payment per user)
    attrib_subq = select(
        AdAttribution.user_id.label("user_id"),
        AdAttribution.first_start_at.label("first_start_at"),
    ).subquery()
    first_payment_subq = (
        select(func.min(Payment.payment_id).label("payment_id"))
        .where(
            Payment.status == "succeeded",
            Payment.funding_source == "external",
        )
        .group_by(Payment.user_id)
        .subquery()
    )
    revenue_stmt = (
        select(func.coalesce(func.sum(Payment.amount), 0.0))
        .select_from(Payment)
        .join(attrib_subq, Payment.user_id == attrib_subq.c.user_id)
        .join(first_payment_subq, Payment.payment_id == first_payment_subq.c.payment_id)
        .where(
            Payment.created_at >= attrib_subq.c.first_start_at,
        )
    )
    total_revenue = float((await session.execute(revenue_stmt)).scalar() or 0.0)

    return {"cost": total_cost, "revenue": total_revenue}


async def delete_campaign(session: AsyncSession, campaign_id: int) -> bool:
    """Delete ad campaign by id along with related attributions.

    Returns True if campaign existed and was deleted, False otherwise.
    """
    try:
        campaign = await session.get(AdCampaign, campaign_id)
        if not campaign:
            return False
        await session.delete(campaign)
        await session.flush()
        logger.info("AdCampaign deleted id=%s", campaign_id)
        return True
    except Exception as e:
        logger.exception("Failed to delete AdCampaign id=%s: %s", campaign_id, e)
        raise
