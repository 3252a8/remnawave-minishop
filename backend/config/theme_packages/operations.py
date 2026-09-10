"""Import sessions, atomic installation, update, rollback and portable export."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
import uuid
from pathlib import Path

from pydantic import ValidationError

from config.webapp_themes_models import WebappTheme

from .archive import (
    allowed_file,
    content_digest,
    deterministic_zip,
    extract_archive,
    inspect_collection,
)
from .css import fork_css
from .models import (
    BUILTINS,
    IMPORT_TTL,
    MAX_ARCHIVE,
    MAX_EXPANDED,
    Candidate,
    ExportRequest,
    ImportRecord,
    InstalledTheme,
    InstalledVersion,
    InstallRequest,
    MutationOut,
    PackageError,
    ThemeSource,
)
from .paths import atomic_model, confined, registry_lock
from .registry import (
    check_generation,
    collect_garbage,
    effective_theme,
    owner_overrides,
    read_registry,
    require_capacity,
    write_registry,
)
from .preview_storage import preview_file


def operation_dir(root: Path, operation_id: str) -> Path:
    if len(operation_id) != 32 or any(char not in "0123456789abcdef" for char in operation_id):
        raise PackageError("import_not_found", status=404)
    return confined(root, f"_imports/{operation_id}")


def candidate_folder(root: Path, operation_id: str, path: str) -> Path:
    extracted = operation_dir(root, operation_id) / "files"
    return extracted if path == "." else confined(extracted, path)


def create_import(root: Path, actor: int, source: ThemeSource) -> ImportRecord:
    collect_garbage(root)
    with registry_lock(root):
        require_capacity(root, MAX_EXPANDED + MAX_ARCHIVE)
        imports = confined(root, "_imports")
        imports.mkdir(exist_ok=True)
        now = time.time()
        active = 0
        for folder in imports.iterdir():
            if not folder.is_dir() or folder.is_symlink():
                continue
            if now - folder.stat().st_mtime > IMPORT_TTL:
                shutil.rmtree(confined(imports, folder.name))
            elif (folder / "record.json").exists():
                record = ImportRecord.model_validate_json((folder / "record.json").read_bytes())
                if record.state in {"downloading", "validating"} and now - record.created_at > 120:
                    record.state, record.error = "failed", "import_interrupted"
                    atomic_model(folder / "record.json", record)
                if record.state in {"downloading", "validating", "ready"}:
                    active += 1
        if active >= 4:
            raise PackageError("too_many_imports", status=429)
        require_capacity(root, (active + 1) * MAX_EXPANDED + MAX_ARCHIVE)
        record = ImportRecord(
            id=uuid.uuid4().hex,
            actor=actor,
            created_at=now,
            source=source,
            generation=read_registry(root).generation,
            state="downloading" if source.kind != "archive" else "validating",
        )
        directory = operation_dir(root, record.id)
        directory.mkdir(mode=0o700)
        atomic_model(directory / "record.json", record)
        return record


def get_import(root: Path, operation_id: str, actor: int) -> ImportRecord:
    folder = operation_dir(root, operation_id)
    try:
        record = ImportRecord.model_validate_json((folder / "record.json").read_bytes())
    except (OSError, ValidationError) as exc:
        raise PackageError("import_not_found", status=404) from exc
    if record.actor != actor:
        raise PackageError("import_not_found", status=404)
    if time.time() - record.created_at > IMPORT_TTL:
        raise PackageError("import_expired", status=410)
    receipts = read_registry(root).completed
    for receipt, keys in receipts.items():
        if receipt.startswith(operation_id + ":"):
            record.state, record.installed = "installed", keys
            return record
    if record.state in {"downloading", "validating"} and time.time() - record.created_at > 120:
        record.state, record.error = "failed", "import_interrupted"
    return record


def inspect_import(root: Path, record: ImportRecord, body: bytes) -> ImportRecord:
    folder = operation_dir(root, record.id)
    try:
        require_capacity(root, len(body))
        extract_archive(body, folder / "files")
        candidates = inspect_collection(folder / "files", record.source.subdir)
        for candidate in candidates:
            if candidate.key in BUILTINS:
                candidate.error, candidate.detail = "protected_theme", candidate.key
        record.candidates, record.state = candidates, "ready"
    except PackageError as exc:
        record.state, record.error, record.detail = "failed", exc.code, exc.detail
    except (OSError, ValueError) as exc:
        record.state, record.error, record.detail = "failed", "import_failed", str(exc)[:300]
    with registry_lock(root):
        current = get_import(root, record.id, record.actor)
        if current.state == "cancelled":
            if (folder / "files").exists():
                shutil.rmtree(confined(folder, "files"))
            return current
        if record.state == "failed" and (folder / "files").exists():
            shutil.rmtree(confined(folder, "files"))
        atomic_model(folder / "record.json", record)
    return record


def fail_import(root: Path, record: ImportRecord, error: PackageError) -> None:
    with registry_lock(root):
        current = get_import(root, record.id, record.actor)
        if current.state == "cancelled":
            return
        current.state, current.error, current.detail = "failed", error.code, error.detail
        atomic_model(operation_dir(root, record.id) / "record.json", current)


def cancel_import(root: Path, operation_id: str, actor: int) -> ImportRecord:
    with registry_lock(root):
        record = get_import(root, operation_id, actor)
        if record.state == "installed":
            raise PackageError("import_already_installed", status=409)
        previous_state = record.state
        record.state = "cancelled"
        atomic_model(operation_dir(root, operation_id) / "record.json", record)
        files = operation_dir(root, operation_id) / "files"
        if previous_state not in {"downloading", "validating"} and files.exists():
            shutil.rmtree(confined(operation_dir(root, operation_id), "files"))
        # A running extraction owns its directory until its final state check.
        return record


def install_import(
    root: Path, operation_id: str, actor: int, request: InstallRequest
) -> MutationOut:
    with registry_lock(root):
        record = get_import(root, operation_id, actor)
        state = read_registry(root)
        fingerprint = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        receipt = f"{operation_id}:{request.idempotency_key}:{fingerprint}"
        for saved, keys in state.completed.items():
            if saved.startswith(f"{operation_id}:{request.idempotency_key}:"):
                if saved != receipt:
                    raise PackageError("idempotency_conflict", status=409)
                return MutationOut(generation=state.generation, keys=keys)
        if record.state != "ready":
            raise PackageError("import_not_ready", status=409)
        check_generation(state, request.expected_generation)
        keys = [choice.key for choice in request.choices]
        if len(set(keys)) != len(keys):
            raise PackageError("duplicate_theme_key")
        choices: list[tuple[Candidate, InstalledTheme]] = []
        for choice in request.choices:
            candidate = next((item for item in record.candidates if item.key == choice.key), None)
            if choice.key in BUILTINS:
                raise PackageError("protected_theme", choice.key)
            if not candidate or candidate.error or not candidate.theme:
                raise PackageError("invalid_theme_selection", choice.key)
            folder = candidate_folder(root, operation_id, candidate.path)
            if content_digest(folder) != candidate.digest:
                raise PackageError("import_changed", status=409)
            previous = state.entries.get(choice.key)
            legacy = root / choice.key
            if previous and choice.action != "update":
                raise PackageError("theme_exists", choice.key, 409)
            if (
                not previous
                and legacy.exists()
                and choice.key not in state.removed
                and choice.action != "adopt"
            ):
                raise PackageError("theme_requires_adoption", choice.key, 409)
            entry = InstalledTheme(
                digest=candidate.digest,
                metadata=candidate.metadata,
                source=record.source,
                installed_at=time.time(),
                original=candidate.theme,
                # Package authors decide whether their theme also styles the admin panel.
                overrides={"default": False, "enabled": True},
            )
            if previous:
                if (
                    content_digest(confined(root, f"_packages/{previous.digest}"))
                    != previous.digest
                ):
                    raise PackageError("theme_modified_on_server", choice.key, 409)
                entry.overrides = previous.overrides
                entry.history = [
                    InstalledVersion.model_validate(
                        previous.model_dump(
                            exclude={"overrides", "history", "adopted_digest", "preview_override"}
                        )
                    ),
                    *previous.history,
                ][:5]
                if entry.digest == previous.digest:
                    entry.history = previous.history
                    entry.installed_at = previous.installed_at
                entry.adopted_digest = previous.adopted_digest
                entry.preview_override = previous.preview_override
                if (
                    entry.adopted_digest
                    and legacy.is_dir()
                    and content_digest(legacy) != entry.adopted_digest
                ):
                    raise PackageError("theme_modified_on_server", choice.key, 409)
                # Validate the merged result before committing any selected theme.
                effective_theme(choice.key, entry)
            elif legacy.exists() and choice.key not in state.removed:
                old = WebappTheme.model_validate_json((legacy / "theme.json").read_bytes())
                entry.overrides = InstalledTheme.model_validate(
                    {
                        **entry.model_dump(),
                        "overrides": owner_overrides(entry.original, old),
                    }
                ).overrides
                entry.adopted_digest = content_digest(legacy)
            choices.append((candidate, entry))
        require_capacity(root, sum(item.size for item, _entry in choices))
        for candidate, entry in choices:
            target = confined(root, f"_packages/{entry.digest}")
            if not target.exists():
                target.parent.mkdir(exist_ok=True)
                staging = confined(root, f"_packages/tmp-{uuid.uuid4().hex}")
                source = candidate_folder(root, operation_id, candidate.path)
                shutil.copytree(source, staging)
                if content_digest(staging) != entry.digest:
                    shutil.rmtree(staging)
                    raise PackageError("import_changed", status=409)
                staging.rename(target)
            elif content_digest(target) != entry.digest:
                raise PackageError("package_corrupted", candidate.key, 409)
            if old_entry := state.entries.get(candidate.key):
                retired = state.retired.setdefault(candidate.key, {})
                for version in [old_entry, *old_entry.history]:
                    retired[version.digest] = time.time() + 7 * 86400
            state.removed = [key for key in state.removed if key != candidate.key]
            state.entries[candidate.key] = entry
        state.completed[receipt] = keys
        write_registry(root, state)
        record.state, record.installed = "installed", keys
        atomic_model(operation_dir(root, operation_id) / "record.json", record)
        return MutationOut(generation=state.generation, keys=keys)


def remove_theme(root: Path, key: str, generation: int, active_key: str) -> MutationOut:
    with registry_lock(root):
        state = read_registry(root)
        check_generation(state, generation)
        if key in BUILTINS:
            raise PackageError("protected_theme", key)
        if key == active_key:
            raise PackageError("active_theme", key, 409)
        if key not in state.entries:
            raise PackageError("theme_not_managed", key, 409)
        entry = state.entries[key]
        if (
            entry.adopted_digest
            and (root / key).is_dir()
            and content_digest(root / key) != entry.adopted_digest
        ):
            raise PackageError("theme_modified_on_server", key, 409)
        state.retired[key] = {
            version.digest: time.time() + 7 * 86400 for version in [entry, *entry.history]
        }
        state.removed.append(key)
        state.preferences.pop(key, None)
        del state.entries[key]
        preview_file(root, key).unlink(missing_ok=True)
        write_registry(root, state)
        return MutationOut(generation=state.generation, keys=[key])


def rollback_theme(root: Path, key: str, generation: int) -> MutationOut:
    with registry_lock(root):
        state = read_registry(root)
        check_generation(state, generation)
        entry = state.entries.get(key)
        if not entry or not entry.history:
            raise PackageError("no_previous_version", key, 409)
        previous = entry.history[0]
        if content_digest(confined(root, f"_packages/{previous.digest}")) != previous.digest:
            raise PackageError("package_corrupted", key, 409)
        changed = InstalledTheme(
            **previous.model_dump(),
            overrides=entry.overrides,
            history=[
                InstalledVersion.model_validate(
                    entry.model_dump(
                        exclude={"overrides", "history", "adopted_digest", "preview_override"}
                    )
                ),
                *entry.history[1:],
            ][:5],
            adopted_digest=entry.adopted_digest,
            preview_override=entry.preview_override,
        )
        effective_theme(key, changed)
        state.entries[key] = changed
        write_registry(root, state)
        return MutationOut(generation=state.generation, keys=[key])


def export_themes(root: Path, request: ExportRequest) -> bytes:
    if len(set(request.keys)) != len(request.keys) or (request.new_key and len(request.keys) != 1):
        raise PackageError("invalid_export_selection")
    if request.new_key in BUILTINS:
        raise PackageError("protected_theme", str(request.new_key))
    with registry_lock(root):
        state = read_registry(root)
        output: dict[str, bytes] = {}
        for key in request.keys:
            entry = state.entries.get(key)
            folder = confined(root, f"_packages/{entry.digest}" if entry else key)
            if not folder.is_dir():
                raise PackageError("theme_not_found", key, 404)
            new_key = request.new_key or key
            for path in sorted(folder.rglob("*")):
                if path.is_symlink():
                    raise PackageError("unsafe_path", path.name)
                if not path.is_file() or not allowed_file(path):
                    continue
                name = path.relative_to(folder).as_posix()
                content = path.read_bytes()
                if name == "theme.json":
                    theme = (
                        effective_theme(key, entry)
                        if entry and request.include_overrides
                        else entry.original
                        if entry
                        else WebappTheme.model_validate_json(content)
                    )
                    data = theme.model_dump(mode="json", exclude_none=True)
                    data.update(key=new_key, default=False, use_in_admin=False, hidden=False)
                    data.pop("variant_alias_for", None)
                    if entry:
                        data["css_file"] = entry.original.css_file
                        data["assets_version"] = entry.original.assets_version
                    content = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
                elif path.suffix.lower() == ".css" and (request.new_key or key in BUILTINS):
                    content = fork_css(content.decode("utf-8"), key, new_key, name).encode("utf-8")
                output[f"{new_key}/{name}"] = content
            captured = preview_file(root, key)
            if captured.is_file():
                output[f"{new_key}/preview.webp"] = captured.read_bytes()
                metadata_path = f"{new_key}/theme-package.json"
                if metadata_path in output:
                    metadata = json.loads(output[metadata_path])
                    metadata["preview"] = "preview.webp"
                    output[metadata_path] = (
                        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"
                    ).encode()
        output["minishop-themes.json"] = json.dumps(
            {
                "schema_version": 1,
                "themes": [{"path": request.new_key or key} for key in request.keys],
            },
            indent=2,
        ).encode()
        result = deterministic_zip(output)
        if len(result) > MAX_ARCHIVE:
            raise PackageError("export_too_large")
        return result
