import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Optional

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from bot.services.backup_archive import (
    BACKUP_APP_ID,
    BACKUP_FILENAME_PREFIX,
    BACKUP_FORMAT_VERSION,
    BACKUP_MANIFEST_NAME,
    attach_archive_integrity,
    backup_filename_timestamp,
    build_file_records,
    write_manifest,
    write_zip_from_directory,
)
from bot.services.backup_worker import (
    DEFAULT_COMPOSE_EXCLUDED_DIRS,
)
from config.settings import Settings
from db.migrator import MIGRATIONS, run_database_migrations
from db.models import Base

logger = logging.getLogger(__name__)

BACKUP_UPLOAD_MAX_BYTES = 2 * 1024 * 1024 * 1024
BACKUP_MAX_MEMBERS = 20_000
BACKUP_MAX_MEMBER_BYTES = 4 * 1024 * 1024 * 1024
BACKUP_MAX_UNCOMPRESSED_BYTES = 16 * 1024 * 1024 * 1024
BACKUP_MAX_COMPOSE_BYTES = 1024 * 1024 * 1024
BACKUP_MAX_COMPOSE_MEMBER_BYTES = 256 * 1024 * 1024
BACKUP_MAX_COMPRESSION_RATIO = 200
BACKUP_ZIP_BOMB_MIN_BYTES = 100 * 1024 * 1024
COMPOSE_PRE_RESTORE_PREFIX = "minishop-pre-restore-"
SAFE_ARCHIVE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@+-]{0,220}\.zip$")
DB_RESTORE_MIGRATION_ADVISORY_LOCK_ID = 817512404897421337


def _applied_migration_ids(connection: Connection) -> set[str]:
    inspector = inspect(connection)
    if "schema_migrations" not in inspector.get_table_names():
        return set()
    return {str(row[0]) for row in connection.execute(text("SELECT id FROM schema_migrations"))}


def _create_missing_tables_and_migrate(connection: Connection) -> list[str]:
    before = _applied_migration_ids(connection)
    Base.metadata.create_all(connection)
    run_database_migrations(connection)
    after = _applied_migration_ids(connection)
    newly_applied = after - before
    return [migration.id for migration in MIGRATIONS if migration.id in newly_applied]


class BackupArchiveError(ValueError):
    """The selected archive cannot be used for restore."""


class BackupRestoreError(RuntimeError):
    """Restore command failed after archive validation."""


@dataclass
class BackupArchiveInfo:
    name: str
    path: Path
    size_bytes: int
    modified_at: datetime
    created_at: Optional[str] = None
    created_at_local: Optional[str] = None
    has_database: bool = False
    has_compose: bool = False
    database_name: Optional[str] = None
    compose_files_count: int = 0
    warnings: list[str] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at.isoformat(),
            "created_at": self.created_at,
            "created_at_local": self.created_at_local,
            "has_database": self.has_database,
            "has_compose": self.has_compose,
            "database_name": self.database_name,
            "compose_files_count": self.compose_files_count,
            "warnings": self.warnings,
            "manifest": self.manifest,
        }


@dataclass
class BackupRestoreResult:
    archive_name: str
    started_at: datetime
    completed_at: datetime
    database_restored: bool = False
    compose_files_restored: int = 0
    compose_target_dir: Optional[str] = None
    compose_pre_restore_archive: Optional[str] = None
    database_migrations_applied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "archive_name": self.archive_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "database_restored": self.database_restored,
            "compose_files_restored": self.compose_files_restored,
            "compose_target_dir": self.compose_target_dir,
            "compose_pre_restore_archive": self.compose_pre_restore_archive,
            "database_migrations_applied": self.database_migrations_applied,
            "warnings": self.warnings,
        }


class BackupRestoreService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def backup_dir(self) -> Path:
        path = Path(self.settings.BACKUP_DIR).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def list_archives(self) -> list[BackupArchiveInfo]:
        backup_dir = self.backup_dir()
        archives = []
        for path in backup_dir.glob("*.zip"):
            if not path.is_file():
                continue
            try:
                archives.append(self.inspect_archive(path))
            except BackupArchiveError as exc:
                logger.warning("Skipping invalid backup archive %s: %s", path, exc)
        return sorted(archives, key=lambda item: item.modified_at, reverse=True)

    def archive_path_for_name(self, archive_name: str) -> Path:
        raw_name = str(archive_name or "").strip()
        safe_name = Path(raw_name).name
        if not raw_name or safe_name != raw_name or not SAFE_ARCHIVE_NAME_RE.fullmatch(safe_name):
            raise BackupArchiveError("Invalid archive name")

        backup_dir = self.backup_dir().resolve()
        archive_path = (backup_dir / safe_name).resolve()
        try:
            archive_path.relative_to(backup_dir)
        except ValueError as exc:
            raise BackupArchiveError("Archive path escapes backup directory") from exc
        if not archive_path.is_file():
            raise BackupArchiveError("Archive does not exist")
        return archive_path

    def inspect_archive(self, archive_path: Path) -> BackupArchiveInfo:
        if not zipfile.is_zipfile(archive_path):
            raise BackupArchiveError("Archive is not a valid ZIP file")

        stat = archive_path.stat()
        warnings: list[str] = []
        with zipfile.ZipFile(archive_path) as archive:
            self._validate_zip_members(archive.infolist())
            manifest = self._read_manifest(archive)
            has_database = self._find_database_dump_member(archive) is not None
            compose_members = self._compose_file_members(archive)

        manifest_warnings = manifest.get("warnings")
        if isinstance(manifest_warnings, list):
            warnings.extend(str(item) for item in manifest_warnings if item)

        postgres_raw = manifest.get("postgres")
        postgres: dict[str, Any] = postgres_raw if isinstance(postgres_raw, dict) else {}
        compose_raw = manifest.get("compose")
        compose: dict[str, Any] = compose_raw if isinstance(compose_raw, dict) else {}
        return BackupArchiveInfo(
            name=archive_path.name,
            path=archive_path,
            size_bytes=int(stat.st_size),
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            created_at=str(manifest.get("created_at") or "") or None,
            created_at_local=str(manifest.get("created_at_local") or "") or None,
            has_database=has_database,
            has_compose=bool(compose_members),
            database_name=str(postgres.get("database") or "") or None,
            compose_files_count=int(compose.get("files_count") or len(compose_members)),
            warnings=warnings,
            manifest=manifest,
        )

    def import_uploaded_archive(
        self,
        temp_path: Path,
        original_filename: str = "",
    ) -> BackupArchiveInfo:
        self._validate_archive_for_restore(temp_path)
        digest = self._file_digest(temp_path)
        stamp = backup_filename_timestamp()
        archive_name = f"{BACKUP_FILENAME_PREFIX}uploaded-{stamp}-{digest}.zip"
        target_path = self._unique_archive_path(archive_name)
        temp_path.replace(target_path)
        return self.inspect_archive(target_path)

    async def restore_archive(
        self,
        archive_name: str,
        *,
        restore_database: bool,
        restore_compose: bool,
    ) -> BackupRestoreResult:
        return await asyncio.to_thread(
            self.restore_archive_sync,
            archive_name,
            restore_database=restore_database,
            restore_compose=restore_compose,
        )

    def restore_archive_sync(
        self,
        archive_name: str,
        *,
        restore_database: bool,
        restore_compose: bool,
    ) -> BackupRestoreResult:
        if not restore_database and not restore_compose:
            raise BackupArchiveError("Select at least one restore target")

        archive_path = self.archive_path_for_name(archive_name)
        self._validate_archive_for_restore(archive_path)
        started_at = datetime.now(timezone.utc)
        warnings: list[str] = []

        with tempfile.TemporaryDirectory(
            prefix=f"restore-{archive_path.stem}-",
            dir=self.backup_dir(),
        ) as tmp:
            temp_dir = Path(tmp)
            with zipfile.ZipFile(archive_path) as archive:
                self._validate_zip_members(archive.infolist())
                db_member = self._find_database_dump_member(archive) if restore_database else None
                compose_members = self._compose_file_members(archive) if restore_compose else []

                if restore_database and db_member is None:
                    raise BackupArchiveError("Archive does not contain a database dump")
                if restore_compose and not compose_members:
                    raise BackupArchiveError("Archive does not contain compose files")

                compose_target_dir: Optional[Path] = None
                compose_pre_restore_archive: Optional[Path] = None
                if restore_compose:
                    compose_target_dir = self._compose_restore_target_dir()
                    self._assert_compose_target_writable(compose_target_dir)
                    compose_pre_restore_archive = self._snapshot_current_compose(compose_target_dir)

                database_restored = False
                database_migrations_applied: list[str] = []
                if db_member is not None:
                    dump_path = self._extract_database_dump(archive, db_member, temp_dir)
                    self._run_pg_restore(dump_path)
                    database_migrations_applied = self._run_post_restore_migrations()
                    database_restored = True

                compose_files_restored = 0
                if compose_target_dir is not None:
                    compose_files_restored = self._restore_compose_members(
                        archive,
                        compose_members,
                        compose_target_dir,
                    )

        return BackupRestoreResult(
            archive_name=archive_path.name,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            database_restored=database_restored,
            compose_files_restored=compose_files_restored,
            compose_target_dir=str(compose_target_dir) if compose_target_dir else None,
            compose_pre_restore_archive=str(compose_pre_restore_archive)
            if compose_pre_restore_archive
            else None,
            database_migrations_applied=database_migrations_applied,
            warnings=warnings,
        )

    def _run_post_restore_migrations(self) -> list[str]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            run_migrations = lambda: asyncio.run(self._run_post_restore_migrations_async())
        else:
            run_migrations = self._run_post_restore_migrations_in_thread

        try:
            return run_migrations()
        except BackupRestoreError:
            raise
        except Exception as exc:
            raise BackupRestoreError(
                f"Database restore completed, but post-restore migrations failed: {str(exc)[:500]}"
            ) from exc

    def _run_post_restore_migrations_in_thread(self) -> list[str]:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="backup-restore-migrate") as pool:
            return pool.submit(
                lambda: asyncio.run(self._run_post_restore_migrations_async())
            ).result()

    async def _run_post_restore_migrations_async(self) -> list[str]:
        engine = create_async_engine(
            self.settings.DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
            pool_size=1,
            max_overflow=0,
        )
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(f"SELECT pg_advisory_xact_lock({DB_RESTORE_MIGRATION_ADVISORY_LOCK_ID})")
                )
                return await connection.run_sync(_create_missing_tables_and_migrate)
        finally:
            await engine.dispose()

    def _run_pg_restore(self, dump_path: Path) -> None:
        pg_restore_path = str(getattr(self.settings, "BACKUP_PG_RESTORE_PATH", "pg_restore") or "")
        pg_restore_path = pg_restore_path or "pg_restore"
        if shutil.which(pg_restore_path) is None and Path(pg_restore_path).name == pg_restore_path:
            raise BackupRestoreError(
                "pg_restore executable was not found. Rebuild the backend image with "
                "PostgreSQL client tools."
            )

        env = os.environ.copy()
        env["PGPASSWORD"] = self.settings.POSTGRES_PASSWORD
        command = [
            pg_restore_path,
            "-h",
            self.settings.POSTGRES_HOST,
            "-p",
            str(self.settings.POSTGRES_PORT),
            "-U",
            self.settings.POSTGRES_USER,
            "-d",
            self.settings.POSTGRES_DB,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            str(dump_path),
        ]
        timeout = max(
            30,
            int(
                getattr(
                    self.settings,
                    "BACKUP_PG_RESTORE_TIMEOUT_SECONDS",
                    self.settings.BACKUP_PG_DUMP_TIMEOUT_SECONDS,
                )
                or 1800
            ),
        )
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            env=env,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise BackupRestoreError(
                f"pg_restore failed with exit code {result.returncode}: {stderr[:500]}"
            )

    def _compose_restore_target_dir(self) -> Path:
        target_raw = (
            getattr(self.settings, "BACKUP_COMPOSE_RESTORE_DIR", None)
            or self.settings.BACKUP_COMPOSE_SOURCE_DIR
            or ""
        )
        if not str(target_raw).strip():
            raise BackupArchiveError("Compose restore directory is not configured")
        return Path(str(target_raw)).expanduser()

    def _assert_compose_target_writable(self, target_dir: Path) -> None:
        if not target_dir.exists() or not target_dir.is_dir():
            raise BackupArchiveError(
                f"Compose restore directory is unavailable: {target_dir}. "
                "Mount the compose folder into the backend container."
            )
        probe = target_dir / f".restore-write-test-{os.getpid()}"
        try:
            probe.write_text("", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise BackupArchiveError(
                f"Compose restore directory is not writable: {target_dir}"
            ) from exc

    def _snapshot_current_compose(self, target_dir: Path) -> Optional[Path]:
        stamp = backup_filename_timestamp()
        archive_path = self._unique_archive_path(f"{COMPOSE_PRE_RESTORE_PREFIX}{stamp}.zip")
        excluded_dirs = self._compose_excluded_dirs()
        files_count = 0
        with tempfile.TemporaryDirectory(
            prefix=f"{archive_path.stem}-",
            dir=self.backup_dir(),
        ) as tmp:
            staging_dir = Path(tmp)
            compose_dir = staging_dir / "compose"
            for path in sorted(target_dir.rglob("*")):
                relative = path.relative_to(target_dir)
                if any(part in excluded_dirs for part in relative.parts):
                    continue
                if path.is_dir() or path.is_symlink():
                    continue
                destination = compose_dir / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
                files_count += 1
            if files_count <= 0:
                return None

            completed_at = datetime.now(timezone.utc)
            manifest = {
                "app": BACKUP_APP_ID,
                "format_version": BACKUP_FORMAT_VERSION,
                "type": "compose-pre-restore",
                "created_at": completed_at.isoformat(),
                "created_at_local": completed_at.astimezone().isoformat(),
                "postgres": {
                    "database": self.settings.POSTGRES_DB,
                    "included": False,
                },
                "compose": {
                    "source_dir": str(target_dir),
                    "included": True,
                    "files_count": files_count,
                },
                "warnings": [],
            }
            attach_archive_integrity(
                manifest,
                file_records=build_file_records(staging_dir),
            )
            write_manifest(staging_dir, manifest)
            tmp_archive = archive_path.with_name(f"{archive_path.name}.tmp")
            try:
                write_zip_from_directory(staging_dir, tmp_archive)
                tmp_archive.replace(archive_path)
            finally:
                if tmp_archive.exists():
                    try:
                        tmp_archive.unlink()
                    except OSError:
                        logger.warning("Failed to remove temporary snapshot %s", tmp_archive)
        return archive_path

    def _restore_compose_members(
        self,
        archive: zipfile.ZipFile,
        members: list[zipfile.ZipInfo],
        target_dir: Path,
    ) -> int:
        target_root = target_dir.resolve()
        restored = 0
        for member in members:
            relative = PurePosixPath(member.filename).relative_to("compose")
            destination = target_root.joinpath(*relative.parts).resolve()
            try:
                destination.relative_to(target_root)
            except ValueError as exc:
                raise BackupArchiveError(
                    f"Unsafe compose archive member: {member.filename}"
                ) from exc
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp_destination = destination.with_name(
                f".{destination.name}.restore-{os.getpid()}.tmp"
            )
            try:
                with archive.open(member) as source, temp_destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
                temp_destination.replace(destination)
            finally:
                if temp_destination.exists():
                    try:
                        temp_destination.unlink()
                    except OSError:
                        logger.warning(
                            "Failed to remove temporary restore file %s",
                            temp_destination,
                        )
            restored += 1
        return restored

    def _extract_database_dump(
        self,
        archive: zipfile.ZipFile,
        member: zipfile.ZipInfo,
        temp_dir: Path,
    ) -> Path:
        dump_dir = temp_dir / "database"
        dump_dir.mkdir(parents=True, exist_ok=True)
        dump_path = dump_dir / Path(member.filename).name
        with archive.open(member) as source, dump_path.open("wb") as target:
            shutil.copyfileobj(source, target)
        return dump_path

    def _find_database_dump_member(self, archive: zipfile.ZipFile) -> Optional[zipfile.ZipInfo]:
        candidates = [
            item
            for item in archive.infolist()
            if not item.is_dir()
            and item.filename.startswith("database/")
            and PurePosixPath(item.filename).suffix.lower() in {".dump", ".backup"}
        ]
        return sorted(candidates, key=lambda item: item.filename)[0] if candidates else None

    def _compose_file_members(self, archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
        members = [
            item
            for item in archive.infolist()
            if not item.is_dir() and item.filename.startswith("compose/")
        ]
        self._validate_compose_members(members)
        return members

    def _validate_zip_members(self, members: list[zipfile.ZipInfo]) -> None:
        if len(members) > BACKUP_MAX_MEMBERS:
            raise BackupArchiveError("Archive contains too many files")

        seen: set[str] = set()
        total_size = 0
        for member in members:
            filename = member.filename
            if "\\" in filename or "\x00" in filename:
                raise BackupArchiveError(f"Unsafe archive member path: {filename}")
            path = PurePosixPath(member.filename)
            if (
                not path.parts
                or path.is_absolute()
                or ".." in path.parts
                or any(part in {"", "."} for part in path.parts)
            ):
                raise BackupArchiveError(f"Unsafe archive member path: {member.filename}")
            if member.is_dir():
                continue
            if filename in seen:
                raise BackupArchiveError(f"Duplicate archive member path: {filename}")
            seen.add(filename)
            if member.file_size > BACKUP_MAX_MEMBER_BYTES:
                raise BackupArchiveError(f"Archive member is too large: {filename}")
            total_size += int(member.file_size)
            if total_size > BACKUP_MAX_UNCOMPRESSED_BYTES:
                raise BackupArchiveError("Archive uncompressed size is too large")
            compressed = max(1, int(member.compress_size or 1))
            ratio = int(member.file_size) / compressed
            if (
                member.file_size >= BACKUP_ZIP_BOMB_MIN_BYTES
                and ratio > BACKUP_MAX_COMPRESSION_RATIO
            ):
                raise BackupArchiveError(
                    f"Archive member compression ratio is too high: {filename}"
                )

    def _validate_compose_members(self, members: list[zipfile.ZipInfo]) -> None:
        total_size = 0
        for member in members:
            if member.file_size > BACKUP_MAX_COMPOSE_MEMBER_BYTES:
                raise BackupArchiveError(f"Compose archive member is too large: {member.filename}")
            total_size += int(member.file_size)
            if total_size > BACKUP_MAX_COMPOSE_BYTES:
                raise BackupArchiveError("Compose archive contents are too large")

    def _read_manifest(self, archive: zipfile.ZipFile) -> dict[str, Any]:
        if BACKUP_MANIFEST_NAME not in archive.namelist():
            raise BackupArchiveError("Archive does not contain manifest.json")
        try:
            manifest = json.loads(archive.read(BACKUP_MANIFEST_NAME).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupArchiveError("manifest.json is not valid JSON") from exc
        if not isinstance(manifest, dict):
            raise BackupArchiveError("manifest.json must contain an object")
        if manifest.get("app") != BACKUP_APP_ID:
            raise BackupArchiveError("Archive manifest belongs to another application")
        try:
            format_version = int(manifest.get("format_version") or 0)
        except (TypeError, ValueError) as exc:
            raise BackupArchiveError("Archive manifest format is not supported") from exc
        if format_version != BACKUP_FORMAT_VERSION:
            raise BackupArchiveError("Archive manifest format is not supported")
        return manifest

    def _validate_archive_for_restore(self, archive_path: Path) -> None:
        if not zipfile.is_zipfile(archive_path):
            raise BackupArchiveError("Archive is not a valid ZIP file")
        with zipfile.ZipFile(archive_path) as archive:
            self._validate_zip_members(archive.infolist())
            manifest = self._read_manifest(archive)
            self._validate_archive_integrity(archive, manifest)

    def _validate_archive_integrity(
        self,
        archive: zipfile.ZipFile,
        manifest: dict[str, Any],
    ) -> None:
        archive_manifest_raw = manifest.get("archive")
        archive_manifest: dict[str, Any] = (
            archive_manifest_raw if isinstance(archive_manifest_raw, dict) else {}
        )
        file_records = archive_manifest.get("files")
        if not isinstance(file_records, list):
            raise BackupArchiveError("Archive manifest does not contain file checksums")

        expected: dict[str, dict[str, Any]] = {}
        for record in file_records:
            if not isinstance(record, dict):
                raise BackupArchiveError("Archive manifest contains invalid file record")
            filename = str(record.get("path") or "")
            if not filename:
                raise BackupArchiveError("Archive manifest contains empty file path")
            if filename in expected:
                raise BackupArchiveError(
                    f"Archive manifest contains duplicate file path: {filename}"
                )
            expected[filename] = record

        actual = {
            item.filename
            for item in archive.infolist()
            if not item.is_dir() and item.filename != BACKUP_MANIFEST_NAME
        }
        if actual != set(expected):
            raise BackupArchiveError("Archive contents do not match manifest")

        for info in archive.infolist():
            if info.is_dir() or info.filename == BACKUP_MANIFEST_NAME:
                continue
            record = expected[info.filename]
            try:
                expected_size = int(record.get("size_bytes") or -1)
            except (TypeError, ValueError) as exc:
                raise BackupArchiveError(
                    f"Archive manifest size is invalid: {info.filename}"
                ) from exc
            expected_hash = str(record.get("sha256") or "")
            if expected_size != int(info.file_size):
                raise BackupArchiveError(
                    f"Archive member size does not match manifest: {info.filename}"
                )
            if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
                raise BackupArchiveError(f"Archive manifest checksum is invalid: {info.filename}")
            digest = hashlib.sha256()
            with archive.open(info) as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            if not hmac.compare_digest(digest.hexdigest(), expected_hash):
                raise BackupArchiveError(
                    f"Archive member checksum does not match manifest: {info.filename}"
                )

    def _compose_excluded_dirs(self) -> set[str]:
        raw_excludes = self.settings.BACKUP_COMPOSE_EXCLUDE_DIRS
        configured = self._split_csv(str(raw_excludes) if raw_excludes is not None else None)
        defaults = {str(item) for item in DEFAULT_COMPOSE_EXCLUDED_DIRS}
        return defaults | set(configured)

    @staticmethod
    def _split_csv(value: Optional[str]) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _file_digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()[:16]

    @staticmethod
    def _safe_original_stem(filename: str) -> str:
        stem = Path(str(filename or "backup")).stem
        safe = re.sub(r"[^A-Za-z0-9_.+-]+", "-", stem).strip(".-")
        return (safe or "backup")[:72]

    def _unique_archive_path(self, archive_name: str) -> Path:
        backup_dir = self.backup_dir()
        stem = Path(archive_name).stem
        suffix = Path(archive_name).suffix
        candidate = backup_dir / archive_name
        counter = 2
        while candidate.exists():
            candidate = backup_dir / f"{stem}-{counter}{suffix}"
            counter += 1
        return candidate
