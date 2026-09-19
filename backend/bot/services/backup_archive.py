import hashlib
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

BACKUP_APP_ID = "remnawave-minishop"
BACKUP_FILENAME_PREFIX = "minishop-"
BACKUP_FORMAT_VERSION = 1
BACKUP_MANIFEST_NAME = "manifest.json"
BACKUP_TARIFFS_CONFIG_MEMBER = "database/tariffs.json"
BACKUP_ZIP_COMPRESSION_LEVEL = 9


def backup_filename_timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H-%M")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_file_records(source_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source_dir).as_posix()
        if relative == BACKUP_MANIFEST_NAME:
            continue
        stat = path.stat()
        records.append(
            {
                "path": relative,
                "size_bytes": int(stat.st_size),
                "sha256": file_sha256(path),
            }
        )
    return records


def attach_archive_integrity(
    manifest: dict[str, Any],
    *,
    file_records: list[dict[str, Any]],
) -> None:
    manifest["app"] = BACKUP_APP_ID
    manifest["format_version"] = BACKUP_FORMAT_VERSION
    manifest["archive"] = {
        "files": file_records,
    }


def write_manifest(source_dir: Path, manifest: dict[str, Any]) -> None:
    (source_dir / BACKUP_MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_zip_from_directory(source_dir: Path, archive_path: Path) -> None:
    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=BACKUP_ZIP_COMPRESSION_LEVEL,
    ) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir).as_posix())
