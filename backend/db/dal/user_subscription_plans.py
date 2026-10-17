"""Select one subscription plan per user for admin lists and statistics."""

from datetime import datetime
from typing import Any

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Subquery

from ..models import Subscription, User


def user_subscription_plans_sq(now: datetime, *, active_only: bool = False) -> Subquery:
    """Prefer live paid → trial → free plans, then the latest inactive history.

    A single row per user keeps list filters, pagination and dashboard totals
    consistent even when imported subscriptions overlap.
    """
    live = and_(Subscription.is_active.is_(True), Subscription.end_date > now)
    provider = func.lower(func.coalesce(Subscription.provider, ""))
    trial = or_(
        provider == "trial",
        func.upper(func.coalesce(Subscription.status_from_panel, "")) == "TRIAL",
    )
    priority = case((and_(provider != "", ~trial), 0), (trial, 1), else_=2)
    tariff_key = case(
        (func.trim(func.coalesce(Subscription.tariff_key, "")) == "", None),
        else_=Subscription.tariff_key,
    )
    ranked = select(
        Subscription.user_id.label("user_id"),
        Subscription.subscription_id.label("subscription_id"),
        tariff_key.label("tariff_key"),
        trial.label("is_trial"),
        live.label("is_active"),
        func.row_number()
        .over(
            partition_by=Subscription.user_id,
            order_by=(
                case((live, 0), else_=1),
                case((live, priority), else_=0),
                Subscription.end_date.desc(),
                Subscription.subscription_id.desc(),
            ),
        )
        .label("rn"),
    ).join(User, Subscription.user_id == User.user_id)
    if active_only:
        ranked = ranked.where(live)
    ranked_sq = ranked.subquery(name="ranked_user_subscription_plans")
    return select(ranked_sq).where(ranked_sq.c.rn == 1).subquery(name="user_subscription_plans")


async def get_user_subscription_plans(
    session: AsyncSession, user_ids: list[int], *, now: datetime
) -> dict[int, dict[str, Any]]:
    if not user_ids:
        return {}
    plans = user_subscription_plans_sq(now)
    result = await session.execute(select(plans).where(plans.c.user_id.in_(user_ids)))
    return {int(row.user_id): dict(row._mapping) for row in result.all()}


async def get_subscription_plan_tariff_keys(session: AsyncSession, *, now: datetime) -> list[str]:
    plans = user_subscription_plans_sq(now)
    result = await session.execute(
        select(plans.c.tariff_key)
        .where(plans.c.tariff_key.is_not(None), plans.c.is_trial.is_(False))
        .distinct()
        .order_by(plans.c.tariff_key)
    )
    return [str(key) for key in result.scalars().all()]


async def get_active_subscription_plan_counts(
    session: AsyncSession, *, now: datetime
) -> list[dict[str, Any]]:
    plans = user_subscription_plans_sq(now, active_only=True)
    # A trial's bound tariff must not split the separate trial segment.
    key = case((plans.c.is_trial.is_(True), None), else_=plans.c.tariff_key)
    result = await session.execute(
        select(
            plans.c.is_trial,
            key.label("tariff_key"),
            func.count(plans.c.user_id).label("active_users"),
        ).group_by(plans.c.is_trial, key)
    )
    return [dict(row._mapping) for row in result.all()]
