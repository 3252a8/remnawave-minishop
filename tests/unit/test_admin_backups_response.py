from datetime import UTC, datetime
from pathlib import Path

from bot.app.web.admin_api_impl.response_schemas import AdminBackupArchiveOut
from bot.services.backup_restore_service import BackupArchiveInfo


def test_backup_archive_response_omits_internal_integrity_records() -> None:
    file_records = [
        {"path": f"compose/service-{index}.yml", "size": index, "sha256": "a" * 64}
        for index in range(100)
    ]
    archive = BackupArchiveInfo(
        name="minishop-backup.zip",
        path=Path("minishop-backup.zip"),
        size_bytes=4096,
        modified_at=datetime(2026, 9, 2, tzinfo=UTC),
        has_database=True,
        has_compose=True,
        manifest={
            "app": "remnawave-minishop",
            "format_version": 1,
            "archive": {"files": file_records},
        },
    )

    payload = AdminBackupArchiveOut.from_archive(archive).model_dump(mode="json")

    assert payload["manifest"] == {
        "app": "remnawave-minishop",
        "format_version": 1,
    }
    assert archive.manifest["archive"] == {"files": file_records}
