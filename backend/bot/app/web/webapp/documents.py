"""Public APIs and Mini App shell route for managed documents."""

from __future__ import annotations

from aiohttp import web

from bot.app.web.http_contracts import HttpResponseModel
from config.documents import Document, DocumentError, DocumentRole, get_document, list_documents

from .asset_paths import APP_ROOT
from .response_helpers import json_response


class PublicDocumentOut(HttpResponseModel):
    title: str
    slug: str
    role: DocumentRole
    show_in_settings: bool
    show_in_sidebar: bool
    group_title: str | None
    sort_order: int

    @classmethod
    def from_document(cls, document: Document) -> PublicDocumentOut:
        return cls(
            title=document.title,
            slug=document.slug,
            role=document.role,
            show_in_settings=document.show_in_settings,
            show_in_sidebar=document.show_in_sidebar,
            group_title=document.group_title,
            sort_order=document.sort_order,
        )


class PublicDocumentContentOut(PublicDocumentOut):
    markdown: str

    @classmethod
    def from_document(cls, document: Document) -> PublicDocumentContentOut:
        metadata = PublicDocumentOut.from_document(document)
        return cls(**metadata.model_dump(), markdown=document.markdown)


class PublicDocumentsOut(HttpResponseModel):
    documents: list[PublicDocumentOut]


def _published(document: Document) -> bool:
    return bool(document.markdown.strip())


async def documents_list_route(_: web.Request) -> web.Response:
    try:
        documents = list_documents(APP_ROOT)
    except DocumentError:
        return json_response({"ok": False, "error": "documents_unavailable"}, status=503)
    payload = PublicDocumentsOut(
        documents=[
            PublicDocumentOut.from_document(document)
            for document in documents
            if _published(document)
        ]
    )
    response = json_response({"ok": True, **payload.model_dump(mode="json")})
    response.headers["Cache-Control"] = "no-store"
    return response


async def document_content_route(request: web.Request) -> web.Response:
    try:
        document = get_document(APP_ROOT, request.match_info["slug"])
    except DocumentError:
        return json_response({"ok": False, "error": "document_not_found"}, status=404)
    if document is None or not _published(document):
        return json_response({"ok": False, "error": "document_not_found"}, status=404)
    payload = PublicDocumentContentOut.from_document(document)
    response = json_response({"ok": True, **payload.model_dump(mode="json")})
    response.headers["Cache-Control"] = "no-store"
    return response


async def document_shell_route(request: web.Request) -> web.Response:
    try:
        document = get_document(APP_ROOT, request.match_info["slug"])
    except DocumentError:
        document = None
    if document is None or not _published(document):
        raise web.HTTPNotFound(text="document_not_found")
    from .assets import index_route

    return await index_route(request)
