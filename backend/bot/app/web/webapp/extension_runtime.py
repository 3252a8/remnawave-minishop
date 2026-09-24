"""User-facing ESM packages have their own asset allowlist and session boundary."""

import asyncio
import hashlib
import json
import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiohttp import web

from bot.app.web.context import get_session_factory
from bot.app.web.route_contracts import BINARY_RESPONSE_SCHEMA, ok_envelope_for
from bot.plugins.extensions import ExtensionError, UserContext
from bot.plugins.extensions.presentation import preferences
from bot.plugins.extensions.registry import get_registry, split_key
from bot.plugins.packages import generation_is_current, package_root, read_state
from db.dal import user_dal

from .common import _require_user_id
from .contract_schemas import user_contract
from .extension_schemas import ExtensionPluginOut, ExtensionRuntimeOut, ExtensionViewOut
from .response_helpers import json_response


@asynccontextmanager
async def user_context(request: web.Request) -> AsyncIterator[UserContext]:
    user_id = _require_user_id(request)
    if not generation_is_current():
        raise web.HTTPServiceUnavailable(
            text='{"ok":false,"error":"extension_generation_changed"}',
            content_type="application/json",
        )
    async with get_session_factory(request)() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if user is None or user.is_banned:
            raise web.HTTPForbidden(
                text='{"ok":false,"error":"access_denied"}', content_type="application/json"
            )
        yield UserContext(session, user_id, str(user.language_code or "en"))


async def extension_runtime_route(request: web.Request) -> web.Response:
    async with user_context(request) as context:
        state = await asyncio.to_thread(read_state, package_root())
        plugins = []
        for owner, installation in sorted(state["installations"].items()):
            entry = get_registry().owners().get(owner)
            if not installation["enabled"] or entry is None:
                continue
            try:
                async with asyncio.timeout(5):
                    release = package_root() / "releases" / owner / installation["digest"]
                    manifest = json.loads(
                        await asyncio.to_thread(
                            (release / "plugin.json").read_text, encoding="utf-8"
                        )
                    )
                    frontend = manifest.get("frontend", {}).get("user")
                    if not isinstance(frontend, dict):
                        continue
                    views = []
                    presentation = await preferences(context.session, owner)
                    for target, collection in (("page", "pages"), ("", "slots")):
                        for raw in frontend.get(collection, []):
                            choice = presentation.get(f"view:{raw['id']}")
                            if choice is not None and not choice[0]:
                                continue
                            try:
                                async with asyncio.timeout(3):
                                    visible = (
                                        await entry.contributions.view_policy(context, raw["id"])
                                        if entry.contributions.view_policy
                                        else True
                                    )
                                if visible:
                                    raw = {**raw, "order": choice[1]} if choice else raw
                                    views.append(
                                        ExtensionViewOut.model_validate(
                                            {**raw, "target": target or raw["target"]}
                                        )
                                    )
                            except Exception:
                                continue  # Visibility policy failures close access to that view.
                    prefix = f"/api/extensions/assets/{owner}/{installation['digest']}/"
                    if views:
                        plugins.append(
                            ExtensionPluginOut(
                                id=owner,
                                digest=installation["digest"],
                                entry=prefix + frontend["entry"],
                                styles=[prefix + item for item in frontend.get("styles", [])],
                                views=sorted(views, key=lambda item: (item.order, item.id)),
                            )
                        )
            except Exception:
                continue  # Isolate malformed assets and slow visibility policies.
        payload = ExtensionRuntimeOut(generation=state["generation"], plugins=plugins)
        return json_response(
            {"ok": True, **payload.model_dump(mode="json")},
            headers={"Cache-Control": "private, no-store"},
        )


async def extension_asset_route(request: web.Request) -> web.Response:
    async with user_context(request):
        owner, digest, relative = (request.match_info[key] for key in ("owner", "digest", "path"))
        state = await asyncio.to_thread(read_state, package_root())
        installation = state["installations"].get(owner)
        if (
            owner not in get_registry().owners()
            or not installation
            or not installation["enabled"]
            or installation["digest"] != digest
            or "\\" in relative
            or any(part in {"", ".", ".."} or ":" in part for part in relative.split("/"))
        ):
            raise web.HTTPNotFound()
        release = package_root() / "releases" / owner / digest
        manifest = json.loads(
            await asyncio.to_thread((release / "plugin.json").read_text, encoding="utf-8")
        )
        frontend = manifest.get("frontend", {}).get("user", {})
        allowed = {frontend.get("entry"), *frontend.get("styles", []), *frontend.get("assets", [])}
        if relative not in allowed or f"frontend/{relative}" not in manifest["files"]:
            raise web.HTTPNotFound()
        data = await asyncio.to_thread((release / "frontend" / relative).read_bytes)
        if hashlib.sha256(data).hexdigest() != manifest["files"][f"frontend/{relative}"]:
            raise web.HTTPServiceUnavailable()
        content_type = mimetypes.guess_type(relative)[0] or "application/octet-stream"
        return web.Response(
            body=data,
            content_type=content_type,
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        )


async def extension_resource_route(request: web.Request) -> web.Response:
    try:
        owner, resource_id = split_key(request.query.get("provider", ""))
        key = request.query.get("key", "")
        if not key or len(key) > 256:
            raise ExtensionError("invalid_extension_resource_key", 400)
        async with user_context(request) as context:
            entry = get_registry().require(owner)
            provider = next(
                (item for item in entry.contributions.resources if item.id == resource_id), None
            )
            if provider is None:
                raise ExtensionError("extension_resource_unavailable", 404)
            async with asyncio.timeout(15):
                result = await provider.resolve(context, key)
            if len(result.body) > 2_097_152:
                raise ExtensionError("extension_resource_too_large", 400)
            safe_types = {
                "text/plain",
                "application/json",
                "application/octet-stream",
                "image/png",
                "image/webp",
            }
            content_type = (
                result.content_type
                if result.content_type in safe_types
                else "application/octet-stream"
            )
            filename = (
                "".join(
                    char
                    for char in result.filename
                    if char.isascii() and (char.isalnum() or char in "._-")
                )[:100]
                or "configuration.txt"
            )
            return web.Response(
                body=result.body,
                content_type=content_type,
                headers={
                    "Cache-Control": "private, no-store",
                    "Referrer-Policy": "no-referrer",
                    "X-Content-Type-Options": "nosniff",
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )
    except ExtensionError as exc:
        return json_response({"ok": False, "error": exc.code}, status=exc.status)


EXTENSION_RUNTIME_ROUTE_CONTRACTS = {
    "extension_runtime_route": user_contract(
        response_schema=ok_envelope_for(ExtensionRuntimeOut), models=(ExtensionRuntimeOut,)
    ),
    "extension_asset_route": user_contract(
        response_schema=BINARY_RESPONSE_SCHEMA, response_content_type="application/octet-stream"
    ),
    "extension_resource_route": user_contract(
        response_schema=BINARY_RESPONSE_SCHEMA, response_content_type="application/octet-stream"
    ),
}
