"""Row-level mapping helpers translating Remnashop data to shop models."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Iterable
from typing import Any
from urllib.parse import unquote, urlparse

from config.tariffs_config import TariffsConfig, normalize_currency_key

from .common import (
    GIB,
    SOURCE,
    UUID_RE,
    _as_utc,
    _jsonish,
    _listish,
    _to_decimal,
    _to_float,
    _to_int,
    _truthy,
)
from .remnashop_env import (
    _normalize_currency,
)

logger = logging.getLogger(__name__)


def remnashop_traffic_gb_to_bytes(value: Any) -> int | None:
    number = _to_decimal(value)
    if number is None:
        return None
    return int(number * GIB)


def remnashop_pricing_amount(pricing: Any) -> float:
    data = _jsonish(pricing)
    for key in ("final_amount", "total_amount", "amount", "price"):
        number = _to_decimal(data.get(key))
        if number is not None:
            return float(number)
    return 0.0


def remnashop_pricing_currency(pricing: Any, fallback: Any = None) -> str:
    data = _jsonish(pricing)
    currency = str(data.get("currency") or fallback or "RUB").strip().upper()
    return currency or "RUB"


def remnashop_transaction_status(status: Any, gateway_type: Any = None) -> str:
    source_status = str(status or "").strip().upper()
    provider = str(gateway_type or "").strip().lower()
    if source_status == "COMPLETED":
        return "succeeded"
    if source_status == "PENDING":
        return f"pending_{provider}" if provider else "pending"
    if source_status == "CANCELED":
        return "canceled"
    if source_status == "REFUNDED":
        return "refunded"
    if source_status == "FAILED":
        return "failed"
    return source_status.lower() or "unknown"


def remnashop_plan_type(plan_snapshot: Any) -> str:
    data = _jsonish(plan_snapshot)
    raw_value = data.get("type")
    if raw_value is not None and hasattr(raw_value, "value"):
        raw_value = raw_value.value
    text_value = str(raw_value or "").strip().upper()
    if "." in text_value:
        text_value = text_value.rsplit(".", 1)[-1]
    return re.sub(r"[^A-Z0-9_]+", "_", text_value).strip("_")


def remnashop_purchased_gb(plan_snapshot: Any) -> float | None:
    if remnashop_plan_type(plan_snapshot) != "TRAFFIC":
        return None
    data = _jsonish(plan_snapshot)
    value = _to_float(data.get("traffic_limit") or data.get("traffic_gb") or data.get("gb"))
    return value if value and value > 0 else None


def remnashop_purchased_hwid_devices(plan_snapshot: Any) -> int | None:
    if remnashop_plan_type(plan_snapshot) != "DEVICES":
        return None
    value = _to_int(_jsonish(plan_snapshot).get("device_limit"))
    return value if value and value > 0 else None


def remnashop_sale_mode(purchase_type: Any, plan_snapshot: Any = None) -> str:
    source_type = str(purchase_type or "").strip().upper()
    plan_type = remnashop_plan_type(plan_snapshot)
    if source_type in {"NEW", "RENEW"} and plan_type == "TRAFFIC":
        return "traffic_package"
    if source_type in {"NEW", "RENEW"} and plan_type == "DEVICES":
        return "hwid_devices"
    if source_type in {"NEW", "RENEW"}:
        return "subscription"
    if source_type == "CHANGE":
        return "tariff_upgrade"
    return source_type.lower() or "subscription"


def remnashop_subscription_provider(is_trial: Any) -> str:
    return "trial" if _truthy(is_trial) else SOURCE


def remnashop_months_from_plan_snapshot(
    plan_snapshot: Any,
    *,
    created_at: Any = None,
    expire_at: Any = None,
) -> int | None:
    data = _jsonish(plan_snapshot)
    for key in ("duration_months", "months", "month"):
        months = _to_int(data.get(key))
        if months and months > 0:
            return months

    for key in ("duration_days", "days", "duration"):
        days = _to_int(data.get(key))
        if days and days > 0:
            return max(1, round(days / 30))

    start = _as_utc(created_at)
    end = _as_utc(expire_at)
    if start and end and end > start:
        return max(1, round((end - start).days / 30))
    return None


def remnashop_tariff_key(plan_snapshot: Any, tariff_map: dict[str, str]) -> str | None:
    data = _jsonish(plan_snapshot)
    candidates = [
        data.get("id"),
        data.get("name"),
        data.get("tag"),
        data.get("public_code"),
    ]
    for candidate in candidates:
        key = str(candidate or "").strip()
        if key and key in tariff_map:
            return tariff_map[key]
    return None


def remnashop_row_telegram_id(
    row: dict[str, Any],
    user_telegram_by_id: dict[int, int] | None = None,
    *,
    user_id_key: str = "user_id",
    telegram_id_key: str = "user_telegram_id",
) -> int | None:
    telegram_id = _to_int(row.get(telegram_id_key))
    if telegram_id is None and telegram_id_key != "telegram_id":
        telegram_id = _to_int(row.get("telegram_id"))
    if telegram_id is not None:
        return telegram_id

    user_id = _to_int(row.get(user_id_key))
    if user_id is None or not user_telegram_by_id:
        return None
    return _to_int(user_telegram_by_id.get(user_id))


def remnashop_days_to_months(days: Any) -> int | None:
    value = _to_int(days)
    if value is None or value <= 0:
        return None
    return max(1, round(value / 30))


def _remnashop_enum_text(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    text_value = str(value or "").strip().upper()
    if "." in text_value:
        text_value = text_value.rsplit(".", 1)[-1]
    return re.sub(r"[^A-Z0-9_]+", "_", text_value).strip("_")


def _remnashop_tariff_slug(value: Any) -> str:
    text_value = str(value or "").strip().lower()
    slug = re.sub(r"[^a-z0-9_]+", "_", text_value).strip("_")
    slug = re.sub(r"_+", "_", slug)
    if slug and slug[0].isdigit():
        slug = f"plan_{slug}"
    return slug


def _remnashop_plan_tariff_base_key(plan: dict[str, Any]) -> str:
    for key in ("tag", "public_code", "name", "id"):
        slug = _remnashop_tariff_slug(plan.get(key))
        if slug:
            return slug
    return "remnashop_plan"


def _unique_tariff_key(base_key: str, used_keys: set[str]) -> str:
    key = base_key or "remnashop_plan"
    if key not in used_keys:
        used_keys.add(key)
        return key
    index = 2
    while f"{key}_{index}" in used_keys:
        index += 1
    unique = f"{key}_{index}"
    used_keys.add(unique)
    return unique


def _remnashop_currency_key(value: Any) -> str:
    normalized = _normalize_currency(value) or str(value or "")
    key: str = normalize_currency_key(normalized)
    return key


def _remnashop_price_value(value: Any) -> float | None:
    price = _to_float(value)
    if price is None or price < 0:
        return None
    return price


def _remnashop_squad_uuids(value: Any) -> list[str]:
    squads: list[str] = []
    for item in _listish(value):
        text_value = str(item or "").strip()
        if text_value and text_value not in squads:
            squads.append(text_value)
    return squads


def _remnashop_plan_enabled(plan: dict[str, Any]) -> bool:
    if not _truthy(plan.get("is_active")):
        return False
    availability = _remnashop_enum_text(plan.get("availability"))
    return availability not in {"ALLOWED", "LINK"}


def _add_tariff_map_entries(
    tariff_map: dict[str, str],
    plan: dict[str, Any],
    tariff_key: str,
) -> None:
    for source_key in ("id", "name", "tag", "public_code"):
        value = str(plan.get(source_key) or "").strip()
        if value:
            tariff_map.setdefault(value, tariff_key)


def _duration_prices_by_id(price_rows: Iterable[dict[str, Any]]) -> dict[int, dict[str, float]]:
    prices: dict[int, dict[str, float]] = defaultdict(dict)
    for row in price_rows:
        duration_id = _to_int(row.get("plan_duration_id"))
        price = _remnashop_price_value(row.get("price"))
        currency = _remnashop_currency_key(row.get("currency"))
        if duration_id is None or price is None or not currency:
            continue
        prices[duration_id][currency] = price
    return prices


def _durations_by_plan(duration_rows: Iterable[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in duration_rows:
        plan_id = _to_int(row.get("plan_id"))
        if plan_id is None:
            continue
        result[plan_id].append(row)
    for rows in result.values():
        rows.sort(
            key=lambda item: (
                _to_int(item.get("order_index")) or 0,
                _to_int(item.get("id")) or 0,
            )
        )
    return result


def remnashop_build_tariff_catalog(
    plans: Iterable[dict[str, Any]],
    durations: Iterable[dict[str, Any]],
    prices: Iterable[dict[str, Any]],
    *,
    default_currency: Any = "RUB",
) -> dict[str, Any]:
    duration_rows_by_plan = _durations_by_plan(durations)
    prices_by_duration = _duration_prices_by_id(prices)
    tariff_map: dict[str, str] = {}
    warnings: list[str] = []
    used_keys: set[str] = set()
    tariffs: list[dict[str, Any]] = []
    default_tariff: str | None = None
    default_currency_key = _remnashop_currency_key(default_currency) or "rub"
    if default_currency_key == "stars":
        default_currency_key = "rub"

    sorted_plans = sorted(
        plans,
        key=lambda item: (_to_int(item.get("order_index")) or 0, _to_int(item.get("id")) or 0),
    )
    for plan in sorted_plans:
        plan_id = _to_int(plan.get("id"))
        plan_type = _remnashop_enum_text(plan.get("type"))
        if _truthy(plan.get("is_trial")):
            continue
        if plan_type == "DEVICES":
            warnings.append(
                f"Skipped device-only Remnashop tariff {plan_id or plan.get('name')}: "
                "Minishop migrates device limits inside tariffs instead of as separate "
                "device tariffs."
            )
            continue
        if plan_type not in {"BOTH", "TRAFFIC", "UNLIMITED", "DURATION", "SUBSCRIPTION"}:
            warnings.append(
                f"Skipped unsupported Remnashop tariff {plan_id or plan.get('name')} "
                f"with type {plan_type or 'unknown'}."
            )
            continue

        key = _unique_tariff_key(_remnashop_plan_tariff_base_key(plan), used_keys)
        name = str(plan.get("name") or key).strip() or key
        description = str(plan.get("description") or "").strip()
        enabled = _remnashop_plan_enabled(plan)
        if not enabled and _truthy(plan.get("is_active")):
            warnings.append(
                f"Remnashop tariff {plan_id or name} was imported disabled because it has "
                "availability restrictions; review the rules manually."
            )

        tariff: dict[str, Any] = {
            "key": key,
            "names": {"ru": name, "en": name},
            "descriptions": {"ru": description, "en": description} if description else {},
            "squad_uuids": _remnashop_squad_uuids(plan.get("internal_squads")),
            "enabled": enabled,
            "hwid_device_limit": _to_int(plan.get("device_limit")),
        }
        if plan.get("external_squad"):
            warnings.append(
                f"Remnashop tariff {plan_id or name} has "
                f"external_squad={plan.get('external_squad')}; "
                "Minishop only migrates internal squads. Configure external routing "
                "manually if needed."
            )

        plan_durations = duration_rows_by_plan.get(plan_id or -1, [])
        if plan_type == "TRAFFIC":
            traffic_gb = _to_float(plan.get("traffic_limit"))
            if traffic_gb is None or traffic_gb <= 0:
                warnings.append(
                    f"Skipped traffic tariff {plan_id or name}: traffic_limit is empty."
                )
                continue
            packages: dict[str, list[dict[str, float]]] = defaultdict(list)
            seen_packages: set[tuple[str, float, float]] = set()
            for duration in plan_durations:
                duration_id = _to_int(duration.get("id"))
                for currency, price in prices_by_duration.get(duration_id or -1, {}).items():
                    if price <= 0:
                        continue
                    package_key = (currency, traffic_gb, price)
                    if package_key in seen_packages:
                        continue
                    seen_packages.add(package_key)
                    packages[currency].append({"gb": traffic_gb, "price": price})
            if not any(packages.values()):
                warnings.append(
                    f"Skipped traffic tariff {plan_id or name}: no positive prices were found."
                )
                continue
            tariff.update(
                {
                    "billing_model": "traffic",
                    "traffic_packages": dict(packages),
                }
            )
        else:
            monthly_gb = _to_float(plan.get("traffic_limit")) or 0.0
            period_prices: dict[str, dict[str, float]] = defaultdict(dict)
            enabled_periods: list[int] = []
            for duration in plan_durations:
                duration_id = _to_int(duration.get("id"))
                months = remnashop_days_to_months(duration.get("days"))
                if months is None:
                    continue
                duration_prices = prices_by_duration.get(duration_id or -1, {})
                if not any(price > 0 for price in duration_prices.values()):
                    continue
                if months not in enabled_periods:
                    enabled_periods.append(months)
                for currency, price in duration_prices.items():
                    period_prices[currency][str(months)] = price
            if not enabled_periods:
                warnings.append(
                    f"Skipped recurring tariff {plan_id or name}: no payable periods were found."
                )
                continue
            tariff.update(
                {
                    "billing_model": "period",
                    "monthly_gb": monthly_gb,
                    "prices": {
                        currency: dict(values) for currency, values in period_prices.items()
                    },
                    "enabled_periods": enabled_periods,
                }
            )

        if tariff["enabled"] and default_tariff is None:
            default_tariff = key
        tariffs.append(tariff)
        _add_tariff_map_entries(tariff_map, plan, key)

    if not tariffs:
        return {"catalog": None, "tariff_map": tariff_map, "warnings": warnings}
    default_tariff = default_tariff or next(
        (item["key"] for item in tariffs if item["enabled"]),
        None,
    )
    if default_tariff is None:
        warnings.append(
            "No enabled Remnashop tariffs could be generated; the tariff catalog was skipped."
        )
        return {"catalog": None, "tariff_map": tariff_map, "warnings": warnings}

    catalog = {
        "default_tariff": default_tariff,
        "default_currency": default_currency_key,
        "tariffs": tariffs,
    }
    try:
        TariffsConfig.model_validate(catalog)
    except Exception as exc:
        warnings.append(f"The generated Remnashop tariff catalog is invalid: {exc}")
        return {"catalog": None, "tariff_map": tariff_map, "warnings": warnings}

    return {"catalog": catalog, "tariff_map": tariff_map, "warnings": warnings}


def remnashop_notification_overrides(notifications: Any) -> dict[str, Any]:
    data = _jsonish(notifications)
    routes = data.get("routes") if isinstance(data.get("routes"), dict) else data
    if not isinstance(routes, dict):
        return {"overrides": {}, "route": None, "warnings": []}

    preferred_order = (
        "SYSTEM",
        "BOT_LIFECYCLE",
        "USER_REGISTERED",
        "SUBSCRIPTION",
        "PAYMENT",
    )
    route_keys = [key for key in preferred_order if key in routes] + sorted(
        key for key in routes if key not in preferred_order
    )
    candidates: list[dict[str, Any]] = []
    for route_key in route_keys:
        route = routes.get(route_key)
        if isinstance(route, dict):
            chat_id = _to_int(
                route.get("chat_id")
                or route.get("chatId")
                or route.get("telegram_chat_id")
                or route.get("telegramChatId")
            )
            thread_id = _to_int(
                route.get("thread_id")
                or route.get("threadId")
                or route.get("message_thread_id")
                or route.get("messageThreadId")
            )
        else:
            chat_id = _to_int(route)
            thread_id = None
        if chat_id is None:
            continue
        candidates.append({"route": route_key, "chat_id": chat_id, "thread_id": thread_id})

    if not candidates:
        return {"overrides": {}, "route": None, "warnings": []}

    selected = candidates[0]
    overrides: dict[str, Any] = {"LOG_CHAT_ID": selected["chat_id"]}
    if selected.get("thread_id") and int(selected["thread_id"]) > 0:
        overrides["LOG_THREAD_ID"] = int(selected["thread_id"])

    warnings: list[str] = []
    distinct_targets = {
        (candidate["chat_id"], candidate.get("thread_id") or None) for candidate in candidates
    }
    if len(distinct_targets) > 1:
        warnings.append(
            "Multiple notification targets were found in Remnashop; Minishop uses one "
            f"LOG_CHAT_ID. Imported route {selected['route']}; all routes were saved "
            "in the migration notes."
        )

    return {"overrides": overrides, "route": selected, "warnings": warnings}


def _provider_value(gateway_type: Any) -> str:
    value = str(gateway_type or "remnashop").strip().lower()
    if value == "telegram_stars":
        return "stars"
    return value or "remnashop"


def _extract_panel_subscription_uuid(url: Any, panel_user_uuid: str | None) -> str | None:
    value = str(url or "")
    if not value:
        return None
    panel_user_uuid = str(panel_user_uuid or "").lower()
    for match in UUID_RE.finditer(value):
        candidate = match.group(0).lower()
        if candidate != panel_user_uuid:
            return candidate
    path = urlparse(value).path if "://" in value else value
    token = unquote(str(path or "").strip().rstrip("/").rsplit("/", 1)[-1]).strip()
    if token and token.lower() != panel_user_uuid:
        return token
    return None


def _legacy_user_metadata(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "points",
        "personal_discount",
        "purchase_discount",
        "role",
        "is_rules_accepted",
        "is_trial_available",
        "language",
        "current_subscription_id",
    )
    return {key: row.get(key) for key in keys if row.get(key) is not None}
