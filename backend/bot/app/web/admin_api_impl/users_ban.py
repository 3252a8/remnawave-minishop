import logging

from aiohttp import web

from bot.app.web.context import (
    get_optional_subscription_service,
    get_panel_service,
    get_session_factory,
    get_settings,
)
from bot.app.web.request_parsing import parse_body_or_400
from db.dal import user_dal

from .auth import _require_admin_user_id
from .common import _error, _ok, _serialize_user
from .schemas import AdminUserBanBody
from .users_listing import _invalidate_after_admin_user_mutation

logger = logging.getLogger(__name__)


async def admin_user_ban_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    body = await parse_body_or_400(request, AdminUserBanBody)
    desired = bool(body.banned)

    settings = get_settings(request)
    panel_service = get_panel_service(request)
    if panel_service is None:
        subscription_service = get_optional_subscription_service(request)
        panel_service = getattr(subscription_service, "panel_service", None)
    async_session_factory = get_session_factory(request)
    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, target_id)
        if not user:
            return _error(404, "not_found")

        panel_user_uuids = await user_dal.get_panel_user_uuids_for_user(
            session, target_id, user=user
        )
        if panel_user_uuids and panel_service is None:
            await session.rollback()
            return _error(503, "panel_service_unavailable")

        for panel_uuid in panel_user_uuids:
            try:
                panel_updated = await panel_service.update_user_status_on_panel(
                    panel_uuid, not desired
                )
            except Exception:
                logger.warning(
                    "Admin webapp failed to set panel user %s banned=%s for user %s",
                    panel_uuid,
                    desired,
                    target_id,
                    exc_info=True,
                )
                await session.rollback()
                return _error(502, "panel_status_update_failed")

            if not panel_updated:
                await session.rollback()
                return _error(502, "panel_status_update_failed")

        user.is_banned = desired
        await session.commit()
        await session.refresh(user)
    await _invalidate_after_admin_user_mutation(settings, target_id)
    return _ok({"user": _serialize_user(user)})
