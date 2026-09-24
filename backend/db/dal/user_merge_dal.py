# Legacy SQLAlchemy Columns confuse mypy when this DAL mutates loaded ORM instances.
# mypy: disable-error-code="assignment,arg-type,operator"

"""Account merge and deletion, re-exported by ``user_dal`` for compatibility."""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import String, and_, case, cast, delete, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from bot.infra import events
from bot.infra.event_payloads import AccountMergedPayload

from ..models import (
    AccountAlias,
    AccountRole,
    AccountRoleEvent,
    AdAttribution,
    EmailVerificationCode,
    FlexibleTrafficLimit,
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
    UserEmailAddress,
    UserExternalIdentity,
    UserPasskeyCredential,
    UserPaymentMethod,
    UserTelegramAvatar,
    WebAuthnChallenge,
)
from ..partner_models import (
    PartnerApplication,
    PartnerAuditEvent,
    PartnerClient,
    PartnerLedgerEntry,
    PartnerProfile,
    PartnerWithdrawal,
)
from .user_merge_entitlements import (
    _merged_subscription_end as _merged_subscription_end,
)
from .user_merge_entitlements import (
    inspect_recurring_merge,
    merge_active_subscription_entitlements,
    merge_user_billing_state,
    transfer_entitlement_ownership,
)
from .user_reads_dal import get_user_by_id

logger = logging.getLogger(__name__)

RecurringCancellation = Callable[
    [AsyncSession, int, Subscription | None, tuple[str, ...]],
    Awaitable[bool],
]


class UserMergeConflictError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        message_key: str | None = None,
        code: str = "account_merge_conflict",
    ) -> None:
        super().__init__(message)
        self.message_key = message_key
        self.code = code


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


async def merge_users(
    session: AsyncSession,
    *,
    source_user_id: int,
    target_user_id: int,
    reason: str = "unknown",
    send_user_email: bool = False,
    cancel_source_recurring: RecurringCancellation | None = None,
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

    # A merge must not silently move privileges or erase the audit trail of a
    # privileged account. Such accounts require a separate reviewed procedure.
    source_role = (
        await session.execute(
            select(AccountRole.user_id).where(AccountRole.user_id == source_user_id).limit(1)
        )
    ).scalar_one_or_none()
    source_role_event = (
        await session.execute(
            select(AccountRoleEvent.event_id)
            .where(
                or_(
                    AccountRoleEvent.user_id == source_user_id,
                    AccountRoleEvent.actor_user_id == source_user_id,
                )
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if source_role is not None or source_role_event is not None:
        raise UserMergeConflictError(
            "A privileged account cannot be merged automatically.",
            message_key="account_merge_privileged_source",
            code="account_merge_privileged_source",
        )

    if (
        source.telegram_id
        and target.telegram_id
        and int(source.telegram_id) != int(target.telegram_id)
    ):
        raise UserMergeConflictError(
            "Both accounts already have different Telegram IDs.",
            message_key="account_merge_telegram_conflict",
            code="account_merge_telegram_conflict",
        )
    if await _accounts_share_promo_activation(session, source_user_id, target_user_id):
        raise UserMergeConflictError(
            "Both accounts already redeemed the same one-time code.",
            message_key="account_merge_duplicate_promo_conflict",
            code="account_merge_duplicate_promo_conflict",
        )
    source_provider_rows = (
        (
            await session.execute(
                select(UserExternalIdentity.provider).where(
                    UserExternalIdentity.user_id == source_user_id
                )
            )
        )
        .scalars()
        .all()
    )
    target_provider_rows = set(
        (
            await session.execute(
                select(UserExternalIdentity.provider).where(
                    UserExternalIdentity.user_id == target_user_id
                )
            )
        )
        .scalars()
        .all()
    )
    overlapping_provider = next(
        (provider for provider in source_provider_rows if provider in target_provider_rows), None
    )
    if overlapping_provider:
        provider = str(overlapping_provider).strip().lower()
        message_key = (
            f"account_merge_{provider}_conflict"
            if provider in {"google", "yandex"}
            else "account_merge_provider_conflict"
        )
        raise UserMergeConflictError(
            f"Both accounts already have different {provider} identities.",
            message_key=message_key,
            code=message_key,
        )

    source_partner = (
        await session.execute(
            select(PartnerProfile).where(PartnerProfile.user_id == source_user_id).with_for_update()
        )
    ).scalar_one_or_none()
    target_partner = (
        await session.execute(
            select(PartnerProfile).where(PartnerProfile.user_id == target_user_id).with_for_update()
        )
    ).scalar_one_or_none()
    if source_partner and target_partner:
        raise UserMergeConflictError("Both accounts already have partner profiles.")
    source_partner_client = (
        await session.execute(
            select(PartnerClient)
            .where(PartnerClient.client_user_id == source_user_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    target_partner_client = (
        await session.execute(
            select(PartnerClient)
            .where(PartnerClient.client_user_id == target_user_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if source_partner_client and target_partner_client:
        raise UserMergeConflictError("Both accounts are attributed to different partner records.")
    resulting_partner = target_partner or source_partner
    resulting_client = target_partner_client or source_partner_client
    if (
        resulting_partner
        and resulting_client
        and int(resulting_partner.partner_id) == int(resulting_client.partner_id)
    ):
        raise UserMergeConflictError("Account merge would create partner self-attribution.")
    source_pending_application = (
        await session.execute(
            select(PartnerApplication.application_id).where(
                PartnerApplication.user_id == source_user_id,
                PartnerApplication.status == "pending",
            )
        )
    ).scalar_one_or_none()
    target_pending_application = (
        await session.execute(
            select(PartnerApplication.application_id).where(
                PartnerApplication.user_id == target_user_id,
                PartnerApplication.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if source_pending_application and target_pending_application:
        raise UserMergeConflictError("Both accounts have pending partner applications.")

    source_panel_uuid = source.panel_user_uuid
    target_panel_uuid = target.panel_user_uuid
    panel_uuid_to_keep = target_panel_uuid or source_panel_uuid

    now = datetime.now(UTC)
    source_active_sub = await _get_active_subscription_for_user(
        session, source_user_id, source_panel_uuid
    )
    if not source_active_sub and source_panel_uuid:
        source_active_sub = await _get_active_subscription_for_user(session, source_user_id)
    target_active_sub = await _get_active_subscription_for_user(
        session, target_user_id, target_panel_uuid
    )
    if not target_active_sub and target_panel_uuid:
        target_active_sub = await _get_active_subscription_for_user(session, target_user_id)
    target_anchor_sub = target_active_sub
    if not target_anchor_sub and target_panel_uuid:
        target_anchor_sub = await _get_latest_subscription_for_user(
            session, target_user_id, target_panel_uuid
        )
    if not target_anchor_sub and not target_panel_uuid:
        target_anchor_sub = await _get_latest_subscription_for_user(session, target_user_id)
    if not target_anchor_sub:
        target_anchor_sub = await _get_latest_subscription_for_user(session, target_user_id)

    recurring_state = await inspect_recurring_merge(
        session,
        source_user_id=source_user_id,
        target_user_id=target_user_id,
        source_subscription=source_active_sub,
        target_subscription=target_active_sub,
        now=now,
    )
    if recurring_state.source_has_recurring and recurring_state.target_has_recurring:
        cancelled = bool(
            cancel_source_recurring
            and await cancel_source_recurring(
                session,
                source_user_id,
                source_active_sub,
                recurring_state.source_managed_providers,
            )
        )
        if not cancelled:
            raise UserMergeConflictError(
                "The secondary account recurring payment could not be cancelled safely.",
                message_key="account_merge_recurring_cancel_failed",
                code="account_merge_conflict",
            )
        recurring_state = type(recurring_state)(
            source_has_recurring=False,
            target_has_recurring=True,
            source_managed_providers=(),
        )

    from db.dal import auto_renew_dal

    await auto_renew_dal.stop_open_cycles_for_user(
        session,
        source_user_id,
        "account_merged",
    )

    if (
        source_active_sub
        and target_anchor_sub
        and int(source_active_sub.subscription_id) != int(target_anchor_sub.subscription_id)
    ):
        await merge_active_subscription_entitlements(
            session,
            source_active_sub,
            target_anchor_sub,
            now=now,
            source_has_recurring=recurring_state.source_has_recurring,
            target_has_recurring=recurring_state.target_has_recurring,
        )
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

    source_primary_email = str(source.email or "").strip().lower()
    target_primary_email = str(target.email or "").strip().lower()
    source_primary_verified = bool(source_primary_email and source.email_verified_at)
    target_primary_verified = bool(target_primary_email and target.email_verified_at)
    # The established target account keeps its verified primary address. A
    # verified source address replaces only an empty or unverified target
    # address; otherwise it is retained below as an additional verified login.
    promote_source_primary = bool(
        source_primary_email
        and (not target_primary_email or (source_primary_verified and not target_primary_verified))
    )
    email_to_move = source.email if promote_source_primary else None
    email_verified_at_to_move = source.email_verified_at if email_to_move else None
    telegram_id_to_move = (
        source.telegram_id if source.telegram_id and not target.telegram_id else None
    )
    referral_code_to_move = (
        source.referral_code if source.referral_code and not target.referral_code else None
    )
    source_notification_email = (
        str(getattr(source, "notification_email", None) or source.email or "").strip().lower()
    )
    target_notification_email = (
        str(
            getattr(target, "notification_email", None)
            or (target.email if target_primary_verified else "")
            or ""
        )
        .strip()
        .lower()
    )

    if email_to_move:
        source.email = None
    if telegram_id_to_move:
        source.telegram_id = None
    if source_panel_uuid:
        source.panel_user_uuid = None
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
    if target_notification_email:
        # Preserve the established account's notification destination even
        # when the merged source contributes another verified address.
        target.notification_email = target_notification_email
    elif source_notification_email:
        target.notification_email = source_notification_email

    # An opt-out on either identity wins. Account linking must never silently
    # re-enable a channel that the person already disabled.
    for preference_attr in (
        "marketing_notifications_email_enabled",
        "marketing_notifications_telegram_enabled",
        "system_notifications_email_enabled",
        "system_notifications_telegram_enabled",
    ):
        setattr(
            target,
            preference_attr,
            bool(getattr(target, preference_attr, True))
            and bool(getattr(source, preference_attr, True)),
        )
    source_password_hash = getattr(source, "password_hash", None)
    if source_password_hash and not getattr(target, "password_hash", None):
        # A user has already proved control of both accounts. Preserve the only
        # password credential; when both sides have one, the established target
        # password wins and can be reset later from Security settings.
        target.password_hash = source_password_hash
        target.password_set_at = getattr(source, "password_set_at", None)

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

    await merge_user_billing_state(
        session,
        source_user_id=source_user_id,
        target_user_id=target_user_id,
        source_subscription=source_active_sub,
        recurring_state=recurring_state,
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
    for model in (Payment, PromoCodeActivation):
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

    await transfer_entitlement_ownership(
        session,
        source_user_id=source_user_id,
        target_user_id=target_user_id,
        panel_user_uuid=panel_uuid_to_keep,
    )

    await session.execute(
        update(PartnerProfile)
        .where(PartnerProfile.user_id == source_user_id)
        .values(user_id=target_user_id)
    )
    await session.execute(
        update(PartnerClient)
        .where(PartnerClient.client_user_id == source_user_id)
        .values(client_user_id=target_user_id)
    )
    await session.execute(
        update(PartnerClient)
        .where(PartnerClient.attributed_by_admin_id == source_user_id)
        .values(attributed_by_admin_id=target_user_id)
    )
    await session.execute(
        update(PartnerApplication)
        .where(PartnerApplication.user_id == source_user_id)
        .values(user_id=target_user_id)
    )
    await session.execute(
        update(PartnerApplication)
        .where(PartnerApplication.decided_by_admin_id == source_user_id)
        .values(decided_by_admin_id=target_user_id)
    )
    await session.execute(
        update(PartnerWithdrawal)
        .where(PartnerWithdrawal.handled_by_admin_id == source_user_id)
        .values(handled_by_admin_id=target_user_id)
    )
    await session.execute(
        update(PartnerLedgerEntry)
        .where(PartnerLedgerEntry.actor_admin_id == source_user_id)
        .values(actor_admin_id=target_user_id)
    )
    await session.execute(
        update(PartnerAuditEvent)
        .where(PartnerAuditEvent.actor_user_id == source_user_id)
        .values(actor_user_id=target_user_id)
    )

    # Support history and verification codes reference users(user_id) with a
    # plain foreign key -- no ON DELETE clause, and User declares no
    # relationship for them, so neither the database nor the ORM moves them
    # implicitly. Leaving them behind makes the delete below raise
    # ForeignKeyViolationError and rolls the whole merge back, which is what a
    # customer who opened a ticket before linking their email would hit.
    await session.execute(
        update(SupportTicket)
        .where(SupportTicket.user_id == source_user_id)
        .values(user_id=target_user_id)
    )
    await session.execute(
        update(SupportTicketMessage)
        .where(SupportTicketMessage.author_user_id == source_user_id)
        .values(author_user_id=target_user_id)
    )
    await session.execute(
        update(EmailVerificationCode)
        .where(EmailVerificationCode.target_user_id == source_user_id)
        .values(target_user_id=target_user_id, status="superseded", consumed_at=datetime.now(UTC))
    )
    target_address_emails = select(UserEmailAddress.email).where(
        UserEmailAddress.user_id == target_user_id
    )
    await session.execute(
        delete(UserEmailAddress).where(
            UserEmailAddress.user_id == source_user_id,
            UserEmailAddress.email.in_(target_address_emails),
        )
    )
    # Clear both partial-unique flags before moving addresses, then restore
    # them according to the surviving account policy. This lets distinct
    # verified addresses coexist without a transient uniqueness violation.
    await session.execute(
        update(UserEmailAddress)
        .where(UserEmailAddress.user_id.in_([source_user_id, target_user_id]))
        .values(is_primary=False, is_notification=False)
    )
    await session.execute(
        update(UserEmailAddress)
        .where(UserEmailAddress.user_id == source_user_id)
        .values(user_id=target_user_id)
    )
    final_primary_email = str(target.email or "").strip().lower()
    final_notification_email = (
        str(getattr(target, "notification_email", None) or final_primary_email).strip().lower()
    )
    if final_primary_email and target.email_verified_at:
        await session.execute(
            update(UserEmailAddress)
            .where(
                UserEmailAddress.user_id == target_user_id,
                UserEmailAddress.email == final_primary_email,
            )
            .values(is_primary=True)
        )
    if final_notification_email:
        await session.execute(
            update(UserEmailAddress)
            .where(
                UserEmailAddress.user_id == target_user_id,
                UserEmailAddress.email == final_notification_email,
            )
            .values(is_notification=True)
        )
    await session.execute(
        update(UserExternalIdentity)
        .where(UserExternalIdentity.user_id == source_user_id)
        .values(user_id=target_user_id)
    )
    await session.execute(
        update(UserPasskeyCredential)
        .where(UserPasskeyCredential.user_id == source_user_id)
        .values(user_id=target_user_id)
    )
    await session.execute(
        delete(WebAuthnChallenge).where(WebAuthnChallenge.user_id == source_user_id)
    )

    from .gift_dal import merge_owner

    await merge_owner(session, source_user_id, target_user_id)
    await session.execute(
        update(AccountAlias)
        .where(AccountAlias.new_user_id == source_user_id)
        .values(new_user_id=target_user_id)
    )
    session.add(
        AccountAlias(
            old_user_id=source_user_id,
            new_user_id=target_user_id,
            reason=reason[:64],
        )
    )
    await session.delete(source)
    await session.flush()
    await session.refresh(target)

    logger.info(
        "Account merge staged source_user_id=%s target_user_id=%s reason=%s",
        source_user_id,
        target_user_id,
        reason,
    )
    await events.emit_model(
        AccountMergedPayload(
            source_user_id=int(source_user_id),
            target_user_id=int(target_user_id),
            reason=reason,
            send_user_email=send_user_email,
            source_panel_user_uuid=source_panel_uuid,
            target_panel_user_uuid=target.panel_user_uuid,
            email=getattr(target, "notification_email", None) or target.email,
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
    await session.execute(delete(UserEmailAddress).where(UserEmailAddress.user_id == user_id))
    await session.execute(
        delete(UserExternalIdentity).where(UserExternalIdentity.user_id == user_id)
    )
    await session.execute(
        delete(UserPasskeyCredential).where(UserPasskeyCredential.user_id == user_id)
    )
    await session.execute(delete(WebAuthnChallenge).where(WebAuthnChallenge.user_id == user_id))

    # Financial partner history is intentionally retained, but the deleted
    # account must no longer be identifiable or able to receive attribution.
    now = datetime.now(UTC)
    profile_ids = (
        (
            await session.execute(
                select(PartnerProfile.partner_id).where(PartnerProfile.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    for partner_id in profile_ids:
        await session.execute(
            update(PartnerProfile)
            .where(PartnerProfile.partner_id == partner_id)
            .values(
                user_id=None,
                status="closed",
                display_label_snapshot=f"Deleted partner {int(partner_id)}",
                welcome_message=None,
                pause_reason=None,
                closed_at=now,
                updated_at=now,
            )
        )
    await session.execute(
        update(PartnerClient)
        .where(PartnerClient.client_user_id == user_id)
        .values(client_user_id=None, public_label_snapshot="Deleted client")
    )
    await session.execute(
        update(PartnerApplication)
        .where(PartnerApplication.user_id == user_id)
        .values(
            user_id=None,
            display_label_snapshot="Deleted account",
            message="",
            decision_message=None,
            status=case(
                (PartnerApplication.status == "pending", "canceled"),
                else_=PartnerApplication.status,
            ),
            decided_at=case(
                (PartnerApplication.status == "pending", now),
                else_=PartnerApplication.decided_at,
            ),
        )
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
        delete(FlexibleTrafficLimit).where(
            or_(
                FlexibleTrafficLimit.subscription_id.in_(subscription_ids),
                FlexibleTrafficLimit.payment_id.in_(payment_ids),
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
    # Keep the append-only audit trail when an account is removed.  The user
    # foreign keys are nullable specifically so historical events can survive
    # without blocking deletion of the personally identifiable user row.
    await session.execute(
        update(MessageLog).where(MessageLog.user_id == user_id).values(user_id=None)
    )
    await session.execute(
        update(MessageLog).where(MessageLog.target_user_id == user_id).values(target_user_id=None)
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
