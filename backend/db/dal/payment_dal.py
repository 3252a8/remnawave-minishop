import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import Date, and_, case, cast, func, or_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload

from db.models import Payment, User

logger = logging.getLogger(__name__)

_PAYMENT_STATUS_SUCCEEDED = "succeeded"
_PAYMENT_STATUS_PENDING_FINALIZATION = "succeeded_pending_finalization"
_YOOKASSA_RECONCILABLE_STATUSES = (
    "pending_yookassa",
    "pending",
    "waiting_for_capture",
    _PAYMENT_STATUS_PENDING_FINALIZATION,
)


@dataclass(frozen=True, slots=True)
class YooKassaReconciliationCandidate:
    payment_id: int
    provider_payment_id: str


def _normalize_payment_status(status: Any) -> str:
    return str(status or "").strip().lower()


def _would_overwrite_succeeded_payment(current_status: Any, new_status: Any) -> bool:
    return (
        _normalize_payment_status(current_status) == _PAYMENT_STATUS_SUCCEEDED
        and _normalize_payment_status(new_status) != _PAYMENT_STATUS_SUCCEEDED
    )


def _decimal_order_value(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        normalized = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return normalized if normalized.is_finite() else None


def _datetime_order_value(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _validate_existing_provider_payment_order(
    payment: Payment,
    *,
    user_id: int,
    amount: float,
    currency: str,
    months: int,
    provider: str,
    sale_mode: str | None,
    tariff_key: str | None,
    purchased_gb: float | None,
    purchased_hwid_devices: int | None,
    hwid_valid_from: Any | None,
    hwid_valid_until: Any | None,
    hwid_pricing_period_months: int | None,
    hwid_proration_ratio: float | None,
    hwid_full_price: float | None,
    hwid_traffic_bonus_bytes: int | None,
) -> None:
    """Ensure a provider id cannot be rebound to a different entitlement."""
    comparisons = {
        "user_id": (int(getattr(payment, "user_id", 0)), int(user_id)),
        "amount": (
            _decimal_order_value(getattr(payment, "amount", None)),
            _decimal_order_value(amount),
        ),
        "currency": (
            str(getattr(payment, "currency", "") or "").strip().upper(),
            str(currency or "").strip().upper(),
        ),
        "subscription_duration_months": (
            getattr(payment, "subscription_duration_months", None),
            months,
        ),
        "provider": (
            str(getattr(payment, "provider", "") or "").strip().lower(),
            str(provider or "").strip().lower(),
        ),
        "sale_mode": (
            str(getattr(payment, "sale_mode", "") or "").strip() or None,
            str(sale_mode or "").strip() or None,
        ),
        "tariff_key": (
            str(getattr(payment, "tariff_key", "") or "").strip() or None,
            str(tariff_key or "").strip() or None,
        ),
        "purchased_gb": (
            _decimal_order_value(getattr(payment, "purchased_gb", None)),
            _decimal_order_value(purchased_gb),
        ),
        "purchased_hwid_devices": (
            getattr(payment, "purchased_hwid_devices", None),
            purchased_hwid_devices,
        ),
        "hwid_valid_from": (
            _datetime_order_value(getattr(payment, "hwid_valid_from", None)),
            _datetime_order_value(hwid_valid_from),
        ),
        "hwid_valid_until": (
            _datetime_order_value(getattr(payment, "hwid_valid_until", None)),
            _datetime_order_value(hwid_valid_until),
        ),
        "hwid_pricing_period_months": (
            getattr(payment, "hwid_pricing_period_months", None),
            hwid_pricing_period_months,
        ),
        "hwid_proration_ratio": (
            _decimal_order_value(getattr(payment, "hwid_proration_ratio", None)),
            _decimal_order_value(hwid_proration_ratio),
        ),
        "hwid_full_price": (
            _decimal_order_value(getattr(payment, "hwid_full_price", None)),
            _decimal_order_value(hwid_full_price),
        ),
        "hwid_traffic_bonus_bytes": (
            getattr(payment, "hwid_traffic_bonus_bytes", None),
            hwid_traffic_bonus_bytes,
        ),
    }
    mismatched = [field for field, (stored, expected) in comparisons.items() if stored != expected]
    if mismatched:
        raise ValueError(
            "Provider payment id already belongs to a different order: " + ", ".join(mismatched)
        )


async def list_yookassa_reconciliation_candidates(
    session: AsyncSession,
    *,
    limit: int = 100,
    grace_seconds: int = 30,
) -> list[YooKassaReconciliationCandidate]:
    """Return old pending YooKassa orders that can be polled safely.

    The provider identifier is persisted before an order becomes eligible.
    ``updated_at`` is also used as the last-poll timestamp so a permanently
    pending order cannot monopolize the front of a bounded batch.
    """

    cutoff = datetime.now(UTC) - timedelta(seconds=max(0, int(grace_seconds)))
    provider_payment_id = func.coalesce(
        Payment.yookassa_payment_id,
        Payment.provider_payment_id,
    )
    last_activity_at = func.coalesce(Payment.updated_at, Payment.created_at)
    stmt = (
        select(Payment.payment_id, provider_payment_id)
        .where(
            func.lower(Payment.provider) == "yookassa",
            func.lower(Payment.status).in_(_YOOKASSA_RECONCILABLE_STATUSES),
            provider_payment_id.isnot(None),
            last_activity_at <= cutoff,
        )
        .order_by(last_activity_at.asc(), Payment.payment_id.asc())
        .limit(max(1, int(limit)))
    )
    rows = (await session.execute(stmt)).all()
    return [
        YooKassaReconciliationCandidate(
            payment_id=int(payment_id),
            provider_payment_id=str(remote_id),
        )
        for payment_id, remote_id in rows
        if remote_id
    ]


async def mark_yookassa_reconciliation_checked(
    session: AsyncSession,
    payment_id: int,
) -> None:
    """Rotate an unresolved order to the back of the reconciliation queue."""

    await session.execute(
        update(Payment)
        .where(
            Payment.payment_id == payment_id,
            func.lower(Payment.provider) == "yookassa",
            func.lower(Payment.status).in_(_YOOKASSA_RECONCILABLE_STATUSES),
        )
        .values(updated_at=func.now())
    )


async def _validate_payment_record_references(
    session: AsyncSession,
    payment_data: dict[str, Any],
) -> None:
    """Reject a payment payload whose referenced rows do not exist."""

    from .user_dal import get_user_by_id

    user = await get_user_by_id(session, payment_data["user_id"])
    if not user:
        raise ValueError(f"User with id {payment_data['user_id']} not found for creating payment.")

    if payment_data.get("promo_code_id"):
        from .promo_code_dal import get_promo_code_by_id

        promo = await get_promo_code_by_id(session, payment_data["promo_code_id"])
        if not promo:
            raise ValueError(f"Promo code with id {payment_data['promo_code_id']} not found.")


async def create_payment_record(session: AsyncSession, payment_data: dict[str, Any]) -> Payment:
    await _validate_payment_record_references(session, payment_data)

    new_payment = Payment(**payment_data)
    session.add(new_payment)
    await session.flush()
    await session.refresh(new_payment)
    logger.info(
        "Payment record %s created for user %s", new_payment.payment_id, new_payment.user_id
    )
    return new_payment


async def get_payment_by_idempotence_key(
    session: AsyncSession,
    idempotence_key: str,
    *,
    fresh: bool = False,
) -> Payment | None:
    """Fetch a payment by the immutable provider idempotence key."""
    key = str(idempotence_key or "").strip()
    if not key:
        return None
    stmt = select(Payment).where(Payment.idempotence_key == key)
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_or_get_payment_record_by_idempotence_key(
    session: AsyncSession,
    payment_data: dict[str, Any],
) -> tuple[Payment, bool]:
    """Atomically claim one local payment row for an idempotent provider call.

    PostgreSQL resolves concurrent ``ON CONFLICT`` attempts against the unique
    ``payments.idempotence_key`` constraint, so only one caller can own the
    order before it reaches an external payment API.  The caller commits the
    newly created row before issuing that API call; a concurrent caller then
    loads the same row and can safely reuse the provider idempotence key.
    """
    payload = dict(payment_data)
    idempotence_key = str(payload.get("idempotence_key") or "").strip()
    if not idempotence_key:
        raise ValueError("idempotence_key is required for idempotent payment creation.")
    payload["idempotence_key"] = idempotence_key

    existing = await get_payment_by_idempotence_key(session, idempotence_key, fresh=True)
    if existing:
        return existing, False

    await _validate_payment_record_references(session, payload)
    stmt = (
        pg_insert(Payment)
        .values(**payload)
        .on_conflict_do_nothing(index_elements=[Payment.idempotence_key])
        .returning(Payment.payment_id)
    )
    result = await session.execute(stmt)
    created = result.scalar_one_or_none() is not None

    payment = await get_payment_by_idempotence_key(session, idempotence_key, fresh=True)
    if payment is None:
        raise RuntimeError(
            f"Failed to load payment after claiming its idempotence key {idempotence_key!r}."
        )
    if created:
        logger.info(
            "Payment record %s created with idempotence key %s",
            payment.payment_id,
            idempotence_key,
        )
    return payment, created


async def get_payment_by_provider_payment_id(
    session: AsyncSession,
    provider: str,
    provider_payment_id: str,
    *,
    fresh: bool = False,
) -> Payment | None:
    """Fetch a payment by provider-specific identifier."""
    provider_key = str(provider or "").strip().lower()
    remote_id = str(provider_payment_id or "").strip()
    if not provider_key or not remote_id:
        return None
    stmt = select(Payment).where(
        Payment.provider == provider_key,
        Payment.provider_payment_id == remote_id,
    )
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def ensure_payment_with_provider_id(
    session: AsyncSession,
    *,
    user_id: int,
    amount: float,
    currency: str,
    months: int,
    description: str,
    provider: str,
    provider_payment_id: str,
    sale_mode: str | None = None,
    tariff_key: str | None = None,
    purchased_gb: float | None = None,
    purchased_hwid_devices: int | None = None,
    hwid_valid_from: Any | None = None,
    hwid_valid_until: Any | None = None,
    hwid_pricing_period_months: int | None = None,
    hwid_proration_ratio: float | None = None,
    hwid_full_price: float | None = None,
    hwid_traffic_bonus_bytes: int | None = None,
) -> Payment:
    """Atomically create or validate one order for a provider payment id."""
    provider_key = str(provider or "").strip().lower()
    if not provider_key:
        raise ValueError("provider is required for payment creation.")
    remote_id = str(provider_payment_id or "").strip()
    if not remote_id:
        raise ValueError("provider_payment_id is required for payment creation.")

    existing = await get_payment_by_provider_payment_id(
        session,
        provider_key,
        remote_id,
        fresh=True,
    )
    if existing:
        _validate_existing_provider_payment_order(
            existing,
            user_id=user_id,
            amount=amount,
            currency=currency,
            months=months,
            provider=provider_key,
            sale_mode=sale_mode,
            tariff_key=tariff_key,
            purchased_gb=purchased_gb,
            purchased_hwid_devices=purchased_hwid_devices,
            hwid_valid_from=hwid_valid_from,
            hwid_valid_until=hwid_valid_until,
            hwid_pricing_period_months=hwid_pricing_period_months,
            hwid_proration_ratio=hwid_proration_ratio,
            hwid_full_price=hwid_full_price,
            hwid_traffic_bonus_bytes=hwid_traffic_bonus_bytes,
        )
        return existing

    pending_status = f"pending_{provider_key}"
    payment_payload: dict[str, Any] = {
        "user_id": user_id,
        "amount": float(amount),
        "currency": currency,
        "status": pending_status,
        "description": description,
        "subscription_duration_months": months,
        "provider_payment_id": remote_id,
        "provider": provider_key,
    }
    optional_fields = {
        "sale_mode": sale_mode,
        "tariff_key": tariff_key,
        "purchased_gb": purchased_gb,
        "purchased_hwid_devices": purchased_hwid_devices,
        "hwid_valid_from": hwid_valid_from,
        "hwid_valid_until": hwid_valid_until,
        "hwid_pricing_period_months": hwid_pricing_period_months,
        "hwid_proration_ratio": hwid_proration_ratio,
        "hwid_full_price": hwid_full_price,
        "hwid_traffic_bonus_bytes": hwid_traffic_bonus_bytes,
    }
    payment_payload.update(
        {field: value for field, value in optional_fields.items() if value is not None}
    )
    await _validate_payment_record_references(session, payment_payload)
    stmt = (
        pg_insert(Payment)
        .values(**payment_payload)
        .on_conflict_do_nothing(index_elements=[Payment.provider, Payment.provider_payment_id])
        .returning(Payment.payment_id)
    )
    result = await session.execute(stmt)
    created = result.scalar_one_or_none() is not None

    payment = await get_payment_by_provider_payment_id(
        session,
        provider_key,
        remote_id,
        fresh=True,
    )
    if payment is None:
        raise RuntimeError(f"Failed to load payment after claiming provider id {remote_id!r}.")
    _validate_existing_provider_payment_order(
        payment,
        user_id=user_id,
        amount=amount,
        currency=currency,
        months=months,
        provider=provider_key,
        sale_mode=sale_mode,
        tariff_key=tariff_key,
        purchased_gb=purchased_gb,
        purchased_hwid_devices=purchased_hwid_devices,
        hwid_valid_from=hwid_valid_from,
        hwid_valid_until=hwid_valid_until,
        hwid_pricing_period_months=hwid_pricing_period_months,
        hwid_proration_ratio=hwid_proration_ratio,
        hwid_full_price=hwid_full_price,
        hwid_traffic_bonus_bytes=hwid_traffic_bonus_bytes,
    )
    if created:
        logger.info(
            "Payment record %s created with provider payment id %s",
            payment.payment_id,
            remote_id,
        )
    return payment


async def get_payment_by_db_id(
    session: AsyncSession,
    payment_db_id: int,
    *,
    fresh: bool = False,
) -> Payment | None:

    stmt = (
        select(Payment)
        .where(Payment.payment_id == payment_db_id)
        .options(joinedload(Payment.user), joinedload(Payment.promo_code_used))
    )
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_payment_by_db_id_for_update(
    session: AsyncSession, payment_db_id: int
) -> Payment | None:
    """Load the current payment row under a transaction-scoped write lock.

    Payment finalization can be entered concurrently by webhook retries, a
    worker, and a Web App status refresh.  ``populate_existing`` is important:
    a session that loaded the row before waiting for the lock must not keep a
    stale pending status after the first finalizer commits.
    """
    stmt = (
        select(Payment)
        .where(Payment.payment_id == payment_db_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def claim_payment_finalization(
    session: AsyncSession,
    payment_db_id: int,
    *,
    provider_payment_id: str | None = None,
    provider_payment_url: str | None = None,
) -> Payment | None:
    """Atomically claim a non-final payment for successful-payment effects.

    The claim and all subsequent activation effects remain in the caller's
    transaction.  A concurrent claimant waits for that transaction and then
    sees ``succeeded`` in the conditional ``UPDATE``, so it cannot produce a
    second entitlement, event, or customer notification.  If the first
    transaction rolls back, a provider retry can safely claim the payment.
    """
    values: dict[str, Any] = {
        "status": _PAYMENT_STATUS_PENDING_FINALIZATION,
        "updated_at": func.now(),
    }
    if provider_payment_id is not None:
        values["provider_payment_id"] = provider_payment_id
    if provider_payment_url is not None:
        values["provider_payment_url"] = provider_payment_url

    stmt = (
        update(Payment)
        .where(
            Payment.payment_id == payment_db_id,
            func.lower(Payment.status) != _PAYMENT_STATUS_SUCCEEDED,
        )
        .values(**values)
        .returning(Payment.payment_id)
    )
    result = await session.execute(stmt)
    claimed_payment_id = result.scalar_one_or_none()
    if claimed_payment_id is None:
        logger.info("Payment record %s already succeeded; skipping finalization.", payment_db_id)
        return None
    # The conditional UPDATE above already holds the row lock until the caller
    # commits. Reload through the normal loader so callers retain eager-loaded
    # relationships such as ``payment.user``.
    return await get_payment_by_db_id(session, int(claimed_payment_id), fresh=True)


async def find_recent_pending_provider_payment(
    session: AsyncSession,
    *,
    user_id: int,
    provider: str,
    pending_status: str,
    amount: float,
    currency: str | None,
    sale_mode: str | None,
    months: int | None,
    purchased_gb: float | None,
    purchased_hwid_devices: int | None,
    hwid_traffic_bonus_bytes: int | None = None,
    tariff_key: str | None = None,
    promo_code_id: int | None = None,
    promo_effect_summary: str | None = None,
    since_minutes: int | None = None,
) -> Payment | None:
    """Return the most recent pending payment matching the given tariff parameters.

    Used to reuse an existing provider payment link instead of creating a new one
    on repeated user clicks. A generic or provider-specific payment id must be
    populated so the caller can verify the remote payment link.

    Status matching is case-insensitive and also accepts the generic ``pending``
    alias so legacy rows (e.g. Platega ``PENDING`` or YooKassa ``pending``) stay
    reusable after provider APIs overwrite the internal pending status.
    """
    from datetime import datetime, timedelta

    conditions = [
        Payment.user_id == user_id,
        Payment.provider == provider,
        func.lower(Payment.status).in_(tuple({str(pending_status).lower(), "pending"})),
        or_(
            Payment.provider_payment_id.isnot(None),
            Payment.yookassa_payment_id.isnot(None),
        ),
        func.abs(Payment.amount - float(amount)) < 0.01,
    ]
    if since_minutes is not None:
        cutoff = datetime.now(UTC) - timedelta(minutes=max(1, since_minutes))
        conditions.append(Payment.created_at >= cutoff)
    if currency is not None:
        conditions.append(func.upper(Payment.currency) == str(currency).strip().upper())
    if sale_mode is not None:
        conditions.append(Payment.sale_mode == sale_mode)
    if tariff_key is not None:
        conditions.append(Payment.tariff_key == tariff_key)
    if promo_code_id is not None:
        conditions.append(Payment.promo_code_id == promo_code_id)
        if promo_effect_summary is not None:
            conditions.append(Payment.promo_effect_summary == promo_effect_summary)
    else:
        conditions.append(Payment.promo_code_id.is_(None))
    if months is not None:
        conditions.append(Payment.subscription_duration_months == months)
    else:
        conditions.append(Payment.subscription_duration_months.is_(None))
    if purchased_gb is not None:
        conditions.append(func.abs(Payment.purchased_gb - float(purchased_gb)) < 0.0001)
    else:
        conditions.append(Payment.purchased_gb.is_(None))
    if purchased_hwid_devices is not None:
        conditions.append(Payment.purchased_hwid_devices == purchased_hwid_devices)
    else:
        conditions.append(Payment.purchased_hwid_devices.is_(None))
    if hwid_traffic_bonus_bytes is not None:
        conditions.append(Payment.hwid_traffic_bonus_bytes == hwid_traffic_bonus_bytes)
    else:
        conditions.append(Payment.hwid_traffic_bonus_bytes.is_(None))

    stmt = (
        select(Payment)
        .where(and_(*conditions))
        .options(joinedload(Payment.user), joinedload(Payment.promo_code_used))
        .order_by(Payment.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_payment_status_by_db_id(
    session: AsyncSession, payment_db_id: int, new_status: str, yk_payment_id: str | None = None
) -> Payment | None:
    payment = await get_payment_by_db_id_for_update(session, payment_db_id)
    if payment:
        preserve_succeeded = _would_overwrite_succeeded_payment(payment.status, new_status)
        if preserve_succeeded:
            logger.info(
                "Payment record %s already succeeded; ignoring status update to %s.",
                payment.payment_id,
                new_status,
            )
        else:
            payment.status = new_status
            payment.updated_at = func.now()
        if yk_payment_id and payment.yookassa_payment_id is None:
            payment.yookassa_payment_id = yk_payment_id
        await session.flush()
        await session.refresh(payment)
        if not preserve_succeeded:
            logger.info("Payment record %s status updated to %s.", payment.payment_id, new_status)
    else:
        logger.warning("Payment record with DB ID %s not found for status update.", payment_db_id)
    return payment


async def get_recent_payment_logs_with_user(
    session: AsyncSession, limit: int = 20, offset: int = 0
) -> list[Payment]:
    stmt = (
        select(Payment)
        .options(joinedload(Payment.user))
        .where(Payment.status == "succeeded")
        .order_by(Payment.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_payments_count(session: AsyncSession) -> int:
    """Get total count of successful payments."""
    stmt = select(func.count(Payment.payment_id)).where(Payment.status == "succeeded")
    result = await session.execute(stmt)
    return result.scalar() or 0


async def get_all_succeeded_payments_with_user(session: AsyncSession) -> list[Payment]:
    """Get all successful payments with user data for export."""
    stmt = (
        select(Payment)
        .options(selectinload(Payment.user))
        .where(Payment.status == "succeeded")
        .order_by(Payment.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_user_succeeded_payments(
    session: AsyncSession, user_id: int, exclude_payment_id: int | None = None
) -> int:
    """Count succeeded payments for a specific user.

    If exclude_payment_id is provided, that specific payment will be excluded
    from the count. Useful to check "prior" payments while processing the
    current payment in the same transaction.
    """
    conditions = [Payment.user_id == user_id, Payment.status == "succeeded"]
    if exclude_payment_id is not None:
        conditions.append(Payment.payment_id != exclude_payment_id)
    stmt = select(func.count(Payment.payment_id)).where(and_(*conditions))
    result = await session.execute(stmt)
    return result.scalar() or 0


async def get_user_succeeded_payments_after(
    session: AsyncSession,
    user_id: int,
    after: Any,
    *,
    limit: int = 20,
    exclude_payment_id: int | None = None,
) -> list[Payment]:
    """Return succeeded payments that could supersede an older checkout."""

    conditions = [Payment.user_id == user_id, Payment.status == "succeeded"]
    if exclude_payment_id is not None:
        conditions.append(Payment.payment_id != exclude_payment_id)
    if after is not None:
        conditions.append(or_(Payment.created_at >= after, Payment.updated_at >= after))

    stmt = (
        select(Payment)
        .where(and_(*conditions))
        .options(joinedload(Payment.user), joinedload(Payment.promo_code_used))
        .order_by(Payment.created_at.desc(), Payment.updated_at.desc(), Payment.payment_id.desc())
        .limit(max(1, int(limit)))
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_provider_payment_and_status(
    session: AsyncSession,
    payment_db_id: int,
    provider_payment_id: str,
    new_status: str,
    provider_payment_url: str | None = None,
) -> Payment | None:
    payment = await get_payment_by_db_id_for_update(session, payment_db_id)
    if payment:
        preserve_succeeded = _would_overwrite_succeeded_payment(payment.status, new_status)
        if preserve_succeeded:
            logger.info(
                "Payment record %s already succeeded; ignoring provider status update to %s.",
                payment.payment_id,
                new_status,
            )
        else:
            payment.status = new_status
            payment.updated_at = func.now()
        payment.provider_payment_id = provider_payment_id
        if provider_payment_url:
            payment.provider_payment_url = provider_payment_url
        await session.flush()
        await session.refresh(payment)
        if not preserve_succeeded:
            logger.info(
                "Payment record %s updated with provider id %s and status %s.",
                payment.payment_id,
                provider_payment_id,
                new_status,
            )
    else:
        logger.warning("Payment record with DB ID %s not found for provider update.", payment_db_id)
    return payment


async def _daily_revenue_series_utc(session: AsyncSession, days: int = 14) -> list[dict[str, Any]]:
    """Succeeded payment totals per calendar day (UTC) for the last `days` days."""
    from datetime import date, datetime, timedelta

    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    range_start = today_start - timedelta(days=days - 1)

    day_col = cast(func.date_trunc("day", Payment.created_at), Date).label("d")
    stmt = (
        select(day_col, func.coalesce(func.sum(Payment.amount), 0.0))
        .where(
            and_(
                Payment.status == "succeeded",
                Payment.created_at >= range_start,
            )
        )
        .group_by(day_col)
        .order_by(day_col)
    )
    result = await session.execute(stmt)
    by_day: dict[date, float] = {}
    for row in result.all():
        d_key = row[0]
        if isinstance(d_key, datetime):
            d_key = d_key.date()
        by_day[d_key] = float(row[1] or 0)

    out: list[dict[str, Any]] = []
    for i in range(days):
        d = (range_start + timedelta(days=i)).date()
        out.append({"date": d.isoformat(), "amount": float(by_day.get(d, 0.0) or 0.0)})
    return out


async def get_financial_statistics(session: AsyncSession) -> dict[str, Any]:
    """Get comprehensive financial statistics."""
    from datetime import datetime, timedelta

    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    month_start = today_start - timedelta(days=30)

    revenue_stmt = select(
        func.coalesce(
            func.sum(case((Payment.created_at >= today_start, Payment.amount), else_=0)), 0
        ),
        func.coalesce(
            func.sum(case((Payment.created_at >= week_start, Payment.amount), else_=0)), 0
        ),
        func.coalesce(
            func.sum(case((Payment.created_at >= month_start, Payment.amount), else_=0)),
            0,
        ),
        func.coalesce(func.sum(Payment.amount), 0),
        func.coalesce(func.sum(case((Payment.created_at >= today_start, 1), else_=0)), 0),
    ).where(Payment.status == "succeeded")
    revenue_row = (await session.execute(revenue_stmt)).one()
    today_amount = revenue_row[0] or 0
    week_amount = revenue_row[1] or 0
    month_amount = revenue_row[2] or 0
    all_amount = revenue_row[3] or 0
    today_payments_count = int(revenue_row[4] or 0)

    # Longer tail for admin dashboard charts (presets up to 1y + custom range on the client).
    daily_series = await _daily_revenue_series_utc(session, days=730)

    return {
        "today_revenue": float(today_amount),
        "week_revenue": float(week_amount),
        "month_revenue": float(month_amount),
        "all_time_revenue": float(all_amount),
        "today_payments_count": today_payments_count,
        "daily_series": daily_series,
    }


async def get_user_total_paid(session: AsyncSession, user_id: int) -> float:
    """Get total amount paid by a specific user (sum of all succeeded payments)."""
    stmt = select(func.sum(Payment.amount)).where(
        and_(Payment.user_id == user_id, Payment.status == "succeeded")
    )
    result = await session.execute(stmt)
    total = result.scalar()
    return float(total or 0)


async def get_referral_revenue(session: AsyncSession, referrer_id: int) -> float:
    """Get total revenue generated from referred users' payments.

    This calculates the sum of all succeeded payments made by users
    where referred_by_id equals the referrer_id.
    """

    stmt = (
        select(func.sum(Payment.amount))
        .join(User, Payment.user_id == User.user_id)
        .where(and_(User.referred_by_id == referrer_id, Payment.status == "succeeded"))
    )
    result = await session.execute(stmt)
    total = result.scalar()
    return float(total or 0)
