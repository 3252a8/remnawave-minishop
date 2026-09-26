"""Admin API for the public file-backed Markdown documents."""

from __future__ import annotations

from aiohttp import web
from pydantic import Field, field_validator

from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from bot.app.web.webapp.asset_paths import APP_ROOT
from config.information_pages import (
    MAX_INFORMATION_PAGE_BYTES,
    InformationPageConflictError,
    InformationPagePathError,
    InformationPageWriteError,
    load_information_page,
    normalize_information_page_path,
    save_information_page,
)

from .auth import _require_admin_user_id
from .common import _error, _ok


class AdminInformationPageSaveBody(HttpBodyModel):
    path: str = Field(min_length=1, max_length=256)
    markdown: str = ""
    previous_path: str | None = Field(default=None, max_length=256)

    @field_validator("markdown")
    @classmethod
    def _validate_markdown_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_INFORMATION_PAGE_BYTES:
            raise ValueError("page markdown is too large")
        return value


class AdminInformationPageOut(HttpResponseModel):
    path: str
    markdown: str
    exists: bool


def _invalidate_webapp_settings_cache(request: web.Request) -> None:
    app = getattr(request, "app", None)
    if app is None:
        return
    cache = app.get("webapp_settings_cache")
    if isinstance(cache, dict):
        cache["ts"] = 0.0
        cache["data"] = {}


register_contract(
    "admin_information_page_get_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminInformationPageOut),
        models=(AdminInformationPageOut,),
    ),
)
register_contract(
    "admin_information_page_save_route",
    RouteContract(
        request_model=AdminInformationPageSaveBody,
        response_schema=ok_envelope_for(AdminInformationPageOut),
        models=(AdminInformationPageSaveBody, AdminInformationPageOut),
    ),
)


def _requested_page_path(request: web.Request) -> str:
    return normalize_information_page_path(request.query.get("path", ""))


async def admin_information_page_get_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    try:
        path = _requested_page_path(request)
    except InformationPagePathError:
        return _error(400, "invalid_page_path")

    page = load_information_page(APP_ROOT, path)
    payload = AdminInformationPageOut(
        path=path,
        markdown=page.markdown if page else "",
        exists=page is not None,
    )
    return _ok(payload.model_dump(mode="json"))


async def admin_information_page_save_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    body = await parse_body_or_400(request, AdminInformationPageSaveBody)
    try:
        page = save_information_page(
            APP_ROOT,
            body.path,
            body.markdown,
            previous_path=body.previous_path,
        )
    except InformationPagePathError:
        return _error(400, "invalid_page_path")
    except InformationPageConflictError:
        return _error(409, "information_page_exists")
    except InformationPageWriteError:
        return _error(500, "information_page_write_failed")

    _invalidate_webapp_settings_cache(request)
    return _ok(
        AdminInformationPageOut(
            path=page.path,
            markdown=page.markdown,
            exists=True,
        ).model_dump(mode="json")
    )
