"""Public purchase offers, with explicit day periods and legacy month aliases."""

from typing import Any

from bot.utils.locale_defaults import tariff_premium_title
from config.settings import Settings
from config.subscription_periods import days_to_legacy_months, legacy_months_to_days
from config.tariff_checkout import serialize_checkout_addons
from config.tariffs_config import default_currency_key_for_settings, payment_currency_code
from config.traffic_strategy import normalize_traffic_limit_strategy

from .common import _format_days_title, _format_number_for_payload, _format_traffic_title
from .serializers_billing_options import (
    _attach_payment_methods_to_plans,
    _serialize_hwid_device_packages,
)


def _serialize_plans(
    settings: Settings,
    lang: str,
    *,
    subscription_options: dict[int, float] | None = None,
    stars_subscription_options: dict[int, int] | None = None,
    traffic_packages: dict[float, float] | None = None,
    stars_traffic_packages: dict[float, int] | None = None,
    assigned_tariff_key: str | None = None,
) -> list[dict[str, Any]]:
    tariffs_config = settings.tariffs_config
    if tariffs_config:
        default_currency = default_currency_key_for_settings(settings)
        default_currency_code = payment_currency_code(default_currency)
        plans = []
        for tariff in tariffs_config.available_tariffs_for_user(assigned_tariff_key):
            effective_hwid_device_limit = (
                tariff.hwid_device_limit
                if tariff.hwid_device_limit is not None
                else settings.USER_HWID_DEVICE_LIMIT
            )
            traffic_limit_strategy = (
                normalize_traffic_limit_strategy(
                    tariff.traffic_limit_strategy or settings.USER_TRAFFIC_STRATEGY,
                    default="MONTH",
                )
                if tariff.billing_model == "period"
                else "NO_RESET"
            )
            premium_traffic_limit_strategy = (
                normalize_traffic_limit_strategy(
                    tariff.premium_traffic_limit_strategy,
                    default=traffic_limit_strategy,
                )
                if tariff.premium_traffic_limit_strategy is not None
                else traffic_limit_strategy
            )
            common = {
                "tariff_key": tariff.key,
                "is_default_tariff": tariff.key == tariffs_config.default_tariff,
                "tariff_name": tariff.name(lang),
                "billing_model": tariff.billing_model,
                "description": tariff.description(lang),
                "squad_uuids": tariff.squad_uuids,
                "currency": default_currency_code,
                "hwid_device_limit": tariff.hwid_device_limit,
                "effective_hwid_device_limit": effective_hwid_device_limit,
                "premium_enabled": bool(tariff.premium_squad_uuids),
                "premium_title": tariff_premium_title(tariff, lang),
                "premium_monthly_gb": tariff.premium_monthly_gb,
                "premium_unlimited": bool(tariff.premium_unlimited),
                "traffic_limit_strategy": traffic_limit_strategy,
                "premium_traffic_limit_strategy": premium_traffic_limit_strategy,
                "hwid_device_packages": _serialize_hwid_device_packages(
                    settings,
                    tariff,
                    tariff.hwid_device_packages,
                    lang,
                )
                if tariff.billing_model == "period"
                else [],
            }
            if tariff.billing_model == "period":
                # Render periods in the configured order (enabled_periods is the
                # source of truth for purchase-period ordering, matching the bot
                # keyboards). Do not sort so admins can reorder via drag & drop.
                for months in tariff.enabled_periods:
                    price = tariff.period_price(int(months), default_currency)
                    stars_price = tariff.period_price(int(months), "stars")
                    if price is None and (stars_price is None or int(stars_price) <= 0):
                        continue
                    plan = {
                        **common,
                        "id": f"{tariff.key}:period:{int(months)}",
                        "sale_mode": "subscription",
                        "months": days_to_legacy_months(tariff.period_duration_days(int(months))),
                        "duration_days": tariff.period_duration_days(int(months)),
                        "period_key": int(months),
                        "price": float(price or 0),
                        "title": tariff.name(lang),
                        "subtitle": _format_days_title(
                            tariff.period_duration_days(int(months)), lang
                        ),
                        "monthly_gb": tariff.monthly_gb,
                        "checkout_addons": serialize_checkout_addons(
                            tariff,
                            default_currency=default_currency,
                            months=int(months),
                            fallback_hwid_limit=settings.USER_HWID_DEVICE_LIMIT,
                            devices_feature_enabled=bool(settings.MY_DEVICES_SECTION_ENABLED),
                        ),
                    }
                    if stars_price is not None and int(stars_price) > 0:
                        plan["stars_price"] = int(stars_price)
                    plans.append(plan)
            else:
                currency_packages = {
                    float(package.gb): float(package.price)
                    for package in (
                        tariff.traffic_packages.for_currency(default_currency)
                        if tariff.traffic_packages
                        else []
                    )
                }
                stars_packages = {
                    float(package.gb): int(float(package.price))
                    for package in (
                        tariff.traffic_packages.stars if tariff.traffic_packages else []
                    )
                }
                # Preserve the configured package order (default-currency list first,
                # then any Stars-only volumes) so admins can reorder via drag & drop.
                # Matches the bot keyboard, which iterates the package list as-is.
                ordered_gb: list[float] = []
                for traffic_gb in list(currency_packages) + list(stars_packages):
                    if traffic_gb not in ordered_gb:
                        ordered_gb.append(traffic_gb)
                for traffic_gb in ordered_gb:
                    price = currency_packages.get(traffic_gb)
                    stars_price = stars_packages.get(traffic_gb)
                    if price is None and (stars_price is None or int(stars_price) <= 0):
                        continue
                    traffic_value = float(traffic_gb)
                    plan = {
                        **common,
                        "id": f"{tariff.key}:traffic:{_format_number_for_payload(traffic_value)}",
                        "sale_mode": "traffic_package",
                        "months": int(traffic_value)
                        if traffic_value.is_integer()
                        else traffic_value,
                        "traffic_gb": traffic_value,
                        "price": float(price or 0),
                        "title": tariff.name(lang),
                        "subtitle": _format_traffic_title(traffic_value, lang),
                    }
                    if stars_price is not None and int(stars_price) > 0:
                        plan["stars_price"] = int(stars_price)
                    plans.append(plan)
        return _attach_payment_methods_to_plans(settings, plans)

    if settings.traffic_sale_mode:
        active_traffic_packages = traffic_packages or settings.traffic_packages
        active_stars_traffic_packages = stars_traffic_packages or settings.stars_traffic_packages
        traffic_units = sorted(set(active_traffic_packages) | set(active_stars_traffic_packages))
        plans = []
        for traffic_gb in traffic_units:
            price = active_traffic_packages.get(traffic_gb)
            stars_price = active_stars_traffic_packages.get(traffic_gb)
            if price is None and (stars_price is None or int(stars_price) <= 0):
                continue
            traffic_value = float(traffic_gb)
            plan = {
                "months": int(traffic_value) if traffic_value.is_integer() else traffic_value,
                "traffic_gb": traffic_value,
                "price": float(price or 0),
                "currency": settings.DEFAULT_CURRENCY_SYMBOL or "RUB",
                "title": _format_traffic_title(traffic_value, lang),
                "sale_mode": "traffic",
            }
            if stars_price is not None and int(stars_price) > 0:
                plan["stars_price"] = int(stars_price)
            plans.append(plan)
        return _attach_payment_methods_to_plans(settings, plans)

    active_subscription_options = subscription_options or settings.subscription_options
    active_stars_subscription_options = (
        stars_subscription_options or settings.stars_subscription_options
    )
    plans = []
    for months in sorted(set(active_subscription_options) | set(active_stars_subscription_options)):
        price = active_subscription_options.get(months)
        stars_price = active_stars_subscription_options.get(months)
        if price is None and (stars_price is None or int(stars_price) <= 0):
            continue
        plan = {
            "months": int(months),
            "duration_days": legacy_months_to_days(int(months)),
            "period_key": int(months),
            "price": float(price or 0),
            "currency": settings.DEFAULT_CURRENCY_SYMBOL or "RUB",
            "title": _format_days_title(legacy_months_to_days(int(months)), lang),
            "sale_mode": "subscription",
        }
        if stars_price is not None and int(stars_price) > 0:
            plan["stars_price"] = int(stars_price)
        plans.append(plan)
    return _attach_payment_methods_to_plans(settings, plans)
