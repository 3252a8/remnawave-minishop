from __future__ import annotations

from config.link_targets import normalize_button_link


def normalize_support_link(value: object) -> str | None:
    """Return a Telegram-safe HTTP(S) support link or ``None`` when invalid."""
    return normalize_button_link(value)
