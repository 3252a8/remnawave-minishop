"""Buttons an admin attaches to a ticket reply.

The buttons are resolved once, when the reply is sent, and the resolved links
are what gets stored. That is deliberate: a promo-code button must keep opening
the code the admin picked even after the code is renamed or deactivated, and
the chat, the Telegram notification and the e-mail must agree on the target.

Storage is a JSON array in a ``TEXT`` column — the schema has no JSON columns
and this keeps the migration a plain ``ADD COLUMN``. Every read goes through
:func:`decode_support_buttons`, which is total: a row written by an older or
newer build degrades to "no buttons" instead of breaking the conversation.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TypedDict

from bot.services.message_button_icons import validate_button_icon
from bot.services.message_composition import (
    MAX_MESSAGE_BUTTONS,
    MESSAGE_BUTTON_KINDS,
    MessageButton,
)

MAX_SUPPORT_MESSAGE_BUTTONS = MAX_MESSAGE_BUTTONS
_MAX_STORED_LABEL = 64
_MAX_STORED_URL = 2048


class SupportButtonPayload(TypedDict):
    label: str
    url: str
    kind: str
    promo_code: str
    section: str
    icon_custom_emoji_id: str | None
    icon_emoji: str


def encode_support_buttons(buttons: Sequence[MessageButton]) -> str | None:
    """Serialize resolved buttons for the message row; ``None`` when empty."""

    payload = [
        {
            "label": str(button.label or "")[:_MAX_STORED_LABEL],
            "url": str(button.url or "")[:_MAX_STORED_URL],
            "kind": str(button.kind or ""),
            "promo_code": str(button.promo_code or ""),
            "section": str(button.section or ""),
            "web_app_url": str(button.telegram_web_app_url or "")[:_MAX_STORED_URL],
            "icon_custom_emoji_id": button.icon_custom_emoji_id,
            "icon_emoji": button.icon_emoji,
        }
        for button in list(buttons)[:MAX_SUPPORT_MESSAGE_BUTTONS]
    ]
    return json.dumps(payload, ensure_ascii=False) if payload else None


def decode_support_buttons(raw: object) -> list[MessageButton]:
    """Read back stored buttons, skipping anything that no longer parses."""

    if not raw:
        return []
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return []
    else:
        parsed = raw
    if not isinstance(parsed, list):
        return []

    buttons: list[MessageButton] = []
    for item in parsed[:MAX_SUPPORT_MESSAGE_BUTTONS]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()[:_MAX_STORED_LABEL]
        url = str(item.get("url") or "").strip()[:_MAX_STORED_URL]
        kind = str(item.get("kind") or "").strip()
        if not label or not url or kind not in MESSAGE_BUTTON_KINDS:
            continue
        web_app_url = str(item.get("web_app_url") or "").strip()[:_MAX_STORED_URL]
        try:
            identifier, emoji = validate_button_icon(
                item.get("icon_custom_emoji_id"), item.get("icon_emoji", "")
            )
        except ValueError:
            identifier, emoji = None, ""
        buttons.append(
            MessageButton(
                label=label,
                url=url,
                kind=kind,
                promo_code=str(item.get("promo_code") or "").strip(),
                section=str(item.get("section") or "").strip(),
                telegram_web_app_url=web_app_url or None,
                icon_custom_emoji_id=identifier,
                icon_emoji=emoji,
            )
        )
    return buttons


def support_buttons_payload(raw: object) -> list[SupportButtonPayload]:
    """Buttons as the HTTP contract exposes them to the chat surfaces."""

    return [
        {
            "label": button.label,
            "url": button.url,
            "kind": button.kind,
            "promo_code": button.promo_code,
            "section": button.section,
            "icon_custom_emoji_id": button.icon_custom_emoji_id,
            "icon_emoji": button.icon_emoji,
        }
        for button in decode_support_buttons(raw)
    ]


__all__ = [
    "MAX_SUPPORT_MESSAGE_BUTTONS",
    "decode_support_buttons",
    "encode_support_buttons",
    "support_buttons_payload",
]
