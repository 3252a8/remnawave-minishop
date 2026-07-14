"""Helpers for Telegram Mini App URLs (subscription webapp)."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from config.settings import Settings
from db.dal.subscription_dal import normalize_install_share_token

_MINI_APP_START_PARAM_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TELEGRAM_BOT_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")


def append_query_params(base_url: str, params: dict[str, str]) -> str:
    """Merge params into an existing URL query string (adds or replaces keys)."""
    raw = (base_url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    existing = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in params.items():
        if value is None:
            existing.pop(key, None)
        else:
            existing[key] = str(value)
    query = urlencode(existing)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def subscription_mini_app_topup_url(settings: Settings, kind: str) -> str | None:
    """Return Mini App URL that opens the traffic top-up flow for ``kind`` (``regular`` or ``premium``)."""  # noqa: E501
    base = str(settings.SUBSCRIPTION_MINI_APP_URL or "").strip()
    if not base:
        return None
    normalized = "premium" if str(kind or "").strip().lower() == "premium" else "regular"
    return append_query_params(base, {"topup": normalized})


def subscription_mini_app_renew_url(
    settings: Settings, tariff_key: str | None = None
) -> str | None:
    """Return Mini App URL that opens the subscription renewal checkout."""
    base = str(settings.SUBSCRIPTION_MINI_APP_URL or "").strip()
    if not base:
        return None
    params = {"renew": "1"}
    normalized_tariff = str(tariff_key or "").strip()
    if normalized_tariff:
        params["renew_tariff"] = normalized_tariff
    return append_query_params(base, params)


def subscription_mini_app_checkout_code_url(settings: Settings, code: str) -> str | None:
    """Return Mini App URL that opens checkout with a prefilled code."""
    base = str(settings.SUBSCRIPTION_MINI_APP_URL or "").strip()
    normalized_code = str(code or "").strip()
    if not base or not normalized_code:
        return None
    return append_query_params(base, {"startapp": f"promo_{normalized_code}"})


def subscription_mini_app_path_url(settings: Settings, path: str) -> str | None:
    """Return a Mini App URL with ``path`` appended to the configured app base."""
    base = str(settings.SUBSCRIPTION_MINI_APP_URL or "").strip()
    if not base:
        return None
    normalized_path = f"/{str(path or '').lstrip('/')}"
    return f"{base.rstrip('/')}{normalized_path}"


def subscription_main_mini_app_deep_link(
    settings: Settings,
    bot_username: str | None,
    start_param: str,
) -> str | None:
    """Return a Telegram Main Mini App link for buttons outside private chats."""
    if not str(settings.SUBSCRIPTION_MINI_APP_URL or "").strip():
        return None
    username = str(bot_username or "").strip().lstrip("@")
    parameter = str(start_param or "").strip()
    if username == "your_bot_username" or not _TELEGRAM_BOT_USERNAME_RE.fullmatch(username):
        return None
    if not _MINI_APP_START_PARAM_RE.fullmatch(parameter):
        return None
    return f"https://t.me/{username}?startapp={parameter}"


def subscription_mini_app_install_url(settings: Settings) -> str | None:
    """Return the personal embedded install guide URL."""
    return subscription_mini_app_path_url(settings, "/install")


def subscription_mini_app_trial_url(settings: Settings) -> str | None:
    """Return the trial activation URL inside the Mini App."""
    return subscription_mini_app_path_url(settings, "/trial")


def subscription_public_install_url(settings: Settings, share_token: str) -> str | None:
    """Return the public install guide URL for a normalized share token."""
    token = normalize_install_share_token(share_token)
    base = str(settings.SUBSCRIPTION_MINI_APP_URL or "").strip()
    if not token or not base:
        return None
    parts = urlsplit(base)
    if parts.scheme and parts.netloc:
        public_base = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    else:
        public_base = base.rstrip("/")
    return f"{public_base.rstrip('/')}/s/{quote(token)}"
