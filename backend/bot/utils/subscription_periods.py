"""Localized billing labels shared by the bot, web checkout and notifications."""

from collections.abc import Callable
from typing import Any

from config.subscription_periods import duration_label_parts


def format_duration_days(duration_days: int, translate: Callable[..., str], language: str) -> str:
    count, unit = duration_label_parts(duration_days)
    bucket = "one" if count == 1 else "many"
    if language.lower().split("-")[0] == "ru":
        if count % 10 == 1 and count % 100 != 11:
            bucket = "one"
        elif count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
            bucket = "few"
    return f"{count} {translate(f'wa_sub_term_{unit}_{bucket}')}"


def localized_duration_days(duration_days: int, i18n: Any, language: str) -> str:
    return format_duration_days(
        duration_days, lambda key: str(i18n.gettext(language, key)), language
    )
