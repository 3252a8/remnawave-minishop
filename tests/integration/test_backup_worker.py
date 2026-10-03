import asyncio
import json
import os
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.services.backup_worker import BACKUP_FILENAME_PREFIX, BackupWorker
from bot.services.settings_override_service import refresh_overrides_from_db
from config.settings import Settings


class _FakeBot:
    def __init__(self):
        self.send_document = AsyncMock()
        self.send_media_group = AsyncMock()
        self.send_message = AsyncMock()


class _FakePgDumpBackupWorker(BackupWorker):
    async def _dump_database(self, dump_path: Path) -> dict[str, object]:
        await asyncio.to_thread(dump_path.write_bytes, b"fake custom pg dump")
        return {"migration_ids": ["0001_initial"], "postgres_version": "17"}


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
        "TARIFFS_CONFIG_PATH": str(tmp_path / "tariffs.json"),
        "WEBAPP_THEMES_DIR": str(tmp_path / "themes"),
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
    history = compose_dir / "data" / "plugin-store" / "releases" / "example" / "old"
    history.mkdir(parents=True)
    (history / "package.so").write_bytes(b"historical package")
    images = compose_dir / "data" / "message-images"
    images.mkdir()
    (images / "welcome.png").write_bytes(b"image bytes")
    tariffs_path = tmp_path / "tariffs.json"
    tariffs_path.write_text('{"default_tariff":"standard","tariffs":[]}\n', encoding="utf-8")

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
    assert result.compose_files_count == 4
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
        archived_tariffs = archive.read("database/tariffs.json")

    assert "database/shop.dump" in names
    assert archived_tariffs == tariffs_path.read_bytes()
    assert "compose/docker-compose.yml" in names
    assert "compose/.env" in names
    assert "compose/Caddyfile" in names
    assert all("node_modules" not in name for name in names)
    assert all("compose/data/plugin-store" not in name for name in names)
    assert "compose/data/message-images/welcome.png" in names
    assert manifest["postgres"]["database"] == "shop"
    assert manifest["tariffs_config"] == {
        "source_path": str(tariffs_path),
        "archive_path": "database/tariffs.json",
        "included": True,
    }
    assert manifest["compose"]["files_count"] == 4


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


def test_backup_worker_forces_database_dump_for_pre_restore_snapshot(tmp_path):
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    settings = _settings(
        tmp_path,
        compose_dir,
        BACKUP_POSTGRES_DUMP_ENABLED=False,
        BACKUP_COMPOSE_ENABLED=False,
    )
    worker = _FakePgDumpBackupWorker(settings, _FakeBot())

    result = asyncio.run(worker.create_backup(backup_type="pre-restore", force_database=True))

    assert result.db_dump_included is True
    with zipfile.ZipFile(result.archive_path) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert "database/shop.dump" in archive.namelist()
    assert manifest["type"] == "pre-restore"
    assert manifest["minishop_version"]
    assert manifest["database_metadata"]["migration_ids"] == ["0001_initial"]
    assert manifest["postgres"]["included"] is True


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


@pytest.mark.parametrize(
    "store_name,theme_name", [("plugin-store", "themes"), ("extensions", "appearance")]
)
def test_backup_preserves_only_installed_packages_once_and_retains_legacy_restore(
    tmp_path, monkeypatch, store_name, theme_name
):
    from bot.plugins import packages
    from bot.services.backup_restore_service import BackupRestoreService
    from config.theme_packages.operations import remove_theme
    from config.theme_packages.registry import read_registry
    from tests.unit.test_theme_packages import install, package, ready

    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    (compose_dir / "docker-compose.yml").write_text("services: {}\n")
    store = compose_dir / "data" / store_name
    for digest in ("a" * 64, "b" * 64):
        release = store / "releases" / "example" / digest
        release.mkdir(parents=True)
        (release / "package.so").write_bytes(digest.encode())
    removed_release = store / "releases" / "removed-plugin" / ("c" * 64)
    removed_release.mkdir(parents=True)
    (removed_release / "package.so").write_bytes(b"removed plugin package")
    (store / "state.json").write_text(
        json.dumps(
            {
                "generation": 1,
                "installations": {
                    "example": {"digest": "a" * 64},
                    "removed-plugin": {"digest": "c" * 64},
                },
            }
        )
    )
    packages.remove_plugin(store, "removed-plugin", 7, 1)
    (store / "trusted-publishers.json").write_text("{}")
    monkeypatch.setattr(packages, "package_root", lambda: store)
    themes = compose_dir / "data" / theme_name
    install(themes, ready(themes))
    removed_digest = read_registry(themes).entries["ocean"].digest
    remove_theme(themes, "ocean", read_registry(themes).generation, "dark")
    install(themes, ready(themes, package("forest")), keys=("forest",))
    active_digest = read_registry(themes).entries["forest"].digest
    settings = _settings(tmp_path, compose_dir, WEBAPP_THEMES_DIR=str(themes))
    result = asyncio.run(_FakePgDumpBackupWorker(settings, _FakeBot()).create_backup())

    with zipfile.ZipFile(result.archive_path) as archive:
        names = set(archive.namelist())
        active = "config/plugin-store/releases/example/" + "a" * 64 + "/package.so"
        assert archive.read(active) == b"a" * 64
        assert "config/plugin-store/state.json" in names
        assert "config/plugin-store/trusted-publishers.json" in names
        assert not any(name.startswith(f"compose/data/{store_name}/") for name in names)
        assert not any(name.startswith(f"compose/data/{theme_name}/") for name in names)
        assert not any("b" * 64 in name for name in names)
        assert not any("removed-plugin" in name for name in names)
        assert not any(removed_digest in name for name in names)
        assert archive.read(f"config/themes/_packages/{active_digest}/theme.css")
        assert removed_release.is_dir()
        assert (themes / "_packages" / removed_digest).is_dir()
    assert "plugin-store" not in BackupRestoreService(settings)._compose_excluded_dirs()
    assert "themes" not in BackupRestoreService(settings)._compose_excluded_dirs()


def test_backup_worker_routes_large_archives_to_telegram_album(tmp_path, monkeypatch):
    from bot.services import backup_telegram

    monkeypatch.setattr(backup_telegram, "BACKUP_PART_BYTES", 17)
    settings = _settings(tmp_path, tmp_path / "compose", BACKUP_COMPOSE_ENABLED=False)
    bot = _FakeBot()
    result = asyncio.run(_FakePgDumpBackupWorker(settings, bot).create_and_send_backup())

    bot.send_document.assert_not_awaited()
    assert bot.send_media_group.await_count >= 1
    assert result.archive_path.is_file()
    assert not list(Path(settings.BACKUP_DIR).glob("telegram-parts-*"))


def test_backup_worker_splits_smaller_after_size_rejection(tmp_path):
    from aiogram.exceptions import TelegramEntityTooLarge
    from aiogram.methods import SendDocument

    settings = _settings(tmp_path, tmp_path / "compose", BACKUP_COMPOSE_ENABLED=False)
    bot = _FakeBot()
    bot.send_document.side_effect = TelegramEntityTooLarge(
        method=SendDocument(chat_id=123, document="backup"), message="Request Entity Too Large"
    )
    result = asyncio.run(_FakePgDumpBackupWorker(settings, bot).create_and_send_backup())

    bot.send_document.assert_awaited_once()
    bot.send_media_group.assert_awaited_once()
    assert len(bot.send_media_group.await_args.kwargs["media"]) >= 3
    assert result.archive_path.is_file()


def test_manual_backup_survives_telegram_failure_but_scheduled_backup_reports_it(tmp_path):
    import pytest

    settings = _settings(tmp_path, tmp_path / "compose", BACKUP_COMPOSE_ENABLED=False)
    bot = _FakeBot()
    bot.send_document.side_effect = RuntimeError("Telegram unavailable")
    worker = _FakePgDumpBackupWorker(settings, bot)
    result = asyncio.run(
        worker.create_and_send_backup(backup_type="manual", tolerate_delivery_failure=True)
    )
    assert result.archive_path.is_file()
    assert any("Telegram" in warning for warning in result.warnings)
    with pytest.raises(RuntimeError, match="Telegram unavailable"):
        asyncio.run(worker.create_and_send_backup())
    assert len(list(Path(settings.BACKUP_DIR).glob("minishop-*.zip"))) == 1
