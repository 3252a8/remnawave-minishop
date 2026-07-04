"""Validation and URL resolution for admin broadcast buttons and channels.

Buttons arrive from the admin webapp as ``AdminBroadcastButtonBody`` items and
are resolved into plain ``(label, url)`` pairs usable by both delivery
channels: Telegram inline keyboards and email CTA links. Promo buttons are
turned into deep links that trigger the existing quick-activation flows
(``/start promo_<CODE>`` in the bot, ``?promo=<CODE>`` in the Mini App).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config.settings import Settings

from .schemas import AdminBroadcastButtonBody

BROADCAST_CHANNELS = ("telegram", "email")
BUTTON_KIND_URL = "url"
BUTTON_KIND_PROMO_BOT = "promo_bot"
BUTTON_KIND_PROMO_WEBAPP = "promo_webapp"
BROADCAST_BUTTON_KINDS = (BUTTON_KIND_URL, BUTTON_KIND_PROMO_BOT, BUTTON_KIND_PROMO_WEBAPP)
MAX_BROADCAST_BUTTONS = 4
MAX_BUTTON_LABEL_LENGTH = 64
# Telegram limits /start payloads to 64 chars; the "promo_" prefix leaves 58.
_PROMO_CODE_DEEPLINK_RE = re.compile(r"^[A-Za-z0-9_-]{1,58}$")
_BOT_USERNAME_FALLBACK = "your_bot_username"


class BroadcastValidationError(ValueError):
    """Raised for admin-facing broadcast payload problems (mapped to HTTP 400/503)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class BroadcastButton:
    label: str
    url: str
    kind: str
    promo_code: str = ""


def normalize_broadcast_channels(raw: list[str] | None) -> list[str]:
    channels = [channel for channel in dict.fromkeys(raw or []) if channel]
    if not channels:
        raise BroadcastValidationError("no_channels")
    unknown = [channel for channel in channels if channel not in BROADCAST_CHANNELS]
    if unknown:
        raise BroadcastValidationError("invalid_channel", ", ".join(unknown))
    return [channel for channel in BROADCAST_CHANNELS if channel in channels]


def _clean_bot_username(bot_username: str | None) -> str:
    username = str(bot_username or "").strip().lstrip("@")
    if not username or username == _BOT_USERNAME_FALLBACK:
        return ""
    return username


def _webapp_base_url(settings: Settings) -> str:
    return str(settings.SUBSCRIPTION_MINI_APP_URL or "").strip().rstrip("/")


def _resolve_button_url(
    button: AdminBroadcastButtonBody,
    *,
    settings: Settings,
    bot_username: str | None,
) -> str:
    if button.kind == BUTTON_KIND_URL:
        url = button.url
        if not url:
            raise BroadcastValidationError("button_url_required", button.label)
        if not url.lower().startswith(("https://", "http://")):
            raise BroadcastValidationError("button_url_invalid", url)
        return url

    code = button.promo_code
    if not code:
        raise BroadcastValidationError("button_promo_code_required", button.label)
    if not _PROMO_CODE_DEEPLINK_RE.fullmatch(code):
        raise BroadcastValidationError("button_promo_code_invalid", code)

    username = _clean_bot_username(bot_username)
    if button.kind == BUTTON_KIND_PROMO_BOT:
        if not username:
            raise BroadcastValidationError("bot_username_unavailable")
        return f"https://t.me/{username}?start=promo_{code}"

    webapp_base = _webapp_base_url(settings)
    if webapp_base:
        return f"{webapp_base}/?promo={quote(code, safe='')}"
    if username:
        return f"https://t.me/{username}?startapp=promo_{code}"
    raise BroadcastValidationError("webapp_url_unavailable")


def resolve_broadcast_buttons(
    buttons: list[AdminBroadcastButtonBody],
    *,
    settings: Settings,
    bot_username: str | None,
) -> list[BroadcastButton]:
    if len(buttons) > MAX_BROADCAST_BUTTONS:
        raise BroadcastValidationError("too_many_buttons", str(MAX_BROADCAST_BUTTONS))

    resolved: list[BroadcastButton] = []
    for button in buttons:
        if button.kind not in BROADCAST_BUTTON_KINDS:
            raise BroadcastValidationError("button_kind_invalid", button.kind)
        if not button.label:
            raise BroadcastValidationError("button_label_required")
        if len(button.label) > MAX_BUTTON_LABEL_LENGTH:
            raise BroadcastValidationError("button_label_too_long", button.label)
        url = _resolve_button_url(button, settings=settings, bot_username=bot_username)
        resolved.append(
            BroadcastButton(
                label=button.label,
                url=url,
                kind=button.kind,
                promo_code=button.promo_code,
            )
        )
    return resolved


def broadcast_promo_codes(buttons: list[BroadcastButton]) -> list[str]:
    """Unique promo codes referenced by the resolved buttons, in input order."""
    return list(dict.fromkeys(button.promo_code for button in buttons if button.promo_code))


def telegram_markup_for_buttons(
    buttons: list[BroadcastButton],
) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button.label, url=button.url)] for button in buttons
        ]
    )


def email_links_for_buttons(buttons: list[BroadcastButton]) -> list[tuple[str, str]]:
    return [(button.label, button.url) for button in buttons]
