import logging
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import String, and_, case, cast, delete, desc, func, or_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import aliased

from bot.infra import events

from ..models import (
    AdAttribution,
    EmailVerificationCode,
    HwidDevicePurchase,
    LegacyImportMapping,
    LegacyReferralCode,
    MessageLog,
    Payment,
    PromoCodeActivation,
    Subscription,
    SubscriptionNotification,
    SupportTicket,
    SupportTicketMessage,
    TariffChange,
    TrafficTopup,
    TrafficWarning,
    User,
    UserBilling,
    UserPaymentMethod,
    UserTelegramAvatar,
)

REFERRAL_CODE_ALPHABET = string.ascii_uppercase + string.digits
REFERRAL_CODE_LENGTH = 9
MAX_REFERRAL_CODE_ATTEMPTS = 25
MAX_EMAIL_USER_ID_ATTEMPTS = 25


class UserMergeConflictError(ValueError):
    pass


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
        normalized = user.referral_code.strip()
        if normalized != user.referral_code:
            user.referral_code = normalized
            await session.flush()
            await session.refresh(user)
        return user.referral_code

    user.referral_code = await generate_unique_referral_code(session)
    await session.flush()
    await session.refresh(user)
    return user.referral_code


async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    stmt = select(User).where(User.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_referrer_for_user(session: AsyncSession, user: User) -> Optional[User]:
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
) -> List[User]:
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
    return result.scalars().all()


async def count_users_referred_by(session: AsyncSession, user_id: int) -> int:
    stmt = select(func.count(User.user_id)).where(User.referred_by_id == user_id)
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def get_user_by_username(session: AsyncSession, username: str) -> Optional[User]:
    clean_username = username.lstrip("@").lower()
    stmt = select(User).where(func.lower(User.username) == clean_username)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_email(session: AsyncSession, email: str) -> Optional[User]:
    clean_email = (email or "").strip().lower()
    if not clean_email:
        return None
    stmt = select(User).where(func.lower(User.email) == clean_email)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_telegram_avatar(
    session: AsyncSession,
    user_id: int,
) -> Optional[UserTelegramAvatar]:
    stmt = select(UserTelegramAvatar).where(UserTelegramAvatar.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_user_telegram_avatar(
    session: AsyncSession,
    *,
    user_id: int,
    file_unique_id: Optional[str],
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
            updated_at=datetime.now(timezone.utc),
        )
        session.add(avatar)
    else:
        avatar.file_unique_id = file_unique_id
        avatar.content_type = content_type
        avatar.image_bytes = image_bytes
        avatar.size_bytes = len(image_bytes)
        avatar.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(avatar)
    return avatar


async def get_user_by_panel_uuid(session: AsyncSession, panel_uuid: str) -> Optional[User]:
    stmt = select(User).where(User.panel_user_uuid == panel_uuid)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


## Removed unused generic get_user helper to keep DAL explicit and simple


async def create_user(
    session: AsyncSession,
    user_data: Dict[str, Any],
    *,
    registered_via: Optional[str] = "auto",
) -> Tuple[User, bool]:
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
        user_data["registration_date"] = datetime.now(timezone.utc)

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

    if created and user is not None:
        logging.info(
            f"New user {user.user_id} created in DAL. Referred by: {user.referred_by_id or 'N/A'}."
        )
        if registered_via == "auto":
            if user_data.get("telegram_id"):
                registered_via = "telegram"
            elif user_data.get("email"):
                registered_via = "email"
            else:
                registered_via = "unknown"
        if registered_via:
            await events.emit(
                events.USER_REGISTERED,
                {
                    "user_id": int(user.user_id),
                    "language": user_data.get("language_code"),
                    "referred_by_id": user_data.get("referred_by_id"),
                    "registered_via": registered_via,
                },
            )
    elif user is not None:
        logging.info(f"User {user.user_id} already exists in DAL. Proceeding without creation.")

    return user, created


async def create_email_user(
    session: AsyncSession,
    *,
    email: str,
    language_code: str,
    email_verified_at: Optional[datetime] = None,
    referred_by_id: Optional[int] = None,
    registered_via: Optional[str] = "email",
) -> Tuple[User, bool]:
    normalized_email = (email or "").strip().lower()
    user_id = await generate_unique_email_user_id(session)
    return await create_user(
        session,
        {
            "user_id": user_id,
            "email": normalized_email,
            "email_verified_at": email_verified_at or datetime.now(timezone.utc),
            "language_code": language_code,
            "referred_by_id": referred_by_id,
            "registration_date": datetime.now(timezone.utc),
        },
        registered_via=registered_via,
    )


async def mark_trial_eligibility_reset(
    session: AsyncSession,
    user_id: int,
    *,
    reset_at: Optional[datetime] = None,
) -> Optional[datetime]:
    reset_at = reset_at or datetime.now(timezone.utc)
    stmt = update(User).where(User.user_id == user_id).values(trial_eligibility_reset_at=reset_at)
    result = await session.execute(stmt)
    if result.rowcount <= 0:
        return None
    return reset_at


async def _has_active_panel_subscription(
    session: AsyncSession, user_id: int, panel_user_uuid: str
) -> bool:
    stmt = (
        select(Subscription.subscription_id)
        .where(
            Subscription.user_id == user_id,
            Subscription.panel_user_uuid == panel_user_uuid,
            Subscription.is_active == True,
            Subscription.end_date > datetime.now(timezone.utc),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _get_latest_subscription_for_user(
    session: AsyncSession,
    user_id: int,
    panel_user_uuid: Optional[str] = None,
    *,
    active_only: bool = False,
) -> Optional[Subscription]:
    stmt = select(Subscription).where(Subscription.user_id == user_id)
    if panel_user_uuid is not None:
        stmt = stmt.where(Subscription.panel_user_uuid == panel_user_uuid)
    if active_only:
        stmt = stmt.where(
            Subscription.is_active == True,
            Subscription.end_date > datetime.now(timezone.utc),
        )
    stmt = stmt.order_by(Subscription.end_date.desc(), Subscription.subscription_id.desc()).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _get_active_subscription_for_user(
    session: AsyncSession,
    user_id: int,
    panel_user_uuid: Optional[str] = None,
) -> Optional[Subscription]:
    return await _get_latest_subscription_for_user(
        session,
        user_id,
        panel_user_uuid,
        active_only=True,
    )


async def merge_users(
    session: AsyncSession,
    *,
    source_user_id: int,
    target_user_id: int,
) -> User:
    """Merge source user data into target user and remove the source row."""

    if source_user_id == target_user_id:
        target = await get_user_by_id(session, target_user_id)
        if not target:
            raise ValueError("Target user not found.")
        return target

    source = await get_user_by_id(session, source_user_id)
    target = await get_user_by_id(session, target_user_id)
    if not source or not target:
        raise ValueError("Both source and target users are required for merge.")

    if source.email and target.email and source.email != target.email:
        raise UserMergeConflictError("Both accounts already have different emails.")
    if (
        source.telegram_id
        and target.telegram_id
        and int(source.telegram_id) != int(target.telegram_id)
    ):
        raise UserMergeConflictError("Both accounts already have different Telegram IDs.")

    source_panel_uuid = source.panel_user_uuid
    target_panel_uuid = target.panel_user_uuid
    panel_uuid_to_keep = target_panel_uuid or source_panel_uuid

    now = datetime.now(timezone.utc)
    source_active_sub = await _get_active_subscription_for_user(
        session, source_user_id, source_panel_uuid
    )
    target_active_sub = await _get_active_subscription_for_user(
        session, target_user_id, target_panel_uuid
    )
    target_anchor_sub = target_active_sub
    if not target_anchor_sub and target_panel_uuid:
        target_anchor_sub = await _get_latest_subscription_for_user(
            session, target_user_id, target_panel_uuid
        )
    if not target_anchor_sub and not target_panel_uuid:
        target_anchor_sub = await _get_latest_subscription_for_user(session, target_user_id)

    if (
        source_active_sub
        and target_anchor_sub
        and source_panel_uuid
        and target_panel_uuid
        and source_panel_uuid != target_panel_uuid
    ):
        source_end = source_active_sub.end_date
        if source_end.tzinfo is None:
            source_end = source_end.replace(tzinfo=timezone.utc)

        target_end = target_anchor_sub.end_date
        if target_end.tzinfo is None:
            target_end = target_end.replace(tzinfo=timezone.utc)

        source_remaining = max(timedelta(0), source_end - now)
        if source_remaining > timedelta(0):
            base_end = target_end if target_end > now else now
            target_anchor_sub.end_date = base_end + source_remaining
            target_anchor_sub.last_notification_sent = None
            target_anchor_sub.is_active = True
            target_anchor_sub.status_from_panel = "ACTIVE_EXTENDED_BY_MERGE"

        source_active_sub.is_active = False
        source_active_sub.skip_notifications = True
        source_active_sub.last_notification_sent = None
        source_active_sub.status_from_panel = "MERGED_INTO_ACCOUNT"
    elif (
        source_active_sub
        and target_panel_uuid
        and source_panel_uuid
        and source_panel_uuid != target_panel_uuid
        and not target_anchor_sub
    ):
        source_active_sub.panel_user_uuid = target_panel_uuid
        source_active_sub.last_notification_sent = None
        source_active_sub.status_from_panel = "ACTIVE_EXTENDED_BY_MERGE"

    email_to_move = source.email if source.email and not target.email else None
    email_verified_at_to_move = (
        source.email_verified_at
        if source.email and (not target.email_verified_at or email_to_move)
        else None
    )
    telegram_id_to_move = (
        source.telegram_id if source.telegram_id and not target.telegram_id else None
    )
    referral_code_to_move = (
        source.referral_code if source.referral_code and not target.referral_code else None
    )

    if email_to_move:
        source.email = None
    if telegram_id_to_move:
        source.telegram_id = None
    if referral_code_to_move:
        source.referral_code = None
    if email_to_move or source_panel_uuid or telegram_id_to_move or referral_code_to_move:
        await session.flush()

    if email_to_move:
        target.email = email_to_move
    if email_verified_at_to_move and not target.email_verified_at:
        target.email_verified_at = email_verified_at_to_move
    if telegram_id_to_move:
        target.telegram_id = telegram_id_to_move
    if panel_uuid_to_keep and not target.panel_user_uuid:
        target.panel_user_uuid = panel_uuid_to_keep
    if referral_code_to_move:
        target.referral_code = referral_code_to_move

    for attr in ("username", "first_name", "last_name", "language_code", "telegram_photo_url"):
        if not getattr(target, attr) and getattr(source, attr):
            setattr(target, attr, getattr(source, attr))
    if (
        not target.channel_subscription_verified
        and source.channel_subscription_verified is not None
    ):
        target.channel_subscription_verified = source.channel_subscription_verified
    if not target.channel_subscription_checked_at and source.channel_subscription_checked_at:
        target.channel_subscription_checked_at = source.channel_subscription_checked_at
    if not target.channel_subscription_verified_for and source.channel_subscription_verified_for:
        target.channel_subscription_verified_for = source.channel_subscription_verified_for
    source_tg_status = str(getattr(source, "telegram_notifications_status", None) or "unknown")
    target_tg_status = str(getattr(target, "telegram_notifications_status", None) or "unknown")
    if source_tg_status == "enabled" and target_tg_status != "enabled":
        target.telegram_notifications_status = source_tg_status
    elif target_tg_status == "unknown" and source_tg_status != "unknown":
        target.telegram_notifications_status = source_tg_status
    if getattr(source, "telegram_notifications_checked_at", None) and (
        not getattr(target, "telegram_notifications_checked_at", None)
        or source.telegram_notifications_checked_at > target.telegram_notifications_checked_at
    ):
        target.telegram_notifications_checked_at = source.telegram_notifications_checked_at
    if getattr(source, "telegram_notifications_enabled_at", None) and (
        not getattr(target, "telegram_notifications_enabled_at", None)
        or source.telegram_notifications_enabled_at > target.telegram_notifications_enabled_at
    ):
        target.telegram_notifications_enabled_at = source.telegram_notifications_enabled_at
    if getattr(source, "telegram_notifications_blocked_at", None) and (
        not getattr(target, "telegram_notifications_blocked_at", None)
        or source.telegram_notifications_blocked_at > target.telegram_notifications_blocked_at
    ):
        target.telegram_notifications_blocked_at = source.telegram_notifications_blocked_at
    if source.lifetime_used_traffic_bytes is not None:
        target.lifetime_used_traffic_bytes = (
            target.lifetime_used_traffic_bytes or 0
        ) + source.lifetime_used_traffic_bytes
        source_synced_at = getattr(source, "lifetime_used_traffic_synced_at", None)
        target_synced_at = getattr(target, "lifetime_used_traffic_synced_at", None)
        if source_synced_at and (not target_synced_at or source_synced_at > target_synced_at):
            target.lifetime_used_traffic_synced_at = source_synced_at
    source_welcome_claimed_at = getattr(source, "referral_welcome_bonus_claimed_at", None)
    target_welcome_claimed_at = getattr(target, "referral_welcome_bonus_claimed_at", None)
    if source_welcome_claimed_at and (
        not target_welcome_claimed_at or source_welcome_claimed_at < target_welcome_claimed_at
    ):
        # The welcome bonus is once-per-person: if either account already
        # claimed it, the merged account must keep that mark so the bonus
        # cannot be re-granted after the merge.
        target.referral_welcome_bonus_claimed_at = source_welcome_claimed_at
    if not target.referred_by_id and source.referred_by_id != target_user_id:
        target.referred_by_id = source.referred_by_id
    if target.referred_by_id == source_user_id:
        target.referred_by_id = source.referred_by_id
        if target.referred_by_id == target_user_id:
            target.referred_by_id = None

    target_method_ids = select(UserPaymentMethod.provider_payment_method_id).where(
        UserPaymentMethod.user_id == target_user_id
    )
    await session.execute(
        delete(UserPaymentMethod).where(
            UserPaymentMethod.user_id == source_user_id,
            UserPaymentMethod.provider_payment_method_id.in_(target_method_ids),
        )
    )

    target_promo_ids = select(PromoCodeActivation.promo_code_id).where(
        PromoCodeActivation.user_id == target_user_id
    )
    await session.execute(
        delete(PromoCodeActivation).where(
            PromoCodeActivation.user_id == source_user_id,
            PromoCodeActivation.promo_code_id.in_(target_promo_ids),
        )
    )

    target_has_billing = (
        await session.execute(
            select(UserBilling.user_id).where(UserBilling.user_id == target_user_id)
        )
    ).scalar_one_or_none()
    if target_has_billing:
        await session.execute(delete(UserBilling).where(UserBilling.user_id == source_user_id))
    else:
        await session.execute(
            update(UserBilling)
            .where(UserBilling.user_id == source_user_id)
            .values(user_id=target_user_id)
        )

    target_has_attribution = (
        await session.execute(
            select(AdAttribution.user_id).where(AdAttribution.user_id == target_user_id)
        )
    ).scalar_one_or_none()
    if target_has_attribution:
        await session.execute(delete(AdAttribution).where(AdAttribution.user_id == source_user_id))
    else:
        await session.execute(
            update(AdAttribution)
            .where(AdAttribution.user_id == source_user_id)
            .values(user_id=target_user_id)
        )

    target_has_avatar = (
        await session.execute(
            select(UserTelegramAvatar.user_id).where(UserTelegramAvatar.user_id == target_user_id)
        )
    ).scalar_one_or_none()
    if target_has_avatar:
        await session.execute(
            delete(UserTelegramAvatar).where(UserTelegramAvatar.user_id == source_user_id)
        )
    else:
        await session.execute(
            update(UserTelegramAvatar)
            .where(UserTelegramAvatar.user_id == source_user_id)
            .values(user_id=target_user_id)
        )

    subscription_update_values: Dict[str, Any] = {"user_id": target_user_id}
    if panel_uuid_to_keep:
        subscription_update_values["panel_user_uuid"] = panel_uuid_to_keep
    await session.execute(
        update(Subscription)
        .where(Subscription.user_id == source_user_id)
        .values(**subscription_update_values)
    )
    for model in (Payment, PromoCodeActivation, UserPaymentMethod):
        await session.execute(
            update(model).where(model.user_id == source_user_id).values(user_id=target_user_id)
        )
    await session.execute(
        update(LegacyReferralCode)
        .where(LegacyReferralCode.user_id == source_user_id)
        .values(user_id=target_user_id)
    )
    await session.execute(
        update(LegacyImportMapping)
        .where(
            LegacyImportMapping.target_table == "users",
            LegacyImportMapping.target_id == str(source_user_id),
        )
        .values(target_id=str(target_user_id))
    )

    await session.execute(
        update(MessageLog)
        .where(MessageLog.user_id == source_user_id)
        .values(user_id=target_user_id)
    )
    await session.execute(
        update(MessageLog)
        .where(MessageLog.target_user_id == source_user_id)
        .values(target_user_id=target_user_id)
    )
    await session.execute(
        update(User)
        .where(User.referred_by_id == source_user_id)
        .values(referred_by_id=target_user_id)
    )

    await session.delete(source)
    await session.flush()
    await session.refresh(target)

    await events.emit(
        events.ACCOUNT_MERGED,
        {
            "source_user_id": int(source_user_id),
            "target_user_id": int(target_user_id),
        },
    )
    return target


async def get_user_by_referral_code(
    session: AsyncSession,
    referral_code: str,
    *,
    include_legacy: bool = False,
) -> Optional[User]:
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


async def update_user(
    session: AsyncSession, user_id: int, update_data: Dict[str, Any]
) -> Optional[User]:
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
    return result.rowcount > 0


async def get_banned_users(session: AsyncSession) -> List[User]:
    """Get all banned users"""
    stmt = select(User).where(User.is_banned == True).order_by(User.registration_date.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_all_users_paginated(
    session: AsyncSession, *, page: int = 0, page_size: int = 15
) -> List[User]:
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
    return result.scalars().all()


async def count_all_users(session: AsyncSession) -> int:
    """Count total number of users."""
    result = await session.execute(select(func.count(User.user_id)))
    return result.scalar_one()


async def get_all_active_user_ids_for_broadcast(session: AsyncSession) -> List[int]:
    stmt = select(User.user_id).where(User.is_banned == False)
    result = await session.execute(stmt)
    return result.scalars().all()


async def count_all_active_users_for_broadcast(session: AsyncSession) -> int:
    stmt = select(func.count(User.user_id)).where(User.is_banned == False)
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def get_all_users_with_panel_uuid(session: AsyncSession) -> List[User]:
    stmt = select(User).where(User.panel_user_uuid.is_not(None))
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_panel_user_uuids_for_user(
    session: AsyncSession,
    user_id: int,
    *,
    user: Optional[User] = None,
) -> List[str]:
    """Return every Remnawave user UUID linked to a bot user.

    The canonical UUID normally lives on ``users.panel_user_uuid``, but older
    or partially-synced records can still have UUIDs only on subscription rows.
    """

    if user is None:
        user = await get_user_by_id(session, user_id)

    panel_uuids: List[str] = []
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


async def get_enhanced_user_statistics(session: AsyncSession) -> Dict[str, Any]:
    """Get comprehensive user statistics including active users, trial users, etc."""
    from datetime import datetime, timezone

    # Use timezone-aware UTC to avoid naive/aware comparison issues in SQL queries
    now = datetime.now(timezone.utc)
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


async def get_user_ids_with_active_subscription(session: AsyncSession) -> List[int]:
    """Return non-banned user IDs who have any active subscription."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

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
    return result.scalars().all()


async def count_users_with_active_subscription_for_broadcast(session: AsyncSession) -> int:
    """Count non-banned users who have any active subscription."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

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


async def get_user_ids_without_active_subscription(session: AsyncSession) -> List[int]:
    """Return non-banned user IDs who do NOT have any active subscription."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

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
    return result.scalars().all()


async def count_users_without_active_subscription_for_broadcast(session: AsyncSession) -> int:
    """Count non-banned users who do NOT have any active subscription."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    stmt = select(func.count(User.user_id)).where(
        User.is_banned == False,
        ~_active_subscription_exists_for_user(now),
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def get_user_ids_without_any_subscription(session: AsyncSession) -> List[int]:
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
    return result.scalars().all()


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


def _expired_subscription_exists_for_user(now: datetime):
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


def _active_subscription_exists_for_user(now: datetime):
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
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    stmt = select(func.count(User.user_id)).where(
        _expired_subscription_exists_for_user(now),
        ~_active_subscription_exists_for_user(now),
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def count_users_with_expired_subscription_for_broadcast(session: AsyncSession) -> int:
    """Count non-banned users with an expired subscription and no active one."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    stmt = select(func.count(User.user_id)).where(
        User.is_banned == False,
        _expired_subscription_exists_for_user(now),
        ~_active_subscription_exists_for_user(now),
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def get_user_ids_with_expired_subscription(session: AsyncSession) -> List[int]:
    """Return non-banned user IDs with an expired subscription and no active one."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    stmt = select(User.user_id).where(
        User.is_banned == False,
        _expired_subscription_exists_for_user(now),
        ~_active_subscription_exists_for_user(now),
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def delete_user_and_relations(session: AsyncSession, user_id: int) -> bool:
    """Completely remove a user and all dependent records from the database.

    This helper ensures we do not leave dangling foreign keys or orphaned data.
    """
    user = await get_user_by_id(session, user_id)
    if not user:
        return False

    # Ensure referral pointers do not block deletion
    await session.execute(
        update(User).where(User.referred_by_id == user_id).values(referred_by_id=None)
    )

    subscription_ids = select(Subscription.subscription_id).where(Subscription.user_id == user_id)
    payment_ids = select(Payment.payment_id).where(Payment.user_id == user_id)
    support_ticket_ids = select(SupportTicket.ticket_id).where(SupportTicket.user_id == user_id)

    # Clean up dependent tables that do not cascade automatically.
    await session.execute(
        delete(TrafficTopup).where(
            or_(
                TrafficTopup.subscription_id.in_(subscription_ids),
                TrafficTopup.payment_id.in_(payment_ids),
            )
        )
    )
    await session.execute(
        delete(HwidDevicePurchase).where(
            or_(
                HwidDevicePurchase.subscription_id.in_(subscription_ids),
                HwidDevicePurchase.payment_id.in_(payment_ids),
            )
        )
    )
    await session.execute(
        delete(TariffChange).where(
            or_(
                TariffChange.subscription_id.in_(subscription_ids),
                TariffChange.payment_id.in_(payment_ids),
            )
        )
    )
    await session.execute(
        delete(TrafficWarning).where(TrafficWarning.subscription_id.in_(subscription_ids))
    )
    await session.execute(
        delete(SubscriptionNotification).where(
            SubscriptionNotification.subscription_id.in_(subscription_ids)
        )
    )
    await session.execute(
        delete(SupportTicketMessage).where(SupportTicketMessage.ticket_id.in_(support_ticket_ids))
    )
    await session.execute(
        update(SupportTicketMessage)
        .where(SupportTicketMessage.author_user_id == user_id)
        .values(author_user_id=None)
    )
    await session.execute(delete(SupportTicket).where(SupportTicket.user_id == user_id))
    await session.execute(
        delete(EmailVerificationCode).where(EmailVerificationCode.target_user_id == user_id)
    )
    await session.execute(
        delete(MessageLog).where(
            or_(MessageLog.user_id == user_id, MessageLog.target_user_id == user_id)
        )
    )
    await session.execute(
        delete(PromoCodeActivation).where(
            or_(
                PromoCodeActivation.user_id == user_id,
                PromoCodeActivation.payment_id.in_(payment_ids),
            )
        )
    )
    await session.execute(delete(UserPaymentMethod).where(UserPaymentMethod.user_id == user_id))
    await session.execute(delete(UserBilling).where(UserBilling.user_id == user_id))
    await session.execute(delete(AdAttribution).where(AdAttribution.user_id == user_id))
    await session.execute(delete(UserTelegramAvatar).where(UserTelegramAvatar.user_id == user_id))
    await session.execute(delete(LegacyReferralCode).where(LegacyReferralCode.user_id == user_id))
    await session.execute(
        delete(LegacyImportMapping).where(
            or_(
                and_(
                    LegacyImportMapping.target_table == "users",
                    LegacyImportMapping.target_id == str(user_id),
                ),
                and_(
                    LegacyImportMapping.target_table == "subscriptions",
                    LegacyImportMapping.target_id.in_(
                        select(cast(Subscription.subscription_id, String)).where(
                            Subscription.user_id == user_id
                        )
                    ),
                ),
                and_(
                    LegacyImportMapping.target_table == "payments",
                    LegacyImportMapping.target_id.in_(
                        select(cast(Payment.payment_id, String)).where(Payment.user_id == user_id)
                    ),
                ),
            )
        )
    )
    await session.execute(delete(Payment).where(Payment.user_id == user_id))
    await session.execute(delete(Subscription).where(Subscription.user_id == user_id))

    await session.delete(user)
    await session.flush()
    return True


async def get_top_users_by_traffic_used(
    session: AsyncSession,
    *,
    limit: int = 10,
) -> List[Dict[str, Any]]:
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
) -> List[Dict[str, Any]]:
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
) -> List[Dict[str, Any]]:
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
) -> List[Dict[str, Any]]:
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
