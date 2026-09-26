from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from aiohttp import web

from bot.app.web.admin_api_impl import documents


class _Request:
    def __init__(
        self,
        *,
        body: dict[str, object] | None = None,
        slug: str = "",
        app: dict[str, object] | None = None,
    ) -> None:
        self._body = body or {}
        self.match_info = {"slug": slug}
        self.app = app or {}

    async def json(self) -> dict[str, object]:
        return self._body


def _allow_admin(_: object) -> int:
    return 1


def _body(**overrides: object) -> dict[str, object]:
    return {
        "title": "Privacy policy",
        "slug": "privacy-policy",
        "markdown": "# Policy",
        "role": "privacy_policy",
        "show_in_settings": True,
        "show_in_sidebar": True,
        "group_title": "Legal",
        "sort_order": 10,
        **overrides,
    }


@pytest.mark.parametrize(
    ("original_slug", "renamed_slug"),
    [
        ("privacy-policy", "privacy"),
        ("guides/privacy-policy", "legal/privacy"),
    ],
)
def test_admin_documents_crud_supports_safe_slug_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    original_slug: str,
    renamed_slug: str,
) -> None:
    monkeypatch.setattr(documents, "APP_ROOT", tmp_path)
    monkeypatch.setattr(documents, "_require_admin_user_id", _allow_admin)
    cache: dict[str, object] = {"ts": 42.0, "data": {"cached": True}}

    created = asyncio.run(
        documents.admin_document_create_route(
            _Request(body=_body(slug=original_slug), app={"webapp_settings_cache": cache})
        )
    )
    listed = asyncio.run(documents.admin_documents_list_route(_Request()))
    updated = asyncio.run(
        documents.admin_document_update_route(
            _Request(
                slug=original_slug,
                body=_body(slug=renamed_slug, title="Privacy", markdown="# Updated"),
            )
        )
    )
    missing_old = asyncio.run(documents.admin_document_get_route(_Request(slug=original_slug)))
    deleted = asyncio.run(documents.admin_document_delete_route(_Request(slug=renamed_slug)))

    assert created.status == 200
    assert json.loads(created.text)["slug"] == original_slug
    assert json.loads(listed.text)["documents"][0]["role"] == "privacy_policy"
    assert json.loads(updated.text)["markdown"] == "# Updated"
    assert missing_old.status == 404
    assert json.loads(deleted.text) == {"ok": True}
    assert cache == {"ts": 0.0, "data": {}}


def test_admin_documents_reject_non_boolean_visibility_and_duplicate_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(documents, "APP_ROOT", tmp_path)
    monkeypatch.setattr(documents, "_require_admin_user_id", _allow_admin)

    with pytest.raises(web.HTTPBadRequest):
        asyncio.run(
            documents.admin_document_create_route(_Request(body=_body(show_in_settings="false")))
        )

    asyncio.run(documents.admin_document_create_route(_Request(body=_body())))
    conflict = asyncio.run(
        documents.admin_document_create_route(
            _Request(body=_body(slug="another-policy", title="Another policy"))
        )
    )

    assert conflict.status == 409
    assert json.loads(conflict.text)["error"] == "document_conflict"
