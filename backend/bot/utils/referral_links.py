"""Pure builders for referral deep links.

Both the bot handler and :class:`ReferralService` used to hold their own copies
of these formats; a service module must not import from ``bot.handlers``, so the
canonical builders live here and both callers re-point to them. Keep the URL
shapes byte-stable — they are shared with the Mini App ``?ref=u<code>`` parser.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def build_bot_referral_link(bot_username: str | None, referral_code: str | None) -> str | None:
    """Bot deep link ``https://t.me/<bot>?start=ref_u<code>``."""
    username = str(bot_username or "").strip().lstrip("@")
    code = str(referral_code or "").strip()
    if not username or not code:
        return None
    return f"https://t.me/{username}?start=ref_u{code}"


def build_webapp_referral_link(base_url: str | None, referral_code: str | None) -> str | None:
    """Mini App referral URL ``<base>?ref=u<code>`` (existing query keys preserved)."""
    if not base_url or not referral_code:
        return None
    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["ref"] = f"u{referral_code}"
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path or "/",
            urlencode(query),
            parts.fragment,
        )
    )
