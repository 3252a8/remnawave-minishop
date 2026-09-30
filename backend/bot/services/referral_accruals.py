"""Persist decisions inside the successful payment transaction, before panel work."""

from datetime import UTC, datetime

from sqlalchemy import false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.referral_accrual_models import ReferralPeriodAccrual


async def enqueue_period_accrual(
    session: AsyncSession,
    *,
    payment_id: int,
    referee_user_id: int,
    user_id: int,
    role: str,
    days: int,
    tariff_key: str | None,
    one_time: bool,
) -> None:
    existing = await session.scalar(
        select(ReferralPeriodAccrual.accrual_id).where(
            or_(
                (ReferralPeriodAccrual.payment_id == payment_id)
                & (ReferralPeriodAccrual.role == role),
                (ReferralPeriodAccrual.one_time_referee_id == referee_user_id)
                & (ReferralPeriodAccrual.role == role)
                if one_time
                else false(),
            )
        )
    )
    if existing is not None:
        return
    session.add(
        ReferralPeriodAccrual(
            payment_id=payment_id,
            referee_user_id=referee_user_id,
            user_id=user_id,
            role=role,
            days=days,
            tariff_key=tariff_key,
            one_time_referee_id=referee_user_id if one_time else None,
        )
    )
    await session.flush()


def utc_date(value: object) -> datetime | None:
    """SQLite fixtures and PostgreSQL timestamps use the same aware comparison."""
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
