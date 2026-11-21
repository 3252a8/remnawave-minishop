"""Admin-only discovery, notification preferences and host update requests."""

from __future__ import annotations

import uuid
from typing import Literal

from aiohttp import web
from pydantic import Field
from redis.exceptions import RedisError

from bot.app.web.context import get_settings
from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from bot.infra.redis import get_redis, redis_key
from bot.services.core_updates import TAG_PATTERN, Release, available, check_image, image_tag
from bot.utils.app_version import resolve_app_version, resolve_build_provenance

from .auth import _require_admin_user_id
from .common import _error, _ok


class CoreUpdateBody(HttpBodyModel):
    tag: str = Field(pattern=TAG_PATTERN, max_length=64)
    revision: str = Field(pattern=r"^[a-f0-9]{40}$")


class CoreUpdatePreference(HttpBodyModel):
    enabled: bool


class CoreUpdateSelection(HttpBodyModel):
    tag: str = Field(pattern=TAG_PATTERN, max_length=64)


class CoreUpdateState(HttpResponseModel):
    current: str
    tag: str
    release: Release | None
    available: bool
    official: bool
    executor: bool
    notifications: bool
    phase: str
    job_tag: str


def _contract(body: type[HttpBodyModel] | None = None) -> RouteContract:
    return RouteContract(
        request_model=body,
        response_schema=ok_envelope_for(CoreUpdateState, key="state"),
        models=(CoreUpdateState, Release),
    )


register_contract("admin_core_updates_route", _contract())
register_contract("admin_core_check_route", _contract(CoreUpdateSelection))
register_contract("admin_core_preference_route", _contract(CoreUpdatePreference))
register_contract("admin_core_apply_route", _contract(CoreUpdateBody))


async def _state(request: web.Request, *, tag: str = "", manual: bool = False) -> web.Response:
    settings = get_settings(request)
    prefix = redis_key(settings, "core-update")
    redis = await get_redis(settings)
    registry: Literal["docker.io", "ghcr.io"] = "docker.io"
    executor = False
    notifications = True
    job: dict[str, str] = {}
    if redis is not None:
        try:
            live, saved_registry, pref = await redis.mget(
                f"{prefix}:live", f"{prefix}:registry", f"{prefix}:notify"
            )
            executor = bool(live)
            if saved_registry == "ghcr.io":
                registry = "ghcr.io"
            notifications = pref != "0"
            job = await redis.hgetall(f"{prefix}:job")
        except RedisError:
            return _error(503, "core_update_storage_unavailable")
    current_tag = image_tag()
    official = resolve_build_provenance() == "official"
    release = await check_image(tag or current_tag, registry, manual=manual) if official else None
    state = CoreUpdateState(
        current=resolve_app_version(),
        tag=current_tag,
        release=release,
        available=available(release) or bool(release and release.tag != current_tag),
        official=official,
        executor=executor,
        notifications=notifications,
        phase=job.get("phase", ""),
        job_tag=job.get("tag", ""),
    )
    return _ok({"state": state.model_dump()})


async def admin_core_updates_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    return await _state(request)


async def admin_core_check_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    body = await parse_body_or_400(request, CoreUpdateSelection)
    return await _state(request, tag=body.tag, manual=True)


async def admin_core_preference_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    body = await parse_body_or_400(request, CoreUpdatePreference)
    settings = get_settings(request)
    redis = await get_redis(settings)
    if redis is None:
        return _error(503, "core_update_storage_unavailable")
    await redis.set(redis_key(settings, "core-update", "notify"), "1" if body.enabled else "0")
    return await _state(request)


_QUEUE = """
if not redis.call('GET', KEYS[1]) then return -1 end
local phase = redis.call('HGET', KEYS[2], 'phase')
if phase and phase ~= 'complete' and phase ~= 'failed' then return 0 end
redis.call('HSET', KEYS[2], 'id', ARGV[1], 'tag', ARGV[2], 'revision', ARGV[3], 'phase', 'queued')
redis.call('EXPIRE', KEYS[2], 90)
return 1
"""


async def admin_core_apply_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    body = await parse_body_or_400(request, CoreUpdateBody)
    settings = get_settings(request)
    redis = await get_redis(settings)
    if redis is None or resolve_build_provenance() != "official":
        return _error(409, "core_update_unavailable")
    prefix = redis_key(settings, "core-update")
    registry = await redis.get(f"{prefix}:registry")
    release = await check_image(body.tag, "ghcr.io" if registry == "ghcr.io" else "docker.io")
    if not release or release.revision != body.revision:
        return _error(409, "core_update_changed")
    result = await redis.eval(
        _QUEUE, 2, f"{prefix}:live", f"{prefix}:job", uuid.uuid4().hex, body.tag, body.revision
    )
    if result != 1:
        return _error(409, "core_update_busy" if result == 0 else "core_update_unavailable")
    return await _state(request)
