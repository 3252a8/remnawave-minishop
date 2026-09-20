"""External-auth event routing shared by the core reaction registry."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

EXTERNAL_REGISTRATION_PROVIDERS = {
    "discord_oauth": "discord",
    "google_oauth": "google",
    "yandex_oauth": "yandex",
}
EXTERNAL_MERGE_PROVIDERS = {
    "discord_verified_email_link": "discord",
    "discord_oauth_link": "discord",
    "google_verified_email_link": "google",
    "google_oauth_link": "google",
    "yandex_verified_email_link": "yandex",
    "yandex_oauth_link": "yandex",
}
ACCOUNT_MERGE_NOTIFY_REASONS = {
    "email_link",
    "telegram_link",
    "login",
    *EXTERNAL_MERGE_PROVIDERS,
}


async def react_to_external_identity_link(reactions: Any, payload: dict[str, Any]) -> None:
    user_id = payload.get("user_id")
    provider = str(payload.get("provider") or "")
    if user_id is None or provider not in {"discord", "google", "yandex"}:
        return
    service = reactions._notification_service()
    if service is None:
        return
    user = await reactions._load_user(user_id)
    try:
        await service.notify_account_external_identity_linked(
            user_id=int(user_id),
            provider=provider,
            link_source=str(payload.get("link_source") or "settings"),
            email=payload.get("email") or getattr(user, "email", None),
            telegram_id=payload.get("telegram_id") or getattr(user, "telegram_id", None),
            username=payload.get("username") or getattr(user, "username", None),
            first_name=payload.get("first_name") or getattr(user, "first_name", None),
        )
    except Exception:
        logger.exception(
            "Failed to react to external identity link provider=%s user_id=%s.",
            provider,
            user_id,
        )
