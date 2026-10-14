"""Account deletion with dependent-record cleanup and retained financial history."""

from datetime import UTC, datetime

from sqlalchemy import String, and_, case, cast, delete, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models import (
    AdAttribution,
    EmailVerificationCode,
    FlexibleTrafficLimit,
    HwidDevicePurchase,
    LegacyImportMapping,
    LegacyReferralCode,
    MessageLog,
    Payment,
    PromoCodeActivation,
    QrLoginRequest,
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
from ..partner_models import PartnerApplication, PartnerClient, PartnerProfile
from .user_reads_dal import get_user_by_id


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
    await session.execute(delete(QrLoginRequest).where(QrLoginRequest.user_id == user_id))

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
    # Null user references to retain the audit trail after account deletion.
    await session.execute(
        update(MessageLog).where(MessageLog.user_id == user_id).values(user_id=None)
    )
    await session.execute(
        update(MessageLog).where(MessageLog.target_user_id == user_id).values(target_user_id=None)
    )
    from bot.services.advertising.accounts import delete_account_evidence

    await delete_account_evidence(session, user_id)
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
    from .extension_accounts_dal import delete_for_user as delete_extension_account

    await delete_extension_account(session, user_id)
    await session.execute(delete(Payment).where(Payment.user_id == user_id))
    await session.execute(delete(Subscription).where(Subscription.user_id == user_id))

    await session.delete(user)
    await session.flush()
    return True
