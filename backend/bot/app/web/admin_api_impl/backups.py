import asyncio
import logging
import secrets
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any, cast

from aiohttp import web

from bot.app.web.context import (
    get_optional_bot,
    get_session_factory,
    get_settings,
)
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    BINARY_RESPONSE_SCHEMA,
    RouteContract,
    ok_envelope_for,
    register_contract,
)
from bot.infra.redis import redis_lock
from bot.plugins.package_backup import prepare_package_restore
from bot.services.backup_parts import BackupPartsError
from bot.services.backup_restore_job import (
    ACTIVE_STATES,
    public_job,
    queue_job,
    read_job,
    valid_token,
)
from bot.services.backup_restore_service import (
    BackupArchiveError,
    BackupArchiveInfo,
    BackupRestoreError,
    BackupRestoreResult,
    BackupRestoreService,
)
from bot.services.backup_upload import read_uploaded_backup
from bot.services.backup_worker import BackupResult, BackupWorker
from bot.services.panel_identity_match import panel_origin_url
from config.settings import Settings

from .auth import (
    _require_admin_user_id,
)
from .common import (
    _error,
    _ok,
)
from .response_schemas import (
    AdminBackupArchiveOut,
    AdminBackupArchiveSummaryOut,
    AdminBackupCreateOut,
    AdminBackupCreateResultOut,
    AdminBackupDetailOut,
    AdminBackupRestoreOut,
    AdminBackupRestoreResultOut,
    AdminBackupRestoreStatusOut,
    AdminBackupsListOut,
    AdminBackupUploadOut,
)
from .schemas import AdminBackupRestoreBody

logger = logging.getLogger(__name__)

_BACKUP_UPLOAD_BODY_SCHEMA = {
    "type": "object",
    "required": ["file"],
    "properties": {
        "file": {
            "oneOf": [
                BINARY_RESPONSE_SCHEMA,
                {"type": "array", "items": BINARY_RESPONSE_SCHEMA},
            ],
            "description": "One ZIP, or a parts manifest and all parts in repeated file fields.",
        }
    },
}
register_contract(
    "admin_backups_list_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminBackupsListOut),
        models=(AdminBackupsListOut,),
    ),
)
register_contract(
    "admin_backup_detail_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminBackupDetailOut),
        models=(AdminBackupDetailOut,),
    ),
)
register_contract(
    "admin_backups_create_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminBackupCreateOut),
        models=(AdminBackupCreateOut,),
    ),
)
register_contract(
    "admin_backups_upload_route",
    RouteContract(
        request_content={"multipart/form-data": _BACKUP_UPLOAD_BODY_SCHEMA},
        response_schema=ok_envelope_for(AdminBackupUploadOut),
        models=(AdminBackupUploadOut,),
    ),
)
register_contract(
    "admin_backups_restore_route",
    RouteContract(
        request_model=AdminBackupRestoreBody,
        response_schema=ok_envelope_for(AdminBackupRestoreOut),
        models=(AdminBackupRestoreBody, AdminBackupRestoreOut),
    ),
)
register_contract(
    "admin_backup_download_route",
    RouteContract(response_schema=BINARY_RESPONSE_SCHEMA, response_content_type="application/zip"),
)
register_contract(
    "backup_restore_status_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminBackupRestoreStatusOut),
        models=(AdminBackupRestoreStatusOut,),
        security=[],
    ),
)


def _backup_archive_payload(archive: BackupArchiveInfo, settings: Settings) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        AdminBackupArchiveOut.from_archive(
            archive, panel_origin_url(settings.PANEL_API_URL)
        ).model_dump(mode="json"),
    )


def _backup_create_result_payload(result: BackupResult) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        AdminBackupCreateResultOut.from_result(result).model_dump(mode="json"),
    )


def _backup_restore_result_payload(result: BackupRestoreResult) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        AdminBackupRestoreResultOut.from_result(result).model_dump(mode="json"),
    )


async def _read_uploaded_backup_file(request: web.Request) -> BackupArchiveInfo:
    return await read_uploaded_backup(request, get_settings(request))


async def admin_backups_list_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = get_settings(request)
    try:
        service = BackupRestoreService(settings)
        archives = await asyncio.to_thread(service.list_archive_summaries)
    except OSError as exc:
        logger.exception("Failed to list backup archives")
        return _error(500, "backup_list_failed", str(exc))
    return _ok(
        {
            "backup_dir": str(service.backup_dir()),
            "archives": [
                AdminBackupArchiveSummaryOut.from_summary(archive).model_dump(mode="json")
                for archive in archives
            ],
        }
    )


async def admin_backup_detail_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings = get_settings(request)
    service = BackupRestoreService(settings)
    try:
        path = service.archive_path_for_name(request.match_info["archive_name"])
        archive = await asyncio.to_thread(service.inspect_archive, path)
    except BackupArchiveError as exc:
        return _error(400, "invalid_backup_archive", str(exc))
    except OSError as exc:
        logger.exception("Failed to inspect backup archive")
        return _error(500, "backup_list_failed", str(exc))
    return _ok({"archive": _backup_archive_payload(archive, settings)})


async def admin_backup_download_route(request: web.Request) -> web.StreamResponse:
    _require_admin_user_id(request)
    service = BackupRestoreService(get_settings(request))
    try:
        path = service.archive_path_for_name(request.match_info["archive_name"])
    except BackupArchiveError as exc:
        return _error(400, "invalid_backup_archive", str(exc))
    return web.FileResponse(
        path,
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )


async def backup_restore_status_route(request: web.Request) -> web.Response:
    settings = get_settings(request)
    job = read_job(BackupRestoreService(settings).backup_dir())
    token = request.headers.get("X-Backup-Restore-Token", "")
    if not job or job.get("id") != request.match_info["job_id"] or not valid_token(job, token):
        return _error(404, "backup_restore_job_not_found")
    return _ok({"job": public_job(job)})


async def admin_backups_upload_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings = get_settings(request)
    content_type = (request.headers.get("Content-Type") or "").lower()
    if not content_type.startswith("multipart/form-data"):
        return _error(400, "invalid_backup_archive", "multipart file upload is required")
    try:
        archive = await _read_uploaded_backup_file(request)
    except BackupPartsError as exc:
        return _error(400, "invalid_backup_parts", str(exc))
    except (BackupArchiveError, ValueError) as exc:
        return _error(400, "invalid_backup_archive", str(exc))
    except OSError as exc:
        logger.exception("Failed to save uploaded backup archive")
        return _error(500, "backup_upload_failed", str(exc))
    return _ok({"archive": _backup_archive_payload(archive, settings)})


async def admin_backups_create_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = get_settings(request)
    job = read_job(BackupRestoreService(settings).backup_dir())
    if job and job.get("status") in ACTIVE_STATES:
        return _error(409, "backup_restore_busy")
    bot = get_optional_bot(request)
    session_factory = get_session_factory(request)
    worker = BackupWorker(settings, bot, session_factory=session_factory)

    ttl_seconds = max(
        60,
        int(
            max(
                settings.BACKUP_LOCK_TTL_SECONDS or 7200,
                settings.BACKUP_PG_DUMP_TIMEOUT_SECONDS or 1800,
            )
        ),
    )
    try:
        async with redis_lock(settings, "backup-worker", ttl_seconds=ttl_seconds) as acquired:
            if not acquired:
                return _error(409, "backup_create_busy", "Backup or restore is already running")
            await worker.refresh_settings()
            result = await worker.create_and_send_backup(
                backup_type="manual", tolerate_delivery_failure=True
            )
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
            "result": _backup_create_result_payload(result),
            "archive": _backup_archive_payload(archive, settings),
        }
    )


async def admin_backups_restore_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = get_settings(request)
    body = await parse_body_or_400(request, AdminBackupRestoreBody)

    archive_name = str(body.archive_name or "").strip()
    restore_database = bool(body.restore_database)
    restore_compose = bool(body.restore_compose)
    reset_panel_origin = body.reset_panel_origin is True
    confirm = bool(body.confirm)
    confirmation = str(body.confirmation or "").strip()
    if not confirm or not secrets.compare_digest(confirmation, archive_name):
        return _error(400, "restore_confirmation_required")

    service = BackupRestoreService(settings)
    if restore_database:
        if restore_compose:
            return _error(400, "backup_restore_targets_separately")
        if reset_panel_origin and not panel_origin_url(settings.PANEL_API_URL):
            return _error(400, "backup_panel_url_required")
        try:
            archive_path = service.archive_path_for_name(archive_name)
            await asyncio.to_thread(service._validate_archive_for_restore, archive_path)
            archive = await asyncio.to_thread(service.inspect_archive, archive_path)
            if not archive.has_database:
                return _error(400, "backup_database_missing")
            with (
                tempfile.TemporaryDirectory(prefix="backup-plugin-preflight-") as staging,
                zipfile.ZipFile(archive_path) as zip_archive,
            ):
                await asyncio.to_thread(prepare_package_restore, zip_archive, Path(staging))
            job, token = queue_job(
                service.backup_dir(), archive_name, reset_panel_origin=reset_panel_origin
            )
        except (BackupArchiveError, OSError, ValueError) as exc:
            return _error(400, "invalid_backup_archive", str(exc))
        except RuntimeError as exc:
            return _error(409, "backup_restore_busy", str(exc))
        return _ok({"job": public_job(job), "status_token": token})

    if reset_panel_origin:
        return _error(400, "backup_database_required_for_panel_reset")
    job = read_job(service.backup_dir())
    if job and job.get("status") in ACTIVE_STATES:
        return _error(409, "backup_restore_busy")
    ttl_seconds = max(
        60,
        int(
            max(
                settings.BACKUP_LOCK_TTL_SECONDS or 7200,
                settings.BACKUP_PG_RESTORE_TIMEOUT_SECONDS or 1800,
            )
        ),
    )
    try:
        async with redis_lock(settings, "backup-worker", ttl_seconds=ttl_seconds) as acquired:
            if not acquired:
                return _error(409, "backup_restore_busy", "Backup or restore is already running")
            result = await service.restore_archive(
                archive_name,
                restore_database=False,
                restore_compose=restore_compose,
            )
    except BackupArchiveError as exc:
        return _error(400, "invalid_backup_archive", str(exc))
    except BackupRestoreError as exc:
        logger.exception("Backup restore failed")
        return _error(500, "backup_restore_failed", str(exc))
    except (OSError, RuntimeError, subprocess.SubprocessError, TimeoutError) as exc:
        logger.exception("Backup restore failed")
        return _error(500, "backup_restore_failed", str(exc))
    return _ok({"result": _backup_restore_result_payload(result)})
