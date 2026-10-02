import logging
from typing import Any

from sqlalchemy import and_, func, or_, update
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
    from bot.services.advertising.validation import money, start_code

    start_param = start_code(start_param)
    cost = float(money(cost))
    from bot.services.advertising.locking import lock_advertising

    await lock_advertising(session, "codes")
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    from db.advertising_models import AdLink

    factory = sqlite_insert if session.get_bind().dialect.name == "sqlite" else pg_insert
    link = (await session.execute(select(AdLink.id).where(AdLink.code == start_param))).first()
    if link:
        raise ValueError("ad_campaign_start_param_exists")
    ident = (
        await session.execute(
            factory(AdCampaign)
            .values(
                source=source,
                name=source,
                start_param=start_param,
                cost=cost,
                advertiser_id=advertiser_id,
            )
            .on_conflict_do_nothing(index_elements=[AdCampaign.start_param])
            .returning(AdCampaign.ad_campaign_id)
        )
    ).scalar_one_or_none()
    if ident is None:
        raise ValueError("ad_campaign_start_param_exists")
    campaign = await session.get(AdCampaign, ident)
    if campaign is None:
        raise RuntimeError("Campaign could not be loaded after insertion")
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
        .where(AdCampaign.ad_campaign_id == campaign_id, AdCampaign.archived_at.is_(None))
        .values(is_active=is_active)
    )
    result = await session.execute(stmt)
    return rowcount(result) > 0


async def ensure_attribution(
    session: AsyncSession, *, user_id: int, campaign_id: int
) -> AdAttribution:
    from bot.services.advertising.capture import insert_once

    await insert_once(
        session,
        AdAttribution,
        {"user_id": user_id, "ad_campaign_id": campaign_id},
        [AdAttribution.user_id],
    )
    result = await get_attribution_for_user(session, user_id)
    if result is None:
        raise RuntimeError("Attribution insert did not produce a row")
    return result


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
    from .ad_statistics import campaign_statistics

    return (await campaign_statistics(session, [campaign_id]))[campaign_id]


async def reset_campaign_stats(session: AsyncSession, campaign_id: int) -> bool:
    stmt = (
        update(AdCampaign)
        .where(AdCampaign.ad_campaign_id == campaign_id)
        .values(stats_reset_at=func.now())
    )
    result = await session.execute(stmt)
    return rowcount(result) > 0


async def list_campaign_purchases(
    session: AsyncSession, campaign_id: int, *, page: int = 0, page_size: int = 50
) -> list[dict[str, Any]]:
    from db.advertising_models import AdPurchaseAttribution
    from db.models import User

    from .ad_statistics import payment_campaign

    campaign = await session.get(AdCampaign, campaign_id)
    if campaign is None:
        return []
    conditions = [
        payment_campaign() == campaign_id,
        Payment.status.in_(("succeeded", "refunded", "reversed")),
    ]
    if campaign.stats_reset_at:
        conditions.append(AdAttribution.first_start_at >= campaign.stats_reset_at)
    conditions.append(
        or_(
            AdPurchaseAttribution.payment_id.is_not(None),
            Payment.created_at >= AdAttribution.first_start_at,
        )
    )
    statement = (
        select(Payment, User.username, User.user_id, AdPurchaseAttribution)
        .outerjoin(AdPurchaseAttribution, AdPurchaseAttribution.payment_id == Payment.payment_id)
        .outerjoin(AdAttribution, AdAttribution.user_id == Payment.user_id)
        .join(User, Payment.user_id == User.user_id)
        .where(*conditions)
        .order_by(Payment.created_at.desc(), Payment.payment_id.desc())
        .offset(max(0, page) * min(100, max(1, page_size)))
        .limit(min(100, max(1, page_size)))
    )
    rows = (await session.execute(statement)).all()
    return [
        {
            "payment_id": p.payment_id,
            "user_id": uid,
            "username": username,
            "amount": float(p.amount),
            "currency": p.currency,
            "description": p.description,
            "created_at": p.created_at,
            "status": p.status,
            "funding_source": p.funding_source,
            "sale_mode": p.sale_mode,
            "evidence": decision.evidence if decision else "legacy_bot_start",
            "first_product_purchase": decision.first_product_purchase if decision else None,
        }
        for p, username, uid, decision in rows
    ]


async def count_campaign_purchases(session: AsyncSession, campaign_id: int) -> int:
    from db.advertising_models import AdPurchaseAttribution

    from .ad_statistics import payment_campaign

    statement = (
        select(func.count(Payment.payment_id))
        .outerjoin(AdPurchaseAttribution, AdPurchaseAttribution.payment_id == Payment.payment_id)
        .outerjoin(AdAttribution, AdAttribution.user_id == Payment.user_id)
        .join(AdCampaign, AdCampaign.ad_campaign_id == payment_campaign())
        .where(
            payment_campaign() == campaign_id,
            Payment.status.in_(("succeeded", "refunded", "reversed")),
            or_(
                AdPurchaseAttribution.payment_id.is_not(None),
                Payment.created_at >= AdAttribution.first_start_at,
            ),
            or_(
                AdCampaign.stats_reset_at.is_(None),
                AdAttribution.first_start_at >= AdCampaign.stats_reset_at,
            ),
        )
    )
    return int((await session.execute(statement)).scalar() or 0)


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
    from .ad_statistics import campaign_statistics

    campaigns = await list_campaigns(session)
    stats = await campaign_statistics(session, [int(c.ad_campaign_id) for c in campaigns])
    return {
        "cost": sum(float(c.cost or 0) for c in campaigns if c.archived_at is None),
        "revenue": sum(float(item["revenue"]) for item in stats.values()),
    }


async def delete_campaign(session: AsyncSession, campaign_id: int) -> bool:
    campaign = await session.get(AdCampaign, campaign_id)
    if campaign is None:
        return False
    campaign.archived_at = func.now()
    campaign.is_active = False
    await session.flush()
    return True
