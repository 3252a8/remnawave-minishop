"""Shared public-grant rotation around the panel's non-transactional revoke."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.mini_app_url import subscription_public_install_url
from config.settings import Settings
from db.dal import subscription_dal


async def reissue_subscription_access(
    session: AsyncSession,
    panel_service: Any,
    *,
    user_id: int,
    panel_user_uuid: str,
    settings: Settings,
) -> tuple[dict[str, Any] | None, str | None]:
    """Commit old-token revocation before asking the panel to rotate its link."""
    await subscription_dal.revoke_install_share_tokens_for_panel_user(session, panel_user_uuid)
    await session.commit()
    updated = await panel_service.revoke_user_subscription(panel_user_uuid)
    if not isinstance(updated, dict):
        return None, None
    short_uuid = str(updated.get("shortUuid") or "").strip()
    if not short_uuid:
        return updated, None
    subscription = await subscription_dal.get_active_subscription_by_user_id(
        session, user_id, panel_user_uuid
    )
    if subscription is None:
        return updated, None
    subscription.panel_subscription_uuid = short_uuid
    token = await subscription_dal.ensure_install_share_token(
        session, subscription, panel_short_uuid=short_uuid
    )
    await session.commit()
    if settings.SUBSCRIPTION_GATEWAY_ENABLED and settings.SUBSCRIPTION_LINK_MODE == "minishop":
        return updated, subscription_public_install_url(settings, token)
    return updated, None
