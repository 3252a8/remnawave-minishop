"""Admin actions for recorded panel devices, separate from device entitlements."""

import logging

from aiohttp import web

from bot.app.web.context import (
    get_optional_subscription_service,
    get_panel_service,
    get_session_factory,
    get_settings,
)
from db.dal import message_log_dal, subscription_dal, user_dal

from .auth import _require_admin_user_id
from .common import _error, _ok
from .users_listing import _invalidate_after_admin_user_mutation

logger = logging.getLogger(__name__)


async def admin_user_hwid_devices_reset_route(request: web.Request) -> web.Response:
    """Clear recorded HWIDs without changing the subscription link or device allowance."""
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    settings = get_settings(request)
    panel_service = get_panel_service(request)
    if panel_service is None:
        subscription_service = get_optional_subscription_service(request)
        panel_service = getattr(subscription_service, "panel_service", None)
    if panel_service is None:
        return _error(503, "panel_service_unavailable")

    async_session_factory = get_session_factory(request)
    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, target_id)
        if user is None:
            return _error(404, "not_found")
        active = await subscription_dal.get_active_subscription_by_user_id(session, target_id)
        panel_user_uuid = str(
            getattr(user, "panel_user_uuid", None) or getattr(active, "panel_user_uuid", None) or ""
        ).strip()
        if not panel_user_uuid:
            return _error(404, "no_panel_user", "The user is not linked to a Remnawave panel user")

        try:
            cleared = await panel_service.reset_user_hwid_devices(panel_user_uuid)
        except Exception:
            logger.warning("Failed to reset recorded devices for user %s", target_id, exc_info=True)
            cleared = False
        finally:
            # A failed multi-device reset can still have removed some devices.
            await _invalidate_after_admin_user_mutation(settings, target_id)
        if not cleared:
            return _error(
                502,
                "panel_hwid_reset_failed",
                "Unable to clear all recorded devices on the Remnawave panel",
            )

        await message_log_dal.create_message_log_no_commit(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_hwid_devices_reset_webapp",
                "content": f"Cleared recorded HWID devices for user_id={target_id}",
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )
        await session.commit()

    return _ok({})
