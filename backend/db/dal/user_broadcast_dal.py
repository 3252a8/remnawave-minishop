# SQLAlchemy legacy Column declarations expose instance attributes as Column[T]
# to mypy; this DAL intentionally reads loaded ORM instances.
# mypy: disable-error-code="assignment,arg-type,operator"

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, case, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import aliased

from ..models import Payment, Subscription, User


async def get_all_active_user_ids_for_broadcast(session: AsyncSession) -> list[int]:
    stmt = select(User.user_id).where(User.is_banned == False)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_all_active_users_for_broadcast(session: AsyncSession) -> int:
    stmt = select(func.count(User.user_id)).where(User.is_banned == False)
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def get_all_users_with_panel_uuid(session: AsyncSession) -> list[User]:
    stmt = select(User).where(User.panel_user_uuid.is_not(None))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_enhanced_user_statistics(session: AsyncSession) -> dict[str, Any]:
    """Get comprehensive user statistics including active users, trial users, etc."""
    from datetime import datetime

    # Use timezone-aware UTC to avoid naive/aware comparison issues in SQL queries
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    user_counts_stmt = select(
        func.count(User.user_id),
        func.coalesce(func.sum(case((User.is_banned == True, 1), else_=0)), 0),
        func.coalesce(func.sum(case((User.registration_date >= today_start, 1), else_=0)), 0),
        func.coalesce(func.sum(case((User.referred_by_id.is_not(None), 1), else_=0)), 0),
    )
    user_counts = (await session.execute(user_counts_stmt)).one()
    total_users = int(user_counts[0] or 0)
    banned_users = int(user_counts[1] or 0)
    active_today = int(user_counts[2] or 0)
    referral_users = int(user_counts[3] or 0)

    provider_value = func.lower(func.coalesce(Subscription.provider, ""))
    panel_status_value = func.upper(func.coalesce(Subscription.status_from_panel, ""))
    trial_subscription_condition = or_(
        provider_value == "trial",
        panel_status_value == "TRIAL",
    )
    paid_subscription_condition = and_(
        provider_value != "",
        provider_value != "trial",
        panel_status_value != "TRIAL",
    )
    free_subscription_condition = and_(
        provider_value == "",
        panel_status_value != "TRIAL",
    )

    active_subscription_flags_sq = (
        select(
            Subscription.user_id.label("user_id"),
            func.max(case((paid_subscription_condition, 1), else_=0)).label(
                "has_paid_subscription"
            ),
            func.max(case((trial_subscription_condition, 1), else_=0)).label(
                "has_trial_subscription"
            ),
            func.max(case((free_subscription_condition, 1), else_=0)).label(
                "has_free_subscription"
            ),
        )
        .join(User, Subscription.user_id == User.user_id)
        .where(
            and_(
                Subscription.is_active == True,
                Subscription.end_date > now,
            )
        )
        .group_by(Subscription.user_id)
        .subquery()
    )

    subscription_counts_stmt = select(
        func.count(active_subscription_flags_sq.c.user_id),
        func.coalesce(func.sum(active_subscription_flags_sq.c.has_paid_subscription), 0),
        func.coalesce(
            func.sum(
                case(
                    (
                        active_subscription_flags_sq.c.has_paid_subscription == 0,
                        active_subscription_flags_sq.c.has_trial_subscription,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
        func.coalesce(
            func.sum(
                case(
                    (
                        and_(
                            active_subscription_flags_sq.c.has_paid_subscription == 0,
                            active_subscription_flags_sq.c.has_trial_subscription == 0,
                        ),
                        active_subscription_flags_sq.c.has_free_subscription,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
    )
    subscription_counts = (await session.execute(subscription_counts_stmt)).one()
    active_subscription_users = int(subscription_counts[0] or 0)
    paid_subs_users = int(subscription_counts[1] or 0)
    trial_users = int(subscription_counts[2] or 0)
    free_subscription_users = int(subscription_counts[3] or 0)

    inactive_users = total_users - active_subscription_users
    expired_subscription_users = await count_users_with_expired_subscription(session)

    return {
        "total_users": total_users,
        "banned_users": banned_users,
        "active_today": active_today,
        "active_subscriptions": active_subscription_users,
        "paid_subscriptions": paid_subs_users,
        "trial_users": trial_users,
        "free_subscription_users": free_subscription_users,
        "inactive_users": max(0, inactive_users),
        "expired_subscription_users": expired_subscription_users,
        "referral_users": referral_users,
    }


async def get_user_ids_with_active_subscription(session: AsyncSession) -> list[int]:
    """Return non-banned user IDs who have any active subscription."""
    from datetime import datetime

    now = datetime.now(UTC)

    stmt = (
        select(func.distinct(Subscription.user_id))
        .join(User, Subscription.user_id == User.user_id)
        .where(
            and_(
                User.is_banned == False,
                Subscription.is_active == True,
                Subscription.end_date > now,
            )
        )
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_users_with_active_subscription_for_broadcast(session: AsyncSession) -> int:
    """Count non-banned users who have any active subscription."""
    from datetime import datetime

    now = datetime.now(UTC)

    stmt = (
        select(func.count(func.distinct(Subscription.user_id)))
        .join(User, Subscription.user_id == User.user_id)
        .where(
            and_(
                User.is_banned == False,
                Subscription.is_active == True,
                Subscription.end_date > now,
            )
        )
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def get_user_ids_without_active_subscription(session: AsyncSession) -> list[int]:
    """Return non-banned user IDs who do NOT have any active subscription."""
    from datetime import datetime

    now = datetime.now(UTC)

    active_subs = aliased(Subscription)

    stmt = (
        select(User.user_id)
        .outerjoin(
            active_subs,
            and_(
                active_subs.user_id == User.user_id,
                active_subs.is_active == True,
                active_subs.end_date > now,
            ),
        )
        .where(
            and_(
                User.is_banned == False,
                active_subs.user_id.is_(None),
            )
        )
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_users_without_active_subscription_for_broadcast(session: AsyncSession) -> int:
    """Count non-banned users who do NOT have any active subscription."""
    from datetime import datetime

    now = datetime.now(UTC)

    stmt = select(func.count(User.user_id)).where(
        User.is_banned == False,
        ~_active_subscription_exists_for_user(now),
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def get_user_ids_without_any_subscription(session: AsyncSession) -> list[int]:
    """Return non-banned user IDs who never had any subscription or trial.

    These are users who registered but have no ``Subscription`` rows at all —
    no active, no expired and no trial history. In other words, accounts that
    signed up and never did anything.
    """
    any_sub = aliased(Subscription)

    stmt = (
        select(User.user_id)
        .outerjoin(any_sub, any_sub.user_id == User.user_id)
        .where(
            and_(
                User.is_banned == False,
                any_sub.user_id.is_(None),
            )
        )
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_users_without_any_subscription_for_broadcast(session: AsyncSession) -> int:
    """Count non-banned users who never had any subscription or trial."""
    any_sub = aliased(Subscription)

    stmt = (
        select(func.count(User.user_id))
        .outerjoin(any_sub, any_sub.user_id == User.user_id)
        .where(
            and_(
                User.is_banned == False,
                any_sub.user_id.is_(None),
            )
        )
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


def _expired_subscription_exists_for_user(now: datetime) -> Any:
    expired_subs = aliased(Subscription)
    normalized_status = func.lower(func.coalesce(expired_subs.status_from_panel, ""))
    blank_status = or_(
        expired_subs.status_from_panel.is_(None),
        expired_subs.status_from_panel == "",
    )
    expired_condition = or_(
        normalized_status == "expired",
        blank_status & expired_subs.is_active.is_(False),
        expired_subs.end_date <= now,
    )

    return (
        select(expired_subs.subscription_id)
        .where(expired_subs.user_id == User.user_id, expired_condition)
        .exists()
    )


def _active_subscription_exists_for_user(now: datetime) -> Any:
    active_subs = aliased(Subscription)
    return (
        select(active_subs.subscription_id)
        .where(
            active_subs.user_id == User.user_id,
            active_subs.is_active == True,
            active_subs.end_date > now,
        )
        .exists()
    )


async def count_users_with_expired_subscription(session: AsyncSession) -> int:
    """Count users who have an expired subscription and no currently active subscription."""
    from datetime import datetime

    now = datetime.now(UTC)
    stmt = select(func.count(User.user_id)).where(
        _expired_subscription_exists_for_user(now),
        ~_active_subscription_exists_for_user(now),
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def count_users_with_expired_subscription_for_broadcast(session: AsyncSession) -> int:
    """Count non-banned users with an expired subscription and no active one."""
    from datetime import datetime

    now = datetime.now(UTC)
    stmt = select(func.count(User.user_id)).where(
        User.is_banned == False,
        _expired_subscription_exists_for_user(now),
        ~_active_subscription_exists_for_user(now),
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def get_user_ids_with_expired_subscription(session: AsyncSession) -> list[int]:
    """Return non-banned user IDs with an expired subscription and no active one."""
    from datetime import datetime

    now = datetime.now(UTC)
    stmt = select(User.user_id).where(
        User.is_banned == False,
        _expired_subscription_exists_for_user(now),
        ~_active_subscription_exists_for_user(now),
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_top_users_by_traffic_used(
    session: AsyncSession,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return top users by total used traffic across all subscriptions."""
    safe_limit = max(1, limit)

    total_traffic_used = func.coalesce(func.sum(Subscription.traffic_used_bytes), 0)

    stmt = (
        select(
            User.user_id,
            User.username,
            User.first_name,
            total_traffic_used.label("traffic_used_bytes"),
        )
        .join(Subscription, Subscription.user_id == User.user_id, isouter=True)
        .group_by(User.user_id, User.username, User.first_name)
        .having(total_traffic_used > 0)
        .order_by(desc("traffic_used_bytes"), User.user_id.asc())
        .limit(safe_limit)
    )

    result = await session.execute(stmt)
    return [dict(row._mapping) for row in result]


async def get_top_users_by_lifetime_traffic_used(
    session: AsyncSession,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return top users by lifetime used traffic from panel data."""
    safe_limit = max(1, limit)
    lifetime_used = func.coalesce(User.lifetime_used_traffic_bytes, 0)

    stmt = (
        select(
            User.user_id,
            User.username,
            User.first_name,
            lifetime_used.label("lifetime_used_traffic_bytes"),
        )
        .where(lifetime_used > 0)
        .order_by(desc("lifetime_used_traffic_bytes"), User.user_id.asc())
        .limit(safe_limit)
    )

    result = await session.execute(stmt)
    return [dict(row._mapping) for row in result]


async def get_top_users_by_referrals_count(
    session: AsyncSession,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return top users by number of invited users."""
    safe_limit = max(1, limit)
    referred_user = aliased(User)

    invited_count = func.count(referred_user.user_id)

    stmt = (
        select(
            User.user_id,
            User.username,
            User.first_name,
            invited_count.label("invited_count"),
        )
        .join(referred_user, referred_user.referred_by_id == User.user_id, isouter=True)
        .group_by(User.user_id, User.username, User.first_name)
        .having(invited_count > 0)
        .order_by(desc("invited_count"), User.user_id.asc())
        .limit(safe_limit)
    )

    result = await session.execute(stmt)
    return [dict(row._mapping) for row in result]


async def get_top_users_by_referral_revenue(
    session: AsyncSession,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return top users by total revenue brought by all invited users."""
    safe_limit = max(1, limit)
    referred_user = aliased(User)

    referral_revenue = func.coalesce(func.sum(Payment.amount), 0.0)

    stmt = (
        select(
            User.user_id,
            User.username,
            User.first_name,
            referral_revenue.label("referral_revenue"),
        )
        .join(referred_user, referred_user.referred_by_id == User.user_id, isouter=True)
        .join(
            Payment,
            and_(
                Payment.user_id == referred_user.user_id,
                Payment.status == "succeeded",
            ),
            isouter=True,
        )
        .group_by(User.user_id, User.username, User.first_name)
        .having(referral_revenue > 0)
        .order_by(desc("referral_revenue"), User.user_id.asc())
        .limit(safe_limit)
    )

    result = await session.execute(stmt)
    return [dict(row._mapping) for row in result]
