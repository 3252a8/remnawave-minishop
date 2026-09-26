from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from bot.app.web.webapp import documents as document_routes
from config import documents
from config.documents import (
    DOCUMENTS_INDEX_VERSION,
    DocumentMetadata,
    DocumentStorageError,
    create_document,
    document_public_path,
    get_document,
    get_document_by_role,
    list_documents,
    normalize_document_slug,
    update_document,
)


def _metadata(slug: str, *, role: str = "none") -> DocumentMetadata:
    return DocumentMetadata(
        title=slug.replace("-", " ").title(),
        slug=slug,
        role=role,
        show_in_settings=True,
        show_in_sidebar=True,
        group_title="Legal",
        sort_order=10,
    )


def test_document_storage_uses_versioned_index_and_content_addressed_bodies(tmp_path: Path) -> None:
    created = create_document(tmp_path, _metadata("privacy-policy", role="privacy_policy"), "# One")

    index_path = tmp_path / "data" / "docs" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    old_body_name = index["documents"][0]["body"]
    assert index["version"] == DOCUMENTS_INDEX_VERSION
    assert (tmp_path / "data" / "docs" / "bodies" / old_body_name).read_text(
        encoding="utf-8"
    ) == "# One"

    updated = update_document(
        tmp_path,
        created.slug,
        _metadata("privacy", role="privacy_policy"),
        "# Two",
    )

    assert updated.slug == "privacy"
    assert get_document(tmp_path, "privacy") == updated
    assert get_document(tmp_path, "privacy-policy") is None
    assert not (tmp_path / "data" / "docs" / "bodies" / old_body_name).exists()


def test_document_storage_reads_existing_legacy_slug_named_body(tmp_path: Path) -> None:
    markdown = "# Existing document"
    legacy_body = f"privacy-policy-{hashlib.sha256(markdown.encode()).hexdigest()[:20]}.md"
    bodies = tmp_path / "data" / "docs" / "bodies"
    bodies.mkdir(parents=True)
    (bodies / legacy_body).write_text(markdown, encoding="utf-8")
    (tmp_path / "data" / "docs" / "index.json").write_text(
        json.dumps(
            {
                "version": DOCUMENTS_INDEX_VERSION,
                "documents": [
                    {
                        "title": "Privacy policy",
                        "slug": "privacy-policy",
                        "role": "privacy_policy",
                        "show_in_settings": True,
                        "show_in_sidebar": True,
                        "group_title": "Legal",
                        "sort_order": 0,
                        "body": legacy_body,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    document = get_document(tmp_path, "privacy-policy", bootstrap_legacy=False)

    assert document is not None
    assert document.markdown == markdown


def test_failed_index_update_keeps_the_previously_published_document(
    tmp_path: Path, monkeypatch
) -> None:
    created = create_document(tmp_path, _metadata("terms", role="user_agreement"), "# Old")
    bodies_dir = tmp_path / "data" / "docs" / "bodies"
    original_body_names = {body.name for body in bodies_dir.iterdir()}
    original_write_records = documents._write_records

    def fail_index_write(*_: object) -> None:
        raise DocumentStorageError("simulated index failure")

    monkeypatch.setattr(documents, "_write_records", fail_index_write)
    with pytest.raises(DocumentStorageError):
        update_document(tmp_path, created.slug, _metadata("terms", role="user_agreement"), "# New")
    monkeypatch.setattr(documents, "_write_records", original_write_records)

    persisted = get_document(tmp_path, "terms")
    assert persisted is not None
    assert persisted.markdown == "# Old"
    assert {body.name for body in bodies_dir.iterdir()} == original_body_names


def test_legacy_bootstrap_preserves_legacy_files_and_avoids_slug_collisions(tmp_path: Path) -> None:
    legacy = tmp_path / "data" / "legal"
    legacy.mkdir(parents=True)
    policy = legacy / "policy.md"
    policy.write_text("# Policy", encoding="utf-8")
    (legacy / "terms.md").write_text("# Terms", encoding="utf-8")
    create_document(tmp_path, _metadata("privacy-policy"), "# Existing")

    imported_policy = get_document_by_role(tmp_path, "privacy_policy")
    imported_terms = get_document_by_role(tmp_path, "user_agreement")

    assert imported_policy is not None
    assert imported_policy.slug == "privacy-policy-legacy"
    assert imported_policy.show_in_settings and imported_policy.show_in_sidebar
    assert imported_terms is not None
    assert imported_terms.show_in_settings and imported_terms.show_in_sidebar
    assert policy.read_text(encoding="utf-8") == "# Policy"
    assert [document.slug for document in list_documents(tmp_path)] == [
        "privacy-policy",
        "privacy-policy-legacy",
        "user-agreement",
    ]


def test_public_documents_api_exposes_nonempty_metadata_and_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_document(tmp_path, _metadata("about"), "# About")
    create_document(tmp_path, _metadata("draft"), "")
    monkeypatch.setattr(document_routes, "APP_ROOT", tmp_path)

    listed = asyncio.run(document_routes.documents_list_route(object()))
    content = asyncio.run(
        document_routes.document_content_route(
            type("Request", (), {"match_info": {"slug": "about"}})()
        )
    )

    assert json.loads(listed.text) == {
        "ok": True,
        "documents": [
            {
                "title": "About",
                "slug": "about",
                "role": "none",
                "show_in_settings": True,
                "show_in_sidebar": True,
                "group_title": "Legal",
                "sort_order": 10,
            }
        ],
    }
    assert json.loads(content.text)["markdown"] == "# About"


def test_document_slugs_allow_nested_paths_and_reject_unsafe_paths() -> None:
    assert normalize_document_slug(" Guides/Install/IOS ") == "guides/install/ios"
    assert normalize_document_slug("/guides/install") == "guides/install"
    assert normalize_document_slug("api/reference") == "api/reference"

    for slug in ("guides//install", "guides/../install"):
        with pytest.raises(documents.DocumentError):
            normalize_document_slug(slug)


def test_document_public_path_uses_the_legacy_prefix_for_reserved_roots() -> None:
    assert document_public_path("guides/install") == "/guides/install"
    assert document_public_path("support") == "/docs/support"


@pytest.mark.parametrize("unsafe_target", ["index", "bodies", "body"])
def test_document_storage_refuses_symlinked_index_and_bodies(
    tmp_path: Path, unsafe_target: str
) -> None:
    metadata = _metadata("terms", role="user_agreement")
    create_document(tmp_path, metadata, "# Terms")
    docs_root = tmp_path / "data" / "docs"
    outside = tmp_path / "outside"
    outside.mkdir()

    if unsafe_target == "index":
        index_path = docs_root / "index.json"
        index_path.unlink()
        index_path.symlink_to(outside / "index.json")
    elif unsafe_target == "bodies":
        bodies = docs_root / "bodies"
        for body in bodies.iterdir():
            body.unlink()
        bodies.rmdir()
        bodies.symlink_to(outside, target_is_directory=True)
    else:
        body = next((docs_root / "bodies").iterdir())
        body.unlink()
        body.symlink_to(outside / "body.md")

    with pytest.raises(DocumentStorageError):
        get_document(tmp_path, "terms", bootstrap_legacy=False)


def test_legacy_bootstrap_does_not_follow_a_symlinked_legal_document(tmp_path: Path) -> None:
    legal = tmp_path / "data" / "legal"
    legal.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("# Private", encoding="utf-8")
    (legal / "policy.md").symlink_to(outside)

    assert get_document_by_role(tmp_path, "privacy_policy") is None
