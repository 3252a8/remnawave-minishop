"""Atomic observations; checked_at is observation time, never processing time."""

from datetime import datetime

from sqlalchemy import and_, case, func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User


async def record_delivery_state(
    session: AsyncSession,
    user_id: int,
    status: str,
    observed_at: datetime,
    *,
    telegram_id: int | None = None,
    update_id: int = 0,
) -> User | None:
    # Event ids only break ties within one timestamp, never across Telegram's
    # week-long update-id reset. Equal-time local observations prefer denial.
    rank = {"unknown": 0, "enabled": 1, "needs_start": 2, "blocked": 3}[status]
    order = update_id * 10 + rank
    fresh = or_(
        User.telegram_notifications_checked_at.is_(None),
        User.telegram_notifications_checked_at < observed_at,
        and_(
            User.telegram_notifications_checked_at == observed_at,
            User.telegram_notifications_observation_order < order,
        ),
    )
    stmt = update(User).where(User.user_id == user_id, fresh)
    if telegram_id is not None:
        stmt = stmt.where(User.telegram_id == telegram_id)
    values: dict[str, object] = {
        "telegram_notifications_status": status,
        "telegram_notifications_checked_at": observed_at,
        "telegram_notifications_observation_order": order,
    }
    if status == "enabled":
        values["telegram_notifications_enabled_at"] = case(
            (User.telegram_notifications_status == status, User.telegram_notifications_enabled_at),
            else_=observed_at,
        )
        values["telegram_notifications_blocked_at"] = None
    elif status == "blocked":
        values["telegram_notifications_blocked_at"] = case(
            (User.telegram_notifications_status == status, User.telegram_notifications_blocked_at),
            else_=observed_at,
        )
    result = await session.execute(
        stmt.values(**values).returning(User).execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def record_channel_membership(
    session: AsyncSession,
    user_id: int,
    telegram_id: int,
    channel_id: int,
    is_member: bool,
    observed_at: datetime,
    *,
    update_id: int = 0,
) -> User | None:
    order = update_id * 10 + (1 if is_member else 2)
    result = await session.execute(
        update(User)
        .where(
            User.user_id == user_id,
            User.telegram_id == telegram_id,
            or_(
                User.channel_subscription_checked_at.is_(None),
                User.channel_subscription_checked_at < observed_at,
                and_(
                    User.channel_subscription_checked_at == observed_at,
                    func.coalesce(User.channel_subscription_observation_order, 0) < order,
                ),
            ),
        )
        .values(
            channel_subscription_verified=is_member,
            channel_subscription_checked_at=observed_at,
            channel_subscription_verified_for=channel_id,
            channel_subscription_observation_order=order,
        )
        .returning(User)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()
