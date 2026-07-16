from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from bot.utils.locale_defaults import (
    SUBSCRIPTION_PURCHASE_DESCRIPTION_DEFAULT_KEY,
    TARIFF_PREMIUM_NAME_DEFAULT_KEY,
    subscription_purchase_description_text,
    tariff_premium_title,
)
from config.settings import DEFAULT_SUBSCRIPTION_PURCHASE_DESCRIPTION_EN, Settings
from config.tariffs_config import Tariff


def _locale(lang: str) -> dict[str, str]:
    return cast(
        dict[str, str],
        json.loads(Path("locales", f"{lang}.json").read_text(encoding="utf-8")),
    )


def _settings_with_description(text: str) -> Settings:
    return cast(
        Settings,
        SimpleNamespace(subscription_purchase_description=lambda language=None: text),
    )


def test_shipped_purchase_description_is_localized_for_russian() -> None:
    settings = _settings_with_description(DEFAULT_SUBSCRIPTION_PURCHASE_DESCRIPTION_EN)

    resolved = subscription_purchase_description_text(settings, "ru")

    expected = _locale("ru")[SUBSCRIPTION_PURCHASE_DESCRIPTION_DEFAULT_KEY]
    assert resolved == expected
    assert resolved != DEFAULT_SUBSCRIPTION_PURCHASE_DESCRIPTION_EN


def test_shipped_purchase_description_stays_english_for_english() -> None:
    settings = _settings_with_description(DEFAULT_SUBSCRIPTION_PURCHASE_DESCRIPTION_EN)

    resolved = subscription_purchase_description_text(settings, "en")

    assert resolved == _locale("en")[SUBSCRIPTION_PURCHASE_DESCRIPTION_DEFAULT_KEY]


def test_operator_purchase_description_is_returned_verbatim() -> None:
    settings = _settings_with_description("Operator copy")

    assert subscription_purchase_description_text(settings, "ru") == "Operator copy"


def test_empty_purchase_description_stays_empty() -> None:
    settings = _settings_with_description("")

    assert subscription_purchase_description_text(settings, "ru") == ""


def test_premium_title_default_is_localized() -> None:
    tariff = Tariff.model_construct(premium_names={})

    assert tariff_premium_title(tariff, "ru") == _locale("ru")[TARIFF_PREMIUM_NAME_DEFAULT_KEY]
    assert tariff_premium_title(tariff, "en") == _locale("en")[TARIFF_PREMIUM_NAME_DEFAULT_KEY]


def test_premium_title_prefers_configured_names() -> None:
    tariff = Tariff.model_construct(premium_names={"en": "Anti-jamming"})

    assert tariff_premium_title(tariff, "en") == "Anti-jamming"
