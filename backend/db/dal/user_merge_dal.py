# SQLAlchemy legacy Column declarations expose instance attributes as Column[T]
# to mypy; this DAL intentionally mutates loaded ORM instances.
# mypy: disable-error-code="assignment,arg-type,operator"

"""Account merge and full-account deletion.

Split out of ``user_dal`` (which re-exports everything here for
compatibility).
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from typing import cast as type_cast

from sqlalchemy import String, and_, cast, delete, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from bot.infra import events
from bot.infra.event_payloads import AccountMergedPayload

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
from .user_reads_dal import get_user_by_id

logger = logging.getLogger(__name__)


class UserMergeConflictError(ValueError):
    def __init__(self, message: str, *, message_key: str | None = None) -> None:
        super().__init__(message)
        self.message_key = message_key


async def _has_active_panel_subscription(
    session: AsyncSession, user_id: int, panel_user_uuid: str
) -> bool:
    stmt = (
        select(Subscription.subscription_id)
        .where(
            Subscription.user_id == user_id,
            Subscription.panel_user_uuid == panel_user_uuid,
            Subscription.is_active == True,
            Subscription.end_date > datetime.now(UTC),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _get_latest_subscription_for_user(
    session: AsyncSession,
    user_id: int,
    panel_user_uuid: str | None = None,
    *,
    active_only: bool = False,
) -> Subscription | None:
    stmt = select(Subscription).where(Subscription.user_id == user_id)
    if panel_user_uuid is not None:
        stmt = stmt.where(Subscription.panel_user_uuid == panel_user_uuid)
    if active_only:
        stmt = stmt.where(
            Subscription.is_active == True,
            Subscription.end_date > datetime.now(UTC),
        )
    stmt = stmt.order_by(Subscription.end_date.desc(), Subscription.subscription_id.desc()).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _get_active_subscription_for_user(
    session: AsyncSession,
    user_id: int,
    panel_user_uuid: str | None = None,
) -> Subscription | None:
    return await _get_latest_subscription_for_user(
        session,
        user_id,
        panel_user_uuid,
        active_only=True,
    )


async def _lock_users_for_merge(
    session: AsyncSession,
    source_user_id: int,
    target_user_id: int,
) -> tuple[User | None, User | None]:
    """Lock both merge participants in a stable order.

    Telegram login payloads can be replayed during their validity window, so
    account merging must be idempotent under concurrent requests.  Ordering
    the row locks also prevents two opposite-direction merges from deadlocking.
    """
    user_ids = sorted({int(source_user_id), int(target_user_id)})
    stmt = (
        select(User)
        .where(User.user_id.in_(user_ids))
        .order_by(User.user_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    result = await session.execute(stmt)
    users_by_id = {int(user.user_id): user for user in result.scalars().all()}
    return users_by_id.get(int(source_user_id)), users_by_id.get(int(target_user_id))


async def _accounts_share_promo_activation(
    session: AsyncSession,
    source_user_id: int,
    target_user_id: int,
) -> bool:
    target_promo_ids = select(PromoCodeActivation.promo_code_id).where(
        PromoCodeActivation.user_id == target_user_id
    )
    stmt = (
        select(PromoCodeActivation.activation_id)
        .where(
            PromoCodeActivation.user_id == source_user_id,
            PromoCodeActivation.promo_code_id.in_(target_promo_ids),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


def _is_free_grant_subscription(subscription: Subscription) -> bool:
    status = str(getattr(subscription, "status_from_panel", "") or "").strip().upper()
    if status in {"TRIAL", "ACTIVE_BONUS", "ACTIVE_MERGED_FREE_GRANT"}:
        return True
    provider = str(getattr(subscription, "provider", "") or "").strip().lower()
    try:
        duration_months = int(getattr(subscription, "duration_months", 0) or 0)
    except (TypeError, ValueError):
        duration_months = 0
    return provider in {"", "trial"} and duration_months <= 0


def _merged_subscription_end(
    source_subscription: Subscription,
    target_subscription: Subscription,
    *,
    now: datetime,
) -> tuple[datetime, str]:
    source_end = type_cast(datetime, source_subscription.end_date)
    if source_end.tzinfo is None:
        source_end = source_end.replace(tzinfo=UTC)

    target_end = type_cast(datetime, target_subscription.end_date)
    if target_end.tzinfo is None:
        target_end = target_end.replace(tzinfo=UTC)

    if _is_free_grant_subscription(source_subscription) or _is_free_grant_subscription(
        target_subscription
    ):
        # Merging identities must not add a separately claimed free trial or
        # bonus on top of either another grant or paid time.  Keeping the later
        # expiry preserves the best existing entitlement without stacking it.
        return max(source_end, target_end), "ACTIVE_MERGED_FREE_GRANT"

    source_remaining = max(timedelta(0), source_end - now)
    base_end = target_end if target_end > now else now
    return base_end + source_remaining, "ACTIVE_EXTENDED_BY_MERGE"


async def merge_users(
    session: AsyncSession,
    *,
    source_user_id: int,
    target_user_id: int,
    reason: str = "unknown",
    send_user_email: bool = False,
) -> User:
    """Merge source user data into target user and remove the source row."""

    if source_user_id == target_user_id:
        target = await get_user_by_id(session, target_user_id)
        if not target:
            raise ValueError("Target user not found.")
        return target

    source, target = await _lock_users_for_merge(session, source_user_id, target_user_id)
    if not source or not target:
        raise ValueError("Both source and target users are required for merge.")
    if bool(getattr(source, "is_banned", False)) or bool(getattr(target, "is_banned", False)):
        raise UserMergeConflictError(
            "Access denied",
            message_key="wa_auth_access_denied",
        )

    if source.email and target.email and source.email != target.email:
        raise UserMergeConflictError("Both accounts already have different emails.")
    if (
        source.telegram_id
        and target.telegram_id
        and int(source.telegram_id) != int(target.telegram_id)
    ):
        raise UserMergeConflictError("Both accounts already have different Telegram IDs.")
    if await _accounts_share_promo_activation(session, source_user_id, target_user_id):
        raise UserMergeConflictError(
            "Both accounts already redeemed the same one-time code.",
            message_key="account_merge_duplicate_promo_conflict",
        )

    source_panel_uuid = source.panel_user_uuid
    target_panel_uuid = target.panel_user_uuid
    panel_uuid_to_keep = target_panel_uuid or source_panel_uuid

    now = datetime.now(UTC)
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
            source_end = source_end.replace(tzinfo=UTC)

        if source_end > now:
            merged_end, merged_status = _merged_subscription_end(
                source_active_sub,
                target_anchor_sub,
                now=now,
            )
            target_anchor_sub.end_date = merged_end
            target_anchor_sub.last_notification_sent = None
            target_anchor_sub.is_active = True
            target_anchor_sub.status_from_panel = merged_status

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
    if (source_tg_status == "enabled" and target_tg_status != "enabled") or (
        target_tg_status == "unknown" and source_tg_status != "unknown"
    ):
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

    subscription_update_values: dict[str, Any] = {"user_id": target_user_id}
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

    await events.emit_model(
        AccountMergedPayload(
            source_user_id=int(source_user_id),
            target_user_id=int(target_user_id),
            reason=reason,
            send_user_email=send_user_email,
            source_panel_user_uuid=source_panel_uuid,
            target_panel_user_uuid=target.panel_user_uuid,
            email=target.email,
            telegram_id=target.telegram_id,
            username=target.username,
            first_name=target.first_name,
            language=target.language_code,
            final_end_date=getattr(target_anchor_sub or source_active_sub, "end_date", None),
        )
    )
    return target


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
