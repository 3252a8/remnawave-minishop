"""Pure conversions for the Bedolaga legacy-source adapter."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from config.tariffs_config import TariffsConfig

from .common import _jsonish, _to_float, _to_int, _truthy

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def bedolaga_tariff_key(row: dict[str, Any], used: set[str]) -> str:
    name = str(row.get("name") or "tariff").strip().lower()
    base = _SLUG_RE.sub("-", name).strip("-") or f"tariff-{row.get('id')}"
    base = f"bedolaga-{base}"[:56].rstrip("-")
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base[:52]}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _price_map(value: Any, *, daily_price: Any = None, is_daily: bool = False) -> dict[str, float]:
    prices: dict[str, float] = {}
    for days, minor in _jsonish(value).items():
        days_value = _to_int(days)
        minor_value = _to_float(minor)
        if days_value and days_value > 0 and minor_value is not None and minor_value >= 0:
            prices[str(days_value)] = minor_value / 100
    daily_minor = _to_float(daily_price)
    if is_daily and daily_minor is not None and daily_minor >= 0:
        prices.setdefault("1", daily_minor / 100)
    return prices


def bedolaga_build_tariff_catalog(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    used: set[str] = set()
    mapping: dict[str, str] = {}
    tariffs: list[dict[str, Any]] = []
    warnings: list[str] = []
    default_tariff: str | None = None

    for row in sorted(
        rows,
        key=lambda item: (_to_int(item.get("display_order")) or 0, _to_int(item.get("id")) or 0),
    ):
        source_id = _to_int(row.get("id"))
        key = bedolaga_tariff_key(row, used)
        prices = _price_map(
            row.get("period_prices"),
            daily_price=row.get("daily_price_kopeks"),
            is_daily=_truthy(row.get("is_daily")),
        )
        if not prices:
            warnings.append(f"Bedolaga tariff {source_id or row.get('name')} has no usable prices")
            continue
        name = str(row.get("name") or key).strip() or key
        description = str(row.get("description") or "").strip()
        enabled = _truthy(row.get("is_active"))
        tariff = {
            "key": key,
            "names": {"ru": name, "en": name},
            "descriptions": {"ru": description, "en": description} if description else {},
            "billing_model": "period",
            "period_unit": "day",
            "monthly_gb": max(0.0, _to_float(row.get("traffic_limit_gb")) or 0.0),
            "prices": {"rub": prices},
            "enabled_periods": sorted(int(days) for days in prices),
            "squad_uuids": [
                str(value)
                for value in (
                    _jsonish(row.get("allowed_squads")) or row.get("allowed_squads") or []
                )
            ]
            if isinstance(row.get("allowed_squads"), list)
            else [],
            "enabled": enabled,
            "hwid_device_limit": max(1, _to_int(row.get("device_limit")) or 1),
        }
        tariffs.append(tariff)
        if source_id is not None:
            mapping[str(source_id)] = key
        mapping[name] = key
        if enabled and default_tariff is None:
            default_tariff = key

    if not tariffs or default_tariff is None:
        return {"catalog": None, "tariff_map": mapping, "warnings": warnings}
    catalog = {
        "schema_version": 2,
        "period_unit": "day",
        "default_tariff": default_tariff,
        "default_currency": "rub",
        "tariffs": tariffs,
    }
    try:
        TariffsConfig.model_validate(catalog)
    except Exception as exc:
        warnings.append(f"Generated Bedolaga tariff catalog is invalid: {exc}")
        return {"catalog": None, "tariff_map": mapping, "warnings": warnings}
    return {"catalog": catalog, "tariff_map": mapping, "warnings": warnings}


def bedolaga_target_user_id(source_id: int, telegram_id: int | None) -> int:
    if telegram_id is not None:
        return telegram_id
    return -(9_000_000_000_000_000 + source_id)


def bedolaga_payment_status(completed: Any) -> str:
    return "succeeded" if _truthy(completed) else "pending"


def bedolaga_ledger_effect(transaction_type: Any, amount_minor: Any) -> tuple[str, int] | None:
    kind = str(transaction_type or "").strip().lower()
    amount = abs(_to_int(amount_minor) or 0)
    if not amount:
        return None
    if kind == "deposit":
        return "payment_topup", amount
    if kind in {"referral_reward", "poll_reward", "refund"}:
        return "admin_adjustment", amount
    if kind in {"subscription_payment", "gift_payment"}:
        return "checkout_spend", -amount
    if kind == "withdrawal":
        return "admin_adjustment", -amount
    return None
