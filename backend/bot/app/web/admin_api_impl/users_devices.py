"""Admin actions for recorded panel devices, separate from device entitlements."""

import logging

from aiohttp import web
from pydantic import Field

from bot.app.web.context import (
    get_session_factory,
    get_settings,
)
from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    RouteContract,
    ok_envelope_for,
    ok_envelope_with,
    register_contract,
)
from bot.app.web.webapp.devices import WebAppDeviceOut, _find_device_by_token, _serialize_device
from db.dal import device_name_dal, message_log_dal

from .auth import _require_admin_user_id
from .common import _error, _ok
from .user_panel_account import linked_panel_account, user_panel_service
from .users_listing import _invalidate_after_admin_user_mutation

logger = logging.getLogger(__name__)


class AdminUserDevicesOut(HttpResponseModel):
    devices: list[WebAppDeviceOut]


class AdminUserDisconnectDeviceBody(HttpBodyModel):
    device_token: str = Field(pattern=r"^[0-9a-f]{32}$")


register_contract(
    "admin_user_devices_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminUserDevicesOut),
        models=(AdminUserDevicesOut,),
    ),
)
register_contract(
    "admin_user_device_disconnect_route",
    RouteContract(
        request_model=AdminUserDisconnectDeviceBody,
        response_schema=ok_envelope_with(),
    ),
)


async def admin_user_devices_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    panel = user_panel_service(request)
    if panel is None:
        return _error(503, "panel_unavailable")
    async with get_session_factory(request)() as session:
        ref = await linked_panel_account(session, target_id)
        if isinstance(ref, web.Response):
            return ref
        names = await device_name_dal.get_device_names(session, target_id)
    devices = await panel.get_user_devices(ref, force_refresh=True)
    if devices is None:
        return _error(502, "devices_load_failed")
    return _ok({"devices": [_serialize_device(row, i, names) for i, row in enumerate(devices, 1)]})


async def admin_user_device_disconnect_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    body = await parse_body_or_400(request, AdminUserDisconnectDeviceBody)
    panel = user_panel_service(request)
    if panel is None:
        return _error(503, "panel_unavailable")
    async with get_session_factory(request)() as session:
        ref = await linked_panel_account(session, target_id, lock=True)
        if isinstance(ref, web.Response):
            return ref
        devices = await panel.get_user_devices(ref, force_refresh=True)
        if devices is None:
            return _error(502, "devices_load_failed")
        matched = _find_device_by_token(devices, body.device_token)
        if not matched:
            return _error(404, "device_not_found")
        if not await panel.disconnect_device(ref, str(matched[1]["hwid"]).strip()):
            return _error(502, "device_disconnect_failed")
        await _invalidate_after_admin_user_mutation(get_settings(request), target_id)
        await message_log_dal.create_message_log_no_commit(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_hwid_device_disconnected_webapp",
                "content": f"Disconnected one registered device for user_id={target_id}",
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )
        await session.commit()
    return _ok({})


async def admin_user_hwid_devices_reset_route(request: web.Request) -> web.Response:
    """Clear recorded HWIDs without changing the subscription link or device allowance."""
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    settings = get_settings(request)
    panel_service = user_panel_service(request)
    if panel_service is None:
        return _error(503, "panel_service_unavailable")

    async_session_factory = get_session_factory(request)
    async with async_session_factory() as session:
        panel_user_uuid = await linked_panel_account(session, target_id)
        if isinstance(panel_user_uuid, web.Response):
            return panel_user_uuid

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
