from __future__ import annotations

import re
from typing import Any

DEFAULT_TARIFF_CURRENCY = "rub"
STARS_TARIFF_CURRENCY = "stars"
TARIFF_ACCESS_CODE_LENGTH = 32
_TARIFF_ACCESS_CODE_RE = re.compile(rf"^[0-9a-f]{{{TARIFF_ACCESS_CODE_LENGTH}}}$")


def normalize_tariff_access_code(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text if _TARIFF_ACCESS_CODE_RE.fullmatch(text) else None


def normalize_currency_key(value: Any, default: str = DEFAULT_TARIFF_CURRENCY) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return default
    aliases = {
        "rur": "rub",
        "xtr": STARS_TARIFF_CURRENCY,
        "star": STARS_TARIFF_CURRENCY,
        "stars": STARS_TARIFF_CURRENCY,
    }
    normalized = aliases.get(text, text)
    cleaned = "".join(ch for ch in normalized if ch.isalnum() or ch in {"_", "-"}).strip("_-")
    return cleaned or default


def payment_currency_code(currency: Any, default: str = "RUB") -> str:
    key = normalize_currency_key(currency, default=normalize_currency_key(default))
    if key == STARS_TARIFF_CURRENCY:
        return "XTR"
    return key.upper()


def default_currency_key_for_settings(settings: Any) -> str:
    try:
        config = settings.tariffs_config
    except Exception:
        config = None
    if config is not None and getattr(config, "default_currency", None):
        return normalize_currency_key(config.default_currency)
    return normalize_currency_key(settings.DEFAULT_CURRENCY_SYMBOL)


def default_payment_currency_code_for_settings(settings: Any) -> str:
    return payment_currency_code(default_currency_key_for_settings(settings))


def referral_welcome_bonus_tariff_key_for_settings(settings: Any) -> str | None:
    config = settings.tariffs_config
    if config is None:
        return None
    resolved_key = str(getattr(config, "referral_welcome_bonus_tariff_key", "") or "").strip()
    if resolved_key:
        return resolved_key
    configured_key = str(getattr(config, "referral_welcome_bonus_tariff", "") or "").strip()
    default_key = str(getattr(config, "default_tariff", "") or "").strip()
    return configured_key or default_key or None
