from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, Date, and_, case, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.gift_models import SubscriptionGift
from db.models import Payment, User

from .app_settings_dal import get_override_values


async def load_reporting_fee_rates(
    session: AsyncSession, provider: str | None = None
) -> dict[str, dict[str, float]]:
    """Read persisted rates in one statement, using the original env values as defaults."""
    from bot.payment_providers.registry import reporting_fee_sources

    sources = reporting_fee_sources(provider)
    overrides = await get_override_values(
        session,
        {
            key
            for methods in sources.values()
            for candidates in methods.values()
            for key, _ in candidates
        },
    )
    rates: dict[str, dict[str, float]] = {}
    for provider_key, methods in sources.items():
        for method, candidates in methods.items():
            for key, default in candidates:
                value = overrides.get(key, default)
                if (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and 0 <= value <= 100
                ):
                    rates.setdefault(provider_key, {})[method] = float(value)
                    break
    return rates


async def snapshot_payment_provider_fee(session: AsyncSession, payment: Payment) -> None:
    """Record a configured fee once, inside the transaction confirming the payment."""
    if (
        getattr(payment, "funding_source", None) != "external"
        or getattr(payment, "provider_fee_amount", None) is not None
    ):
        return
    provider = str(payment.provider)
    method = str(getattr(payment, "provider_method", None) or "")
    rates = (await load_reporting_fee_rates(session, provider)).get(provider, {})
    rate = rates.get(method, rates.get(""))
    if rate is not None:
        payment.provider_fee_amount = float(payment.amount) * (rate / 100)
        await session.flush([payment])


def _external_revenue_filters(currency: str | None) -> list[ColumnElement[bool]]:
    filters = [Payment.status == "succeeded", Payment.funding_source == "external"]
    if currency is not None:
        filters.append(Payment.currency == currency)
    return filters


async def _daily_revenue_series_utc(
    session: AsyncSession,
    days: int | None = 14,
    *,
    currency: str | None = None,
    fee: ColumnElement[float] | None = None,
) -> list[dict[str, Any]]:
    """Succeeded external-payment totals per UTC calendar day.

    ``days=None`` returns the complete series beginning with the first matching
    payment. The result remains dense so calendar presets and KPI slices keep
    their exact day semantics.
    """

    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    range_start = today_start - timedelta(days=days - 1) if days is not None else None
    day_col = cast(func.date_trunc("day", Payment.created_at), Date).label("d")
    filters = _external_revenue_filters(currency)
    if range_start is not None:
        filters.append(Payment.created_at >= range_start)
    fee = fee if fee is not None else func.coalesce(Payment.provider_fee_amount, 0.0)
    result = await session.execute(
        select(day_col, func.sum(Payment.amount), func.sum(fee))
        .where(*filters)
        .group_by(day_col)
        .order_by(day_col)
    )
    by_day: dict[date, tuple[float, float]] = {}
    for day, amount, fees in result.all():
        if isinstance(day, datetime):
            day = day.date()
        by_day[day] = (float(amount or 0), float(fees or 0))
    if range_start is None:
        first_day = min(by_day, default=today_start.date())
        first_day = min(first_day, today_start.date())
        range_start = datetime.combine(first_day, datetime.min.time(), tzinfo=UTC)
        days = (today_start.date() - first_day).days + 1
    assert days is not None
    series: list[dict[str, Any]] = []
    for index in range(days):
        day = (range_start + timedelta(days=index)).date()
        amount, fees = by_day.get(day, (0.0, 0.0))
        series.append({"date": day.isoformat(), "amount": amount, "fees": fees})
    return series


async def get_financial_statistics(
    session: AsyncSession,
    *,
    currency: str | None = None,
    provider_fee_rates: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, Any]:
    """Get cash-revenue statistics, excluding internal balance payments."""

    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    periods = (today_start, today_start - timedelta(days=7), today_start - timedelta(days=30))
    filters = _external_revenue_filters(currency)
    estimated_fee: ColumnElement[float] = literal(0.0)
    if provider_fee_rates:
        fallback = case(
            {provider: rates.get("", 0) / 100 for provider, rates in provider_fee_rates.items()},
            value=Payment.provider,
            else_=0.0,
        )
        method_rates = [
            (and_(Payment.provider == provider, Payment.provider_method == method), rate / 100)
            for provider, rates in provider_fee_rates.items()
            for method, rate in rates.items()
            if method
        ]
        estimated_fee = Payment.amount * (
            case(*method_rates, else_=fallback) if method_rates else fallback
        )
    fee = func.coalesce(Payment.provider_fee_amount, estimated_fee)
    revenue_row = (
        await session.execute(
            select(
                *(
                    func.sum(case((Payment.created_at >= start, value), else_=0))
                    for value in (Payment.amount, fee)
                    for start in periods
                ),
                func.sum(Payment.amount),
                func.sum(fee),
                func.count().filter(Payment.created_at >= today_start),
            ).where(*filters)
        )
    ).one()
    free_gifts = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(
                    func.sum(case((SubscriptionGift.status == "activated", 1), else_=0)), 0
                ),
            )
            .select_from(SubscriptionGift)
            .join(Payment, Payment.payment_id == SubscriptionGift.payment_id)
            .where(
                Payment.provider == "admin_gift",
                Payment.funding_source == "admin_grant",
                Payment.status == "succeeded",
                SubscriptionGift.status != "revoked",
            )
        )
    ).one()
    return {
        "admin_gifts_count": int(free_gifts[0] or 0),
        "admin_gifts_activated_count": int(free_gifts[1] or 0),
        "today_revenue": float(revenue_row[0] or 0),
        "week_revenue": float(revenue_row[1] or 0),
        "month_revenue": float(revenue_row[2] or 0),
        "today_fees": float(revenue_row[3] or 0),
        "week_fees": float(revenue_row[4] or 0),
        "month_fees": float(revenue_row[5] or 0),
        "all_time_revenue": float(revenue_row[6] or 0),
        "all_time_fees": float(revenue_row[7] or 0),
        "today_payments_count": int(revenue_row[8] or 0),
        "daily_series": await _daily_revenue_series_utc(
            session, days=None, currency=currency, fee=fee
        ),
    }


async def get_user_total_paid(session: AsyncSession, user_id: int) -> float:
    result = await session.execute(
        select(func.sum(Payment.amount)).where(
            Payment.user_id == user_id,
            Payment.status == "succeeded",
            Payment.funding_source == "external",
        )
    )
    return float(result.scalar() or 0)


async def get_referral_revenue(session: AsyncSession, referrer_id: int) -> float:
    result = await session.execute(
        select(func.sum(Payment.amount))
        .join(User, Payment.user_id == User.user_id)
        .where(
            User.referred_by_id == referrer_id,
            Payment.status == "succeeded",
            Payment.funding_source == "external",
        )
    )
    return float(result.scalar() or 0)


__all__ = [
    "get_financial_statistics",
    "get_referral_revenue",
    "get_user_total_paid",
    "load_reporting_fee_rates",
    "snapshot_payment_provider_fee",
]
