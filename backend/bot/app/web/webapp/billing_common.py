import html
import logging
import re
from datetime import UTC, datetime
from typing import Any

from aiohttp import web

from bot.app.web.context import (
    get_i18n,
)

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TRIAL_ACTIVATION_FAILURE_STATUSES = {
    "trial_activation_failed_panel_link": 502,
    "trial_activation_failed_panel_update": 502,
    "trial_activation_failed_db": 500,
    "user_not_found_for_trial": 404,
}


def _plain_text_message(value: Any) -> str:
    """Strip Telegram-style HTML markup from a localized message for the web app."""
    text = _HTML_TAG_RE.sub("", str(value))
    return html.unescape(text).strip()


def _localized_webapp_message(request: web.Request, lang: str, key: str) -> str:
    i18n = get_i18n(request)
    if i18n and hasattr(i18n, "gettext"):
        try:
            message = str(i18n.gettext(lang, key) or "")
        except Exception:
            logger.debug("Failed to localize WebApp message key %s", key, exc_info=True)
        else:
            if message and message != key:
                return _plain_text_message(message)
    return key


def _billing_iso_datetime(value: Any | None) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=UTC)
        return normalized.isoformat()
    return str(value)


def _billing_datetime_text(value: Any | None) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=UTC)
        return normalized.strftime("%d.%m.%Y %H:%M")
    text = str(value)
    try:
        normalized = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return normalized.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return text


def _parse_positive_int_units(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not number.is_integer():
        return None
    integer = int(number)
    return integer if integer > 0 else None
