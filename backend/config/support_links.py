from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_TELEGRAM_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")
_TELEGRAM_HOSTS = {"t.me", "telegram.me", "www.t.me", "www.telegram.me"}


def normalize_support_link(value: object) -> str | None:
    """Return a Telegram-safe HTTP(S) support link or ``None`` when invalid."""

    if value is None:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    if raw.startswith("@"):
        username = raw[1:].strip()
        if not _TELEGRAM_USERNAME_RE.fullmatch(username):
            return None
        return f"https://t.me/{username}"

    lowered = raw.lower()
    for prefix in ("t.me/", "telegram.me/", "www.t.me/", "www.telegram.me/"):
        if lowered.startswith(prefix):
            raw = f"https://{raw}"
            break

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

    if hostname in _TELEGRAM_HOSTS:
        return urlunsplit(("https", "t.me", parsed.path, parsed.query, parsed.fragment))

    return raw
