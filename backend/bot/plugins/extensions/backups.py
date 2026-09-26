"""Backup participants run in namespaced directories and preflight before any restore."""

from __future__ import annotations

import asyncio
import json
import shutil
import stat
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING
from zipfile import ZipFile

from pydantic import JsonValue

from .contracts import BackupContributor, BackupStorageProvider, ExtensionError, OperationContext
from .jobs import JSON_OBJECT, enqueue_internal, json_object
from .registry import get_registry, split_key

if TYPE_CHECKING:
    from bot.plugins.spec import PluginContext


def snapshot_extensions(staging: Path) -> dict[str, JsonValue]:
    owners: dict[str, JsonValue] = {}
    for owner, entry in get_registry().owners().items():
        records: dict[str, JsonValue] = {}
        for contributor in entry.contributions.backups:
            directory = staging / "extensions" / owner / contributor.id
            directory.mkdir(parents=True, exist_ok=True)
            metadata = contributor.collect(directory)
            json_object(metadata)
            for path in directory.rglob("*"):
                if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                    raise ExtensionError("unsafe_extension_backup_path", 400)
            records[contributor.id] = {"version": contributor.version, "metadata": metadata}
        owners[owner] = {"version": entry.version, "contributors": records}
    return owners


def prepare_extensions(
    archive: ZipFile, staging: Path
) -> list[tuple[BackupContributor, Path, dict[str, JsonValue]]]:
    manifest = json.loads(archive.read("manifest.json"))
    records = manifest.get("extensions", {})
    if not isinstance(records, dict):
        raise ExtensionError("invalid_extension_backup_manifest", 400)
    prepared = []
    for owner, record in sorted(records.items()):
        if not isinstance(record, dict):
            raise ExtensionError("invalid_extension_backup_manifest", 400)
        entry = get_registry().require(owner)
        if entry.version != record.get("version"):
            raise ExtensionError("extension_backup_version_mismatch")
        contributors = record.get("contributors", {})
        if not isinstance(contributors, dict):
            raise ExtensionError("invalid_extension_backup_manifest", 400)
        for contributor_id, data in sorted(contributors.items()):
            provider = next(
                (item for item in entry.contributions.backups if item.id == contributor_id), None
            )
            if (
                provider is None
                or not isinstance(data, dict)
                or provider.version != data.get("version")
            ):
                raise ExtensionError("extension_backup_contributor_unavailable")
            metadata = JSON_OBJECT.validate_python(data.get("metadata", {}))
            prefix = f"extensions/{owner}/{contributor_id}/"
            directory = staging / "extensions" / owner / contributor_id
            directory.mkdir(parents=True, exist_ok=True)
            for member in archive.infolist():
                if not member.filename.startswith(prefix):
                    continue
                relative = PurePosixPath(member.filename.removeprefix(prefix))
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or "\\" in member.filename
                    or "\\" in member.orig_filename
                    or any(":" in part or part.endswith((".", " ")) for part in relative.parts)
                    or stat.S_ISLNK(member.external_attr >> 16)
                ):
                    raise ExtensionError("unsafe_extension_backup_path", 400)
                target = directory.joinpath(*relative.parts)
                if not target.resolve().is_relative_to(directory.resolve()):
                    raise ExtensionError("unsafe_extension_backup_path", 400)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, target.open("wb") as destination:
                        shutil.copyfileobj(source, destination)
            provider.validate(directory, metadata)
            prepared.append((provider, directory, metadata))
    return prepared


def restore_extensions(
    prepared: list[tuple[BackupContributor, Path, dict[str, JsonValue]]],
) -> None:
    for provider, directory, metadata in prepared:
        provider.restore(directory, metadata)


async def queue_uploads(ctx: PluginContext, archive_path: Path) -> None:
    """Pin an archive copy per destination until upload succeeds; retention cannot race it."""
    if not any(entry.contributions.storage for entry in get_registry().owners().values()):
        return
    async with ctx.require_session_factory()() as session:
        for owner, entry in get_registry().owners().items():
            for provider in entry.contributions.storage:
                directory = archive_path.parent / ".extension-uploads" / owner / provider.id
                directory.mkdir(parents=True, exist_ok=True)
                target = directory / archive_path.name
                if not target.exists():
                    await asyncio.to_thread(shutil.copyfile, archive_path, target)
                await enqueue_internal(
                    session,
                    owner=owner,
                    kind="_backup_upload",
                    idempotency_key=f"{provider.id}:{archive_path.name}",
                    payload={"storage": provider.id, "name": archive_path.name},
                )
        await session.commit()


async def download_archive(ctx: PluginContext, *, storage: str, name: str) -> str:
    """Return a Core-validated imported archive name; do not restore automatically."""
    import tempfile

    from bot.services.backup_restore_service import BackupRestoreService

    owner, key = split_key(storage)
    entry = get_registry().require(owner)
    provider = next((item for item in entry.contributions.storage if item.id == key), None)
    if provider is None:
        raise ExtensionError("extension_storage_unavailable", 404)
    if not name or len(name) > 256:
        raise ExtensionError("invalid_extension_archive_name", 400)
    with tempfile.TemporaryDirectory(prefix="extension-download-") as directory:
        target = Path(directory) / "archive.zip"
        async with asyncio.timeout(600):
            await provider.download(name, target)
        service = BackupRestoreService(ctx.settings)
        imported = await asyncio.to_thread(
            service.import_uploaded_archive, target, original_filename="extension.zip"
        )
        return imported.name


def storage_provider(key: str) -> BackupStorageProvider:
    owner, name = split_key(key)
    entry = get_registry().require(owner)
    provider = next((item for item in entry.contributions.storage if item.id == name), None)
    if provider is None:
        raise ExtensionError("extension_storage_unavailable", 503)
    return provider


async def list_archives(storage: str) -> list[str]:
    async with asyncio.timeout(60):
        names = await storage_provider(storage).list_archives()
    if any(not isinstance(name, str) or not 1 <= len(name) <= 256 for name in names):
        raise ExtensionError("invalid_extension_archive_name", 502)
    return names


async def delete_archive(storage: str, name: str) -> None:
    if not 1 <= len(name) <= 256:
        raise ExtensionError("invalid_extension_archive_name", 400)
    async with asyncio.timeout(60):
        await storage_provider(storage).delete(name)


async def create_backup(ctx: PluginContext) -> str:
    """Create through Core; storage delivery is queued by BackupWorker."""
    from bot.services.backup_worker import BackupWorker

    result = await BackupWorker(
        ctx.settings, ctx.require_bot(), ctx.require_session_factory()
    ).create_backup(backup_type="extension")
    return result.archive_path.name


def upload_path(ctx: PluginContext, owner: str, payload: dict[str, JsonValue]) -> Path:
    from bot.services.backup_restore_service import BackupRestoreService

    storage, name = str(payload["storage"]), str(payload["name"])
    split_key(f"{owner}:{storage}")
    if Path(name).name != name or "/" in name or "\\" in name or ":" in name:
        raise ExtensionError("invalid_extension_archive_name", 400)
    root = BackupRestoreService(ctx.settings).backup_dir() / ".extension-uploads"
    return root / owner / storage / name


async def upload_archive(operation: OperationContext, payload: dict[str, JsonValue]) -> None:
    provider = storage_provider(f"{operation.owner}:{payload['storage']}")
    path = upload_path(operation.runtime, operation.owner, payload)
    if not path.is_file():
        raise ExtensionError("extension_archive_missing", 404)
    operation.assert_current()
    await provider.upload(path, path.name)


def initialize_backup_extensions(settings: object) -> None:
    """Offline restore registers pure declarations without starting application hooks."""
    from bot.plugins.loader import get_plugins
    from bot.plugins.spec import PluginContext
    from config.settings import Settings

    from .registry import ExtensionRegistry, set_registry

    if not isinstance(settings, Settings):
        raise TypeError("Settings required")
    registry = ExtensionRegistry()
    context = PluginContext(settings=settings)
    for plugin in get_plugins(settings):
        registry.register(plugin.name, plugin.version, plugin.extensions(context))
    set_registry(registry)


def restore_archive_extensions(archive_path: Path) -> None:
    import tempfile

    with (
        tempfile.TemporaryDirectory(prefix="extension-restore-") as staging,
        ZipFile(archive_path) as archive,
    ):
        restore_extensions(prepare_extensions(archive, Path(staging)))
