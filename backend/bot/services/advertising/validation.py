"""One validation policy for HTTP, Telegram and import callers."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

RESERVED = re.compile(
    r"^(?:ref_|p_|promo_|plan_|gift_|admin_|ticket_|webapp_auth_)|^(?:notifications|page_ref)$",
    re.I,
)
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")


def start_code(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", value) or RESERVED.search(value):
        raise ValueError("invalid_ad_start_param")
    return value


def money(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("invalid_ad_amount") from error
    if not result.is_finite() or result < 0 or result > 100_000_000:
        raise ValueError("invalid_ad_amount")
    return result


def currency_scale(currency: str) -> int:
    return {"XTR": 0, "TON": 9, "JPY": 0, "KRW": 0}.get(currency.upper(), 2)


def minor_units(value: object, currency: str) -> int:
    scaled = money(value) * (10 ** currency_scale(currency))
    if scaled != scaled.to_integral_value():
        raise ValueError("invalid_ad_amount_precision")
    return int(scaled)


def normalize_utm(values: dict[str, str]) -> dict[str, str]:
    result = {key: str(values.get(key, "")).strip() for key in UTM_KEYS}
    if any(len(value) > 256 or any(ord(char) < 32 for char in value) for value in result.values()):
        raise ValueError("invalid_ad_utm")
    return {key: value for key, value in result.items() if value}


def landing_path(value: str) -> str:
    parsed = urlsplit(value)
    if (
        not value.startswith("/")
        or value.startswith("//")
        or parsed.netloc
        or parsed.scheme
        or "\\" in value
    ):
        raise ValueError("invalid_ad_landing_path")
    if len(value) > 512:
        raise ValueError("invalid_ad_landing_path")
    return value
