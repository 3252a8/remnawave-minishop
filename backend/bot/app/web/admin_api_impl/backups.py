# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405

import secrets
import subprocess

from bot.infra.redis import redis_lock
from bot.services.backup_restore_service import (
    BACKUP_UPLOAD_MAX_BYTES,
    BackupArchiveError,
    BackupArchiveInfo,
    BackupRestoreError,
    BackupRestoreService,
)
from bot.services.backup_worker import BackupWorker


def _backup_archive_payload(archive) -> Dict[str, Any]:
    return archive.to_payload()


async def _read_uploaded_backup_file(request: web.Request) -> BackupArchiveInfo:
    settings: Settings = request.app["settings"]
    service = BackupRestoreService(settings)
    backup_dir = service.backup_dir()
    temp_path: Optional[Path] = None

    reader = await request.multipart()
    try:
        async for part in reader:
            if part.name != "file":
                continue

            original_filename = part.filename or "backup.zip"
            temp_path = backup_dir / f".upload-{secrets.token_urlsafe(12)}.zip.tmp"
            size = 0
            with temp_path.open("wb") as handle:
                while True:
                    chunk = await part.read_chunk(size=1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > BACKUP_UPLOAD_MAX_BYTES:
                        raise BackupArchiveError("Backup archive is too large")
                    handle.write(chunk)
            if size <= 0:
                raise BackupArchiveError("Uploaded archive is empty")
            archive = service.import_uploaded_archive(temp_path, original_filename)
            temp_path = None
            return archive
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                logger.warning("Failed to remove temporary backup upload %s", temp_path)

    raise BackupArchiveError("file field is required")


async def admin_backups_list_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = request.app["settings"]
    try:
        service = BackupRestoreService(settings)
        archives = service.list_archives()
    except OSError as exc:
        logger.exception("Failed to list backup archives")
        return _error(500, "backup_list_failed", str(exc))
    return _ok(
        {
            "backup_dir": str(service.backup_dir()),
            "archives": [_backup_archive_payload(archive) for archive in archives],
        }
    )


async def admin_backups_upload_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    content_type = (request.headers.get("Content-Type") or "").lower()
    if not content_type.startswith("multipart/form-data"):
        return _error(400, "invalid_backup_archive", "multipart file upload is required")
    try:
        archive = await _read_uploaded_backup_file(request)
    except BackupArchiveError as exc:
        return _error(400, "invalid_backup_archive", str(exc))
    except OSError as exc:
        logger.exception("Failed to save uploaded backup archive")
        return _error(500, "backup_upload_failed", str(exc))
    return _ok({"archive": _backup_archive_payload(archive)})


async def admin_backups_create_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = request.app["settings"]
    bot = request.app["bot"]
    session_factory = request.app.get("async_session_factory")
    worker = BackupWorker(settings, bot, session_factory=session_factory)

    ttl_seconds = max(
        60,
        int(
            max(
                getattr(settings, "BACKUP_LOCK_TTL_SECONDS", 7200) or 7200,
                getattr(settings, "BACKUP_PG_DUMP_TIMEOUT_SECONDS", 1800) or 1800,
            )
        ),
    )
    try:
        async with redis_lock(settings, "backup-worker", ttl_seconds=ttl_seconds) as acquired:
            if not acquired:
                return _error(409, "backup_create_busy", "Backup or restore is already running")
            await worker.refresh_settings()
            result = await worker.create_and_send_backup(backup_type="manual")
            archive = BackupRestoreService(settings).inspect_archive(result.archive_path)
    except BackupArchiveError as exc:
        return _error(400, "invalid_backup_archive", str(exc))
    except (OSError, RuntimeError, subprocess.SubprocessError, TimeoutError) as exc:
        logger.exception("Manual backup creation failed")
        return _error(500, "backup_create_failed", str(exc))
    except Exception as exc:
        logger.exception("Manual backup creation failed")
        return _error(500, "backup_create_failed", str(exc))

    return _ok(
        {
            "result": result.to_payload(),
            "archive": _backup_archive_payload(archive),
        }
    )


async def admin_backups_restore_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = request.app["settings"]
    payload = await _read_json(request)

    archive_name = str(payload.get("archive_name") or "").strip()
    restore_database = bool(payload.get("restore_database"))
    restore_compose = bool(payload.get("restore_compose"))
    confirm = bool(payload.get("confirm"))
    if not confirm:
        return _error(400, "restore_confirmation_required")

    service = BackupRestoreService(settings)
    ttl_seconds = max(
        60,
        int(
            max(
                getattr(settings, "BACKUP_LOCK_TTL_SECONDS", 7200) or 7200,
                getattr(settings, "BACKUP_PG_RESTORE_TIMEOUT_SECONDS", 1800) or 1800,
            )
        ),
    )
    try:
        async with redis_lock(settings, "backup-worker", ttl_seconds=ttl_seconds) as acquired:
            if not acquired:
                return _error(409, "backup_restore_busy", "Backup or restore is already running")
            result = await service.restore_archive(
                archive_name,
                restore_database=restore_database,
                restore_compose=restore_compose,
            )
    except BackupArchiveError as exc:
        return _error(400, "invalid_backup_archive", str(exc))
    except BackupRestoreError as exc:
        logger.exception("Backup restore failed")
        return _error(500, "backup_restore_failed", str(exc))
    except (OSError, subprocess.SubprocessError, TimeoutError) as exc:
        logger.exception("Backup restore failed")
        return _error(500, "backup_restore_failed", str(exc))
    finally:
        try:
            from db import database_setup

            if restore_database and database_setup.async_engine is not None:
                await database_setup.async_engine.dispose()
        except Exception:
            logger.exception("Failed to dispose DB engine after backup restore")

    return _ok({"result": result.to_payload()})
