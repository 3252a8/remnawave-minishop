"""Resolve legal links to locally edited Mini App documents when available."""

from __future__ import annotations

from pathlib import Path

from bot.utils.mini_app_url import subscription_mini_app_path_url
from config.documents import (
    Document,
    DocumentError,
    DocumentRole,
    document_public_path,
    get_document_by_role,
    legacy_document_imported,
)
from config.information_pages import load_information_page
from config.settings import Settings

APP_ROOT = Path(__file__).resolve().parents[3]
PRIVACY_POLICY_PATH = "/legal/policy"
USER_AGREEMENT_PATH = "/legal/terms"


def _managed_document_url(settings: Settings, role: str) -> str | None:
    document: Document | None = get_document_by_role(APP_ROOT, role)
    if document is None or not document.markdown.strip():
        return None
    return subscription_mini_app_path_url(settings, document_public_path(document.slug))


def _legacy_document_url(settings: Settings, page_path: str, fallback_url: str | None) -> str:
    """Keep legacy file/config links for deployments not migrated to documents."""

    page = load_information_page(APP_ROOT, page_path)
    if page is not None and page.markdown.strip():
        native_url = subscription_mini_app_path_url(settings, page_path)
        if native_url:
            return native_url
    return str(fallback_url or "").strip()


def _document_url(
    settings: Settings, role: DocumentRole, path: str, fallback_url: str | None
) -> str:
    try:
        managed_url = _managed_document_url(settings, role)
        if managed_url:
            return managed_url
        if legacy_document_imported(APP_ROOT, role):
            return str(fallback_url or "").strip()
        return _legacy_document_url(settings, path, fallback_url)
    except DocumentError:
        return _legacy_document_url(settings, path, fallback_url)


def legal_document_links(settings: Settings) -> tuple[str, str]:
    """Return managed legal links first, retaining local/configured fallbacks."""

    return (
        _document_url(
            settings,
            "privacy_policy",
            PRIVACY_POLICY_PATH,
            settings.PRIVACY_POLICY_URL,
        ),
        _document_url(
            settings,
            "user_agreement",
            USER_AGREEMENT_PATH,
            settings.USER_AGREEMENT_URL,
        ),
    )
