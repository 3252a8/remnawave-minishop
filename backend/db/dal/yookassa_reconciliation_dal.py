"""Durable polling state for YooKassa payments, separate from fulfillment."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Payment

PAYMENT_STATUS_PENDING_REVIEW = "succeeded_pending_review"
YOOKASSA_FINALIZATION_RETRY_KIND = "fulfillment_retryable"
YOOKASSA_FINALIZATION_RETRY_SECONDS = 300
_RECONCILABLE_STATUSES = (
    "pending_yookassa",
    "pending",
    "waiting_for_capture",
    "succeeded_pending_finalization",
)


@dataclass(frozen=True, slots=True)
class YooKassaReconciliationCandidate:
    payment_id: int
    provider_payment_id: str


async def list_yookassa_reconciliation_candidates(
    session: AsyncSession,
    *,
    limit: int = 100,
    grace_seconds: int = 30,
) -> list[YooKassaReconciliationCandidate]:
    """Poll pending orders; failed fulfillment waits at least five minutes."""

    now = datetime.now(UTC)
    grace = max(0, int(grace_seconds))
    provider_payment_id = func.coalesce(Payment.yookassa_payment_id, Payment.provider_payment_id)
    last_activity_at = func.coalesce(Payment.updated_at, Payment.created_at)
    retrying = func.coalesce(Payment.failure_kind, "") == YOOKASSA_FINALIZATION_RETRY_KIND
    stmt = (
        select(Payment.payment_id, provider_payment_id)
        .where(
            func.lower(Payment.provider) == "yookassa",
            func.lower(Payment.status).in_(_RECONCILABLE_STATUSES),
            provider_payment_id.isnot(None),
            or_(
                and_(~retrying, last_activity_at <= now - timedelta(seconds=grace)),
                and_(
                    retrying,
                    last_activity_at
                    <= now - timedelta(seconds=max(grace, YOOKASSA_FINALIZATION_RETRY_SECONDS)),
                ),
            ),
        )
        .order_by(last_activity_at.asc(), Payment.payment_id.asc())
        .limit(max(1, int(limit)))
    )
    rows = (await session.execute(stmt)).all()
    return [
        YooKassaReconciliationCandidate(int(payment_id), str(remote_id))
        for payment_id, remote_id in rows
        if remote_id
    ]


async def mark_yookassa_reconciliation_checked(session: AsyncSession, payment_id: int) -> None:
    """Rotate an unresolved order, including errors, behind other candidates."""

    await session.execute(
        update(Payment)
        .where(
            Payment.payment_id == payment_id,
            func.lower(Payment.provider) == "yookassa",
            func.lower(Payment.status).in_(_RECONCILABLE_STATUSES),
        )
        .values(updated_at=func.now())
    )


async def mark_yookassa_finalization_retry(
    session: AsyncSession, payment_id: int, provider_payment_id: str
) -> None:
    """Remember confirmed receipt after rollback without downgrading a settled order."""

    await session.execute(
        update(Payment)
        .where(
            Payment.payment_id == payment_id,
            func.lower(Payment.provider) == "yookassa",
            func.coalesce(Payment.yookassa_payment_id, Payment.provider_payment_id)
            == provider_payment_id,
            func.lower(Payment.status).in_(_RECONCILABLE_STATUSES),
        )
        .values(
            status="succeeded_pending_finalization",
            failure_kind=YOOKASSA_FINALIZATION_RETRY_KIND,
            updated_at=func.now(),
        )
    )
