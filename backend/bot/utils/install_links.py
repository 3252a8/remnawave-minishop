"""Helpers for Telegram bot install-guide links."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.mini_app_url import (
    subscription_mini_app_install_url,
    subscription_public_install_url,
)
from config.subscription_guides_config import subscription_guides_available
from db.dal import subscription_dal


@dataclass(frozen=True)
class InstallGuideLinks:
    personal_url: Optional[str] = None
    public_share_url: Optional[str] = None


def bot_install_guides_enabled(settings: Any) -> bool:
    return bool(
        getattr(settings, "SUBSCRIPTION_GUIDES_BOT_MENU_ENABLED", False)
        and subscription_guides_available(settings)
        and subscription_mini_app_install_url(settings)
    )


def bot_install_guide_url(settings: Any) -> Optional[str]:
    if not bot_install_guides_enabled(settings):
        return None
    return subscription_mini_app_install_url(settings)


async def ensure_user_install_guide_links(
    session: AsyncSession,
    settings: Any,
    user_id: int,
    panel_user_uuid: Optional[str] = None,
    local_subscription: Optional[Any] = None,
) -> InstallGuideLinks:
    personal_url = bot_install_guide_url(settings)
    if not personal_url:
        return InstallGuideLinks()

    public_share_url = None
    try:
        local_sub = (
            local_subscription
            if local_subscription is not None
            else await subscription_dal.get_active_subscription_by_user_id(
                session,
                user_id,
                panel_user_uuid,
            )
        )
        if local_sub is not None:
            share_token = await subscription_dal.ensure_install_share_token(session, local_sub)
            public_share_url = subscription_public_install_url(settings, share_token)
    except Exception:
        logging.exception("Failed to resolve install guide share link for user %s.", user_id)

    return InstallGuideLinks(personal_url=personal_url, public_share_url=public_share_url)


def append_install_share_link_text(
    text: str,
    translator: Any,
    public_share_url: Optional[str],
) -> str:
    if not public_share_url:
        return text
    try:
        share_line = translator(
            "install_guide_share_link_line",
            install_share_link=public_share_url,
        )
    except Exception:
        share_line = f"\n\nInstall guide:\n<code>{public_share_url}</code>"
    return f"{text}{share_line}"
