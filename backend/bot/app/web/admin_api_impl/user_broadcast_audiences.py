from typing import Literal

from aiohttp import web
from pydantic import Field

from bot.app.web.context import get_session_factory
from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from bot.services.audience_segmentation import audience_target_user_id
from db.dal import broadcast_audience_dal, user_dal

from .auth import _require_admin_user_id
from .broadcast import _resolve_audience_service
from .common import _error, _ok


class UserBroadcastExclusionsOut(HttpResponseModel):
    excluded: list[str]


class UserBroadcastAudiencesOut(UserBroadcastExclusionsOut):
    targets: list[str]


class UserBroadcastExclusionsBody(HttpBodyModel):
    action: Literal["exclude", "include", "exclude_all", "reset"]
    target: str | None = Field(default=None, min_length=1, max_length=64)


register_contract(
    "admin_user_broadcast_audiences_get_route",
    RouteContract(
        response_schema=ok_envelope_for(UserBroadcastAudiencesOut),
        models=(UserBroadcastAudiencesOut,),
    ),
)
register_contract(
    "admin_user_broadcast_audiences_patch_route",
    RouteContract(
        request_model=UserBroadcastExclusionsBody,
        response_schema=ok_envelope_for(UserBroadcastExclusionsOut),
        models=(UserBroadcastExclusionsOut,),
    ),
)


async def admin_user_broadcast_audiences_get_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    user_id = int(request.match_info["user_id"])
    async with get_session_factory(request)() as session:
        if await user_dal.get_user_by_id(session, user_id) is None:
            return _error(404, "not_found", "User not found")
        excluded = await broadcast_audience_dal.user_exclusions(session, user_id)
    targets = await _resolve_audience_service(request).user_audiences(user_id)
    return _ok(UserBroadcastAudiencesOut(targets=targets, excluded=sorted(excluded)).model_dump())


async def admin_user_broadcast_audiences_patch_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    user_id = int(request.match_info["user_id"])
    body = await parse_body_or_400(request, UserBroadcastExclusionsBody)
    target = (body.target or "").strip().lower()
    if (body.action in {"exclude", "include"}) != bool(target):
        return _error(400, "invalid_audience", target)

    service = _resolve_audience_service(request)
    if body.action == "exclude":
        if audience_target_user_id(target) is not None or not service.has_target(target):
            return _error(400, "invalid_audience", target)
        if not service.is_target_available(target):
            return _error(403, "audience_unavailable", target)

    matched = await service.user_audiences(user_id) if body.action == "exclude_all" else []
    async with get_session_factory(request)() as session, session.begin():
        if await user_dal.lock_user_by_id(session, user_id) is None:
            return _error(404, "not_found", "User not found")
        old = await broadcast_audience_dal.user_exclusions(session, user_id)
        if body.action == "exclude":
            new = old | {target}
        elif body.action == "include":
            new = old - {target}
        elif body.action == "exclude_all":
            new = old.union(matched)
        else:
            new = set()
        await broadcast_audience_dal.set_user_exclusions(session, user_id, old, new)
    return _ok(UserBroadcastExclusionsOut(excluded=sorted(new)).model_dump())
