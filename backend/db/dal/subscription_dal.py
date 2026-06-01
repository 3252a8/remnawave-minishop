import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, delete, func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from db.models import Subscription, SubscriptionNotification, User

INSTALL_SHARE_TOKEN_BYTES = 16


def _subscription_model_payload(sub_payload: Dict[str, Any]) -> Dict[str, Any]:
    model_columns = Subscription.__mapper__.columns.keys()
    filtered_payload = {key: value for key, value in sub_payload.items() if key in model_columns}
    ignored_keys = sorted(set(sub_payload) - set(filtered_payload))
    if ignored_keys:
        logging.warning("Ignoring unsupported subscription payload keys: %s", ignored_keys)
    return filtered_payload


async def get_active_subscription_by_user_id(
    session: AsyncSession, user_id: int, panel_user_uuid: Optional[str] = None
) -> Optional[Subscription]:
    stmt = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.is_active == True,
        Subscription.end_date > datetime.now(timezone.utc),
    )
    if panel_user_uuid:
        stmt = stmt.where(Subscription.panel_user_uuid == panel_user_uuid)
    stmt = stmt.order_by(Subscription.end_date.desc()).limit(1)
    result = await session.execute(stmt)
    return result.scalars().first()


async def get_subscription_by_panel_subscription_uuid(
    session: AsyncSession, panel_sub_uuid: str
) -> Optional[Subscription]:
    stmt = select(Subscription).where(Subscription.panel_subscription_uuid == panel_sub_uuid)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def normalize_install_share_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not re.fullmatch(r"[a-f0-9]{32}", token):
        return ""
    return token


async def get_subscription_by_install_share_token(
    session: AsyncSession,
    token: str,
) -> Optional[Subscription]:
    normalized = normalize_install_share_token(token)
    if not normalized:
        return None
    stmt = select(Subscription).where(Subscription.install_share_token == normalized)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def ensure_install_share_token(
    session: AsyncSession,
    subscription: Subscription,
) -> str:
    raw_existing = str(getattr(subscription, "install_share_token", "") or "").strip()
    existing = normalize_install_share_token(raw_existing)
    if existing:
        if existing != getattr(subscription, "install_share_token", None):
            subscription.install_share_token = existing
            await session.flush()
        return existing

    subscription_id = getattr(subscription, "subscription_id", None)
    for _attempt in range(10):
        token = secrets.token_hex(INSTALL_SHARE_TOKEN_BYTES)
        if await get_subscription_by_install_share_token(session, token):
            continue
        if subscription_id:
            result = await session.execute(
                update(Subscription)
                .where(
                    Subscription.subscription_id == subscription_id,
                    or_(
                        Subscription.install_share_token.is_(None),
                        Subscription.install_share_token == "",
                        Subscription.install_share_token == raw_existing,
                    ),
                )
                .values(install_share_token=token)
            )
            await session.flush()
            if result.rowcount:
                await session.refresh(subscription)
                return (
                    normalize_install_share_token(
                        getattr(subscription, "install_share_token", None)
                    )
                    or token
                )

            await session.refresh(subscription)
            raw_existing = str(getattr(subscription, "install_share_token", "") or "").strip()
            existing = normalize_install_share_token(raw_existing)
            if existing:
                return existing
            continue

        subscription.install_share_token = token
        await session.flush()
        await session.refresh(subscription)
        return token

    raise RuntimeError("Failed to generate a unique install share token")


async def get_active_subscriptions_for_user(
    session: AsyncSession, user_id: int
) -> List[Subscription]:
    """Get all active subscriptions for a user."""
    stmt = (
        select(Subscription)
        .where(Subscription.user_id == user_id, Subscription.is_active == True)
        .order_by(Subscription.end_date.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_subscription(
    session: AsyncSession, subscription_id: int, update_data: Dict[str, Any]
) -> Optional[Subscription]:
    sub = await session.get(Subscription, subscription_id)
    if sub:
        for key, value in update_data.items():
            setattr(sub, key, value)
        await session.flush()
        await session.refresh(sub)
    return sub


async def set_auto_renew(
    session: AsyncSession, subscription_id: int, enabled: bool
) -> Optional[Subscription]:
    """Toggle auto_renew_enabled for a subscription."""
    return await update_subscription(session, subscription_id, {"auto_renew_enabled": enabled})


async def set_user_subscriptions_cancelled_with_grace(
    session: AsyncSession, user_id: int, grace_days: int = 1
) -> int:
    """Mark all active user subscriptions as cancelled with a short grace period.

    Sets end_date to now + grace_days, status_from_panel to 'CANCELLED', and
    skip future notifications to reduce noise after cancellation.
    Returns number of updated rows.
    """
    from datetime import datetime, timedelta, timezone

    grace_end = datetime.now(timezone.utc) + timedelta(days=grace_days)
    stmt = (
        update(Subscription)
        .where(Subscription.user_id == user_id, Subscription.is_active == True)
        .values(
            end_date=grace_end,
            status_from_panel="CANCELLED",
            skip_notifications=True,
        )
    )
    result = await session.execute(stmt)
    return result.rowcount or 0


async def upsert_subscription(session: AsyncSession, sub_payload: Dict[str, Any]) -> Subscription:
    panel_sub_uuid = sub_payload.get("panel_subscription_uuid")
    if not panel_sub_uuid:
        raise ValueError("panel_subscription_uuid is required for upsert.")

    existing_sub = await get_subscription_by_panel_subscription_uuid(session, panel_sub_uuid)

    if existing_sub:
        logging.info(
            f"Updating existing subscription {existing_sub.subscription_id} by panel_sub_uuid {panel_sub_uuid}"  # noqa: E501
        )
        for key, value in _subscription_model_payload(sub_payload).items():
            setattr(existing_sub, key, value)
        await session.flush()
        await session.refresh(existing_sub)
        return existing_sub
    else:
        logging.info(f"Creating new subscription with panel_sub_uuid {panel_sub_uuid}")

        if sub_payload.get("user_id") is None and "panel_user_uuid" not in sub_payload:
            raise ValueError("For a new subscription without user_id, panel_user_uuid is required.")
        if "end_date" not in sub_payload:
            raise ValueError("Missing 'end_date' for new subscription.")
        if sub_payload.get("user_id") is not None:
            from .user_dal import get_user_by_id

            user = await get_user_by_id(session, sub_payload["user_id"])
            if not user:
                raise ValueError(
                    f"User {sub_payload['user_id']} not found for new subscription with panel_uuid {panel_sub_uuid}."  # noqa: E501
                )

        new_sub = Subscription(**_subscription_model_payload(sub_payload))
        session.add(new_sub)
        await session.flush()
        await session.refresh(new_sub)
        return new_sub


async def deactivate_other_active_subscriptions(
    session: AsyncSession, panel_user_uuid: str, current_panel_subscription_uuid: Optional[str]
) -> None:
    stmt = (
        update(Subscription)
        .where(
            Subscription.panel_user_uuid == panel_user_uuid,
            Subscription.is_active == True,
        )
        .values(is_active=False, status_from_panel="INACTIVE_BY_BOT_SYNC")
    )
    if current_panel_subscription_uuid:
        stmt = stmt.where(Subscription.panel_subscription_uuid != current_panel_subscription_uuid)

    result = await session.execute(stmt)
    if result.rowcount > 0:
        logging.info(
            f"Deactivated {result.rowcount} other active subscriptions for panel_user_uuid {panel_user_uuid}."  # noqa: E501
        )


async def deactivate_all_user_subscriptions(session: AsyncSession, user_id: int) -> int:
    stmt = (
        update(Subscription)
        .where(Subscription.user_id == user_id, Subscription.is_active == True)
        .values(is_active=False, status_from_panel="INACTIVE_USER_NOT_FOUND")
    )
    result = await session.execute(stmt)
    if result.rowcount > 0:
        logging.info(
            f"Deactivated {result.rowcount} subscriptions for user {user_id} due to missing panel user."  # noqa: E501
        )
    return result.rowcount


async def delete_all_user_subscriptions(session: AsyncSession, user_id: int) -> int:
    """Completely delete all user subscriptions."""
    stmt = delete(Subscription).where(Subscription.user_id == user_id)
    result = await session.execute(stmt)
    if result.rowcount > 0:
        logging.info(
            f"Deleted {result.rowcount} subscription records for user {user_id} for trial reset."
        )
    return result.rowcount


async def update_subscription_end_date(
    session: AsyncSession, subscription_id: int, new_end_date: datetime
) -> Optional[Subscription]:

    return await update_subscription(
        session,
        subscription_id,
        {
            "end_date": new_end_date,
            "last_notification_sent": None,
            "is_active": True,
            "status_from_panel": "ACTIVE_EXTENDED_BY_BOT",
        },
    )


async def has_any_subscription_for_user(session: AsyncSession, user_id: int) -> bool:
    stmt = select(Subscription.subscription_id).where(Subscription.user_id == user_id).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def has_trial_blocking_subscription_for_user(session: AsyncSession, user_id: int) -> bool:
    now_utc = datetime.now(timezone.utc)
    reset_at = (
        select(User.trial_eligibility_reset_at).where(User.user_id == user_id).scalar_subquery()
    )
    subscription_anchor = func.coalesce(Subscription.start_date, Subscription.end_date)
    stmt = (
        select(Subscription.subscription_id)
        .where(
            Subscription.user_id == user_id,
            or_(
                reset_at.is_(None),
                and_(Subscription.is_active == True, Subscription.end_date > now_utc),
                subscription_anchor > reset_at,
            ),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def get_subscriptions_near_expiration(
    session: AsyncSession, days_threshold: int
) -> List[Subscription]:
    now_utc = datetime.now(timezone.utc)
    threshold_date = now_utc + timedelta(days=days_threshold)

    stmt = (
        select(Subscription)
        .join(Subscription.user)
        .where(
            Subscription.is_active == True,
            Subscription.skip_notifications == False,
            Subscription.end_date > now_utc,
            Subscription.end_date <= threshold_date,
            or_(
                Subscription.last_notification_sent == None,
                func.date(Subscription.last_notification_sent) < func.date(now_utc),
            ),
        )
        .order_by(Subscription.end_date.asc())
        .options(selectinload(Subscription.user))
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_subscription_notification_time(
    session: AsyncSession, subscription_id: int, notification_time: datetime
) -> Optional[Subscription]:
    return await update_subscription(
        session, subscription_id, {"last_notification_sent": notification_time}
    )


async def has_subscription_notification(
    session: AsyncSession,
    subscription_id: int,
    notification_key: str,
) -> bool:
    stmt = (
        select(SubscriptionNotification.notification_id)
        .where(
            SubscriptionNotification.subscription_id == subscription_id,
            SubscriptionNotification.notification_key == notification_key,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def record_subscription_notification(
    session: AsyncSession,
    subscription_id: int,
    notification_key: str,
    *,
    sent_at: Optional[datetime] = None,
) -> None:
    if sent_at is None:
        sent_at = datetime.now(timezone.utc)
    existing = await has_subscription_notification(session, subscription_id, notification_key)
    if existing:
        return
    session.add(
        SubscriptionNotification(
            subscription_id=subscription_id,
            notification_key=notification_key,
            sent_at=sent_at,
        )
    )
    await update_subscription_notification_time(session, subscription_id, sent_at)


async def find_subscription_for_notification_update(
    session: AsyncSession, user_id: int, subscription_end_date_to_match: datetime
) -> Optional[Subscription]:

    if subscription_end_date_to_match.tzinfo is None:
        subscription_end_date_to_match = subscription_end_date_to_match.replace(tzinfo=timezone.utc)

    stmt = (
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.is_active == True,
            Subscription.end_date >= subscription_end_date_to_match - timedelta(seconds=1),
            Subscription.end_date <= subscription_end_date_to_match + timedelta(seconds=1),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
