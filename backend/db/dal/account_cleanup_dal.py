"""Conservative, bounded candidate selection; no external calls in this layer."""

import hashlib
from datetime import datetime, timedelta

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from db.auth_models import AccountRole
from db.balance_models import UserBalanceLedgerEntry
from db.cleaned_trial_models import AccountCleanupIntent, CleanedTrialIdentity
from db.gift_models import SubscriptionGift
from db.models import (
    LegacyImportMapping,
    Payment,
    PromoCodeActivation,
    Subscription,
    SupportTicket,
    User,
    UserExternalIdentity,
    UserPaymentMethod,
)
from db.partner_models import PartnerApplication, PartnerClient, PartnerProfile


def trial_identity_key(telegram_id: int) -> str:
    return hashlib.sha256(f"telegram:{telegram_id}".encode()).hexdigest()


async def get_cleanup_intent(session: AsyncSession, account_id: str) -> AccountCleanupIntent | None:
    return await session.get(AccountCleanupIntent, account_id)


async def save_cleanup_intent(
    session: AsyncSession, account_id: str, panel_uuids: str, now: datetime
) -> None:
    await session.merge(
        AccountCleanupIntent(account_id=account_id, panel_uuids=panel_uuids, started_at=now)
    )


async def delete_cleanup_intent(session: AsyncSession, account_id: str) -> None:
    intent = await get_cleanup_intent(session, account_id)
    if intent is not None:
        await session.delete(intent)


async def has_cleaned_trial(session: AsyncSession, telegram_id: int) -> bool:
    return await session.get(CleanedTrialIdentity, trial_identity_key(telegram_id)) is not None


async def remember_cleaned_trial(session: AsyncSession, telegram_id: int, now: datetime) -> None:
    if not await has_cleaned_trial(session, telegram_id):
        session.add(
            CleanedTrialIdentity(identity_key=trial_identity_key(telegram_id), cleaned_at=now)
        )


def _candidate_statement(settings: Settings, now: datetime):
    no_trial = and_(
        settings.UNUSED_ACCOUNTS_NO_TRIAL_ENABLED,
        User.registration_date <= now - timedelta(days=settings.UNUSED_ACCOUNTS_NO_TRIAL_DAYS),
        ~exists().where(Subscription.user_id == User.user_id),
    )
    unused_trial = and_(
        settings.UNUSED_ACCOUNTS_UNUSED_TRIAL_ENABLED,
        exists().where(Subscription.user_id == User.user_id, Subscription.provider == "trial"),
        ~exists().where(
            Subscription.user_id == User.user_id,
            or_(
                Subscription.provider.is_(None),
                Subscription.provider != "trial",
                Subscription.start_date.is_(None),
                Subscription.start_date
                > now - timedelta(days=settings.UNUSED_ACCOUNTS_UNUSED_TRIAL_DAYS),
                Subscription.end_date > now,
                Subscription.last_connected_at.is_not(None),
                Subscription.traffic_used_bytes > 0,
                Subscription.premium_used_bytes > 0,
            ),
        ),
    )
    protected_records = (
        AccountRole.user_id,
        Payment.user_id,
        PromoCodeActivation.user_id,
        UserBalanceLedgerEntry.user_id,
        PartnerProfile.user_id,
        PartnerApplication.user_id,
        PartnerClient.client_user_id,
        SupportTicket.user_id,
        UserExternalIdentity.user_id,
        UserPaymentMethod.user_id,
    )
    return select(User.user_id).where(
        or_(no_trial, unused_trial),
        User.telegram_id.is_not(None),
        User.email.is_(None),
        User.is_banned.is_not(True),
        User.trial_eligibility_reset_at.is_(None),
        or_(User.lifetime_used_traffic_bytes.is_(None), User.lifetime_used_traffic_bytes == 0),
        User.telegram_id.not_in(settings.ADMIN_IDS),
        User.user_id.not_in(settings.ADMIN_IDS),
        *(~exists().where(column == User.user_id) for column in protected_records),
        ~exists().where(
            or_(
                SubscriptionGift.purchaser_id == User.user_id,
                SubscriptionGift.recipient_id == User.user_id,
            )
        ),
        ~exists().where(
            LegacyImportMapping.target_table == "users",
            LegacyImportMapping.target_id == User.user_id.cast(LegacyImportMapping.target_id.type),
        ),
    )


async def cleanup_candidate_ids(
    session: AsyncSession, settings: Settings, now: datetime, after_id: int, limit: int = 100
) -> list[int]:
    statement = (
        _candidate_statement(settings, now)
        .where(User.user_id > after_id)
        .order_by(User.user_id)
        .limit(limit)
    )
    return [int(value) for value in (await session.execute(statement)).scalars()]


async def still_cleanup_candidate(
    session: AsyncSession, settings: Settings, now: datetime, user_id: int
) -> bool:
    result = await session.execute(
        _candidate_statement(settings, now).where(User.user_id == user_id)
    )
    return result.scalar_one_or_none() is not None


async def panel_identity_is_shared(session: AsyncSession, user_id: int, panel_uuid: str) -> bool:
    return bool(
        await session.scalar(
            select(
                or_(
                    exists().where(User.user_id != user_id, User.panel_user_uuid == panel_uuid),
                    exists().where(
                        Subscription.user_id != user_id, Subscription.panel_user_uuid == panel_uuid
                    ),
                )
            )
        )
    )
