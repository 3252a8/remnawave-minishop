from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AutoRenewCycle, Payment, Subscription, UserPaymentMethod

RETRYABLE_CYCLE_STATES = ("transport_retry", "financial_retry")
OPEN_CYCLE_STATES = (
    "scheduled",
    "dispatching",
    "transport_retry",
    "financial_retry",
    "waiting_provider",
)
BLOCKING_PAYMENT_STATUSES = (
    "pending",
    "pending_yookassa",
    "waiting_for_capture",
    "succeeded_pending_finalization",
    "succeeded_pending_review",
    "succeeded",
)


@dataclass(frozen=True, slots=True)
class AutoRenewDueCandidate:
    cycle_id: int
    subscription_id: int
    user_id: int


@dataclass(frozen=True, slots=True)
class AutoRenewSubscriptionCandidate:
    subscription_id: int
    user_id: int


def cycle_anchor_utc(value: datetime) -> date:
    value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return value.date()


async def _get_payment(
    session: AsyncSession,
    payment_id: int,
) -> Payment | None:
    return (
        await session.execute(
            select(Payment)
            .where(Payment.payment_id == payment_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def get_cycle(
    session: AsyncSession,
    cycle_id: int,
    *,
    fresh: bool = False,
) -> AutoRenewCycle | None:
    stmt = select(AutoRenewCycle).where(AutoRenewCycle.cycle_id == cycle_id)
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_cycle_by_subscription_anchor(
    session: AsyncSession,
    *,
    subscription_id: int,
    cycle_anchor: date,
    fresh: bool = False,
) -> AutoRenewCycle | None:
    stmt = select(AutoRenewCycle).where(
        AutoRenewCycle.subscription_id == subscription_id,
        AutoRenewCycle.cycle_anchor == cycle_anchor,
    )
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_or_get_cycle(
    session: AsyncSession,
    payload: dict[str, Any],
) -> tuple[AutoRenewCycle, bool]:
    subscription_id = int(payload["subscription_id"])
    cycle_anchor = payload["cycle_anchor"]
    if not isinstance(cycle_anchor, date):
        raise ValueError("cycle_anchor must be a date")

    existing = await get_cycle_by_subscription_anchor(
        session,
        subscription_id=subscription_id,
        cycle_anchor=cycle_anchor,
        fresh=True,
    )
    if existing is not None:
        return existing, False

    result = await session.execute(
        pg_insert(AutoRenewCycle)
        .values(**payload)
        .on_conflict_do_nothing(
            index_elements=[
                AutoRenewCycle.subscription_id,
                AutoRenewCycle.cycle_anchor,
            ]
        )
        .returning(AutoRenewCycle.cycle_id)
    )
    created = result.scalar_one_or_none() is not None
    cycle = await get_cycle_by_subscription_anchor(
        session,
        subscription_id=subscription_id,
        cycle_anchor=cycle_anchor,
        fresh=True,
    )
    if cycle is None:
        raise RuntimeError("Failed to load auto-renew cycle after atomic claim")
    return cycle, created


async def update_cycle(
    session: AsyncSession,
    cycle_id: int,
    **values: Any,
) -> AutoRenewCycle | None:
    values["updated_at"] = func.now()
    await session.execute(
        update(AutoRenewCycle).where(AutoRenewCycle.cycle_id == cycle_id).values(**values)
    )
    return await get_cycle(session, cycle_id, fresh=True)


async def record_payment_dispatch(
    session: AsyncSession,
    *,
    cycle_id: int,
    payment_id: int,
    attempt_number: int,
    transport_replays: int,
    fallback_retry_at: datetime,
    lease_expires_at: datetime,
) -> AutoRenewCycle | None:
    return await update_cycle(
        session,
        cycle_id,
        state="transport_retry",
        current_payment_id=payment_id,
        financial_attempts=attempt_number,
        transport_replays=transport_replays,
        next_attempt_at=fallback_retry_at,
        lease_expires_at=lease_expires_at,
        stopped_reason=None,
    )


async def prepare_payment_dispatch(
    session: AsyncSession,
    *,
    payment_id: int,
    request_snapshot: str,
    cycle_id: int,
    attempt_number: int,
    consent_version: int,
    payment_method_id: int | None,
) -> Payment | None:
    await session.execute(
        update(Payment)
        .where(Payment.payment_id == payment_id)
        .values(
            provider_request_snapshot=func.coalesce(
                Payment.provider_request_snapshot,
                request_snapshot,
            ),
            auto_renew_cycle_id=func.coalesce(Payment.auto_renew_cycle_id, cycle_id),
            renewal_attempt_number=func.coalesce(
                Payment.renewal_attempt_number,
                attempt_number,
            ),
            renewal_consent_version=func.coalesce(
                Payment.renewal_consent_version,
                consent_version,
            ),
            renewal_payment_method_id=func.coalesce(
                Payment.renewal_payment_method_id,
                payment_method_id,
            ),
            failure_kind=None,
            failure_http_status=None,
            failure_provider_code=None,
            updated_at=func.now(),
        )
    )
    return await _get_payment(session, payment_id)


async def mark_request_failure(
    session: AsyncSession,
    *,
    payment_id: int,
    status: str,
    failure_kind: str,
    http_status: int | None,
    provider_code: str | None,
) -> Payment | None:
    await session.execute(
        update(Payment)
        .where(Payment.payment_id == payment_id)
        .values(
            status=status,
            failure_kind=failure_kind,
            failure_http_status=http_status,
            failure_provider_code=provider_code,
            updated_at=func.now(),
        )
    )
    return await _get_payment(session, payment_id)


async def record_provider_cancellation(
    session: AsyncSession,
    *,
    payment_id: int,
    party: str | None,
    reason: str | None,
) -> Payment | None:
    await session.execute(
        update(Payment)
        .where(Payment.payment_id == payment_id)
        .values(
            provider_cancellation_party=party,
            provider_cancellation_reason=reason,
            updated_at=func.now(),
        )
    )
    return await _get_payment(session, payment_id)


async def mark_waiting_provider(
    session: AsyncSession,
    cycle_id: int,
) -> AutoRenewCycle | None:
    return await update_cycle(
        session,
        cycle_id,
        state="waiting_provider",
        next_attempt_at=None,
        lease_expires_at=None,
        last_failure_kind=None,
        last_http_status=None,
        last_provider_code=None,
    )


async def schedule_transport_retry(
    session: AsyncSession,
    *,
    cycle_id: int,
    next_attempt_at: datetime,
    failure_kind: str,
    http_status: int | None,
    provider_code: str | None,
    transport_replays: int,
) -> AutoRenewCycle | None:
    return await update_cycle(
        session,
        cycle_id,
        state="transport_retry",
        next_attempt_at=next_attempt_at,
        lease_expires_at=None,
        last_failure_kind=failure_kind,
        last_http_status=http_status,
        last_provider_code=provider_code,
        transport_replays=transport_replays,
    )


async def schedule_financial_retry(
    session: AsyncSession,
    *,
    cycle_id: int,
    next_attempt_at: datetime,
    cancellation_party: str | None,
    cancellation_reason: str,
) -> AutoRenewCycle | None:
    return await update_cycle(
        session,
        cycle_id,
        state="financial_retry",
        next_attempt_at=next_attempt_at,
        lease_expires_at=None,
        cancellation_party=cancellation_party,
        cancellation_reason=cancellation_reason,
        stopped_reason=None,
    )


async def defer_cycle(
    session: AsyncSession,
    cycle_id: int,
    *,
    next_attempt_at: datetime,
) -> AutoRenewCycle | None:
    return await update_cycle(
        session,
        cycle_id,
        next_attempt_at=next_attempt_at,
        lease_expires_at=None,
    )


async def stop_cycle(
    session: AsyncSession,
    cycle_id: int,
    reason: str,
    *,
    cancellation_party: str | None = None,
    cancellation_reason: str | None = None,
) -> AutoRenewCycle | None:
    return await update_cycle(
        session,
        cycle_id,
        state="stopped",
        next_attempt_at=None,
        lease_expires_at=None,
        stopped_reason=reason,
        cancellation_party=cancellation_party,
        cancellation_reason=cancellation_reason,
        completed_at=func.now(),
    )


async def stop_open_cycles_for_subscription(
    session: AsyncSession,
    subscription_id: int,
    reason: str,
) -> None:
    await session.execute(
        update(AutoRenewCycle)
        .where(
            AutoRenewCycle.subscription_id == subscription_id,
            AutoRenewCycle.state.in_(OPEN_CYCLE_STATES),
        )
        .values(
            state="stopped",
            next_attempt_at=None,
            lease_expires_at=None,
            stopped_reason=reason,
            completed_at=func.now(),
            updated_at=func.now(),
        )
    )


async def stop_open_cycles_for_user(
    session: AsyncSession,
    user_id: int,
    reason: str,
    *,
    provider: str | None = None,
) -> None:
    filters = [
        AutoRenewCycle.user_id == user_id,
        AutoRenewCycle.state.in_(OPEN_CYCLE_STATES),
    ]
    if provider:
        filters.append(func.lower(AutoRenewCycle.provider) == provider.strip().lower())
    await session.execute(
        update(AutoRenewCycle)
        .where(*filters)
        .values(
            state="stopped",
            next_attempt_at=None,
            lease_expires_at=None,
            stopped_reason=reason,
            completed_at=func.now(),
            updated_at=func.now(),
        )
    )


async def mark_retry_notified(
    session: AsyncSession,
    cycle_id: int,
) -> None:
    await session.execute(
        update(AutoRenewCycle)
        .where(AutoRenewCycle.cycle_id == cycle_id)
        .values(retry_notified_at=func.now(), updated_at=func.now())
    )


async def list_due_cycles(
    session: AsyncSession,
    *,
    limit: int,
) -> list[AutoRenewDueCandidate]:
    now = datetime.now(UTC)
    stmt = (
        select(
            AutoRenewCycle.cycle_id,
            AutoRenewCycle.subscription_id,
            AutoRenewCycle.user_id,
        )
        .where(
            AutoRenewCycle.state.in_(RETRYABLE_CYCLE_STATES),
            AutoRenewCycle.next_attempt_at.isnot(None),
            AutoRenewCycle.next_attempt_at <= now,
            or_(
                AutoRenewCycle.lease_expires_at.is_(None),
                AutoRenewCycle.lease_expires_at <= now,
            ),
        )
        .order_by(AutoRenewCycle.next_attempt_at.asc(), AutoRenewCycle.cycle_id.asc())
        .limit(max(1, int(limit)))
    )
    return [
        AutoRenewDueCandidate(
            cycle_id=int(cycle_id),
            subscription_id=int(subscription_id),
            user_id=int(user_id),
        )
        for cycle_id, subscription_id, user_id in (await session.execute(stmt)).all()
    ]


async def claim_due_cycle(
    session: AsyncSession,
    cycle_id: int,
    *,
    lease_seconds: int,
) -> AutoRenewCycle | None:
    now = datetime.now(UTC)
    stmt = (
        select(AutoRenewCycle)
        .where(
            AutoRenewCycle.cycle_id == cycle_id,
            AutoRenewCycle.state.in_(RETRYABLE_CYCLE_STATES),
            AutoRenewCycle.next_attempt_at.isnot(None),
            AutoRenewCycle.next_attempt_at <= now,
            or_(
                AutoRenewCycle.lease_expires_at.is_(None),
                AutoRenewCycle.lease_expires_at <= now,
            ),
        )
        .with_for_update(skip_locked=True)
    )
    cycle = (await session.execute(stmt)).scalar_one_or_none()
    if cycle is None:
        return None
    cycle.lease_expires_at = now + timedelta(seconds=max(30, int(lease_seconds)))
    cycle.updated_at = now
    await session.flush()
    return cycle


async def cycle_has_blocking_payment(
    session: AsyncSession,
    cycle_id: int,
    *,
    exclude_payment_id: int | None = None,
) -> bool:
    filters = [
        Payment.auto_renew_cycle_id == cycle_id,
        func.lower(Payment.status).in_(BLOCKING_PAYMENT_STATUSES),
    ]
    if exclude_payment_id is not None:
        filters.append(Payment.payment_id != exclude_payment_id)
    stmt = select(exists().where(*filters))
    return bool((await session.execute(stmt)).scalar())


async def validate_dispatch_context_for_update(
    session: AsyncSession,
    cycle_id: int,
) -> bool:
    """Lock consent and saved-method rows for the final pre-provider check."""

    cycle = (
        await session.execute(
            select(AutoRenewCycle).where(AutoRenewCycle.cycle_id == cycle_id).with_for_update()
        )
    ).scalar_one_or_none()
    if cycle is None or cycle.state not in OPEN_CYCLE_STATES:
        return False
    subscription = (
        await session.execute(
            select(Subscription)
            .where(Subscription.subscription_id == cycle.subscription_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if (
        subscription is None
        or not bool(subscription.is_active)
        or not bool(subscription.auto_renew_enabled)
        or str(subscription.provider or "").strip().lower()
        != str(cycle.provider or "").strip().lower()
        or int(subscription.auto_renew_consent_version or 0) != int(cycle.consent_version or 0)
    ):
        return False
    if cycle.payment_method_id is None:
        return True
    payment_method = (
        await session.execute(
            select(UserPaymentMethod)
            .where(
                UserPaymentMethod.method_id == cycle.payment_method_id,
                UserPaymentMethod.user_id == cycle.user_id,
                func.lower(UserPaymentMethod.provider) == str(cycle.provider or "").strip().lower(),
                UserPaymentMethod.provider_payment_method_id == cycle.payment_method_provider_id,
                UserPaymentMethod.is_default.is_(True),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    return payment_method is not None


async def mark_cycle_succeeded_for_payment(
    session: AsyncSession,
    payment_id: int,
) -> None:
    cycle_id = (
        await session.execute(
            select(Payment.auto_renew_cycle_id).where(Payment.payment_id == payment_id)
        )
    ).scalar_one_or_none()
    if cycle_id is None:
        return
    await mark_cycle_succeeded(session, int(cycle_id))


async def mark_cycle_succeeded(
    session: AsyncSession,
    cycle_id: int,
) -> None:
    await session.execute(
        update(AutoRenewCycle)
        .where(AutoRenewCycle.cycle_id == cycle_id)
        .values(
            state="succeeded",
            next_attempt_at=None,
            lease_expires_at=None,
            stopped_reason=None,
            completed_at=func.now(),
            updated_at=func.now(),
        )
    )


async def mark_cycle_succeeded_for_record(
    session: AsyncSession,
    payment: Payment,
) -> None:
    cycle_id = getattr(payment, "auto_renew_cycle_id", None)
    if cycle_id is not None:
        await mark_cycle_succeeded(session, int(cycle_id))


async def list_due_subscriptions(
    session: AsyncSession,
    *,
    providers: tuple[str, ...],
    hours_ahead: int,
    limit: int,
) -> list[AutoRenewSubscriptionCandidate]:
    provider_keys = tuple(
        dict.fromkeys(str(provider or "").strip().lower() for provider in providers)
    )
    provider_keys = tuple(provider for provider in provider_keys if provider)
    if not provider_keys:
        return []
    now = datetime.now(UTC)
    cutoff = now + timedelta(hours=max(1, int(hours_ahead)))
    rows = (
        await session.execute(
            select(Subscription.subscription_id, Subscription.user_id)
            .where(
                Subscription.is_active.is_(True),
                Subscription.auto_renew_enabled.is_(True),
                func.lower(Subscription.provider).in_(provider_keys),
                Subscription.end_date > now,
                Subscription.end_date <= cutoff,
            )
            .order_by(Subscription.end_date.asc(), Subscription.subscription_id.asc())
            .limit(max(1, int(limit)))
        )
    ).all()
    return [
        AutoRenewSubscriptionCandidate(
            subscription_id=int(subscription_id),
            user_id=int(user_id),
        )
        for subscription_id, user_id in rows
    ]
