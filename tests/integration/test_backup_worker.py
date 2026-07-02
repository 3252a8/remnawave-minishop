import asyncio
import json
import os
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.services.backup_worker import BACKUP_FILENAME_PREFIX, BackupWorker
from bot.services.settings_override_service import refresh_overrides_from_db
from config.settings import Settings


class _FakeBot:
    def __init__(self):
        self.send_document = AsyncMock()
        self.send_message = AsyncMock()


class _FakePgDumpBackupWorker(BackupWorker):
    def _run_pg_dump(self, dump_path: Path) -> None:
        dump_path.write_bytes(b"fake custom pg dump")


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSessionFactory:
    def __call__(self):
        return _FakeSession()


def _settings(tmp_path: Path, compose_dir: Path, **overrides) -> Settings:
    values = {
        "BOT_TOKEN": "token",
        "POSTGRES_USER": "app_user",
        "POSTGRES_PASSWORD": "app_password",
        "POSTGRES_DB": "shop",
        "BACKUP_DIR": str(tmp_path / "backups"),
        "BACKUP_COMPOSE_SOURCE_DIR": str(compose_dir),
        "BACKUP_CHAT_ID": 123,
        "BACKUP_LOCAL_RETENTION": 1,
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_backup_worker_creates_archive_with_db_dump_and_compose_snapshot(tmp_path):
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    (compose_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (compose_dir / ".env").write_text("POSTGRES_PASSWORD=secret\n", encoding="utf-8")
    (compose_dir / "Caddyfile").write_text("example.com\n", encoding="utf-8")
    (compose_dir / "node_modules").mkdir()
    (compose_dir / "node_modules" / "ignored.txt").write_text("ignored", encoding="utf-8")

    settings = _settings(tmp_path, compose_dir)
    backup_dir = Path(settings.BACKUP_DIR)
    backup_dir.mkdir(parents=True)
    old_archive = backup_dir / f"{BACKUP_FILENAME_PREFIX}old.zip"
    old_archive.write_text("old", encoding="utf-8")
    os.utime(old_archive, (1, 1))

    bot = _FakeBot()
    worker = _FakePgDumpBackupWorker(settings, bot)

    result = asyncio.run(worker.create_and_send_backup())

    assert result.archive_path.is_file()
    assert result.db_dump_included is True
    assert result.compose_files_count == 3
    assert re.fullmatch(r"minishop-\d{8}-\d{2}-\d{2}\.zip", result.archive_path.name)
    assert not old_archive.exists()
    bot.send_document.assert_awaited_once()
    send_kwargs = bot.send_document.await_args.kwargs
    assert send_kwargs["chat_id"] == 123
    assert "Database dump: yes" in send_kwargs["caption"]
    assert "Warnings" not in send_kwargs["caption"]

    with zipfile.ZipFile(result.archive_path) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

    assert "database/shop.dump" in names
    assert "compose/docker-compose.yml" in names
    assert "compose/.env" in names
    assert "compose/Caddyfile" in names
    assert all("node_modules" not in name for name in names)
    assert manifest["postgres"]["database"] == "shop"
    assert manifest["compose"]["files_count"] == 3


def test_backup_worker_falls_back_to_log_chat_and_thread(tmp_path):
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    settings = _settings(
        tmp_path,
        compose_dir,
        BACKUP_CHAT_ID="",
        BACKUP_THREAD_ID="",
        LOG_CHAT_ID=-100123,
        LOG_THREAD_ID=77,
        BACKUP_POSTGRES_DUMP_ENABLED=False,
        BACKUP_COMPOSE_ENABLED=False,
    )
    bot = _FakeBot()
    worker = _FakePgDumpBackupWorker(settings, bot)

    result = asyncio.run(worker.create_and_send_backup())

    assert result.db_dump_included is False
    bot.send_document.assert_awaited_once()
    send_kwargs = bot.send_document.await_args.kwargs
    assert send_kwargs["chat_id"] == -100123
    assert send_kwargs["message_thread_id"] == 77


def test_backup_worker_can_create_manual_backup(tmp_path):
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    settings = _settings(
        tmp_path,
        compose_dir,
        BACKUP_POSTGRES_DUMP_ENABLED=True,
        BACKUP_COMPOSE_ENABLED=False,
    )
    bot = _FakeBot()
    worker = _FakePgDumpBackupWorker(settings, bot)

    result = asyncio.run(worker.create_backup(backup_type="manual"))

    assert result.archive_path.is_file()
    assert result.to_payload()["archive_name"] == result.archive_path.name
    with zipfile.ZipFile(result.archive_path) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert manifest["type"] == "manual"
    assert "archive" in manifest


def test_backup_worker_allocates_unique_archive_path(tmp_path):
    settings = _settings(tmp_path, tmp_path / "compose")
    worker = _FakePgDumpBackupWorker(settings, _FakeBot())
    archive_path = tmp_path / "minishop-20260527-12-00.zip"
    archive_path.write_text("existing", encoding="utf-8")

    unique_path = worker._unique_archive_path(archive_path)

    assert unique_path.name == "minishop-20260527-12-00-2.zip"


def test_backup_worker_does_not_fail_when_compose_source_is_not_mounted(tmp_path):
    missing_compose_dir = tmp_path / "missing-compose"
    settings = _settings(
        tmp_path,
        missing_compose_dir,
        BACKUP_POSTGRES_DUMP_ENABLED=True,
        BACKUP_COMPOSE_ENABLED=True,
    )
    bot = _FakeBot()
    worker = _FakePgDumpBackupWorker(settings, bot)

    result = asyncio.run(worker.create_and_send_backup())

    assert result.archive_path.is_file()
    assert result.db_dump_included is True
    assert result.compose_files_count == 0
    assert any(
        "Compose source directory is unavailable in this container" in item
        for item in result.warnings
    )
    bot.send_document.assert_awaited_once()
    caption = bot.send_document.await_args.kwargs["caption"]
    assert "Warnings (1):" in caption
    assert "1. If manual backup includes compose but scheduled backup does not" in caption
    assert "Compose source directory is unavailable in this container" in caption
    assert "recreate the worker service" in caption
    with zipfile.ZipFile(result.archive_path) as archive:
        names = set(archive.namelist())
    assert "database/shop.dump" in names


def test_backup_worker_caption_lists_and_truncates_warning_details(tmp_path):
    settings = _settings(tmp_path, tmp_path / "compose")
    worker = _FakePgDumpBackupWorker(settings, _FakeBot())
    result = SimpleNamespace(
        completed_at=datetime.now(UTC),
        db_dump_included=True,
        compose_files_count=0,
        size_bytes=1024,
        warnings=[
            "first warning",
            "second warning",
            "third warning",
            "fourth warning",
            "fifth warning",
            "sixth warning",
            "seventh warning",
        ],
    )

    caption = worker._caption(result)

    assert "Warnings (7):" in caption
    assert "1. first warning" in caption
    assert "6. sixth warning" in caption
    assert "seventh warning" not in caption
    assert "... and 1 more warning(s)" in caption
    assert len(caption) <= 1024


def test_backup_settings_refresh_restores_env_default_when_override_is_deleted(monkeypatch):
    from bot.services import settings_override_service

    settings = SimpleNamespace(BACKUP_ENABLED=True)
    monkeypatch.setattr(
        settings_override_service.app_settings_dal,
        "get_all_overrides",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        settings_override_service,
        "Settings",
        lambda: SimpleNamespace(BACKUP_ENABLED=False),
    )

    applied = asyncio.run(
        refresh_overrides_from_db(
            settings,
            _FakeSessionFactory(),
            keys={"BACKUP_ENABLED"},
        )
    )

    assert applied == 0
    assert settings.BACKUP_ENABLED is False
