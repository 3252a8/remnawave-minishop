"""The same tariff limits for purchase offers and tariff switch targets."""

from typing import Any

from bot.utils.locale_defaults import tariff_premium_title
from config.settings import Settings
from config.tariffs_config import Tariff
from config.traffic_strategy import normalize_traffic_limit_strategy


def serialize_tariff_limits(settings: Settings, tariff: Tariff, lang: str) -> dict[str, Any]:
    traffic_strategy = (
        normalize_traffic_limit_strategy(
            tariff.traffic_limit_strategy or settings.USER_TRAFFIC_STRATEGY,
            default="MONTH",
        )
        if tariff.billing_model == "period"
        else "NO_RESET"
    )
    premium_strategy = (
        normalize_traffic_limit_strategy(
            tariff.premium_traffic_limit_strategy,
            default=traffic_strategy,
        )
        if tariff.premium_traffic_limit_strategy is not None
        else traffic_strategy
    )
    return {
        "hwid_device_limit": tariff.hwid_device_limit,
        "effective_hwid_device_limit": (
            tariff.hwid_device_limit
            if tariff.hwid_device_limit is not None
            else settings.USER_HWID_DEVICE_LIMIT
        ),
        "premium_enabled": bool(tariff.premium_squad_uuids),
        "premium_title": tariff_premium_title(tariff, lang),
        "premium_monthly_gb": tariff.premium_monthly_gb,
        "premium_unlimited": bool(tariff.premium_unlimited),
        "traffic_limit_strategy": traffic_strategy,
        "premium_traffic_limit_strategy": premium_strategy,
    }
