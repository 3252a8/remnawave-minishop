"""Read and edit the linked Remnawave user's description."""

from aiohttp import web

from bot.app.web.context import PanelService, get_session_factory, get_settings
from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from db.dal import message_log_dal

from .auth import _require_admin_user_id
from .common import _error, _ok
from .user_panel_account import linked_panel_account, user_panel_service
from .users_listing import _invalidate_after_admin_user_mutation


class AdminUserNoteBody(HttpBodyModel):
    note: str
    previous_note: str


class AdminUserNoteOut(HttpResponseModel):
    note: str


register_contract(
    "admin_user_note_get_route",
    RouteContract(response_schema=ok_envelope_for(AdminUserNoteOut), models=(AdminUserNoteOut,)),
)
register_contract(
    "admin_user_note_put_route",
    RouteContract(
        request_model=AdminUserNoteBody,
        response_schema=ok_envelope_for(AdminUserNoteOut),
        models=(AdminUserNoteOut,),
    ),
)


async def _read_note(panel: PanelService, reference: str) -> str | web.Response:
    lookup = await panel.get_user_by_uuid_lookup(reference)
    if lookup.get("not_found"):
        return _error(404, "panel_user_not_found")
    user = lookup.get("user")
    if not lookup.get("ok") or not isinstance(user, dict):
        return _error(502, "panel_unavailable")
    return str(user.get("description") or "")


async def admin_user_note_get_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    panel = user_panel_service(request)
    if panel is None:
        return _error(503, "panel_unavailable")
    async with get_session_factory(request)() as session:
        ref = await linked_panel_account(session, int(request.match_info["user_id"]))
    if isinstance(ref, web.Response):
        return ref
    note = await _read_note(panel, ref)
    return note if isinstance(note, web.Response) else _ok({"note": note})


async def admin_user_note_put_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    body = await parse_body_or_400(request, AdminUserNoteBody)
    panel = user_panel_service(request)
    if panel is None:
        return _error(503, "panel_unavailable")
    async with get_session_factory(request)() as session:
        ref = await linked_panel_account(session, target_id, lock=True)
        if isinstance(ref, web.Response):
            return ref
        current = await _read_note(panel, ref)
        if isinstance(current, web.Response):
            return current
        if current == body.note:
            return _ok({"note": current})
        if current != body.previous_note:
            return _error(409, "note_conflict")
        updated = await panel.update_user_details_on_panel(ref, {"description": body.note or None})
        if updated is None or str(updated.get("description") or "") != body.note:
            return _error(502, "panel_unavailable")
        await message_log_dal.create_message_log_no_commit(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_user_note_updated_webapp",
                "content": f"Updated panel note for user_id={target_id}",
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )
        await session.commit()
    await _invalidate_after_admin_user_mutation(
        get_settings(request), target_id, include_devices=False
    )
    return _ok({"note": body.note})
