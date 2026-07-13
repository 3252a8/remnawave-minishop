# SQLAlchemy legacy Column declarations expose instance attributes as Column[T]
# to mypy; this DAL intentionally mutates loaded ORM instances.
# mypy: disable-error-code="assignment,arg-type,operator"

import logging
import secrets
import string
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from bot.infra import events
from bot.infra.event_payloads import UserRegisteredPayload

from ..models import (
    User,
    UserTelegramAvatar,
)
from ._sqlalchemy import rowcount
from .user_broadcast_dal import (  # noqa: F401
    count_all_active_users_for_broadcast,
    count_users_with_active_subscription_for_broadcast,
    count_users_with_expired_subscription,
    count_users_with_expired_subscription_for_broadcast,
    count_users_without_active_subscription_for_broadcast,
    count_users_without_any_subscription_for_broadcast,
    get_all_active_user_ids_for_broadcast,
    get_all_users_with_panel_uuid,
    get_email_recipients_for_broadcast,
    get_enhanced_user_statistics,
    get_telegram_recipients_for_broadcast,
    get_top_users_by_lifetime_traffic_used,
    get_top_users_by_referral_revenue,
    get_top_users_by_referrals_count,
    get_top_users_by_traffic_used,
    get_user_ids_with_active_subscription,
    get_user_ids_with_expired_subscription,
    get_user_ids_without_active_subscription,
    get_user_ids_without_any_subscription,
)
from .user_merge_dal import (  # noqa: F401
    UserMergeConflictError,
    delete_user_and_relations,
    merge_users,
)
from .user_reads_dal import (  # noqa: F401
    count_all_users,
    count_users_referred_by,
    get_all_users_paginated,
    get_banned_users,
    get_panel_user_uuids_for_user,
    get_referrer_for_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_panel_uuid,
    get_user_by_referral_code,
    get_user_by_telegram_id,
    get_user_by_username,
    get_user_telegram_avatar,
    get_users_referred_by,
)

logger = logging.getLogger(__name__)

REFERRAL_CODE_ALPHABET = string.ascii_uppercase + string.digits
REFERRAL_CODE_LENGTH = 9
MAX_REFERRAL_CODE_ATTEMPTS = 25
MAX_EMAIL_USER_ID_ATTEMPTS = 25


def _generate_referral_code_candidate() -> str:
    return "".join(secrets.choice(REFERRAL_CODE_ALPHABET) for _ in range(REFERRAL_CODE_LENGTH))


async def _referral_code_exists(session: AsyncSession, code: str) -> bool:
    stmt = select(User.user_id).where(User.referral_code == code)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def generate_unique_referral_code(session: AsyncSession) -> str:
    """
    Generate a unique referral code consisting of uppercase alphanumeric characters.
    Retries until a free code is found or raises RuntimeError after exceeding attempts.
    """
    for _ in range(MAX_REFERRAL_CODE_ATTEMPTS):
        candidate = _generate_referral_code_candidate()
        if not await _referral_code_exists(session, candidate):
            return candidate
    raise RuntimeError("Failed to generate a unique referral code after several attempts.")


async def generate_unique_email_user_id(session: AsyncSession) -> int:
    for _ in range(MAX_EMAIL_USER_ID_ATTEMPTS):
        candidate = -(secrets.randbelow(9_000_000_000_000_000) + 1)
        if not await get_user_by_id(session, candidate):
            return candidate
    raise RuntimeError("Failed to generate a unique email user id after several attempts.")


async def ensure_referral_code(session: AsyncSession, user: User) -> str:
    """
    Ensure the provided user has a referral code, generating and persisting it if missing.
    Returns the existing or newly generated code.
    """
    if user.referral_code:
        normalized = str(user.referral_code).strip()
        if normalized != user.referral_code:
            user.referral_code = normalized
            await session.flush()
            await session.refresh(user)
        return normalized

    referral_code = await generate_unique_referral_code(session)
    user.referral_code = referral_code
    await session.flush()
    await session.refresh(user)
    return referral_code


async def lock_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    """Serialize entitlement changes for one user inside the current transaction.

    ``populate_existing`` matters when the caller loaded the user before waiting
    for the lock: one-time markers changed by the previous transaction must be
    visible after the wait instead of coming from SQLAlchemy's identity map.
    """
    stmt = (
        select(User)
        .where(User.user_id == user_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


## Removed unused generic get_user helper to keep DAL explicit and simple


async def create_user(
    session: AsyncSession,
    user_data: dict[str, Any],
    *,
    registered_via: str | None = "auto",
) -> tuple[User, bool]:
    """Create a user if not exists in a race-safe way.

    Returns a tuple of (user, created_flag).

    When a new row is created, a ``user.registered`` domain event is emitted.
    ``registered_via`` labels the registration source in the event payload:
    ``"auto"`` (default) derives ``telegram``/``email``/``unknown`` from the
    payload, an explicit string (e.g. ``"panel_sync"``) is used as-is, and
    ``None`` suppresses the event for technical row creation that is not a
    real registration (e.g. the intermediate row built during account
    linking, or bulk migration imports).
    """

    if "registration_date" not in user_data:
        user_data["registration_date"] = datetime.now(UTC)

    if not user_data.get("referral_code"):
        user_data["referral_code"] = await generate_unique_referral_code(session)
    else:
        user_data["referral_code"] = user_data["referral_code"].strip()

    # Use PostgreSQL upsert to avoid IntegrityError on concurrent inserts
    stmt = (
        pg_insert(User)
        .values(**user_data)
        .on_conflict_do_nothing(index_elements=[User.user_id])
        .returning(User.user_id)
    )

    result = await session.execute(stmt)
    inserted_row = result.first()
    created = inserted_row is not None

    # Fetch the user (inserted just now or pre-existing)
    user_id: int = user_data["user_id"]
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise RuntimeError(f"Failed to load user {user_id} after upsert.")

    if created:
        logger.info(
            "New user %s created in DAL. Referred by: %s.",
            user.user_id,
            user.referred_by_id or "N/A",
        )
        if registered_via == "auto":
            if user_data.get("telegram_id"):
                registered_via = "telegram"
            elif user_data.get("email"):
                registered_via = "email"
            else:
                registered_via = "unknown"
        if registered_via:
            await events.emit_model(
                UserRegisteredPayload(
                    user_id=int(user.user_id),
                    language=user_data.get("language_code"),
                    referred_by_id=user_data.get("referred_by_id"),
                    registered_via=registered_via,
                    telegram_id=user_data.get("telegram_id"),
                    username=user_data.get("username"),
                    first_name=user_data.get("first_name"),
                    email=user_data.get("email"),
                )
            )
    else:
        logger.info("User %s already exists in DAL. Proceeding without creation.", user.user_id)

    return user, created


async def create_email_user(
    session: AsyncSession,
    *,
    email: str,
    language_code: str,
    email_verified_at: datetime | None = None,
    referred_by_id: int | None = None,
    registered_via: str | None = "email",
) -> tuple[User, bool]:
    normalized_email = (email or "").strip().lower()
    user_id = await generate_unique_email_user_id(session)
    return await create_user(
        session,
        {
            "user_id": user_id,
            "email": normalized_email,
            "email_verified_at": email_verified_at or datetime.now(UTC),
            "language_code": language_code,
            "referred_by_id": referred_by_id,
            "registration_date": datetime.now(UTC),
        },
        registered_via=registered_via,
    )


async def mark_trial_eligibility_reset(
    session: AsyncSession,
    user_id: int,
    *,
    reset_at: datetime | None = None,
) -> datetime | None:
    reset_at = reset_at or datetime.now(UTC)
    stmt = update(User).where(User.user_id == user_id).values(trial_eligibility_reset_at=reset_at)
    result = await session.execute(stmt)
    if rowcount(result) <= 0:
        return None
    return reset_at


async def upsert_user_telegram_avatar(
    session: AsyncSession,
    *,
    user_id: int,
    file_unique_id: str | None,
    content_type: str,
    image_bytes: bytes,
) -> UserTelegramAvatar:
    avatar = await get_user_telegram_avatar(session, user_id)
    if avatar is None:
        avatar = UserTelegramAvatar(
            user_id=user_id,
            file_unique_id=file_unique_id,
            content_type=content_type,
            image_bytes=image_bytes,
            size_bytes=len(image_bytes),
            updated_at=datetime.now(UTC),
        )
        session.add(avatar)
    else:
        avatar.file_unique_id = file_unique_id
        avatar.content_type = content_type
        avatar.image_bytes = image_bytes
        avatar.size_bytes = len(image_bytes)
        avatar.updated_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(avatar)
    return avatar


async def update_user(
    session: AsyncSession, user_id: int, update_data: dict[str, Any]
) -> User | None:
    user = await get_user_by_id(session, user_id)
    if user:
        for key, value in update_data.items():
            setattr(user, key, value)
        await session.flush()
        await session.refresh(user)
    return user


async def update_user_language(session: AsyncSession, user_id: int, lang_code: str) -> bool:
    stmt = update(User).where(User.user_id == user_id).values(language_code=lang_code)
    result = await session.execute(stmt)
    return rowcount(result) > 0
