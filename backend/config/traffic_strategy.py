from typing import Any

REMNAWAVE_TRAFFIC_LIMIT_STRATEGIES = frozenset(
    {
        "NO_RESET",
        "DAY",
        "WEEK",
        "MONTH",
        "MONTH_ROLLING",
    }
)

_TRAFFIC_LIMIT_STRATEGY_ALIASES = {
    "NONE": "NO_RESET",
    "NO_RESET": "NO_RESET",
    "NO-RESET": "NO_RESET",
    "DAILY": "DAY",
    "WEEKLY": "WEEK",
    "MONTHLY": "MONTH",
    "MONTHLY_ROLLING": "MONTH_ROLLING",
    "MONTH-ROLLING": "MONTH_ROLLING",
}


def normalize_traffic_limit_strategy(value: Any, *, default: str | None = "NO_RESET") -> str:
    fallback = ""
    if default is not None:
        fallback = str(default or "NO_RESET").strip().upper().replace("-", "_") or "NO_RESET"
        fallback = _TRAFFIC_LIMIT_STRATEGY_ALIASES.get(fallback, fallback)
        if fallback not in REMNAWAVE_TRAFFIC_LIMIT_STRATEGIES:
            fallback = "NO_RESET"

    strategy = _traffic_limit_strategy_key(value)
    if not strategy:
        return fallback

    canonical = canonical_traffic_limit_strategy(strategy)
    if canonical:
        return canonical
    return strategy


def canonical_traffic_limit_strategy(value: Any) -> str | None:
    strategy = _traffic_limit_strategy_key(value)
    if not strategy:
        return None
    return _TRAFFIC_LIMIT_STRATEGY_ALIASES.get(strategy) or (
        strategy if strategy in REMNAWAVE_TRAFFIC_LIMIT_STRATEGIES else None
    )


def _traffic_limit_strategy_key(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_")
