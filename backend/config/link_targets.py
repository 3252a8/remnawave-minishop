"""Shared normalization for customer-facing HTTP and Telegram button links."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

TELEGRAM_LINK_HOSTS = frozenset({"t.me", "telegram.me", "www.t.me", "www.telegram.me"})

_TELEGRAM_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")
_TELEGRAM_SHORT_PREFIXES = ("t.me/", "telegram.me/", "www.t.me/", "www.telegram.me/")


def normalize_button_link(value: object, *, telegram_only: bool = False) -> str | None:
    """Return a safe HTTP(S) link, canonicalizing Telegram shortcuts to ``t.me``."""

    if value is None:
        return None
    raw = str(value).strip()
    if not raw or len(raw) > 2048:
        return None

    if raw.startswith("@"):
        username = raw[1:].strip()
        if not _TELEGRAM_USERNAME_RE.fullmatch(username):
            return None
        raw = f"https://t.me/{username}"
    else:
        lowered = raw.lower()
        if lowered.startswith(_TELEGRAM_SHORT_PREFIXES):
            raw = f"https://{raw}"

    if any(character.isspace() or ord(character) < 32 for character in raw):
        return None

    try:
        parsed = urlsplit(raw)
        _ = parsed.port
    except ValueError:
        return None

    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    if scheme not in {"http", "https"} or not parsed.netloc or not hostname:
        return None
    if parsed.username or parsed.password:
        return None

    is_telegram = hostname in TELEGRAM_LINK_HOSTS
    if telegram_only and not is_telegram:
        return None
    if is_telegram:
        if not parsed.path.strip("/"):
            return None
        return urlunsplit(("https", "t.me", parsed.path, parsed.query, parsed.fragment))

    return urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))


def is_telegram_button_link(value: object) -> bool:
    """Return whether ``value`` resolves to a canonical Telegram link."""

    normalized = normalize_button_link(value)
    return bool(normalized and (urlsplit(normalized).hostname or "").lower() == "t.me")
