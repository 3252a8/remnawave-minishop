"""Public API and SPA entry routes for file-backed Markdown pages."""

from __future__ import annotations

from aiohttp import web

from config.documents import (
    DocumentError,
    DocumentRole,
    get_document,
    get_document_by_role,
    legacy_document_imported,
)
from config.information_pages import InformationPage, load_information_page

from .asset_paths import APP_ROOT
from .response_helpers import json_response

# Keep reserved application roots out of the catch-all route entirely. Besides
# preserving their own handlers, this makes a request such as /admin/themes a
# normal router 404 rather than a missing information page.
INFORMATION_PAGE_ROUTE_PATTERN = (
    r"(?!(?:admin|api|auth|checkout|devices|favicon\.ico|fonts|health|home|icon-192\.png|"
    r"icon-512\.png|install|invite|login|open-app|partner|plans|robots\.txt|s|settings|status|"
    r"subscription_webapp\.css|subscription_webapp\.js|support|trial|unsubscribe|"
    r"webapp-default-logo\.webp|webapp-favicon|webapp-logo|webapp-theme-assets|webapp-theme-css|"
    r"webapp-uploaded-logo)(?:/|$)).+"
)


def _page_from_request(request: web.Request) -> InformationPage | None:
    page_path = str(request.match_info.get("page_path", "") or "").lstrip("/")
    document_slug = page_path.removeprefix("docs/") if page_path.startswith("docs/") else page_path
    try:
        document = get_document(APP_ROOT, document_slug)
    except DocumentError:
        document = None
    if document is not None and document.markdown.strip():
        return InformationPage(path=f"/{page_path}", markdown=document.markdown)
    legacy_roles: dict[str, DocumentRole] = {
        "legal/policy": "privacy_policy",
        "legal/terms": "user_agreement",
    }
    role = legacy_roles.get(page_path)
    if role is not None:
        try:
            document = get_document_by_role(APP_ROOT, role)
        except DocumentError:
            document = None
        if document is not None and document.markdown.strip():
            return InformationPage(path=f"/{page_path}", markdown=document.markdown)
        try:
            if legacy_document_imported(APP_ROOT, role):
                return None
        except DocumentError:
            return None
    page = load_information_page(APP_ROOT, f"/{page_path}")
    return page if page is not None and page.markdown.strip() else None


async def information_page_content_route(request: web.Request) -> web.Response:
    page = _page_from_request(request)
    if page is None:
        return json_response({"ok": False, "error": "page_not_found"}, status=404)
    response = json_response({"ok": True, "path": page.path, "markdown": page.markdown})
    response.headers["Cache-Control"] = "no-store"
    return response


async def information_page_route(request: web.Request) -> web.Response:
    if _page_from_request(request) is None:
        raise web.HTTPNotFound(text="page_not_found")
    # Keep the HTML shell (branding, theme and CSP) identical to the rest of the Mini App.
    from .assets import index_route

    return await index_route(request)
