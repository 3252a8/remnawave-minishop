"""Bounded, checksummed transport parts for an unchanged backup ZIP."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

BACKUP_PART_BYTES = 45_000_000
PARTS_FORMAT = "remnawave-minishop-backup-parts"
PARTS_VERSION = 1
READ_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_PARTS = 10_000


class BackupPartsError(ValueError):
    """Transport parts are incomplete, unsafe, or inconsistent."""


@dataclass(frozen=True)
class BackupPart:
    path: Path
    size_bytes: int
    sha256: str


def split_backup(
    archive_path: Path, target_dir: Path, *, part_bytes: int = BACKUP_PART_BYTES
) -> tuple[list[BackupPart], Path]:
    if part_bytes < 1:
        raise ValueError("Part size must be positive")
    parts: list[BackupPart] = []
    archive_hash = hashlib.sha256()
    with archive_path.open("rb") as source:
        while chunk := source.read(min(READ_BYTES, part_bytes)):
            if len(parts) >= MAX_PARTS:
                raise BackupPartsError("Too many backup parts")
            path = target_dir / f"{archive_path.name}.part{len(parts) + 1:04d}"
            part_hash = hashlib.sha256()
            size = 0
            with path.open("xb") as output:
                while chunk:
                    output.write(chunk)
                    part_hash.update(chunk)
                    archive_hash.update(chunk)
                    size += len(chunk)
                    if size == part_bytes:
                        break
                    chunk = source.read(min(READ_BYTES, part_bytes - size))
            parts.append(BackupPart(path, size, part_hash.hexdigest()))
    if not parts:
        raise BackupPartsError("Backup archive is empty")
    manifest = {
        "format": PARTS_FORMAT,
        "version": PARTS_VERSION,
        "archive_name": archive_path.name,
        "size_bytes": sum(part.size_bytes for part in parts),
        "sha256": archive_hash.hexdigest(),
        "parts": [
            {"name": part.path.name, "size_bytes": part.size_bytes, "sha256": part.sha256}
            for part in parts
        ],
    }
    manifest_path = target_dir / f"{archive_path.name}.parts.json"
    encoded = json.dumps(manifest, indent=2).encode("utf-8")
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise BackupPartsError("Backup parts manifest is too large")
    with manifest_path.open("xb") as output:
        output.write(encoded)
    return parts, manifest_path


def validate_backup_filename(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or any(character in value for character in ("/", "\\", ":", "\x00"))
    ):
        raise BackupPartsError("Manifest contains an unsafe filename")
    return value


def _size(value: object) -> int:
    if type(value) is not int or value < 1:
        raise BackupPartsError("Manifest contains an invalid size")
    return value


def _sha256(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise BackupPartsError("Manifest contains an invalid SHA-256")
    return value


def join_backup(manifest_path: Path, output_path: Path | None = None) -> Path:
    """Verify all parts and atomically publish the ZIP without overwriting files."""
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise BackupPartsError("Backup parts manifest is too large")
    try:
        data: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise BackupPartsError("Invalid backup parts manifest") from exc
    if not isinstance(data, dict) or (
        data.get("format") != PARTS_FORMAT or data.get("version") != PARTS_VERSION
    ):
        raise BackupPartsError("Unsupported backup parts manifest")
    archive_name = validate_backup_filename(data.get("archive_name"))
    expected_size = _size(data.get("size_bytes"))
    expected_hash = _sha256(data.get("sha256"))
    records = data.get("parts")
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_PARTS:
        raise BackupPartsError("Manifest contains an invalid parts list")
    parts: list[BackupPart] = []
    names: set[str] = {manifest_path.name, archive_name}
    for record in records:
        if not isinstance(record, dict):
            raise BackupPartsError("Manifest contains an invalid part")
        name = validate_backup_filename(record.get("name"))
        if name in names:
            raise BackupPartsError("Manifest contains duplicate or conflicting filenames")
        names.add(name)
        path = manifest_path.parent / name
        if path.is_symlink() or not path.is_file():
            raise BackupPartsError(f"Backup part is missing or is a symlink: {name}")
        parts.append(
            BackupPart(path, _size(record.get("size_bytes")), _sha256(record.get("sha256")))
        )
    if sum(part.size_bytes for part in parts) != expected_size:
        raise BackupPartsError("Part sizes do not match the archive size")
    target = output_path or manifest_path.parent / archive_name
    if target.exists() or target.is_symlink():
        raise BackupPartsError(f"Output already exists: {target.name}")
    with tempfile.TemporaryDirectory(prefix=".join-backup-", dir=target.parent) as temporary:
        candidate = Path(temporary) / "archive.zip"
        archive_hash = hashlib.sha256()
        with candidate.open("xb") as output:
            for part in parts:
                part_hash = hashlib.sha256()
                size = 0
                with part.path.open("rb") as source:
                    while chunk := source.read(READ_BYTES):
                        size += len(chunk)
                        if size > part.size_bytes:
                            raise BackupPartsError(f"Backup part size mismatch: {part.path.name}")
                        output.write(chunk)
                        part_hash.update(chunk)
                        archive_hash.update(chunk)
                if size != part.size_bytes or part_hash.hexdigest() != part.sha256:
                    raise BackupPartsError(
                        f"Backup part checksum or size mismatch: {part.path.name}"
                    )
        if archive_hash.hexdigest() != expected_hash:
            raise BackupPartsError("Reassembled archive SHA-256 mismatch")
        # A hard link publishes only the verified bytes and refuses a concurrent overwrite.
        os.link(candidate, target)
    return target
