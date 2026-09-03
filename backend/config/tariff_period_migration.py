"""Lossless, repeatable conversion of tariff period keys; never writes files."""

from copy import deepcopy
from datetime import UTC, datetime
from math import isfinite
from typing import Any

from config.subscription_periods import add_period_days, legacy_months_to_days, positive_period

CATALOG_VERSION = 2


def _period_map(value: Any, *, legacy: bool) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("period prices and mappings must be objects")
    result: dict[str, Any] = {}
    for key, item in value.items():
        days = legacy_months_to_days(key) if legacy else positive_period(key)
        canonical = str(days)
        if canonical in result:
            raise ValueError(f"duplicate subscription period: {canonical}")
        result[canonical] = item
    return result


def normalize_tariff_periods(value: dict[str, Any], *, legacy: bool) -> dict[str, Any]:
    tariff = deepcopy(value)
    if tariff.get("billing_model") != "period":
        return tariff
    expected_unit = "month" if legacy else "day"
    if tariff.get("period_unit", expected_unit) != expected_unit:
        raise ValueError("tariff period_unit conflicts with catalog schema_version")
    old_periods = tariff.get("enabled_periods") or []
    if not isinstance(old_periods, list):
        raise ValueError("enabled_periods must be an array")
    periods = [legacy_months_to_days(p) if legacy else positive_period(p) for p in old_periods]
    if len(set(periods)) != len(periods):
        raise ValueError("duplicate enabled subscription periods")
    for days in periods:
        add_period_days(datetime.now(UTC), days)
    tariff["enabled_periods"] = periods
    tariff["period_unit"] = "day"
    for field in (
        "prices_rub",
        "prices_stars",
        "referral_bonus_days_inviter",
        "referral_bonus_days_referee",
    ):
        if field in tariff:
            tariff[field] = _period_map(tariff[field], legacy=legacy)
    if "prices" in tariff:
        tariff["prices"] = {
            currency: _period_map(prices, legacy=legacy)
            for currency, prices in tariff["prices"].items()
        }
    tribute = tariff.get("tribute")
    if isinstance(tribute, dict):
        tribute["period_unit"] = "day"
        for field in ("period_ids", "period_links", "period_subscription_ids"):
            if field in tribute:
                tribute[field] = _period_map(tribute[field], legacy=legacy)
    packages = tariff.get("hwid_device_packages")
    if isinstance(packages, dict):
        for entries in packages.values():
            for package in entries:
                old_prices = package.get("prices") or {}
                prices = _period_map(old_prices, legacy=legacy)
                if legacy:
                    for period in old_periods:
                        prices.setdefault(
                            str(legacy_months_to_days(period)),
                            float(package.get("price") or 0) * positive_period(period),
                        )
                package["prices"] = prices
                package["period_unit"] = "day"
    if legacy:
        # Preserve the price of annual checkout additions: 12 monthly rates,
        # not 365/30 rates. New periods use the explicitly documented 30-day rate.
        from config.subscription_periods import days_to_legacy_months

        all_periods = set(periods)
        for prices in tariff.get("prices", {}).values():
            all_periods.update(int(key) for key in prices)
        for field in ("prices_rub", "prices_stars"):
            all_periods.update(int(key) for key in tariff.get(field, {}))
        tariff["addon_period_factors"] = {
            str(days): days_to_legacy_months(days) for days in sorted(all_periods)
        }
    elif "addon_period_factors" in tariff:
        tariff["addon_period_factors"] = _period_map(tariff["addon_period_factors"], legacy=False)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or value <= 0
            for value in tariff["addon_period_factors"].values()
        ):
            raise ValueError("addon_period_factors must contain positive finite numbers")
    return tariff


def normalize_tariff_catalog(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    version = value.get("schema_version", 1)
    if isinstance(version, bool) or version not in (1, CATALOG_VERSION):
        raise ValueError("unsupported tariff catalog schema_version")
    legacy = version == 1
    if value.get("period_unit", "month" if legacy else "day") != ("month" if legacy else "day"):
        raise ValueError("tariff catalog version conflicts with period_unit")
    result = deepcopy(value)
    result["schema_version"] = CATALOG_VERSION
    result["period_unit"] = "day"
    result["tariffs"] = [
        normalize_tariff_periods(tariff, legacy=legacy) if isinstance(tariff, dict) else tariff
        for tariff in result.get("tariffs", [])
    ]
    return result
