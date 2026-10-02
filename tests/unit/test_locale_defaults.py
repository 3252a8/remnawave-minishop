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
    trial_premium_title,
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


def test_trial_premium_title_prefers_configured_title() -> None:
    settings = cast(Settings, SimpleNamespace(TRIAL_PREMIUM_TITLE="  Trial fast lane  "))

    assert trial_premium_title(settings, "en") == "Trial fast lane"
    assert trial_premium_title(settings, "ru") == "Trial fast lane"


def test_blank_trial_premium_title_uses_localized_default() -> None:
    for title in (None, "", " \t "):
        settings = cast(Settings, SimpleNamespace(TRIAL_PREMIUM_TITLE=title))
        for lang in ("ru", "en"):
            assert (
                trial_premium_title(settings, lang)
                == _locale(lang)[TARIFF_PREMIUM_NAME_DEFAULT_KEY]
            )


def test_admin_override_hint_translations_are_not_empty() -> None:
    # Regression guard: these shipped as empty placeholders once, which made
    # the admin card surface raw i18n keys via the ``fallback || key`` path.
    for lang in ("ru", "en"):
        locale = _locale(lang)
        for key in (
            "admin_user_regular_override_bonus_hint",
            "admin_user_premium_override_bonus_hint",
        ):
            assert locale[key].strip(), f"{lang}:{key} must not be empty"
