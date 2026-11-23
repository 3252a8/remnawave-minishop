"""Admin-only discovery, notification preferences and host update requests."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Literal

from aiohttp import web
from pydantic import Field
from redis.exceptions import RedisError

from bot.app.web.context import get_settings
from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from bot.infra.redis import get_redis, redis_key
from bot.services.core_update_publications import build_publication, publication_time
from bot.services.core_updates import (
    TAG_PATTERN,
    Release,
    available,
    bundled_distribution,
    check_image,
    image_tag,
    notifications_enabled,
    notifications_key,
)
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
    current_published_at: datetime | None = None
    tag: str
    release: Release | None
    available: bool
    official: bool
    installable: bool
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
    current_tag = image_tag()
    preference = None
    job: dict[str, str] = {}
    if redis is not None:
        try:
            live, saved_registry, preference = await redis.mget(
                f"{prefix}:live", f"{prefix}:registry", notifications_key(prefix, current_tag)
            )
            executor = bool(live)
            if saved_registry == "ghcr.io":
                registry = "ghcr.io"
            job = await redis.hgetall(f"{prefix}:job")
        except RedisError:
            return _error(503, "core_update_storage_unavailable")
    official = resolve_build_provenance() == "official"
    installable = official and not bundled_distribution()
    release = await check_image(tag or current_tag, registry, manual=manual) if official else None
    current = resolve_app_version()
    current_published_at = None
    if official:
        current_label, current_revision = build_publication(current)
        if release:
            target_label = "dev" if release.tag == "dev" else release.version
            current_published_at, published = await asyncio.gather(
                publication_time(current_label, current_revision),
                publication_time(target_label, release.revision),
            )
            release = release.model_copy(update={"published_at": published})
        else:
            current_published_at = await publication_time(current_label, current_revision)
    state = CoreUpdateState(
        current=current,
        current_published_at=current_published_at,
        tag=current_tag,
        release=release,
        available=available(release) or bool(release and release.tag != current_tag),
        official=official,
        installable=installable,
        executor=installable and executor,
        notifications=notifications_enabled(current_tag, preference),
        phase=job.get("phase", "") if installable else "",
        job_tag=job.get("tag", "") if installable else "",
    )
    return _ok({"state": state.model_dump(mode="json")})


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
    prefix = redis_key(settings, "core-update")
    await redis.set(notifications_key(prefix, image_tag()), "1" if body.enabled else "0")
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
    if redis is None or resolve_build_provenance() != "official" or bundled_distribution():
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
