"""Administrative package installation and runtime asset routes."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import mimetypes
from pathlib import Path
from typing import Any

from aiohttp import BodyPartReader, web

from bot.app.web.route_contracts import (
    BINARY_RESPONSE_SCHEMA,
    JSON_ARRAY_SCHEMA,
    JSON_OBJECT_SCHEMA,
    RouteContract,
    ok_envelope_with,
    register_contract,
)
from bot.plugins.packages import (
    MAX_ARCHIVE_BYTES,
    PluginPackageError,
    activate_staged,
    inspect_archive,
    package_root,
    read_state,
    remove_plugin,
    set_enabled,
    stage_archive,
    trust_publisher,
)
from bot.plugins.sources import fetch_ready_package

from .auth import _require_admin_user_id
from .common import _error, _ok

logger = logging.getLogger(__name__)


async def _json(request: web.Request) -> dict[str, Any]:
    if request.content_length and request.content_length > 4096:
        raise PluginPackageError("request_too_large", status=413)
    try:
        value = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PluginPackageError("invalid_request") from exc
    if not isinstance(value, dict):
        raise PluginPackageError("invalid_request")
    return value


async def _archive(request: web.Request) -> bytes:
    if request.content_length and request.content_length > MAX_ARCHIVE_BYTES + 65536:
        raise PluginPackageError("archive_too_large", status=413)
    try:
        reader = await request.multipart()
        part = await reader.next()
    except (ValueError, AssertionError) as exc:
        raise PluginPackageError("archive_file_required") from exc
    if not isinstance(part, BodyPartReader) or part.name != "file":
        raise PluginPackageError("archive_file_required")
    body = bytearray()
    async with asyncio.timeout(120):
        while chunk := await part.read_chunk(64 * 1024):
            body.extend(chunk)
            if len(body) > MAX_ARCHIVE_BYTES:
                raise PluginPackageError("archive_too_large", status=413)
        if await reader.next() is not None:
            raise PluginPackageError("one_archive_required")
    return bytes(body)


def guarded(handler: Any) -> Any:
    async def wrapper(request: web.Request) -> web.Response:
        actor = _require_admin_user_id(request)
        request["plugin_actor"] = actor
        try:
            return await handler(request)
        except PluginPackageError as exc:
            return _error(exc.status, exc.code)
        except (OSError, KeyError):
            logger.exception("Plugin package storage operation failed")
            return _error(503, "plugin_storage_unavailable")

    wrapper.__name__ = handler.__name__
    return wrapper


@guarded
async def admin_plugin_packages_route(request: web.Request) -> web.Response:
    state = await asyncio.to_thread(read_state, package_root())
    from importlib import metadata

    bundled = [
        {"id": point.name, "source": "image", "status": "active"}
        for point in metadata.entry_points(group="minishop.plugins")
    ]
    return _ok(
        {
            "generation": state["generation"],
            "installations": state["installations"],
            "operations": state.get("operations", []),
            "bundled": bundled,
            "observations": state.get("observations", {}),
            "failed_generation": state.get("failed_generation"),
            "failure": state.get("failure", ""),
        }
    )


@guarded
async def admin_plugin_preview_route(request: web.Request) -> web.Response:
    body = await _archive(request)
    result = await asyncio.to_thread(inspect_archive, package_root(), body)
    return _ok(result.public())


@guarded
async def admin_plugin_stage_route(request: web.Request) -> web.Response:
    body = await _archive(request)
    result = await asyncio.to_thread(stage_archive, package_root(), body, request["plugin_actor"])
    return _ok(result)


async def _repository_candidate(request: web.Request) -> tuple[bytes, dict[str, str]]:
    body = await _json(request)
    url = body.get("url")
    ref = body.get("ref", "")
    if not isinstance(url, str) or not isinstance(ref, str):
        raise PluginPackageError("invalid_request")
    return await fetch_ready_package(url, ref)


@guarded
async def admin_plugin_repository_preview_route(request: web.Request) -> web.Response:
    archive, source = await _repository_candidate(request)
    result = await asyncio.to_thread(inspect_archive, package_root(), archive)
    return _ok({**result.public(), "source": source})


@guarded
async def admin_plugin_repository_stage_route(request: web.Request) -> web.Response:
    archive, source = await _repository_candidate(request)
    result = await asyncio.to_thread(
        stage_archive, package_root(), archive, request["plugin_actor"], source
    )
    return _ok({**result, "source": source})


@guarded
async def admin_plugin_trust_route(request: web.Request) -> web.Response:
    body = await _json(request)
    publisher = body.get("publisher")
    public_key = body.get("public_key")
    fingerprint = body.get("fingerprint")
    if not all(isinstance(value, str) for value in (publisher, public_key, fingerprint)):
        raise PluginPackageError("invalid_request")
    result = await asyncio.to_thread(
        trust_publisher, package_root(), publisher, public_key, fingerprint
    )
    return _ok({"fingerprint": result})


@guarded
async def admin_plugin_install_route(request: web.Request) -> web.Response:
    body = await _json(request)
    operation_id = body.get("operation_id")
    digest = body.get("digest")
    generation = body.get("generation")
    if (
        not isinstance(operation_id, str)
        or not isinstance(digest, str)
        or not isinstance(generation, int)
    ):
        raise PluginPackageError("invalid_request")
    state = await asyncio.to_thread(
        activate_staged, package_root(), operation_id, digest, request["plugin_actor"], generation
    )
    return _ok(state)


@guarded
async def admin_plugin_enabled_route(request: web.Request) -> web.Response:
    body = await _json(request)
    enabled = body.get("enabled")
    generation = body.get("generation")
    if not isinstance(enabled, bool) or not isinstance(generation, int):
        raise PluginPackageError("invalid_request")
    state = await asyncio.to_thread(
        set_enabled,
        package_root(),
        request.match_info["plugin_id"],
        enabled,
        request["plugin_actor"],
        generation,
    )
    return _ok(state)


@guarded
async def admin_plugin_remove_route(request: web.Request) -> web.Response:
    body = await _json(request)
    generation = body.get("generation")
    if not isinstance(generation, int):
        raise PluginPackageError("invalid_request")
    state = await asyncio.to_thread(
        remove_plugin,
        package_root(),
        request.match_info["plugin_id"],
        request["plugin_actor"],
        generation,
    )
    return _ok(state)


def _active_frontends(root: Path) -> tuple[int, list[dict[str, Any]]]:
    state = read_state(root)
    generation = state["generation"]
    if not all(
        state.get("observations", {}).get(role) == {"generation": generation, "status": "active"}
        for role in ("backend", "worker")
    ):
        return generation, []
    entries: list[dict[str, Any]] = []
    for plugin_id, installation in state["installations"].items():
        if not installation["enabled"]:
            continue
        release = root / "releases" / plugin_id / installation["digest"]
        manifest = json.loads((release / "plugin.json").read_text(encoding="utf-8"))
        frontend = manifest.get("frontend")
        if not isinstance(frontend, dict):
            continue
        entries.append(
            {
                "id": plugin_id,
                "digest": installation["digest"],
                "sections": frontend.get("sections", []),
                "section_groups": frontend.get("section_groups", []),
                "section_tabs": frontend.get("section_tabs", []),
                "user_panels": frontend.get("user_panels", []),
                "styles": [
                    f"/api/admin/plugins/assets/{plugin_id}/{installation['digest']}/{style}"
                    for style in frontend.get("styles", [])
                ],
                "entry": (
                    f"/api/admin/plugins/assets/{plugin_id}/"
                    f"{installation['digest']}/{frontend['entry']}"
                ),
            }
        )
    return generation, entries


@guarded
async def admin_plugin_runtime_route(request: web.Request) -> web.Response:
    generation, entries = await asyncio.to_thread(_active_frontends, package_root())
    return _ok({"generation": generation, "plugins": entries})


@guarded
async def admin_plugin_asset_route(request: web.Request) -> web.Response:
    plugin_id = request.match_info["plugin_id"]
    digest = request.match_info["digest"]
    relative = request.match_info["path"]
    state = await asyncio.to_thread(read_state, package_root())
    installation = state["installations"].get(plugin_id)
    if not installation or not installation["enabled"] or installation["digest"] != digest:
        raise PluginPackageError("plugin_asset_unavailable", status=404)
    if (
        not relative
        or any(part in ("", ".", "..") for part in relative.split("/"))
        or "\\" in relative
    ):
        raise PluginPackageError("plugin_asset_unavailable", status=404)
    target = package_root() / "releases" / plugin_id / digest / "frontend" / relative
    manifest_path = package_root() / "releases" / plugin_id / digest / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if f"frontend/{relative}" not in manifest["files"] or not target.is_file():
        raise PluginPackageError("plugin_asset_unavailable", status=404)
    data = await asyncio.to_thread(target.read_bytes)
    if hashlib.sha256(data).hexdigest() != manifest["files"][f"frontend/{relative}"]:
        raise PluginPackageError("plugin_asset_corrupt", status=503)
    content_type = mimetypes.guess_type(relative)[0] or "application/octet-stream"
    return web.Response(
        body=data,
        content_type=content_type,
        headers={
            "Cache-Control": "private, immutable, max-age=31536000",
            "X-Content-Type-Options": "nosniff",
        },
    )


def setup_plugin_packages(router: web.UrlDispatcher) -> None:
    router.add_get("/api/admin/plugins", admin_plugin_packages_route)
    router.add_post("/api/admin/plugins/preview", admin_plugin_preview_route)
    router.add_post("/api/admin/plugins/stage", admin_plugin_stage_route)
    router.add_post("/api/admin/plugins/repository/preview", admin_plugin_repository_preview_route)
    router.add_post("/api/admin/plugins/repository/stage", admin_plugin_repository_stage_route)
    router.add_post("/api/admin/plugins/trust", admin_plugin_trust_route)
    router.add_post("/api/admin/plugins/install", admin_plugin_install_route)
    router.add_post("/api/admin/plugins/{plugin_id}/enabled", admin_plugin_enabled_route)
    router.add_post("/api/admin/plugins/{plugin_id}/remove", admin_plugin_remove_route)
    router.add_get("/api/admin/plugins/runtime", admin_plugin_runtime_route)
    router.add_get(
        "/api/admin/plugins/assets/{plugin_id}/{digest}/{path:.+}", admin_plugin_asset_route
    )


register_contract(
    "admin_plugin_packages_route",
    RouteContract(
        response_schema=ok_envelope_with(
            {
                "generation": {"type": "integer"},
                "installations": JSON_OBJECT_SCHEMA,
                "operations": JSON_ARRAY_SCHEMA,
                "bundled": JSON_ARRAY_SCHEMA,
                "observations": JSON_OBJECT_SCHEMA,
                "failed_generation": {"type": ["integer", "null"]},
                "failure": {"type": "string"},
            }
        )
    ),
)
for _name in ("admin_plugin_preview_route", "admin_plugin_stage_route"):
    register_contract(
        _name,
        RouteContract(
            request_content={
                "multipart/form-data": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {"file": BINARY_RESPONSE_SCHEMA},
                }
            },
            response_schema=ok_envelope_with(
                {
                    "digest": {"type": "string"},
                    "manifest": JSON_OBJECT_SCHEMA,
                    "trusted": {"type": "boolean"},
                    "trust_reason": {"type": "string"},
                    "operation_id": {"type": "string"},
                },
                required=["digest", "manifest", "trusted", "trust_reason"],
            ),
        ),
    )
for _name in ("admin_plugin_repository_preview_route", "admin_plugin_repository_stage_route"):
    register_contract(
        _name,
        RouteContract(
            request_schema={
                "type": "object",
                "properties": {"url": {"type": "string"}, "ref": {"type": "string"}},
                "required": ["url"],
                "additionalProperties": False,
            },
            response_schema=ok_envelope_with(
                {
                    "digest": {"type": "string"},
                    "manifest": JSON_OBJECT_SCHEMA,
                    "trusted": {"type": "boolean"},
                    "trust_reason": {"type": "string"},
                    "source": JSON_OBJECT_SCHEMA,
                    "operation_id": {"type": "string"},
                },
                required=["digest", "manifest", "trusted", "trust_reason", "source"],
            ),
        ),
    )
for _name in (
    "admin_plugin_trust_route",
    "admin_plugin_install_route",
    "admin_plugin_enabled_route",
    "admin_plugin_remove_route",
):
    register_contract(
        _name,
        RouteContract(
            request_schema=JSON_OBJECT_SCHEMA,
            response_schema=ok_envelope_with({"generation": {"type": "integer"}}, required=[]),
        ),
    )
register_contract(
    "admin_plugin_runtime_route",
    RouteContract(
        response_schema=ok_envelope_with(
            {
                "generation": {"type": "integer"},
                "plugins": JSON_ARRAY_SCHEMA,
            }
        )
    ),
)
register_contract(
    "admin_plugin_asset_route",
    RouteContract(
        response_schema=BINARY_RESPONSE_SCHEMA, response_content_type="application/octet-stream"
    ),
)
