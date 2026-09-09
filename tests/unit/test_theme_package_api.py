from __future__ import annotations

import asyncio
import io
import json
import warnings
import zipfile
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from aiohttp import FormData, web
from aiohttp.test_utils import TestClient, TestServer
from aiohttp.web_exceptions import NotAppKeyWarning

from bot.app.web import session as web_session
from bot.app.web.admin_api_impl import auth, theme_library
from config.theme_packages.archive import deterministic_zip
from tests.support.settings_stub import settings_stub
from tests.unit.test_theme_packages import package


@asynccontextmanager
async def client_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[TestClient]:
    settings = settings_stub(
        ADMIN_IDS=[99],
        WEBAPP_THEMES_DIR=str(tmp_path),
        WEBAPP_PRIMARY_COLOR="#00fe7a",
        WEBAPP_DEFAULT_THEME=None,
    )
    monkeypatch.setattr(auth, "get_settings", lambda _request: settings)
    monkeypatch.setattr(web_session, "get_settings", lambda _request: settings)
    monkeypatch.setattr(theme_library, "get_settings", lambda _request: settings)
    monkeypatch.setattr(
        web_session,
        "verify_webapp_session_token",
        lambda _settings, token: {"user7": 7, "user8": 8}.get(token),
    )

    async def refresh(_request: web.Request, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(theme_library, "refresh_webapp_runtime_after_settings_change", refresh)

    @web.middleware
    async def identity(
        request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        if request.headers.get("X-Test-Admin") == "yes":
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", NotAppKeyWarning)
                request["admin_telegram_id"] = 99
        return await handler(request)

    app = web.Application(middlewares=[identity])
    theme_library.setup_theme_jobs(app)
    theme_library.setup_theme_library(app.router)
    async with TestClient(TestServer(app)) as test_client:
        yield test_client


def test_authentication_and_admin_role_precede_import_processing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        async with client_context(tmp_path, monkeypatch) as client:
            for path, method in [
                ("/api/admin/themes/library", "GET"),
                ("/api/admin/themes/imports", "POST"),
                ("/api/admin/themes/export", "POST"),
                ("/api/admin/themes/library/ocean", "DELETE"),
                ("/api/admin/themes/library/ocean/rollback", "POST"),
                ("/api/admin/themes/library/ocean/preview", "GET"),
            ]:
                response = await client.request(method, path)
                assert response.status == 401
                response = await client.request(
                    method, path, headers={"Authorization": "Bearer user7"}
                )
                assert response.status == 403

    asyncio.run(scenario())


def test_upload_preview_install_export_and_owner_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        async with client_context(tmp_path, monkeypatch) as client:
            headers = {"Authorization": "Bearer user7", "X-Test-Admin": "yes"}
            response = await client.get("/api/admin/themes/library", headers=headers)
            assert response.status == 200
            initial = await response.json()

            form = FormData()
            form.add_field(
                "file",
                deterministic_zip(package()),
                filename="ocean.zip",
                content_type="application/zip",
            )
            response = await client.post("/api/admin/themes/imports", data=form, headers=headers)
            assert response.status == 200, await response.text()
            operation = (await response.json())["operation"]
            assert operation["state"] == "ready"
            base = "/api/admin/themes/imports/" + operation["id"]

            other = await client.get(base, headers={**headers, "Authorization": "Bearer user8"})
            assert other.status == 404
            preview = await client.get(base + "/preview/ocean", headers=headers)
            assert preview.status == 200
            assert "sandbox;" in preview.headers["Content-Security-Policy"]
            document = await preview.text()
            assert "<script" not in document.lower()
            assert "THEME_KEY_PLACEHOLDER" not in document
            assert "connect-src" not in document or "connect-src 'none'" in document
            assert "Content-Security-Policy" in document

            body = {
                "choices": [{"key": "ocean"}],
                "expected_generation": initial["generation"],
                "idempotency_key": "browser-click-0001",
            }
            response = await client.post(base + "/install", json=body, headers=headers)
            assert response.status == 200, await response.text()
            installed = await response.json()
            replay = await client.post(base + "/install", json=body, headers=headers)
            assert (await replay.json()) == installed
            response = await client.post(
                "/api/admin/themes/export",
                json={"keys": ["ocean"], "new_key": "ocean-copy"},
                headers=headers,
            )
            assert response.status == 200
            assert response.content_type == "application/zip"
            with zipfile.ZipFile(io.BytesIO(await response.read())) as archive:
                assert json.loads(archive.read("ocean-copy/theme.json"))["key"] == "ocean-copy"

    asyncio.run(scenario())


def test_bad_zip_and_unsupported_repository_return_bounded_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        async with client_context(tmp_path, monkeypatch) as client:
            headers = {"Authorization": "Bearer user7", "X-Test-Admin": "yes"}
            form = FormData()
            form.add_field("file", b"not a zip", filename="bad.zip", content_type="application/zip")
            response = await client.post("/api/admin/themes/imports", data=form, headers=headers)
            assert response.status == 200
            assert (await response.json())["operation"]["state"] == "failed"
            response = await client.post(
                "/api/admin/themes/imports",
                json={"url": "https://127.0.0.1/private"},
                headers=headers,
            )
            assert response.status == 400

    asyncio.run(scenario())


def test_multipart_theme_upload_exceeds_the_ordinary_request_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_STORED) as archive:
            for name, content in package().items():
                archive.writestr(name, content)
            for name in ("one.txt", "two.txt"):
                archive.writestr("ocean/" + name, b"a" * (6 * 1024 * 1024))
        async with client_context(tmp_path, monkeypatch) as client:
            form = FormData()
            form.add_field(
                "file",
                io.BytesIO(stream.getvalue()),
                filename="large.zip",
                content_type="application/zip",
            )
            response = await client.post(
                "/api/admin/themes/imports",
                data=form,
                headers={
                    "Authorization": "Bearer user7",
                    "X-Test-Admin": "yes",
                },
            )
            assert response.status == 200
            assert (await response.json())["operation"]["state"] == "ready"

    asyncio.run(scenario())
