"""Stream a ZIP or Telegram transport parts into a verified server-side backup."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from aiohttp import web
from aiohttp.multipart import BodyPartReader

from bot.services.backup_parts import (
    MAX_MANIFEST_BYTES,
    MAX_PARTS,
    BackupPartsError,
    join_backup,
    validate_backup_filename,
)
from bot.services.backup_restore_service import (
    BACKUP_UPLOAD_MAX_BYTES,
    BackupArchiveError,
    BackupArchiveInfo,
    BackupRestoreService,
)
from config.settings import Settings


async def read_uploaded_backup(request: web.Request, settings: Settings) -> BackupArchiveInfo:
    service = BackupRestoreService(settings)
    backup_dir = service.backup_dir()
    reader = await request.multipart()
    with tempfile.TemporaryDirectory(prefix=".upload-", dir=backup_dir) as temporary:
        staging = Path(temporary)
        uploads: dict[str, Path] = {}
        sizes: dict[str, int] = {}
        total = 0
        async for part in reader:
            if not isinstance(part, BodyPartReader) or part.name != "file":
                raise BackupArchiveError("Only multipart file fields are supported")
            if len(uploads) >= MAX_PARTS + 1:
                raise BackupPartsError("Too many uploaded backup files")
            name = validate_backup_filename(part.filename or "backup.zip")
            if name in uploads:
                raise BackupPartsError("Uploaded backup files have duplicate names")
            target = staging / name
            maximum = (
                MAX_MANIFEST_BYTES if name.endswith(".parts.json") else BACKUP_UPLOAD_MAX_BYTES
            )
            size = 0
            handle = await asyncio.to_thread(target.open, "xb")
            try:
                while chunk := await part.read_chunk(size=1024 * 1024):
                    size += len(chunk)
                    total += len(chunk)
                    if size > maximum or total > BACKUP_UPLOAD_MAX_BYTES + MAX_MANIFEST_BYTES:
                        raise BackupArchiveError("Backup upload is too large")
                    await asyncio.to_thread(handle.write, chunk)
            finally:
                await asyncio.to_thread(handle.close)
            if size == 0:
                raise BackupArchiveError("Uploaded backup file is empty")
            uploads[name] = target
            sizes[name] = size
        if not uploads:
            raise BackupArchiveError("file field is required")
        if len(uploads) == 1 and next(iter(uploads)).lower().endswith(".zip"):
            name, source = next(iter(uploads.items()))
        else:
            manifests = [path for name, path in uploads.items() if name.endswith(".zip.parts.json")]
            if len(manifests) != 1:
                raise BackupPartsError("Select one ZIP or one parts manifest and every part")
            manifest = manifests[0]
            try:
                data: object = json.loads(
                    await asyncio.to_thread(manifest.read_text, encoding="utf-8")
                )
            except (ValueError, UnicodeError) as exc:
                raise BackupPartsError("Invalid backup parts manifest") from exc
            if not isinstance(data, dict) or not isinstance(data.get("parts"), list):
                raise BackupPartsError("Invalid backup parts manifest")
            names: list[str] = []
            for record in data["parts"]:
                if not isinstance(record, dict):
                    raise BackupPartsError("Manifest contains an invalid part")
                names.append(validate_backup_filename(record.get("name")))
            expected = set(names) | {manifest.name}
            if len(names) != len(set(names)) or set(uploads) != expected:
                raise BackupPartsError("Uploaded files do not match the manifest parts list")
            if (
                sum(size for name, size in sizes.items() if name != manifest.name)
                > BACKUP_UPLOAD_MAX_BYTES
            ):
                raise BackupArchiveError("Backup archive is too large")
            source = await asyncio.to_thread(join_backup, manifest)
            name = source.name
        return await asyncio.to_thread(service.import_uploaded_archive, source, name)
