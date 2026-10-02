import asyncio
import io
from pathlib import Path

import pytest
from aiohttp import FormData, web
from aiohttp.test_utils import TestClient, TestServer

from bot.app.web.admin_api_impl import backups
from bot.services import backup_upload
from bot.services.backup_archive import (
    attach_archive_integrity,
    build_file_records,
    write_manifest,
    write_zip_from_directory,
)
from bot.services.backup_parts import split_backup
from config.settings import Settings


def make_zip(tmp_path: Path) -> Path:
    staging = tmp_path / "source"
    (staging / "compose").mkdir(parents=True)
    (staging / "compose" / "docker-compose.yml").write_text("services: {}\n")
    manifest = {
        "app": "remnawave-minishop",
        "format_version": 1,
        "created_at": "2026-10-02T09:00:00+00:00",
        "compose": {"included": True, "files_count": 1},
        "postgres": {"included": False},
    }
    attach_archive_integrity(manifest, file_records=build_file_records(staging))
    write_manifest(staging, manifest)
    archive = tmp_path / "original.zip"
    write_zip_from_directory(staging, archive)
    return archive


def configure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = Settings(
        BOT_TOKEN="123:test",
        POSTGRES_USER="test",
        POSTGRES_PASSWORD="test",
        BACKUP_DIR=str(tmp_path / "backups"),
        _env_file=None,
    )
    monkeypatch.setattr(backups, "get_settings", lambda _request: settings)
    monkeypatch.setattr(backups, "_require_admin_user_id", lambda _request: 1)
    return settings


def body(files: list[tuple[str, bytes]]) -> FormData:
    form = FormData()
    for name, payload in files:
        form.add_field("file", io.BytesIO(payload), filename=name)
    return form


def test_web_upload_parts_in_any_order_produces_one_full_downloadable_zip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = configure(tmp_path, monkeypatch)
    archive = make_zip(tmp_path)
    transport = tmp_path / "transport"
    transport.mkdir()
    parts, manifest = split_backup(archive, transport, part_bytes=100)
    files = [(part.path.name, part.path.read_bytes()) for part in reversed(parts)]
    files.insert(2, (manifest.name, manifest.read_bytes()))

    async def scenario() -> None:
        app = web.Application()
        app.router.add_post("/upload", backups.admin_backups_upload_route)
        app.router.add_get("/download/{archive_name}", backups.admin_backup_download_route)
        async with TestClient(TestServer(app)) as client:
            response = await client.post("/upload", data=body(files))
            assert response.status == 200, await response.text()
            data = await response.json()
            name = data["archive"]["name"]
            assert name.endswith(".zip")
            downloaded = await client.get(f"/download/{name}")
            assert downloaded.status == 200
            assert await downloaded.read() == await asyncio.to_thread(archive.read_bytes)
            assert 'filename="' + name + '"' in downloaded.headers["Content-Disposition"]

    asyncio.run(scenario())
    saved = list(Path(settings.BACKUP_DIR).iterdir())
    assert len(saved) == 1
    assert saved[0].suffix == ".zip"


def test_web_upload_single_zip_remains_compatible(tmp_path: Path, monkeypatch) -> None:
    settings = configure(tmp_path, monkeypatch)
    archive = make_zip(tmp_path)
    payload = archive.read_bytes()

    async def scenario() -> None:
        app = web.Application()
        app.router.add_post("/upload", backups.admin_backups_upload_route)
        async with TestClient(TestServer(app)) as client:
            response = await client.post("/upload", data=body([(archive.name, payload)]))
            assert response.status == 200, await response.text()

    asyncio.run(scenario())
    assert len(list(Path(settings.BACKUP_DIR).glob("*.zip"))) == 1


@pytest.mark.parametrize(
    "fault", ["missing", "duplicate", "corrupt", "extra", "mixed_zip", "two_manifests", "unsafe"]
)
def test_invalid_web_parts_never_publish_archive_or_leave_temporary_files(
    tmp_path: Path, monkeypatch, fault: str
) -> None:
    settings = configure(tmp_path, monkeypatch)
    archive = make_zip(tmp_path)
    transport = tmp_path / "transport"
    transport.mkdir()
    parts, manifest = split_backup(archive, transport, part_bytes=100)
    files = [(manifest.name, manifest.read_bytes())] + [
        (part.path.name, part.path.read_bytes()) for part in parts
    ]
    if fault == "missing":
        files.pop()
    elif fault == "duplicate":
        files.append(files[-1])
    elif fault == "corrupt":
        name, payload = files[-1]
        files[-1] = (name, b"x" * len(payload))
    elif fault == "extra":
        files.append(("different.zip.part0001", b"other backup"))
    elif fault == "mixed_zip":
        files.append((archive.name, archive.read_bytes()))
    elif fault == "two_manifests":
        files.append(("different.zip.parts.json", manifest.read_bytes()))
    else:
        files[1] = ("../escape.zip.part0001", files[1][1])

    async def scenario() -> None:
        app = web.Application()
        app.router.add_post("/upload", backups.admin_backups_upload_route)
        async with TestClient(TestServer(app)) as client:
            response = await client.post("/upload", data=body(files))
            assert response.status == 400, await response.text()
            data = await response.json()
            assert data["error"] == "invalid_backup_parts"

    asyncio.run(scenario())
    assert list(Path(settings.BACKUP_DIR).iterdir()) == []


def test_web_upload_enforces_combined_limit(tmp_path: Path, monkeypatch) -> None:
    settings = configure(tmp_path, monkeypatch)
    monkeypatch.setattr(backup_upload, "BACKUP_UPLOAD_MAX_BYTES", 10)

    async def scenario() -> None:
        app = web.Application()
        app.router.add_post("/upload", backups.admin_backups_upload_route)
        async with TestClient(TestServer(app)) as client:
            response = await client.post("/upload", data=body([("archive.zip", b"x" * 11)]))
            assert response.status == 400

    asyncio.run(scenario())
    assert list(Path(settings.BACKUP_DIR).iterdir()) == []
