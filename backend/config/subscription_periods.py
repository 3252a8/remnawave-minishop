"""Explicit fixed-day billing periods and adapters for historical month contracts."""

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

PeriodUnit = Literal["day", "month"]
PeriodSemantics = Literal["fixed_days", "calendar_months", "provider_managed"]
DAY_SECONDS = 86_400
MONTH_DAYS = 30
YEAR_DAYS = 365
MAX_DURATION_DAYS = 2_147_483_647


def positive_period(value: object) -> int:
    """Parse an integer without coercing booleans, fractional numbers or exponents."""
    if isinstance(value, bool):
        raise ValueError("subscription period must be a positive integer")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str) and value.strip().isascii() and value.strip().isdigit():
        result = int(value.strip())
    else:
        raise ValueError("subscription period must be a positive integer")
    if not 0 < result <= MAX_DURATION_DAYS:
        raise ValueError("subscription period is out of range")
    return result


def legacy_months_to_days(value: object) -> int:
    months = positive_period(value)
    years, remainder = divmod(months, 12)
    return positive_period(years * YEAR_DAYS + remainder * MONTH_DAYS)


def days_to_legacy_months(value: object) -> int | None:
    days = positive_period(value)
    years, remainder = divmod(days, YEAR_DAYS)
    if remainder % MONTH_DAYS or remainder // MONTH_DAYS >= 12:
        return None
    return years * 12 + remainder // MONTH_DAYS


def period_to_days(value: object, unit: PeriodUnit) -> int:
    return legacy_months_to_days(value) if unit == "month" else positive_period(value)


def resolve_period_days(*, duration_days: object = None, months: object = None) -> int:
    """Accept the old API only at the boundary, rejecting contradictory inputs."""
    if duration_days is None:
        return legacy_months_to_days(months)
    days = positive_period(duration_days)
    if months is not None and legacy_months_to_days(months) != days:
        raise ValueError("conflicting subscription period units")
    return days


def duration_label_parts(value: object) -> tuple[int, Literal["day", "month", "year"]]:
    days = positive_period(value)
    if days % YEAR_DAYS == 0:
        return days // YEAR_DAYS, "year"
    if days % MONTH_DAYS == 0:
        return days // MONTH_DAYS, "month"
    return days, "day"


def add_period_days(base: datetime, value: object) -> datetime:
    days = positive_period(value)
    if base.tzinfo is None:
        raise ValueError("billing dates must be timezone-aware")
    try:
        return base.astimezone(UTC) + timedelta(days=days)
    except OverflowError as exc:
        raise ValueError("subscription end date is out of range") from exc


def multiplied_bonus_days(duration_days: int, multiplier: float) -> int:
    extra = Decimal(positive_period(duration_days)) * max(Decimal(0), Decimal(str(multiplier)) - 1)
    return int(extra.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def tariff_period_key(tariff: Any, *, duration_days: object = None, months: object = None) -> int:
    days = resolve_period_days(duration_days=duration_days, months=months)
    unit: PeriodUnit = "day" if getattr(tariff, "period_unit", "month") == "day" else "month"
    for period in tariff.enabled_periods:
        if period_to_days(period, unit) == days:
            return int(period)
    raise ValueError("subscription period is not available")


def checkout_duration_days(settings: Any, units: object, sale_mode: str) -> int | None:
    base, _, tariff_key = sale_mode.split("|", 1)[0].partition("@")
    if base != "subscription":
        return None
    encoded = sale_mode_duration_days(sale_mode)
    if encoded is not None:
        add_period_days(datetime.now(UTC), encoded)
        return encoded
    try:
        config = settings.tariffs_config
    except AttributeError:
        config = None
    tariff = config.get(tariff_key) if config is not None and tariff_key else None
    unit: PeriodUnit = "day" if getattr(tariff, "period_unit", "month") == "day" else "month"
    # Historical adapters parse their generic units slot as float.
    if isinstance(units, float) and units.is_integer():
        units = int(units)
    days = period_to_days(units, unit)
    add_period_days(datetime.now(UTC), days)
    return days


def sale_mode_duration_days(sale_mode: str) -> int | None:
    """Decode the explicit duration token used by historical callback adapters."""
    values = [
        token[1:]
        for token in sale_mode.split("|")[1:]
        if token.startswith("d") and token[1:].isdigit()
    ]
    if len(values) > 1:
        raise ValueError("duplicate billing duration token")
    return positive_period(values[0]) if values else None


def with_period_days(sale_mode: str, duration_days: int) -> str:
    days = positive_period(duration_days)
    existing = sale_mode_duration_days(sale_mode)
    if existing is not None and existing != days:
        raise ValueError("conflicting billing duration token")
    return sale_mode if existing is not None else f"{sale_mode}|d{days}"


def fixed_day_metadata(sale_mode: str) -> dict[str, str]:
    days = sale_mode_duration_days(sale_mode)
    if days is None:
        return {}
    return {
        "subscription_days": str(days),
        "subscription_months": str(days_to_legacy_months(days) or 0),
        "period_semantics": "fixed_days",
    }
