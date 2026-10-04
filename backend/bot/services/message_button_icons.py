"""Validated button icons shared by immediate, queued and email delivery."""

from __future__ import annotations

import html
import re

from bot.utils.custom_emoji import valid_emoji_fallback
from config.telegram_emoji import CUSTOM_EMOJI_ID_RE

_EMAIL_ICON_LABEL = re.compile(
    r'^<tg-emoji emoji-id="([1-9][0-9]{0,19})">([^<>]*)</tg-emoji> (.*)$', re.DOTALL
)


def validate_button_icon(identifier: object, emoji: object) -> tuple[str | None, str]:
    """Keep document IDs as strings and require one complete Unicode sequence."""
    if identifier is not None and (
        not isinstance(identifier, str) or not CUSTOM_EMOJI_ID_RE.fullmatch(identifier)
    ):
        raise ValueError("button_custom_emoji_invalid")
    if not isinstance(emoji, str) or (emoji and not valid_emoji_fallback(emoji)):
        raise ValueError("button_emoji_invalid")
    return identifier, emoji


def unicode_button_label(label: str, identifier: str | None, emoji: str) -> str:
    fallback = emoji or ("🙂" if identifier else "")
    return f"{fallback} {label}" if fallback else label


def email_button_label(label: str, identifier: str | None, emoji: str) -> str:
    """Plain pairs remain compatible; opted-in icons carry a restricted prefix."""
    if not identifier:
        return unicode_button_label(label, identifier, emoji)
    fallback = emoji or "🙂"
    return (
        f'<tg-emoji emoji-id="{identifier}">{html.escape(fallback)}</tg-emoji> {html.escape(label)}'
    )


def email_button_label_parts(label: str) -> tuple[str, str]:
    """Return escaped HTML and plain text without enabling caption HTML."""
    match = _EMAIL_ICON_LABEL.fullmatch(label)
    if match is None or not valid_emoji_fallback(html.unescape(match[2])):
        return html.escape(label), label
    identifier, escaped_emoji, escaped_caption = match.groups()
    # Re-escape after decoding so even a forged prefix cannot inject caption markup.
    fallback = html.unescape(escaped_emoji)
    caption = html.unescape(escaped_caption)
    return (
        f'<span data-telegram-emoji-id="{identifier}">{html.escape(fallback)}</span> '
        f"{html.escape(caption)}",
        f"{fallback} {caption}",
    )
