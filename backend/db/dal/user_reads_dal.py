"""Read-only user queries.

Split out of ``user_dal`` (which re-exports everything here for
compatibility); keep this module free of mutations.
"""

from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models import (
    LegacyReferralCode,
    Subscription,
    User,
    UserTelegramAvatar,
)


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    stmt = select(User).where(User.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_referrer_for_user(session: AsyncSession, user: User) -> User | None:
    referred_by_id = getattr(user, "referred_by_id", None)
    if referred_by_id is None:
        return None
    return await get_user_by_id(session, int(referred_by_id))


async def get_users_referred_by(
    session: AsyncSession,
    user_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[User]:
    safe_limit = max(1, min(500, int(limit or 50)))
    safe_offset = max(0, int(offset or 0))
    stmt = (
        select(User)
        .where(User.referred_by_id == user_id)
        .order_by(User.registration_date.desc().nullslast(), User.user_id.desc())
        .offset(safe_offset)
        .limit(safe_limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_users_referred_by(session: AsyncSession, user_id: int) -> int:
    stmt = select(func.count(User.user_id)).where(User.referred_by_id == user_id)
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    clean_username = username.lstrip("@").lower()
    stmt = select(User).where(func.lower(User.username) == clean_username)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    clean_email = (email or "").strip().lower()
    if not clean_email:
        return None
    stmt = select(User).where(func.lower(User.email) == clean_email)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_telegram_avatar(
    session: AsyncSession,
    user_id: int,
) -> UserTelegramAvatar | None:
    stmt = select(UserTelegramAvatar).where(UserTelegramAvatar.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_panel_uuid(session: AsyncSession, panel_uuid: str) -> User | None:
    stmt = select(User).where(User.panel_user_uuid == panel_uuid)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_referral_code(
    session: AsyncSession,
    referral_code: str,
    *,
    include_legacy: bool = False,
) -> User | None:
    normalized = referral_code.strip()
    if not normalized:
        return None

    stmt = select(User).where(User.referral_code == normalized)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user:
        return user

    upper_normalized = normalized.upper()
    if upper_normalized != normalized:
        stmt = select(User).where(User.referral_code == upper_normalized)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            return user

    if not include_legacy:
        return None

    stmt = (
        select(User)
        .join(LegacyReferralCode, LegacyReferralCode.user_id == User.user_id)
        .where(LegacyReferralCode.code == normalized, LegacyReferralCode.is_active == True)
        .limit(1)
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user:
        return user

    if upper_normalized != normalized:
        stmt = (
            select(User)
            .join(LegacyReferralCode, LegacyReferralCode.user_id == User.user_id)
            .where(
                LegacyReferralCode.code == upper_normalized,
                LegacyReferralCode.is_active == True,
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            return user

    return None


async def get_banned_users(session: AsyncSession) -> list[User]:
    """Get all banned users"""
    stmt = select(User).where(User.is_banned == True).order_by(User.registration_date.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_all_users_paginated(
    session: AsyncSession, *, page: int = 0, page_size: int = 15
) -> list[User]:
    """Return a slice of users ordered by newest registration first."""
    safe_page = max(page, 0)
    safe_page_size = max(page_size, 1)

    stmt = (
        select(User)
        .order_by(User.registration_date.desc())
        .offset(safe_page * safe_page_size)
        .limit(safe_page_size)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_all_users(session: AsyncSession) -> int:
    """Count total number of users."""
    result = await session.execute(select(func.count(User.user_id)))
    return result.scalar_one()


async def get_panel_user_uuids_for_user(
    session: AsyncSession,
    user_id: int,
    *,
    user: User | None = None,
) -> list[str]:
    """Return every Remnawave user UUID linked to a bot user.

    The canonical UUID normally lives on ``users.panel_user_uuid``, but older
    or partially-synced records can still have UUIDs only on subscription rows.
    """

    if user is None:
        user = await get_user_by_id(session, user_id)

    panel_uuids: list[str] = []
    seen: set[str] = set()

    def add_uuid(value: Any) -> None:
        panel_uuid = str(value or "").strip()
        if panel_uuid and panel_uuid not in seen:
            seen.add(panel_uuid)
            panel_uuids.append(panel_uuid)

    add_uuid(getattr(user, "panel_user_uuid", None))

    stmt = select(Subscription.panel_user_uuid).where(Subscription.user_id == user_id)
    result = await session.execute(stmt)
    for panel_uuid in result.scalars().all():
        add_uuid(panel_uuid)

    return panel_uuids
