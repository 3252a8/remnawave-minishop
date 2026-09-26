"""Admin API for versioned public Markdown documents."""

from __future__ import annotations

from aiohttp import web
from pydantic import Field, StrictBool, field_validator

from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from bot.app.web.webapp.asset_paths import APP_ROOT
from config.documents import (
    MAX_DOCUMENT_BYTES,
    MAX_DOCUMENT_SLUG_LENGTH,
    Document,
    DocumentConflictError,
    DocumentError,
    DocumentMetadata,
    DocumentNotFoundError,
    DocumentRole,
    DocumentStorageError,
    create_document,
    delete_document,
    get_document,
    list_documents,
    normalize_document_metadata,
    update_document,
)

from .auth import _require_admin_user_id
from .common import _error, _ok


class AdminDocumentBody(HttpBodyModel):
    title: str = Field(min_length=1, max_length=160)
    markdown: str = ""
    role: DocumentRole = "none"
    show_in_settings: StrictBool = False
    show_in_sidebar: StrictBool = False
    group_title: str | None = Field(default=None, max_length=120)
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)

    @field_validator("markdown")
    @classmethod
    def _validate_markdown_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_DOCUMENT_BYTES:
            raise ValueError("document markdown is too large")
        return value


class AdminDocumentCreateBody(AdminDocumentBody):
    slug: str = Field(min_length=1, max_length=MAX_DOCUMENT_SLUG_LENGTH)


class AdminDocumentUpdateBody(AdminDocumentBody):
    slug: str = Field(min_length=1, max_length=MAX_DOCUMENT_SLUG_LENGTH)


class AdminDocumentOut(HttpResponseModel):
    title: str
    slug: str
    markdown: str
    role: DocumentRole
    show_in_settings: bool
    show_in_sidebar: bool
    group_title: str | None
    sort_order: int

    @classmethod
    def from_document(cls, document: Document) -> AdminDocumentOut:
        return cls(
            title=document.title,
            slug=document.slug,
            markdown=document.markdown,
            role=document.role,
            show_in_settings=document.show_in_settings,
            show_in_sidebar=document.show_in_sidebar,
            group_title=document.group_title,
            sort_order=document.sort_order,
        )


class AdminDocumentsOut(HttpResponseModel):
    documents: list[AdminDocumentOut]


def _metadata(body: AdminDocumentBody, slug: str) -> DocumentMetadata:
    return normalize_document_metadata(
        title=body.title,
        slug=slug,
        role=body.role,
        show_in_settings=body.show_in_settings,
        show_in_sidebar=body.show_in_sidebar,
        group_title=body.group_title,
        sort_order=body.sort_order,
    )


def _invalidate_webapp_settings_cache(request: web.Request) -> None:
    cache = request.app.get("webapp_settings_cache")
    if isinstance(cache, dict):
        cache["ts"] = 0.0
        cache["data"] = {}


def _storage_error(error: DocumentError) -> web.Response:
    if isinstance(error, DocumentNotFoundError):
        return _error(404, "document_not_found")
    if isinstance(error, DocumentConflictError):
        return _error(409, "document_conflict")
    if isinstance(error, DocumentStorageError):
        return _error(500, "document_storage_failed")
    return _error(400, "invalid_document")


register_contract(
    "admin_documents_list_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminDocumentsOut),
        models=(AdminDocumentOut, AdminDocumentsOut),
    ),
)
register_contract(
    "admin_document_create_route",
    RouteContract(
        request_model=AdminDocumentCreateBody,
        response_schema=ok_envelope_for(AdminDocumentOut),
        models=(AdminDocumentCreateBody, AdminDocumentOut),
    ),
)
register_contract(
    "admin_document_get_route",
    RouteContract(response_schema=ok_envelope_for(AdminDocumentOut), models=(AdminDocumentOut,)),
)
register_contract(
    "admin_document_update_route",
    RouteContract(
        request_model=AdminDocumentUpdateBody,
        response_schema=ok_envelope_for(AdminDocumentOut),
        models=(AdminDocumentUpdateBody, AdminDocumentOut),
    ),
)
register_contract(
    "admin_document_delete_route",
    RouteContract(response_schema=ok_envelope_for()),
)


async def admin_documents_list_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    try:
        documents = list_documents(APP_ROOT)
    except DocumentError as exc:
        return _storage_error(exc)
    payload = AdminDocumentsOut(
        documents=[AdminDocumentOut.from_document(item) for item in documents]
    )
    return _ok(payload.model_dump())


async def admin_document_create_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    body = await parse_body_or_400(request, AdminDocumentCreateBody)
    try:
        document = create_document(APP_ROOT, _metadata(body, body.slug), body.markdown)
    except DocumentError as exc:
        return _storage_error(exc)
    _invalidate_webapp_settings_cache(request)
    return _ok(AdminDocumentOut.from_document(document).model_dump())


async def admin_document_get_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    try:
        document = get_document(APP_ROOT, request.match_info["slug"])
    except DocumentError as exc:
        return _storage_error(exc)
    if document is None:
        return _error(404, "document_not_found")
    return _ok(AdminDocumentOut.from_document(document).model_dump())


async def admin_document_update_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    body = await parse_body_or_400(request, AdminDocumentUpdateBody)
    slug = request.match_info["slug"]
    try:
        document = update_document(APP_ROOT, slug, _metadata(body, body.slug), body.markdown)
    except DocumentError as exc:
        return _storage_error(exc)
    _invalidate_webapp_settings_cache(request)
    return _ok(AdminDocumentOut.from_document(document).model_dump())


async def admin_document_delete_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    try:
        delete_document(APP_ROOT, request.match_info["slug"])
    except DocumentError as exc:
        return _storage_error(exc)
    _invalidate_webapp_settings_cache(request)
    return _ok({})
