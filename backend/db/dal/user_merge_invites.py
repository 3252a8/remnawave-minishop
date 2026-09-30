"""Retain invitation identifiers and reserved period during account merge."""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import LegacyReferralCode, Payment, PromoCodeActivation, User
from db.referral_accrual_models import ReferralPeriodAccrual


def preserve_native_invitation(session: AsyncSession, source: User, target: User) -> None:
    if (
        source.referral_code
        and target.referral_code
        and source.referral_code != target.referral_code
    ):
        session.add(
            LegacyReferralCode(
                source="core-account-merge",
                code=source.referral_code,
                user_id=target.user_id,
                is_active=True,
            )
        )
    reserved = []
    for user in (source, target):
        date = getattr(user, "period_accrual_reserved_until", None)
        if isinstance(date, datetime):
            reserved.append(date.replace(tzinfo=UTC) if date.tzinfo is None else date)
    if reserved:
        target.period_accrual_reserved_until = max(reserved)


async def merge_period_accruals(
    session: AsyncSession, source_user_id: int, target_user_id: int
) -> None:
    for role in ("inviter", "referee"):
        target_claim = (
            await session.execute(
                select(ReferralPeriodAccrual.accrual_id).where(
                    ReferralPeriodAccrual.one_time_referee_id == target_user_id,
                    ReferralPeriodAccrual.role == role,
                )
            )
        ).scalar_one_or_none()
        if target_claim is None:
            await session.execute(
                update(ReferralPeriodAccrual)
                .where(
                    ReferralPeriodAccrual.one_time_referee_id == source_user_id,
                    ReferralPeriodAccrual.role == role,
                )
                .values(one_time_referee_id=target_user_id)
            )
    await session.execute(
        update(ReferralPeriodAccrual)
        .where(ReferralPeriodAccrual.user_id == source_user_id)
        .values(user_id=target_user_id)
    )
    await session.execute(
        update(ReferralPeriodAccrual)
        .where(ReferralPeriodAccrual.referee_user_id == source_user_id)
        .values(referee_user_id=target_user_id)
    )


async def reassign_invitation_aliases(
    session: AsyncSession, source_user_id: int, target_user_id: int
) -> None:
    await session.execute(
        update(LegacyReferralCode)
        .where(LegacyReferralCode.user_id == source_user_id)
        .values(user_id=target_user_id)
    )


async def reassign_invitation_relations(
    session: AsyncSession, source_user_id: int, target_user_id: int
) -> None:
    await merge_period_accruals(session, source_user_id, target_user_id)
    await reassign_invitation_aliases(session, source_user_id, target_user_id)
    for model in (Payment, PromoCodeActivation):
        await session.execute(
            update(model).where(model.user_id == source_user_id).values(user_id=target_user_id)
        )
