import logging
from typing import Any

from sqlalchemy import and_, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models import AdAttribution, AdCampaign, Payment
from ._sqlalchemy import rowcount


async def create_campaign(
    session: AsyncSession, *, source: str, start_param: str, cost: float
) -> AdCampaign:
    existing = await get_campaign_by_start_param(session, start_param)
    if existing:
        raise ValueError("ad_campaign_start_param_exists")

    campaign = AdCampaign(source=source, start_param=start_param, cost=float(cost))
    session.add(campaign)
    await session.flush()
    await session.refresh(campaign)
    logging.info(
        f"AdCampaign created id={campaign.ad_campaign_id}, source={source}, start={start_param}, cost={cost}"  # noqa: E501
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


async def list_campaigns(session: AsyncSession, *, only_active: bool = False) -> list[AdCampaign]:
    stmt = select(AdCampaign).order_by(AdCampaign.created_at.desc())
    if only_active:
        stmt = stmt.where(AdCampaign.is_active == True)
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
    logging.info(f"AdAttribution created for user {user_id} -> campaign {campaign_id}")
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
    # Starts (attributed users)
    starts_stmt = select(func.count(AdAttribution.user_id)).where(
        AdAttribution.ad_campaign_id == campaign_id
    )
    starts = (await session.execute(starts_stmt)).scalar() or 0

    # Trials
    trials_stmt = select(func.count(AdAttribution.user_id)).where(
        and_(
            AdAttribution.ad_campaign_id == campaign_id,
            AdAttribution.trial_activated_at.is_not(None),
        )
    )
    trials = (await session.execute(trials_stmt)).scalar() or 0

    # Payers (unique users with succeeded payments)
    attrib_subq = (
        select(
            AdAttribution.user_id.label("user_id"),
            AdAttribution.first_start_at.label("first_start_at"),
        )
        .where(AdAttribution.ad_campaign_id == campaign_id)
        .subquery()
    )
    payers_stmt = (
        select(func.count(func.distinct(Payment.user_id)))
        .select_from(Payment)
        .join(attrib_subq, Payment.user_id == attrib_subq.c.user_id)
        .where(
            and_(
                Payment.status == "succeeded",
                Payment.created_at >= attrib_subq.c.first_start_at,
            )
        )
    )
    payers = (await session.execute(payers_stmt)).scalar() or 0

    # Revenue sum
    revenue_stmt = (
        select(func.coalesce(func.sum(Payment.amount), 0.0))
        .select_from(Payment)
        .join(attrib_subq, Payment.user_id == attrib_subq.c.user_id)
        .where(
            and_(
                Payment.status == "succeeded",
                Payment.created_at >= attrib_subq.c.first_start_at,
            )
        )
    )
    revenue = float((await session.execute(revenue_stmt)).scalar() or 0.0)

    return {
        "starts": int(starts),
        "trials": int(trials),
        "payers": int(payers),
        "revenue": revenue,
    }


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

    # Total revenue from all attributed users (unique users counted across all campaigns)
    attrib_subq = select(
        AdAttribution.user_id.label("user_id"),
        AdAttribution.first_start_at.label("first_start_at"),
    ).subquery()
    revenue_stmt = (
        select(func.coalesce(func.sum(Payment.amount), 0.0))
        .select_from(Payment)
        .join(attrib_subq, Payment.user_id == attrib_subq.c.user_id)
        .where(
            and_(
                Payment.status == "succeeded",
                Payment.created_at >= attrib_subq.c.first_start_at,
            )
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
        logging.info(f"AdCampaign deleted id={campaign_id}")
        return True
    except Exception as e:
        logging.error(f"Failed to delete AdCampaign id={campaign_id}: {e}", exc_info=True)
        raise
