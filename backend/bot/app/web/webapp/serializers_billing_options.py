"""Billing option serializers for the subscription web app."""

from __future__ import annotations

from ._runtime import (
    Any,
    Dict,
    List,
    Optional,
    Settings,
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
    payment_currency_code,
    web,
)
from .common import (
    _format_months_title,
    _format_number_for_payload,
    _format_traffic_title,
)


def _traffic_percent(used: Optional[int], limit: Optional[int]) -> int:
    used_val = int(used or 0)
    limit_val = int(limit or 0)
    if limit_val <= 0:
        return 0
    return max(0, min(100, round((used_val / limit_val) * 100)))


def _serialize_topup_packages(
    settings: Settings,
    tariff: Any,
    packages: Optional[Any],
    lang: str,
    *,
    sale_mode: str = "topup",
    title_prefix: str = "",
) -> List[Dict[str, Any]]:
    default_currency = default_currency_key_for_settings(settings)
    default_currency_code = payment_currency_code(default_currency)
    currency_packages = {
        float(package.gb): float(package.price)
        for package in (packages.for_currency(default_currency) if packages else [])
    }
    stars_packages = {
        float(package.gb): int(float(package.price))
        for package in (packages.stars if packages else [])
    }
    plans: List[Dict[str, Any]] = []
    for traffic_gb in sorted(set(currency_packages) | set(stars_packages)):
        price = currency_packages.get(traffic_gb)
        stars_price = stars_packages.get(traffic_gb)
        if price is None and (stars_price is None or int(stars_price) <= 0):
            continue
        traffic_value = float(traffic_gb)
        plan: Dict[str, Any] = {
            "id": f"{tariff.key}:{sale_mode}:{_format_number_for_payload(traffic_value)}",
            "tariff_key": tariff.key,
            "tariff_name": tariff.name(lang),
            "billing_model": tariff.billing_model,
            "sale_mode": sale_mode,
            "months": int(traffic_value) if traffic_value.is_integer() else traffic_value,
            "traffic_gb": traffic_value,
            "price": float(price or 0),
            "currency": default_currency_code,
            "title": f"{title_prefix}{_format_traffic_title(traffic_value, lang)}",
            "subtitle": tariff.premium_name(lang)
            if sale_mode == "premium_topup"
            else tariff.name(lang),
        }
        if stars_price is not None and int(stars_price) > 0:
            plan["stars_price"] = int(stars_price)
        plans.append(plan)
    return plans


def _serialize_hwid_device_packages(
    settings: Settings,
    tariff: Any,
    packages: Optional[Any],
    lang: str,
) -> List[Dict[str, Any]]:
    default_currency = default_currency_key_for_settings(settings)
    default_currency_code = payment_currency_code(default_currency)
    currency_packages = {
        int(package.count): float(package.price)
        for package in (packages.for_currency(default_currency) if packages else [])
    }
    stars_packages = {
        int(package.count): int(float(package.price))
        for package in (packages.stars if packages else [])
    }
    plans: List[Dict[str, Any]] = []
    for count in sorted(set(currency_packages) | set(stars_packages)):
        price = currency_packages.get(count)
        stars_price = stars_packages.get(count)
        if price is None and (stars_price is None or int(stars_price) <= 0):
            continue
        plan: Dict[str, Any] = {
            "id": f"{tariff.key}:hwid:{count}",
            "tariff_key": tariff.key,
            "tariff_name": tariff.name(lang),
            "billing_model": tariff.billing_model,
            "sale_mode": "hwid_devices",
            "months": int(count),
            "device_count": int(count),
            "price": float(price or 0),
            "currency": default_currency_code,
            "title": f"+{count}",
            "subtitle": tariff.name(lang),
        }
        if stars_price is not None and int(stars_price) > 0:
            plan["stars_price"] = int(stars_price)
        plans.append(plan)
    return plans


def _serialize_tariff_change_target(
    settings: Settings,
    config: Any,
    tariff: Any,
    options: Dict[str, Any],
    lang: str,
) -> Dict[str, Any]:
    default_currency = default_currency_key_for_settings(settings)
    default_currency_code = payment_currency_code(default_currency)
    actions: List[Dict[str, Any]] = []
    mode = str(options.get("mode") or "")
    if mode == "period_to_period":
        actions.append(
            {
                "mode": "recalc_days",
                "kind": "free",
                "title": "recalc_days",
                "days_after": int(options.get("recalc_days") or 0),
                "remaining_days": int(options.get("remaining_days") or 0),
                "converted_hwid_value_rub": float(options.get("converted_hwid_value_rub") or 0),
                "converted_hwid_days": int(options.get("converted_hwid_days") or 0),
            }
        )
        paid_diff = float(options.get("paid_diff_rub") or 0)
        if paid_diff > 0:
            actions.append(
                {
                    "mode": "paid_diff",
                    "kind": "payment",
                    "title": "paid_diff",
                    "price": paid_diff,
                    "currency": default_currency_code,
                }
            )
    elif mode == "period_to_traffic":
        actions.append(
            {
                "mode": "convert_days_to_gb",
                "kind": "free",
                "title": "convert_days_to_gb",
                "converted_gb": float(options.get("converted_gb") or 0),
                "remaining_days": int(options.get("remaining_days") or 0),
                "converted_hwid_value_rub": float(options.get("converted_hwid_value_rub") or 0),
                "converted_hwid_gb": float(options.get("converted_hwid_gb") or 0),
            }
        )
        actions.extend(
            {
                "mode": "buy_package",
                "kind": "payment",
                "title": f"+{package.gb:g} GB",
                "traffic_gb": float(package.gb),
                "price": float(package.price),
                "currency": default_currency_code,
            }
            for package in (
                tariff.traffic_packages.for_currency(default_currency)
                if tariff.traffic_packages
                else []
            )
        )
    else:
        for months in tariff.enabled_periods:
            price = tariff.period_price(int(months), default_currency)
            if price:
                actions.append(
                    {
                        "mode": "buy_period",
                        "kind": "payment",
                        "months": int(months),
                        "title": _format_months_title(int(months), lang),
                        "price": float(price),
                        "currency": default_currency_code,
                    }
                )
    return {
        "tariff_key": tariff.key,
        "title": tariff.name(lang),
        "description": tariff.description(lang),
        "billing_model": tariff.billing_model,
        "monthly_gb": tariff.monthly_gb,
        "options": options,
        "actions": actions,
    }


def _serialize_payment_methods(
    settings: Settings,
    app: web.Application,
    lang: str = "ru",
    *,
    is_admin: bool = False,
) -> List[Dict[str, Any]]:
    from bot.payment_providers import get_provider_spec, resolve_provider_presentation

    methods: List[Dict[str, Any]] = []
    payment_currency = default_payment_currency_code_for_settings(settings)
    for method in settings.payment_methods_order:
        method = method.lower()
        spec = get_provider_spec(method)
        if (
            spec
            and spec.is_visible_for_user(settings, app, is_admin=is_admin)
            and spec.is_usable_for_payment_currency(settings, payment_currency)
        ):
            presentation = resolve_provider_presentation(spec, settings, language=lang)
            payload = {
                "id": method,
                "name": presentation.webapp_label,
                "icon": presentation.webapp_icon,
            }
            minimum = spec.payment_minimum(settings, payment_currency)
            if minimum:
                payload.update(minimum)
            methods.append(payload)
    return methods
