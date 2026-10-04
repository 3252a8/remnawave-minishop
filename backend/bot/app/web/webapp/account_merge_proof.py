"""Short-lived, account-bound proof for an explicit merge of login identities."""

from __future__ import annotations

import secrets
import time
from typing import Any

from aiohttp import web

from bot.app.web.context import get_settings
from bot.app.web.webapp_auth import (
    create_signed_telegram_oauth_state,
    verify_signed_telegram_oauth_state,
)
from config.settings import Settings

MERGE_COOKIE = "rw_account_merge_proof"
MERGE_TTL = 600


def set_merge_proof(
    response: web.StreamResponse,
    settings: Settings,
    *,
    user_id: int,
    source_user_id: int,
    provider: str,
    subject: str,
) -> None:
    write_merge_proof(
        response,
        settings,
        {
            "purpose": "account_merge",
            "user_id": user_id,
            "source_user_id": source_user_id,
            "provider": provider,
            "subject": subject,
            "challenge": secrets.token_urlsafe(24),
            "expires_at": int(time.time()) + MERGE_TTL,
            "target_confirmed": False,
        },
    )


def write_merge_proof(
    response: web.StreamResponse, settings: Settings, proof: dict[str, Any]
) -> None:
    ttl = max(1, int(proof["expires_at"]) - int(time.time()))
    response.set_cookie(
        MERGE_COOKIE,
        create_signed_telegram_oauth_state(settings, proof, ttl_seconds=ttl),
        httponly=True,
        secure=True,
        samesite="Lax",
        path="/",
        max_age=ttl,
    )


def read_merge_proof(request: web.Request, user_id: int) -> dict[str, Any] | None:
    proof = verify_signed_telegram_oauth_state(
        get_settings(request), request.cookies.get(MERGE_COOKIE, "")
    )
    if not proof or proof.get("purpose") != "account_merge":
        return None
    try:
        if int(proof["user_id"]) != user_id or int(proof["expires_at"]) <= int(time.time()):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    if not proof.get("provider") or not proof.get("subject") or not proof.get("challenge"):
        return None
    return proof


def confirm_merge_target(
    request: web.Request,
    response: web.StreamResponse,
    *,
    user_id: int,
    challenge: str,
) -> bool:
    proof = read_merge_proof(request, user_id)
    if not proof or not secrets.compare_digest(str(proof["challenge"]), challenge):
        return False
    write_merge_proof(response, get_settings(request), {**proof, "target_confirmed": True})
    return True


def clear_merge_proof(response: web.StreamResponse) -> None:
    response.del_cookie(MERGE_COOKIE, path="/", httponly=True, secure=True, samesite="Lax")
