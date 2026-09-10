"""Authenticated package lifecycle; downloads never execute repository code."""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from aiohttp import web
from aiohttp.multipart import BodyPartReader
from pydantic import BaseModel

from bot.app.web.context import get_settings
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    BINARY_RESPONSE_SCHEMA,
    RouteContract,
    ok_envelope_for,
    register_contract,
)
from bot.app.web.webapp.cache_helpers import refresh_webapp_runtime_after_settings_change
from config.theme_packages.models import (
    MAX_ARCHIVE,
    ExportRequest,
    ImportOut,
    InstallRequest,
    LibraryOut,
    MutationOut,
    MutationRequest,
    PackageError,
    PreviewUploadOut,
    RepositoryRequest,
    ThemeSource,
)
from config.theme_packages.operations import (
    cancel_import,
    create_import,
    export_themes,
    fail_import,
    get_import,
    inspect_import,
    install_import,
    remove_theme,
    rollback_theme,
)
from config.theme_packages.providers import fetch_repository, repository_parts
from config.theme_packages.registry import library
from config.theme_packages.preview_storage import MAX_PREVIEW_BYTES, preview_url, save_preview
from config.webapp_themes_config import WebappThemesConfig, resolved_webapp_themes_catalog

from .auth import _require_admin_user_id
from .common import _error, _ok

logger = logging.getLogger(__name__)
_JOBS = web.AppKey("theme_import_jobs", set[asyncio.Task[None]])
Handler = Callable[[web.Request], Awaitable[web.Response]]


def package_route(handler: Handler) -> Handler:
    @functools.wraps(handler)
    async def guarded(request: web.Request) -> web.Response:
        _require_admin_user_id(request)
        try:
            return await handler(request)
        except PackageError as exc:
            return _error(exc.status, exc.code)
        except OSError:
            logger.exception("Theme library storage operation failed")
            return _error(503, "theme_storage_unavailable")

    return guarded


def root_for(request: web.Request) -> Path:
    return Path(get_settings(request).WEBAPP_THEMES_DIR).expanduser()


def catalog_for(request: web.Request) -> WebappThemesConfig:
    settings = get_settings(request)
    return resolved_webapp_themes_catalog(
        primary_accent=settings.WEBAPP_PRIMARY_COLOR or "#00fe7a",
        env_default_theme=settings.WEBAPP_DEFAULT_THEME,
        theme_dir=settings.WEBAPP_THEMES_DIR,
    )


@package_route
async def admin_theme_library_route(request: web.Request) -> web.Response:
    result = await asyncio.to_thread(library, root_for(request), catalog_for(request))
    return _ok(result.model_dump(mode="json"))


async def read_archive(request: web.Request) -> tuple[bytes, str]:
    if request.content_length and request.content_length > MAX_ARCHIVE + 65536:
        raise PackageError("archive_too_large", status=413)
    reader = await request.multipart()
    part = await reader.next()
    if not isinstance(part, BodyPartReader) or part.name != "file" or not part.filename:
        raise PackageError("archive_file_required")
    name = Path(part.filename.replace("\\", "/")).name[:120]
    if not name.lower().endswith(".zip"):
        raise PackageError("zip_required")
    content = bytearray()
    async with asyncio.timeout(60):
        while chunk := await part.read_chunk(64 * 1024):
            content.extend(chunk)
            if len(content) > MAX_ARCHIVE:
                raise PackageError("archive_too_large", status=413)
        if await reader.next() is not None:
            raise PackageError("one_archive_required")
    return bytes(content), name


async def repository_job(
    root: Path, actor: int, operation_id: str, body: RepositoryRequest
) -> None:
    record = await asyncio.to_thread(get_import, root, operation_id, actor)
    try:
        async with asyncio.timeout(90):
            archive, record.source = await fetch_repository(body)
        await asyncio.to_thread(inspect_import, root, record, archive)
    except PackageError as exc:
        await asyncio.to_thread(fail_import, root, record, exc)
    except (OSError, TimeoutError):
        await asyncio.to_thread(fail_import, root, record, PackageError("repository_unavailable"))
    except asyncio.CancelledError:
        await asyncio.to_thread(fail_import, root, record, PackageError("import_interrupted"))
        raise
    except Exception:
        logger.exception("Theme repository import failed")
        await asyncio.to_thread(fail_import, root, record, PackageError("import_failed"))


@package_route
async def admin_theme_import_route(request: web.Request) -> web.Response:
    actor = _require_admin_user_id(request)
    root = root_for(request)
    if request.content_type == "multipart/form-data":
        record = await asyncio.to_thread(create_import, root, actor, ThemeSource())
        try:
            archive, name = await read_archive(request)
            record.source.label = name
            record = await asyncio.to_thread(inspect_import, root, record, archive)
        except (PackageError, TimeoutError, ValueError) as exc:
            error = exc if isinstance(exc, PackageError) else PackageError("invalid_archive")
            await asyncio.to_thread(fail_import, root, record, error)
            raise error from exc
    else:
        body = await parse_body_or_400(request, RepositoryRequest)
        repository_parts(body)
        record = await asyncio.to_thread(
            create_import, root, actor, ThemeSource(kind="github", label=body.url)
        )
        jobs = request.app.get(_JOBS)
        if jobs is None:
            raise PackageError("theme_import_unavailable", status=503)
        task = asyncio.create_task(repository_job(root, actor, record.id, body))
        jobs.add(task)
        task.add_done_callback(jobs.discard)
    return _ok(ImportOut(operation=record).model_dump(mode="json"))


@package_route
async def admin_theme_import_status_route(request: web.Request) -> web.Response:
    record = await asyncio.to_thread(
        get_import,
        root_for(request),
        request.match_info["operation_id"],
        _require_admin_user_id(request),
    )
    return _ok(ImportOut(operation=record).model_dump(mode="json"))


@package_route
async def admin_theme_import_cancel_route(request: web.Request) -> web.Response:
    record = await asyncio.to_thread(
        cancel_import,
        root_for(request),
        request.match_info["operation_id"],
        _require_admin_user_id(request),
    )
    return _ok(ImportOut(operation=record).model_dump(mode="json"))


async def refreshed(request: web.Request, result: MutationOut) -> web.Response:
    await refresh_webapp_runtime_after_settings_change(request, updates={}, deletes=[])
    return _ok(result.model_dump(mode="json"))


@package_route
async def admin_theme_install_route(request: web.Request) -> web.Response:
    body = await parse_body_or_400(request, InstallRequest)
    result = await asyncio.to_thread(
        install_import,
        root_for(request),
        request.match_info["operation_id"],
        _require_admin_user_id(request),
        body,
    )
    return await refreshed(request, result)


@package_route
async def admin_theme_remove_route(request: web.Request) -> web.Response:
    body = await parse_body_or_400(request, MutationRequest)
    catalog = catalog_for(request)
    key = request.match_info["key"]
    theme = next((theme for theme in catalog.themes if theme.key == key), None)
    if theme and theme.default and theme.use_in_admin:
        raise PackageError("admin_theme_active", status=409)
    result = await asyncio.to_thread(
        remove_theme,
        root_for(request),
        key,
        body.expected_generation,
        catalog.default_theme,
    )
    return await refreshed(request, result)


@package_route
async def admin_theme_rollback_route(request: web.Request) -> web.Response:
    body = await parse_body_or_400(request, MutationRequest)
    result = await asyncio.to_thread(
        rollback_theme,
        root_for(request),
        request.match_info["key"],
        body.expected_generation,
    )
    return await refreshed(request, result)


@package_route
async def admin_theme_export_route(request: web.Request) -> web.Response:
    body = await parse_body_or_400(request, ExportRequest)
    archive = await asyncio.to_thread(export_themes, root_for(request), body)
    return web.Response(
        body=archive,
        content_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="minishop-themes.zip"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def read_preview(request: web.Request) -> bytes:
    if request.content_length and request.content_length > MAX_PREVIEW_BYTES + 65536:
        raise PackageError("preview_too_large", status=413)
    reader = await request.multipart()
    part = await reader.next()
    if not isinstance(part, BodyPartReader) or part.name != "file":
        raise PackageError("preview_file_required")
    content = bytearray()
    while chunk := await part.read_chunk(64 * 1024):
        content.extend(chunk)
        if len(content) > MAX_PREVIEW_BYTES:
            raise PackageError("preview_too_large", status=413)
    if await reader.next() is not None:
        raise PackageError("one_preview_required")
    return bytes(content)


@package_route
async def admin_theme_preview_upload_route(request: web.Request) -> web.Response:
    key = request.match_info["key"]
    if not any(theme.key == key for theme in catalog_for(request).themes):
        raise PackageError("theme_not_found", key, 404)
    url, _generation = await asyncio.to_thread(
        save_preview, root_for(request), key, await read_preview(request)
    )
    return _ok(PreviewUploadOut(preview_url=url).model_dump(mode="json"))


@package_route
async def admin_theme_preview_route(request: web.Request) -> web.Response:
    from config.theme_packages.preview import preview_import

    document = await asyncio.to_thread(
        preview_import,
        root_for(request),
        request.match_info["operation_id"],
        _require_admin_user_id(request),
        request.match_info["key"],
        request.query.get("variant", "dark"),
    )
    return web.Response(
        text=document,
        content_type="text/html",
        headers={
            "Content-Security-Policy": (
                "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
                "font-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
            ),
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


@package_route
async def admin_theme_installed_preview_route(request: web.Request) -> web.Response:
    from config.theme_packages.preview import preview_installed

    document = await asyncio.to_thread(
        preview_installed,
        root_for(request),
        request.match_info["key"],
        request.query.get("variant", "dark"),
    )
    return web.Response(
        text=document,
        content_type="text/html",
        headers={
            "Content-Security-Policy": (
                "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
                "font-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
            ),
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def cleanup_jobs(app: web.Application) -> None:
    jobs = app.get(_JOBS, set())
    for task in jobs:
        task.cancel()
    if jobs:
        await asyncio.gather(*jobs, return_exceptions=True)


def setup_theme_library(router: web.UrlDispatcher) -> None:
    router.add_get("/api/admin/themes/library", admin_theme_library_route)
    router.add_post("/api/admin/themes/imports", admin_theme_import_route)
    router.add_get("/api/admin/themes/imports/{operation_id}", admin_theme_import_status_route)
    router.add_delete("/api/admin/themes/imports/{operation_id}", admin_theme_import_cancel_route)
    router.add_post("/api/admin/themes/imports/{operation_id}/install", admin_theme_install_route)
    router.add_get(
        "/api/admin/themes/imports/{operation_id}/preview/{key}", admin_theme_preview_route
    )
    router.add_get("/api/admin/themes/library/{key}/preview", admin_theme_installed_preview_route)
    router.add_post("/api/admin/themes/export", admin_theme_export_route)
    router.add_post("/api/admin/themes/library/{key}/preview", admin_theme_preview_upload_route)
    router.add_delete("/api/admin/themes/library/{key}", admin_theme_remove_route)
    router.add_post("/api/admin/themes/library/{key}/rollback", admin_theme_rollback_route)


def setup_theme_jobs(app: web.Application) -> None:
    app[_JOBS] = set()
    app.on_cleanup.append(cleanup_jobs)


def contract(
    handler: Handler, response: type[BaseModel], body: type[BaseModel] | None = None
) -> None:
    models = (response, body) if body else (response,)
    register_contract(
        handler.__name__,
        RouteContract(
            request_model=body,
            response_schema=ok_envelope_for(response),
            models=models,
        ),
    )


contract(admin_theme_library_route, LibraryOut)
contract(admin_theme_import_status_route, ImportOut)
contract(admin_theme_import_cancel_route, ImportOut)
contract(admin_theme_install_route, MutationOut, InstallRequest)
contract(admin_theme_remove_route, MutationOut, MutationRequest)
contract(admin_theme_rollback_route, MutationOut, MutationRequest)
register_contract(
    "admin_theme_import_route",
    RouteContract(
        request_content={
            "application/json": {"$ref": "#/components/schemas/RepositoryRequest"},
            "multipart/form-data": {
                "type": "object",
                "required": ["file"],
                "additionalProperties": False,
                "properties": {"file": BINARY_RESPONSE_SCHEMA},
            },
        },
        response_schema=ok_envelope_for(ImportOut),
        models=(RepositoryRequest, ImportOut),
    ),
)
register_contract(
    "admin_theme_preview_upload_route",
    RouteContract(
        request_content={"multipart/form-data": {"type": "object", "required": ["file"], "properties": {"file": BINARY_RESPONSE_SCHEMA}}},
        response_schema=ok_envelope_for(PreviewUploadOut),
        models=(PreviewUploadOut,),
    ),
)
register_contract(
    "admin_theme_export_route",
    RouteContract(
        request_model=ExportRequest,
        response_schema=BINARY_RESPONSE_SCHEMA,
        response_content_type="application/zip",
        models=(ExportRequest,),
    ),
)
register_contract(
    "admin_theme_preview_route",
    RouteContract(
        response_schema={"type": "string"},
        response_content_type="text/html",
    ),
)

register_contract(
    "admin_theme_installed_preview_route",
    RouteContract(
        response_schema={"type": "string"},
        response_content_type="text/html",
    ),
)
