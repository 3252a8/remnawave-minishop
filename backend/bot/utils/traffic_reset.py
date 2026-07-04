from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from bot.utils.date_utils import add_months, month_start
from config.traffic_strategy import (
    canonical_traffic_limit_strategy,
    normalize_traffic_limit_strategy,
)

PANEL_NEXT_RESET_KEYS = (
    "nextTrafficResetAt",
    "next_traffic_reset_at",
    "trafficNextResetAt",
    "traffic_next_reset_at",
)
PANEL_LAST_RESET_KEYS = (
    "lastTrafficResetAt",
    "last_traffic_reset_at",
)


def aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_panel_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None
    return aware_utc(parsed)


def first_panel_datetime(payload: dict[str, Any], keys: tuple[str, ...]) -> datetime | None:
    for key in keys:
        parsed = parse_panel_datetime(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def panel_traffic_stats(panel_user_data: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(panel_user_data, dict):
        return {}
    raw = panel_user_data.get("userTraffic")
    return raw if isinstance(raw, dict) else {}


def panel_traffic_limit_strategy(
    panel_user_data: dict[str, Any] | None,
    fallback_strategy: str,
) -> str:
    fallback = normalize_traffic_limit_strategy(fallback_strategy, default="MONTH")
    if not isinstance(panel_user_data, dict):
        return fallback
    stats = panel_traffic_stats(panel_user_data)
    for raw in (
        panel_user_data.get("trafficLimitStrategy"),
        stats.get("trafficLimitStrategy"),
    ):
        canonical = canonical_traffic_limit_strategy(raw)
        if canonical is not None:
            return canonical
    return fallback


def panel_last_traffic_reset_at(panel_user_data: dict[str, Any] | None) -> datetime | None:
    if not isinstance(panel_user_data, dict):
        return None
    parsed = first_panel_datetime(panel_user_data, PANEL_LAST_RESET_KEYS)
    if parsed is not None:
        return parsed
    return first_panel_datetime(panel_traffic_stats(panel_user_data), PANEL_LAST_RESET_KEYS)


def panel_next_traffic_reset_at(
    panel_user_data: dict[str, Any] | None,
    *,
    fallback_strategy: str,
    now: datetime | None = None,
) -> datetime | None:
    if not isinstance(panel_user_data, dict):
        return None
    stats = panel_traffic_stats(panel_user_data)
    explicit_next = first_panel_datetime(panel_user_data, PANEL_NEXT_RESET_KEYS)
    if explicit_next is None:
        explicit_next = first_panel_datetime(stats, PANEL_NEXT_RESET_KEYS)
    if explicit_next is not None:
        return explicit_next

    strategy = panel_traffic_limit_strategy(panel_user_data, fallback_strategy)
    return next_traffic_reset_after(
        panel_last_traffic_reset_at(panel_user_data),
        strategy,
        now=now,
    )


def traffic_accounting_period_start(
    strategy: str,
    now: datetime,
    *,
    subscription_start_at: datetime | None = None,
    previous_period_start_at: datetime | None = None,
    panel_user_data: dict[str, Any] | None = None,
) -> datetime:
    normalized = panel_traffic_limit_strategy(panel_user_data, strategy)
    current = aware_utc(now) or datetime.now(UTC)
    panel_last_reset = panel_last_traffic_reset_at(panel_user_data)

    if normalized == "NO_RESET":
        subscription_start = aware_utc(subscription_start_at)
        if subscription_start is not None:
            if subscription_start <= current:
                return subscription_start
            previous_period = aware_utc(previous_period_start_at)
            if previous_period is not None and previous_period <= current:
                return previous_period
        return month_start(current)

    if panel_last_reset is not None and panel_last_reset <= current:
        derived = traffic_period_start_from_anchor(panel_last_reset, normalized, now=current)
        if derived is not None:
            return derived

    previous_period = aware_utc(previous_period_start_at)
    if previous_period is not None and previous_period <= current:
        derived = traffic_period_start_from_anchor(previous_period, normalized, now=current)
        if derived is not None:
            return derived

    if normalized == "DAY":
        return datetime(current.year, current.month, current.day, tzinfo=UTC)
    if normalized == "WEEK":
        day_start = datetime(current.year, current.month, current.day, tzinfo=UTC)
        return day_start - timedelta(days=day_start.weekday())
    if normalized == "MONTH_ROLLING":
        anchor = _first_not_after(current, previous_period_start_at, subscription_start_at)
        if anchor is not None:
            derived = traffic_period_start_from_anchor(anchor, normalized, now=current)
            if derived is not None:
                return derived
    return month_start(current)


def traffic_period_start_from_anchor(
    anchor: datetime,
    strategy: str,
    *,
    now: datetime,
) -> datetime | None:
    normalized = normalize_traffic_limit_strategy(strategy, default="MONTH")
    if normalized == "NO_RESET":
        return aware_utc(anchor)

    current = aware_utc(now) or datetime.now(UTC)
    candidate = aware_utc(anchor)
    if candidate is None:
        return None
    if candidate > current:
        return None

    for _ in range(512):
        next_candidate = advance_traffic_reset(candidate, normalized)
        if next_candidate > current:
            return candidate
        candidate = next_candidate
    return None


def next_traffic_reset_after(
    period_start_at: datetime | None,
    strategy: str,
    *,
    now: datetime | None = None,
) -> datetime | None:
    if period_start_at is None:
        return None
    normalized = normalize_traffic_limit_strategy(strategy, default="MONTH")
    if normalized == "NO_RESET":
        return None

    anchor = aware_utc(period_start_at)
    if anchor is None:
        return None
    candidate = advance_traffic_reset(anchor, normalized)
    if now is None:
        return candidate

    current = aware_utc(now) or datetime.now(UTC)
    for _ in range(512):
        if candidate > current:
            return candidate
        candidate = advance_traffic_reset(candidate, normalized)
    return None


def advance_traffic_reset(value: datetime, strategy: str) -> datetime:
    normalized = normalize_traffic_limit_strategy(strategy, default="MONTH")
    if normalized == "DAY":
        return value + timedelta(days=1)
    if normalized == "WEEK":
        return value + timedelta(days=7)
    return add_months(value, 1)


def previous_traffic_reset(value: datetime, strategy: str) -> datetime | None:
    normalized = normalize_traffic_limit_strategy(strategy, default="MONTH")
    anchor = aware_utc(value)
    if anchor is None or normalized == "NO_RESET":
        return None
    if normalized == "DAY":
        return anchor - timedelta(days=1)
    if normalized == "WEEK":
        return anchor - timedelta(days=7)
    return add_months(anchor, -1)


def traffic_period_starts_match(
    value: datetime | None,
    period_start_at: datetime,
    strategy: str,
) -> bool:
    normalized = normalize_traffic_limit_strategy(strategy, default="MONTH")
    value_utc = aware_utc(value)
    period_start_utc = aware_utc(period_start_at)
    if value_utc is None or period_start_utc is None:
        return False
    if normalized == "MONTH" and month_start(period_start_utc) == period_start_utc:
        return month_start(value_utc) == period_start_utc
    return value_utc == period_start_utc


def format_traffic_reset_date(value: datetime, user_lang: str) -> str:
    reset_at = aware_utc(value) or value
    lang = str(user_lang or "").lower()
    if lang.startswith("ru"):
        return reset_at.strftime("%d.%m.%Y")
    return reset_at.date().isoformat()


def _first_not_after(current: datetime, *values: datetime | None) -> datetime | None:
    for value in values:
        candidate = aware_utc(value)
        if candidate is not None and candidate <= current:
            return candidate
    return None
