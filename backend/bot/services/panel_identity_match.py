"""Conservative ownership checks for native panel references."""

import hashlib
from typing import Any
from urllib.parse import urlsplit


def panel_origin_url(panel_api_url: str | None) -> str | None:
    """Return the panel API origin without credentials, query, or fragment."""
    if not panel_api_url:
        return None
    parsed = urlsplit(panel_api_url.strip())
    if not parsed.scheme or not parsed.hostname:
        return None
    return (
        f"{parsed.scheme.lower()}://{parsed.hostname.lower()}"
        f"{':' + str(parsed.port) if parsed.port else ''}"
        f"{parsed.path.rstrip('/')}"
    )


def panel_origin_fingerprint(panel_api_url: str | None) -> str | None:
    origin = panel_origin_url(panel_api_url)
    if origin is None:
        return None
    return hashlib.sha256(origin.encode("utf-8")).hexdigest()


def panel_candidate_matches_account(user: Any, candidate: dict[str, Any]) -> bool:
    """A matching numeric ID alone cannot establish ownership after a panel move."""
    username = str(candidate.get("username") or "").strip()
    if username and username in {
        str(getattr(user, "panel_username", None) or "").strip(),
        str(getattr(user, "minishop_id", None) or "").strip(),
    }:
        return True

    local_telegram_id = getattr(user, "telegram_id", None)
    panel_telegram_id = candidate.get("telegramId")
    if local_telegram_id is not None and panel_telegram_id is not None:
        try:
            if int(local_telegram_id) == int(panel_telegram_id):
                return True
        except (TypeError, ValueError):
            pass

    local_email = str(getattr(user, "email", None) or "").strip().lower()
    panel_email = str(candidate.get("email") or "").strip().lower()
    return bool(
        getattr(user, "email_verified_at", None)
        and local_email
        and panel_email
        and local_email == panel_email
    )
