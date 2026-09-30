import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bot.app.web.webapp import pages
from config.information_pages import (
    InformationPageConflictError,
    InformationPagePathError,
    information_page_file_path,
    load_information_page,
    normalize_information_page_path,
    save_information_page,
)


def test_legal_and_generic_routes_map_to_separate_markdown_roots(tmp_path: Path) -> None:
    legal = tmp_path / "data" / "legal"
    page_dir = tmp_path / "data" / "pages" / "company"
    legal.mkdir(parents=True)
    page_dir.mkdir(parents=True)
    (legal / "terms.md").write_text("# Terms", encoding="utf-8")
    (page_dir / "about.md").write_text("# About", encoding="utf-8")

    assert information_page_file_path(tmp_path, "/legal/terms")[1] == legal / "terms.md"
    assert information_page_file_path(tmp_path, "/company/about")[1] == page_dir / "about.md"
    terms = load_information_page(tmp_path, "/legal/terms")
    about = load_information_page(tmp_path, "/company/about")
    assert terms is not None and terms.markdown == "# Terms"
    assert about is not None and about.path == "/company/about"


@pytest.mark.parametrize(
    "path",
    [
        "/home",
        "/login/password",
        "/webapp-logo",
        "/legal",
        "/plans",
        "/settings/security",
        "/api/pages/test",
        "/../secret",
        "/about/../secret",
        "/about%2fsecret",
        "/about?draft=1",
        "about",
    ],
)
def test_information_page_paths_reject_application_collisions_and_traversal(path: str) -> None:
    with pytest.raises(InformationPagePathError):
        normalize_information_page_path(path)


def test_information_page_loader_rejects_symlinks_outside_data_root(
    tmp_path: Path, symlink_support: None
) -> None:
    page_dir = tmp_path / "data" / "pages"
    page_dir.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("private", encoding="utf-8")
    (page_dir / "about.md").symlink_to(outside)

    assert load_information_page(tmp_path, "/about") is None


def test_information_page_save_writes_then_moves_a_document_without_overwriting_target(
    tmp_path: Path,
) -> None:
    original = save_information_page(tmp_path, "/company/about", "# About")

    moved = save_information_page(
        tmp_path,
        "/legal/terms",
        "# Terms",
        previous_path=original.path,
    )

    assert moved.path == "/legal/terms"
    assert (tmp_path / "data" / "legal" / "terms.md").read_text(encoding="utf-8") == "# Terms"
    assert not (tmp_path / "data" / "pages" / "company" / "about.md").exists()

    save_information_page(tmp_path, "/company/privacy", "# Privacy")
    with pytest.raises(InformationPageConflictError):
        save_information_page(
            tmp_path,
            "/company/privacy",
            "# Replacement",
            previous_path="/legal/terms",
        )

    assert load_information_page(tmp_path, "/legal/terms") is not None


def test_information_page_api_uses_a_route_parameter_without_losing_its_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legal = tmp_path / "data" / "legal"
    legal.mkdir(parents=True)
    (legal / "terms.md").write_text("# Terms", encoding="utf-8")
    monkeypatch.setattr(pages, "APP_ROOT", tmp_path)

    request = SimpleNamespace(match_info={"page_path": "legal/terms"})
    response = asyncio.run(pages.information_page_content_route(request))

    assert response.status == 200
    assert json.loads(response.text) == {
        "ok": True,
        "path": "/legal/terms",
        "markdown": "# Terms",
    }
    assert response.headers["Cache-Control"] == "no-store"


def test_information_page_api_returns_the_wire_envelope_for_missing_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pages, "APP_ROOT", tmp_path)

    request = SimpleNamespace(match_info={"page_path": "company/about"})
    response = asyncio.run(pages.information_page_content_route(request))

    assert response.status == 404
    assert json.loads(response.text) == {"ok": False, "error": "page_not_found"}


def test_deleted_import_is_not_published_at_the_old_legal_path(tmp_path: Path, monkeypatch) -> None:
    from config.documents import delete_document, get_document_by_role

    save_information_page(tmp_path, "/legal/policy", "# Old policy")
    imported = get_document_by_role(tmp_path, "privacy_policy")
    assert imported is not None
    delete_document(tmp_path, imported.slug)
    monkeypatch.setattr(pages, "APP_ROOT", tmp_path)

    response = asyncio.run(
        pages.information_page_content_route(
            SimpleNamespace(match_info={"page_path": "legal/policy"})
        )
    )
    assert response.status == 404


def test_empty_file_page_is_not_published(tmp_path: Path, monkeypatch) -> None:
    save_information_page(tmp_path, "/about", " \n\t")
    monkeypatch.setattr(pages, "APP_ROOT", tmp_path)

    response = asyncio.run(
        pages.information_page_content_route(SimpleNamespace(match_info={"page_path": "about"}))
    )
    assert response.status == 404
