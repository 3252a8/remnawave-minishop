"""Runtime defaults whose localized variants live in the locale files.

Backend source is English-only (the ``cyrillic_fallbacks`` gate), so any
default that has a Russian variant is stored in ``locales/*.json`` and
resolved here at runtime; the in-code string stays the English safety net.
"""

from __future__ import annotations

from bot.middlewares.i18n import get_i18n_instance
from config.settings import (
    DEFAULT_SUBSCRIPTION_PURCHASE_DESCRIPTION_EN,
    DEFAULT_SUBSCRIPTION_PURCHASE_DESCRIPTION_RU,
    Settings,
)
from config.tariffs_config import Tariff

TARIFF_PREMIUM_NAME_DEFAULT_KEY = "tariff_premium_name_default"
SUBSCRIPTION_PURCHASE_DESCRIPTION_DEFAULT_KEY = "subscription_purchase_description_default"


def localized_default_text(lang: str | None, key: str) -> str | None:
    """Return the locale text for ``key``, or ``None`` when the key is missing."""
    text = get_i18n_instance().gettext(lang, key)
    if text and text != key:
        return str(text)
    return None


def tariff_premium_title(tariff: Tariff, lang: str) -> str:
    """Premium-servers section title for a tariff with a localized default."""
    return tariff.premium_name(
        lang,
        default=localized_default_text(lang, TARIFF_PREMIUM_NAME_DEFAULT_KEY),
    )


def subscription_purchase_description_text(settings: Settings, lang: str | None) -> str:
    """Purchase description honoring operator overrides.

    An operator-provided text is returned verbatim; the shipped default is
    replaced with its localized locale-file variant for the requested
    language.
    """
    text = settings.subscription_purchase_description(lang)
    if not text:
        return ""
    unchanged_defaults = {
        DEFAULT_SUBSCRIPTION_PURCHASE_DESCRIPTION_RU.strip(),
        DEFAULT_SUBSCRIPTION_PURCHASE_DESCRIPTION_EN.strip(),
    }
    if text.strip() in unchanged_defaults:
        localized = localized_default_text(lang, SUBSCRIPTION_PURCHASE_DESCRIPTION_DEFAULT_KEY)
        if localized:
            return localized
    return text
