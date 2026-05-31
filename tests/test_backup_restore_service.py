import asyncio
import re
import tempfile
import zipfile
from pathlib import Path

import pytest

from bot.services.backup_archive import (
    attach_archive_integrity,
    build_file_records,
    write_manifest,
    write_zip_from_directory,
)
from bot.services.backup_restore_service import (
    COMPOSE_PRE_RESTORE_PREFIX,
    BackupArchiveError,
    BackupRestoreService,
)
from bot.services.backup_worker import BACKUP_FILENAME_PREFIX
from config.settings import Settings


def _settings(tmp_path: Path, compose_dir: Path, **overrides) -> Settings:
    values = {
        "BOT_TOKEN": "token",
        "POSTGRES_USER": "app_user",
        "POSTGRES_PASSWORD": "app_password",
        "POSTGRES_DB": "shop",
        "BACKUP_DIR": str(tmp_path / "backups"),
        "BACKUP_COMPOSE_SOURCE_DIR": str(compose_dir),
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def _write_backup_archive(
    path: Path,
    *,
    include_db=True,
    include_compose=True,
    unsafe=False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as tmp:
        staging_dir = Path(tmp)
        if include_db:
            dump_dir = staging_dir / "database"
            dump_dir.mkdir(parents=True)
            (dump_dir / "shop.dump").write_bytes(b"fake dump")
        if include_compose:
            compose_dir = staging_dir / "compose"
            compose_dir.mkdir(parents=True)
            (compose_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
            (compose_dir / ".env").write_text("POSTGRES_PASSWORD=secret\n", encoding="utf-8")
        manifest = {
            "app": "remnawave-minishop",
            "format_version": 1,
            "type": "test",
            "created_at": "2026-05-27T09:00:00+00:00",
            "postgres": {"database": "shop", "included": include_db},
            "compose": {"included": include_compose, "files_count": 2 if include_compose else 0},
            "warnings": [],
        }
        attach_archive_integrity(
            manifest,
            file_records=build_file_records(staging_dir),
        )
        write_manifest(staging_dir, manifest)
        write_zip_from_directory(staging_dir, path)
    if unsafe:
        # Add a malicious member after signing; validation must reject before restore.
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr("compose/../evil.txt", "nope")


def test_backup_restore_service_lists_archives_with_contents(tmp_path):
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    settings = _settings(tmp_path, compose_dir)
    archive_path = Path(settings.BACKUP_DIR) / f"{BACKUP_FILENAME_PREFIX}20260527-12-00.zip"
    _write_backup_archive(archive_path)

    archives = BackupRestoreService(settings).list_archives()

    assert [item.name for item in archives] == [archive_path.name]
    assert archives[0].has_database is True
    assert archives[0].has_compose is True
    assert archives[0].database_name == "shop"
    assert archives[0].compose_files_count == 2


def test_backup_restore_service_rejects_path_traversal_archive_name(tmp_path):
    settings = _settings(tmp_path, tmp_path / "compose")
    service = BackupRestoreService(settings)

    with pytest.raises(BackupArchiveError):
        service.archive_path_for_name("../backup.zip")


def test_backup_restore_service_restores_compose_and_snapshots_current(tmp_path, monkeypatch):
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    (compose_dir / "docker-compose.yml").write_text("old: true\n", encoding="utf-8")

    settings = _settings(tmp_path, compose_dir)
    monkeypatch.setattr(
        "bot.services.backup_restore_service.backup_filename_timestamp",
        lambda: "20260527-12-15",
    )
    existing_snapshot = (
        Path(settings.BACKUP_DIR) / f"{COMPOSE_PRE_RESTORE_PREFIX}20260527-12-15.zip"
    )
    existing_snapshot.parent.mkdir(parents=True, exist_ok=True)
    existing_snapshot.write_text("existing", encoding="utf-8")
    archive_path = Path(settings.BACKUP_DIR) / f"{BACKUP_FILENAME_PREFIX}20260527-12-00.zip"
    _write_backup_archive(archive_path, include_db=False)

    service = BackupRestoreService(settings)
    result = service.restore_archive_sync(
        archive_path.name,
        restore_database=False,
        restore_compose=True,
    )

    assert result.database_restored is False
    assert result.compose_files_restored == 2
    assert (compose_dir / "docker-compose.yml").read_text(encoding="utf-8") == "services: {}\n"
    assert (compose_dir / ".env").read_text(encoding="utf-8") == "POSTGRES_PASSWORD=secret\n"
    assert result.compose_pre_restore_archive
    snapshot_path = Path(result.compose_pre_restore_archive)
    assert snapshot_path.is_file()
    assert snapshot_path.name == f"{COMPOSE_PRE_RESTORE_PREFIX}20260527-12-15-2.zip"
    assert existing_snapshot.read_text(encoding="utf-8") == "existing"
    snapshot = service.inspect_archive(Path(result.compose_pre_restore_archive))
    assert snapshot.has_compose is True
    assert snapshot.compose_files_count == 1


def test_backup_restore_service_prevents_zip_slip_in_compose_restore(tmp_path):
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    settings = _settings(tmp_path, compose_dir)
    archive_path = Path(settings.BACKUP_DIR) / f"{BACKUP_FILENAME_PREFIX}20260527-12-00.zip"
    _write_backup_archive(archive_path, include_db=False, unsafe=True)

    with pytest.raises(BackupArchiveError):
        BackupRestoreService(settings).restore_archive_sync(
            archive_path.name,
            restore_database=False,
            restore_compose=True,
        )

    assert not (tmp_path / "evil.txt").exists()


def test_backup_restore_service_runs_pg_restore_for_dump(tmp_path):
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    settings = _settings(tmp_path, compose_dir)
    archive_path = Path(settings.BACKUP_DIR) / f"{BACKUP_FILENAME_PREFIX}20260527-12-00.zip"
    _write_backup_archive(archive_path, include_compose=False)
    service = BackupRestoreService(settings)
    restored_payloads = []

    def fake_pg_restore(dump_path: Path) -> None:
        restored_payloads.append(dump_path.read_bytes())

    service._run_pg_restore = fake_pg_restore
    service._run_post_restore_migrations = lambda: []

    result = asyncio.run(
        service.restore_archive(
            archive_path.name,
            restore_database=True,
            restore_compose=False,
        )
    )

    assert result.database_restored is True
    assert restored_payloads == [b"fake dump"]
    assert result.database_migrations_applied == []


def test_backup_restore_service_runs_migrations_after_database_restore(tmp_path):
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    settings = _settings(tmp_path, compose_dir)
    archive_path = Path(settings.BACKUP_DIR) / f"{BACKUP_FILENAME_PREFIX}20260527-12-00.zip"
    _write_backup_archive(archive_path, include_compose=False)
    service = BackupRestoreService(settings)
    calls = []

    def fake_pg_restore(dump_path: Path) -> None:
        calls.append(("restore", dump_path.read_bytes()))

    def fake_migrations() -> list[str]:
        calls.append(("migrate", None))
        return ["0031_add_subscription_notifications", "0032_add_telegram_notification_status"]

    service._run_pg_restore = fake_pg_restore
    service._run_post_restore_migrations = fake_migrations

    result = service.restore_archive_sync(
        archive_path.name,
        restore_database=True,
        restore_compose=False,
    )

    assert calls == [("restore", b"fake dump"), ("migrate", None)]
    assert result.database_restored is True
    assert result.database_migrations_applied == [
        "0031_add_subscription_notifications",
        "0032_add_telegram_notification_status",
    ]
    assert result.to_payload()["database_migrations_applied"] == [
        "0031_add_subscription_notifications",
        "0032_add_telegram_notification_status",
    ]


def test_backup_restore_service_accepts_archive_from_another_instance(tmp_path):
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    target_settings = _settings(tmp_path, compose_dir, BOT_TOKEN="target-token")
    archive_path = Path(target_settings.BACKUP_DIR) / (
        f"{BACKUP_FILENAME_PREFIX}20260527-12-00.zip"
    )
    _write_backup_archive(archive_path, include_compose=False)

    service = BackupRestoreService(target_settings)
    restored_payloads = []

    def fake_pg_restore(dump_path: Path) -> None:
        restored_payloads.append(dump_path.read_bytes())

    service._run_pg_restore = fake_pg_restore
    service._run_post_restore_migrations = lambda: []

    result = service.restore_archive_sync(
        archive_path.name,
        restore_database=True,
        restore_compose=False,
    )

    assert result.database_restored is True
    assert restored_payloads == [b"fake dump"]


def test_backup_restore_service_validates_uploaded_zip(tmp_path):
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    settings = _settings(tmp_path, compose_dir)
    temp_path = tmp_path / "not-a-backup.zip"
    temp_path.write_text("not zip", encoding="utf-8")

    with pytest.raises(BackupArchiveError):
        BackupRestoreService(settings).import_uploaded_archive(temp_path, "backup.zip")


def test_backup_restore_service_imports_uploaded_archive_with_compact_name(tmp_path):
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    settings = _settings(tmp_path, compose_dir)
    temp_path = tmp_path / "source.zip"
    _write_backup_archive(temp_path)

    archive = BackupRestoreService(settings).import_uploaded_archive(
        temp_path,
        "very-long-original-backup-name.zip",
    )

    assert re.fullmatch(
        r"minishop-uploaded-\d{8}-\d{2}-\d{2}-[a-f0-9]{16}\.zip",
        archive.name,
    )


def test_backup_restore_service_rejects_tampered_archive(tmp_path):
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    settings = _settings(tmp_path, compose_dir)
    archive_path = Path(settings.BACKUP_DIR) / f"{BACKUP_FILENAME_PREFIX}20260527-12-00.zip"
    _write_backup_archive(archive_path, include_compose=False)

    tampered_path = archive_path.with_name("tampered.zip")
    with zipfile.ZipFile(archive_path) as source, zipfile.ZipFile(tampered_path, "w") as target:
        for member in source.infolist():
            payload = source.read(member.filename)
            if member.filename == "database/shop.dump":
                payload = b"not the signed dump"
            target.writestr(member, payload)

    with pytest.raises(BackupArchiveError):
        BackupRestoreService(settings).import_uploaded_archive(tampered_path, "tampered.zip")
