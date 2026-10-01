"""Invitation bonus days a user has actually received.

The period accrual ledger (``referral_period_accruals``) records every invitation
bonus decided since migration ``0094_referral_accruals``. That migration marked all
earlier payments as processed without writing ledger rows, so bonuses granted before
it ran left no record anywhere. The total is therefore complete only for users whose
invitees made no bonus-eligible purchase before the ledger began; for everyone else
it covers the bonuses granted since then and carries that starting point.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import DateTime, and_, exists, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from db.models import Payment, User
from db.referral_accrual_models import ReferralPeriodAccrual

LEDGER_MIGRATION_ID = "0094_referral_accruals"


@dataclass(frozen=True)
class ReceivedInviterBonus:
    """Invitation bonus days credited to a user.

    ``since`` is set when part of the user's history predates the ledger: ``days``
    then counts only the bonuses granted from that moment on.
    """

    days: int
    since: datetime | None = None


async def ledger_started_at(session: AsyncSession) -> datetime | None:
    """When this database began recording invitation period accruals.

    The migrator's own record of the run that created the ledger is the boundary;
    ``None`` means the schema was built without the migrator and has no history.
    """
    statement = text("SELECT applied_at FROM schema_migrations WHERE id = :revision").columns(
        applied_at=DateTime(timezone=True)
    )
    started_at = await session.scalar(statement, {"revision": LEDGER_MIGRATION_ID})
    return started_at if isinstance(started_at, datetime) else None


def _bonus_eligible_purchase() -> ColumnElement[bool]:
    """A paid subscription purchase; a later refund does not undo its bonus."""
    return and_(
        Payment.status.in_(("succeeded", "refunded", "reversed")),
        Payment.amount > 0,
        or_(
            Payment.sale_mode == "subscription",
            Payment.sale_mode.like("subscription@%"),
            Payment.sale_mode.like("subscription|%"),
        ),
    )


async def get_received_inviter_bonus(session: AsyncSession, user_id: int) -> ReceivedInviterBonus:
    """Invitation bonus days credited to ``user_id`` and where the count starts."""
    started_at = await ledger_started_at(session)
    purchased_before_ledger = False
    if started_at is not None:
        purchased_before_ledger = bool(
            await session.scalar(
                select(
                    exists().where(
                        User.referred_by_id == user_id,
                        Payment.user_id == User.user_id,
                        Payment.created_at < started_at,
                        _bonus_eligible_purchase(),
                    )
                )
            )
        )
    received = await session.scalar(
        select(func.coalesce(func.sum(ReferralPeriodAccrual.days), 0)).where(
            ReferralPeriodAccrual.user_id == user_id,
            ReferralPeriodAccrual.role == "inviter",
            ReferralPeriodAccrual.state == "applied",
        )
    )
    return ReceivedInviterBonus(
        days=int(received or 0),
        since=started_at if purchased_before_ledger else None,
    )
