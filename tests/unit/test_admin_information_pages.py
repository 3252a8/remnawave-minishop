import asyncio
import json
from pathlib import Path

from bot.app.web.admin_api_impl import information_pages


class _Request:
    def __init__(
        self,
        *,
        query: dict[str, str] | None = None,
        body: dict | None = None,
        app: dict | None = None,
    ) -> None:
        self.query = query or {}
        self._body = body or {}
        self.app = app

    async def json(self) -> dict:
        return self._body


def _allow_admin(_: object) -> int:
    return 1


def test_admin_information_page_editor_loads_missing_document_and_saves_it(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(information_pages, "APP_ROOT", tmp_path)
    monkeypatch.setattr(information_pages, "_require_admin_user_id", _allow_admin)

    missing = asyncio.run(
        information_pages.admin_information_page_get_route(
            _Request(query={"path": "/company/about"})
        )
    )

    assert json.loads(missing.text) == {
        "ok": True,
        "path": "/company/about",
        "markdown": "",
        "exists": False,
    }

    saved = asyncio.run(
        information_pages.admin_information_page_save_route(
            _Request(body={"path": "/company/about", "markdown": "# About"})
        )
    )

    assert saved.status == 200
    assert json.loads(saved.text) == {
        "ok": True,
        "path": "/company/about",
        "markdown": "# About",
        "exists": True,
    }
    saved_path = tmp_path / "data" / "pages" / "company" / "about.md"
    assert saved_path.read_text(encoding="utf-8") == "# About"


def test_admin_information_page_editor_rejects_invalid_routes_and_conflicting_move(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(information_pages, "APP_ROOT", tmp_path)
    monkeypatch.setattr(information_pages, "_require_admin_user_id", _allow_admin)

    invalid = asyncio.run(
        information_pages.admin_information_page_get_route(_Request(query={"path": "/api/pages"}))
    )
    assert invalid.status == 400
    assert json.loads(invalid.text) == {
        "ok": False,
        "error": "invalid_page_path",
        "message": "invalid_page_path",
    }

    asyncio.run(
        information_pages.admin_information_page_save_route(
            _Request(body={"path": "/company/about", "markdown": "# About"})
        )
    )
    asyncio.run(
        information_pages.admin_information_page_save_route(
            _Request(body={"path": "/company/privacy", "markdown": "# Privacy"})
        )
    )
    conflict = asyncio.run(
        information_pages.admin_information_page_save_route(
            _Request(
                body={
                    "path": "/company/privacy",
                    "markdown": "# Replaced",
                    "previous_path": "/company/about",
                }
            )
        )
    )

    assert conflict.status == 409
    assert json.loads(conflict.text) == {
        "ok": False,
        "error": "information_page_exists",
        "message": "information_page_exists",
    }
    assert (tmp_path / "data" / "pages" / "company" / "about.md").exists()


def test_admin_information_page_save_invalidates_cached_webapp_settings(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(information_pages, "APP_ROOT", tmp_path)
    monkeypatch.setattr(information_pages, "_require_admin_user_id", _allow_admin)
    cache = {"ts": 42.0, "data": {"privacy_policy_url": "https://legacy.example/privacy"}}

    saved = asyncio.run(
        information_pages.admin_information_page_save_route(
            _Request(
                body={"path": "/legal/policy", "markdown": "# Policy"},
                app={"webapp_settings_cache": cache},
            )
        )
    )

    assert saved.status == 200
    assert cache == {"ts": 0.0, "data": {}}
