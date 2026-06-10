import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import Date, and_, case, cast, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload

from db.models import Payment, User


async def create_payment_record(session: AsyncSession, payment_data: Dict[str, Any]) -> Payment:

    from .user_dal import get_user_by_id

    user = await get_user_by_id(session, payment_data["user_id"])
    if not user:
        raise ValueError(f"User with id {payment_data['user_id']} not found for creating payment.")

    if payment_data.get("promo_code_id"):
        from .promo_code_dal import get_promo_code_by_id

        promo = await get_promo_code_by_id(session, payment_data["promo_code_id"])
        if not promo:
            raise ValueError(f"Promo code with id {payment_data['promo_code_id']} not found.")

    new_payment = Payment(**payment_data)
    session.add(new_payment)
    await session.flush()
    await session.refresh(new_payment)
    logging.info(f"Payment record {new_payment.payment_id} created for user {new_payment.user_id}")
    return new_payment


async def get_payment_by_provider_payment_id(
    session: AsyncSession, provider_payment_id: str
) -> Optional[Payment]:
    """Fetch a payment by provider-specific identifier."""
    stmt = select(Payment).where(Payment.provider_payment_id == provider_payment_id)
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
    sale_mode: Optional[str] = None,
    tariff_key: Optional[str] = None,
    purchased_gb: Optional[float] = None,
    purchased_hwid_devices: Optional[int] = None,
    hwid_valid_from: Optional[Any] = None,
    hwid_valid_until: Optional[Any] = None,
    hwid_pricing_period_months: Optional[int] = None,
    hwid_proration_ratio: Optional[float] = None,
    hwid_full_price: Optional[float] = None,
) -> Payment:
    """Idempotently create a payment record for a provider event.

    If a payment with the same provider_payment_id already exists, returns it.
    Otherwise creates a new pending payment with provided data.
    """
    existing = await get_payment_by_provider_payment_id(session, provider_payment_id)
    if existing:
        return existing

    pending_status = f"pending_{provider}" if provider else "pending"
    payment_payload: Dict[str, Any] = {
        "user_id": user_id,
        "amount": float(amount),
        "currency": currency,
        "status": pending_status,
        "description": description,
        "subscription_duration_months": months,
        "provider_payment_id": provider_payment_id,
        "provider": provider,
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
    }
    payment_payload.update(
        {field: value for field, value in optional_fields.items() if value is not None}
    )
    return await create_payment_record(session, payment_payload)


async def get_payment_by_db_id(session: AsyncSession, payment_db_id: int) -> Optional[Payment]:

    stmt = (
        select(Payment)
        .where(Payment.payment_id == payment_db_id)
        .options(joinedload(Payment.user), joinedload(Payment.promo_code_used))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def find_recent_pending_provider_payment(
    session: AsyncSession,
    *,
    user_id: int,
    provider: str,
    pending_status: str,
    amount: float,
    currency: Optional[str],
    sale_mode: Optional[str],
    months: Optional[int],
    purchased_gb: Optional[float],
    purchased_hwid_devices: Optional[int],
    tariff_key: Optional[str] = None,
    since_minutes: Optional[int] = None,
) -> Optional[Payment]:
    """Return the most recent pending payment matching the given tariff parameters.

    Used to reuse an existing provider payment link instead of creating a new one
    on repeated user clicks. A generic or provider-specific payment id must be
    populated so the caller can verify the remote payment link.

    Status matching is case-insensitive and also accepts the generic ``pending``
    alias so legacy rows (e.g. Platega ``PENDING`` or YooKassa ``pending``) stay
    reusable after provider APIs overwrite the internal pending status.
    """
    from datetime import datetime, timedelta, timezone

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
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(1, since_minutes))
        conditions.append(Payment.created_at >= cutoff)
    if currency is not None:
        conditions.append(func.upper(Payment.currency) == str(currency).strip().upper())
    if sale_mode is not None:
        conditions.append(Payment.sale_mode == sale_mode)
    if tariff_key is not None:
        conditions.append(Payment.tariff_key == tariff_key)
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
    session: AsyncSession, payment_db_id: int, new_status: str, yk_payment_id: Optional[str] = None
) -> Optional[Payment]:
    payment = await get_payment_by_db_id(session, payment_db_id)
    if payment:
        payment.status = new_status
        payment.updated_at = func.now()
        if yk_payment_id and payment.yookassa_payment_id is None:
            payment.yookassa_payment_id = yk_payment_id
        await session.flush()
        await session.refresh(payment)
        logging.info(f"Payment record {payment.payment_id} status updated to {new_status}.")
    else:
        logging.warning(f"Payment record with DB ID {payment_db_id} not found for status update.")
    return payment


async def get_recent_payment_logs_with_user(
    session: AsyncSession, limit: int = 20, offset: int = 0
) -> List[Payment]:
    stmt = (
        select(Payment)
        .options(joinedload(Payment.user))
        .where(Payment.status == "succeeded")
        .order_by(Payment.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_payments_count(session: AsyncSession) -> int:
    """Get total count of successful payments."""
    stmt = select(func.count(Payment.payment_id)).where(Payment.status == "succeeded")
    result = await session.execute(stmt)
    return result.scalar() or 0


async def get_all_succeeded_payments_with_user(session: AsyncSession) -> List[Payment]:
    """Get all successful payments with user data for export."""
    stmt = (
        select(Payment)
        .options(selectinload(Payment.user))
        .where(Payment.status == "succeeded")
        .order_by(Payment.created_at.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def count_user_succeeded_payments(
    session: AsyncSession, user_id: int, exclude_payment_id: Optional[int] = None
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


async def update_provider_payment_and_status(
    session: AsyncSession,
    payment_db_id: int,
    provider_payment_id: str,
    new_status: str,
    provider_payment_url: Optional[str] = None,
) -> Optional[Payment]:
    payment = await get_payment_by_db_id(session, payment_db_id)
    if payment:
        payment.status = new_status
        payment.provider_payment_id = provider_payment_id
        if provider_payment_url:
            payment.provider_payment_url = provider_payment_url
        payment.updated_at = func.now()
        await session.flush()
        await session.refresh(payment)
        logging.info(
            f"Payment record {payment.payment_id} updated with provider id {provider_payment_id} and status {new_status}."  # noqa: E501
        )
    else:
        logging.warning(f"Payment record with DB ID {payment_db_id} not found for provider update.")
    return payment


async def _daily_revenue_series_utc(session: AsyncSession, days: int = 14) -> List[Dict[str, Any]]:
    """Succeeded payment totals per calendar day (UTC) for the last `days` days."""
    from datetime import date, datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
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
    by_day: Dict[date, float] = {}
    for row in result.all():
        d_key = row[0]
        if isinstance(d_key, datetime):
            d_key = d_key.date()
        by_day[d_key] = float(row[1] or 0)

    out: List[Dict[str, Any]] = []
    for i in range(days):
        d = (range_start + timedelta(days=i)).date()
        out.append({"date": d.isoformat(), "amount": float(by_day.get(d, 0.0) or 0.0)})
    return out


async def get_financial_statistics(session: AsyncSession) -> Dict[str, Any]:
    """Get comprehensive financial statistics."""
    from datetime import datetime, timedelta

    now = datetime.utcnow()
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
