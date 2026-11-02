"""Typed invitation links shared by the two independent invitation programs."""

import re
from typing import Literal
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

DEFAULT_INVITE_LINK_PREFIX = "discount"


def invitation_link_prefix(settings: object) -> str:
    return str(getattr(settings, "INVITE_LINK_PREFIX", DEFAULT_INVITE_LINK_PREFIX))


def decode_invitation_payload(raw: str | None, prefix: str = DEFAULT_INVITE_LINK_PREFIX) -> str:
    value = str(raw or "").strip()
    for candidate in {DEFAULT_INVITE_LINK_PREFIX, prefix} - {""}:
        if value.startswith(f"{candidate}_"):
            payload = value[len(candidate) + 1 :]
            match = re.fullmatch(r"([rp])_([A-Za-z0-9_-]{1,43})", payload)
            if match:
                kind, code = match.groups()
                return f"ref_u{code}" if kind == "r" else f"p_{code}"
    return value


def build_invitation_link(
    target: str | None,
    code: str | None,
    *,
    kind: Literal["r", "p"],
    prefix: str,
    telegram: bool,
) -> str | None:
    base = str(target or "").strip()
    token = str(code or "").strip()
    if not base or not token:
        return None
    if telegram:
        username = base.lstrip("@")
        if not username:
            return None
        payload = (
            f"{prefix}_{kind}_{token}"
            if prefix
            else (f"ref_u{token}" if kind == "r" else f"p_{token}")
        )
        return f"https://t.me/{quote(username, safe='')}?start={quote(payload, safe='')}"
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key in {"ref", "partner", DEFAULT_INVITE_LINK_PREFIX, prefix} - {""}:
        query.pop(key, None)
    key = prefix or ("ref" if kind == "r" else "partner")
    query[key] = f"{kind}_{token}" if prefix else (f"u{token}" if kind == "r" else token)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path or "/", urlencode(query), parts.fragment)
    )
