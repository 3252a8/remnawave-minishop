"""Verified, immutable plugin packages shared by the application roles.

The archive inspector never imports package code. A process only sees the
selected backend directory after the administrator has trusted its publisher
and selected a generation. The store is deliberately limited to one Compose
host; every role uses the same data volume.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import platform
import re
import shutil
import sys
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path, PurePosixPath
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from config.theme_packages.paths import atomic_bytes, registry_lock

from .capabilities import CORE_PLUGIN_CAPABILITIES

MAX_ARCHIVE_BYTES = 96 * 1024 * 1024
MAX_UNPACKED_BYTES = 384 * 1024 * 1024
MAX_FILES = 4096
IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
PACKAGE_SCHEMA = 1
FRONTEND_HOST_API = 1


class PluginPackageError(ValueError):
    """An untrusted, incompatible, or conflicting package."""

    def __init__(self, code: str, *, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class Candidate:
    digest: str
    manifest: dict[str, Any]
    trusted: bool
    reason: str

    def public(self) -> dict[str, Any]:
        return {
            "digest": self.digest,
            "manifest": self.manifest,
            "trusted": self.trusted,
            "trust_reason": self.reason,
        }


def _json_object(raw: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PluginPackageError(code) from exc
    if not isinstance(value, dict):
        raise PluginPackageError(code)
    return value


def _path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        not name
        or name.startswith("/")
        or "\\" in name
        or ":" in name
        or any(part in ("", ".", "..") for part in name.split("/"))
        or len(name) > 240
    ):
        raise PluginPackageError("invalid_package_path")
    return path


def _canonical_manifest(manifest: dict[str, Any]) -> bytes:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _running_core_revision() -> str | None:
    marker = Path(__file__).resolve().parents[3] / ".build-commit"
    return marker.read_text(encoding="utf-8").strip() if marker.exists() else None


def _trust_keys(root: Path) -> dict[str, str]:
    path = root / "trusted-publishers.json"
    if not path.exists():
        return {}
    value = _json_object(path.read_bytes(), "invalid_trust_policy")
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise PluginPackageError("invalid_trust_policy")
    return value


def trust_publisher(root: Path, publisher: str, key_base64: str, fingerprint: str) -> str:
    """Pin a publisher key only after the owner confirms its fingerprint."""
    if not IDENTIFIER.fullmatch(publisher):
        raise PluginPackageError("invalid_publisher")
    try:
        key = base64.b64decode(key_base64, validate=True)
        Ed25519PublicKey.from_public_bytes(key)
    except (ValueError, TypeError) as exc:
        raise PluginPackageError("invalid_publisher_key") from exc
    actual = hashlib.sha256(key).hexdigest()
    if actual != fingerprint:
        raise PluginPackageError("publisher_fingerprint_mismatch")
    with registry_lock(root):
        keys = _trust_keys(root)
        if publisher in keys and keys[publisher] != key_base64:
            raise PluginPackageError("publisher_key_rotation_requires_recovery", status=409)
        keys[publisher] = key_base64
        atomic_bytes(root / "trusted-publishers.json", _canonical_manifest(keys))
    return actual


def _validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != PACKAGE_SCHEMA:
        raise PluginPackageError("unsupported_package_schema")
    if not isinstance(manifest.get("id"), str) or not IDENTIFIER.fullmatch(manifest["id"]):
        raise PluginPackageError("invalid_plugin_id")
    if not isinstance(manifest.get("publisher"), str) or not IDENTIFIER.fullmatch(
        manifest["publisher"]
    ):
        raise PluginPackageError("invalid_publisher")
    if not isinstance(manifest.get("version"), str) or not re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.]+)?", manifest["version"]
    ):
        raise PluginPackageError("invalid_plugin_version")
    if manifest.get("plugin_api") != 1 or manifest.get("frontend_host_api") != FRONTEND_HOST_API:
        raise PluginPackageError("incompatible_plugin_api")
    core_revision = manifest.get("core_revision")
    if not isinstance(core_revision, str) or not re.fullmatch(r"[0-9a-f]{7,40}", core_revision):
        raise PluginPackageError("core_revision_required")
    compatibility = manifest.get("core_compatibility")
    if compatibility is None:
        running_revision = _running_core_revision()
        if running_revision is not None and not (
            core_revision.startswith(running_revision) or running_revision.startswith(core_revision)
        ):
            raise PluginPackageError("incompatible_core_revision")
    else:
        if (
            not isinstance(compatibility, dict)
            or set(compatibility) != {"mode", "requires"}
            or compatibility.get("mode") != "capabilities"
            or not isinstance(compatibility.get("requires"), dict)
            or not compatibility["requires"]
        ):
            raise PluginPackageError("invalid_core_compatibility")
        for name, version in compatibility["requires"].items():
            if (
                not isinstance(name, str)
                or type(version) is not int
                or CORE_PLUGIN_CAPABILITIES.get(name) != version
            ):
                raise PluginPackageError("incompatible_core_capability")
    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict):
        raise PluginPackageError("runtime_required")
    expected = {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "system": platform.system().lower(),
        "machine": platform.machine().lower(),
    }
    for key, value in expected.items():
        if runtime.get(key) != value:
            raise PluginPackageError(f"incompatible_runtime_{key}")
    backend = manifest.get("backend")
    if not isinstance(backend, dict) or not isinstance(backend.get("entry_point"), str):
        raise PluginPackageError("backend_entry_point_required")
    if not re.fullmatch(r"[A-Za-z_][\w.]*:[A-Za-z_]\w*", backend["entry_point"]):
        raise PluginPackageError("invalid_backend_entry_point")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise PluginPackageError("file_hashes_required")
    for name, digest in files.items():
        if not isinstance(name, str) or not isinstance(digest, str):
            raise PluginPackageError("invalid_file_hash")
        _path(name)
        if not SHA256.fullmatch(digest):
            raise PluginPackageError("invalid_file_hash")
        if not name.startswith(("backend/", "frontend/", "locales/", "metadata/")):
            raise PluginPackageError("invalid_package_member")
        if name.casefold().endswith(".whl"):
            raise PluginPackageError("nested_wheel_not_supported")
    if not any(name.startswith("backend/") for name in files):
        raise PluginPackageError("backend_payload_required")
    if compatibility is not None and any(
        not name.endswith(".py") for name in files if name.startswith("backend/")
    ):
        raise PluginPackageError("portable_backend_requires_python_source")
    module = backend["entry_point"].split(":", 1)[0].split(".", 1)[0]
    if module in {"bot", "config", "db", "sitecustomize", "usercustomize"}:
        raise PluginPackageError("reserved_python_namespace")
    for name in files:
        if name.endswith((".pth", ".pyc", ".pyo")):
            raise PluginPackageError("implicit_python_startup_forbidden")
        if name.startswith("backend/"):
            top = name.split("/", 2)[1]
            if top in {"bot", "config", "db", "sitecustomize.py", "usercustomize.py"}:
                raise PluginPackageError("reserved_python_namespace")
    frontend = manifest.get("frontend")
    if frontend is not None:
        if not isinstance(frontend, dict):
            raise PluginPackageError("invalid_frontend_manifest")
        if not isinstance(frontend.get("entry"), str) or not isinstance(
            frontend.get("styles", []), list
        ):
            raise PluginPackageError("invalid_frontend_manifest")
        paths = [frontend["entry"], *frontend.get("styles", [])]
        preview = frontend.get("preview")
        if preview is not None:
            paths.append(preview)
        for path in paths:
            if not isinstance(path, str) or f"frontend/{path}" not in files:
                raise PluginPackageError("invalid_frontend_asset")
        for collection in (
            "sections",
            "section_groups",
            "section_tabs",
            "user_panels",
            "settings_tabs",
        ):
            views = frontend.get(collection, [])
            if not isinstance(views, list) or len(views) > 64:
                raise PluginPackageError("invalid_frontend_manifest")
            for view in views:
                if not isinstance(view, dict) or not isinstance(view.get("id"), str):
                    raise PluginPackageError("invalid_frontend_manifest")
                if not IDENTIFIER.fullmatch(view["id"]):
                    raise PluginPackageError("invalid_frontend_manifest")
                if collection != "section_groups" and not isinstance(view.get("view"), str):
                    raise PluginPackageError("invalid_frontend_manifest")
                if (
                    collection == "sections"
                    and "hideInNavigation" in view
                    and not isinstance(view["hideInNavigation"], bool)
                ):
                    raise PluginPackageError("invalid_frontend_manifest")


def inspect_archive(root: Path, body: bytes) -> Candidate:
    """Check an archive without importing code or running build hooks."""
    if len(body) > MAX_ARCHIVE_BYTES:
        raise PluginPackageError("archive_too_large", status=413)
    digest = hashlib.sha256(body).hexdigest()
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile as exc:
        raise PluginPackageError("invalid_zip") from exc
    with archive:
        members = archive.infolist()
        if len(members) > MAX_FILES or sum(item.file_size for item in members) > MAX_UNPACKED_BYTES:
            raise PluginPackageError("archive_limits_exceeded", status=413)
        names: set[str] = set()
        folded_names: set[str] = set()
        for item in members:
            if item.is_dir():
                continue
            name = str(_path(item.filename))
            if (
                name in names
                or name.casefold() in folded_names
                or item.flag_bits & 1
                or (item.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise PluginPackageError("invalid_package_member")
            if (
                item.file_size > MAX_ARCHIVE_BYTES
                or item.file_size > max(item.compress_size, 1) * 100
            ):
                raise PluginPackageError("archive_limits_exceeded", status=413)
            names.add(name)
            folded_names.add(name.casefold())
        if "plugin.json" not in names:
            raise PluginPackageError("manifest_required")
        if archive.getinfo("plugin.json").file_size > 1024 * 1024:
            raise PluginPackageError("invalid_plugin_manifest")
        manifest = _json_object(archive.read("plugin.json"), "invalid_plugin_manifest")
        _validate_manifest(manifest)
        expected_files = manifest["files"]
        if names != set(expected_files) | {"plugin.json", "signatures/ed25519.sig"}:
            raise PluginPackageError("package_file_set_mismatch")
        for name, expected in expected_files.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise PluginPackageError("package_file_hash_mismatch")
        key_base64 = _trust_keys(root).get(manifest["publisher"])
        if not key_base64:
            return Candidate(digest, manifest, False, "publisher_not_trusted")
        try:
            key = Ed25519PublicKey.from_public_bytes(base64.b64decode(key_base64, validate=True))
            key.verify(archive.read("signatures/ed25519.sig"), _canonical_manifest(manifest))
        except (ValueError, TypeError, KeyError, InvalidSignature) as exc:
            raise PluginPackageError("invalid_package_signature") from exc
        return Candidate(digest, manifest, True, "verified")


def _state_path(root: Path) -> Path:
    return root / "state.json"


def read_state(root: Path) -> dict[str, Any]:
    path = _state_path(root)
    if not path.exists():
        return {"generation": 0, "installations": {}, "operations": []}
    state = _json_object(path.read_bytes(), "invalid_plugin_state")
    if not isinstance(state.get("generation"), int) or not isinstance(
        state.get("installations"), dict
    ):
        raise PluginPackageError("invalid_plugin_state")
    return state


def _write_state(root: Path, state: dict[str, Any]) -> None:
    atomic_bytes(_state_path(root), _canonical_manifest(state))


def stage_archive(
    root: Path, body: bytes, actor: int, source: dict[str, str] | None = None
) -> dict[str, Any]:
    candidate = inspect_archive(root, body)
    if not candidate.trusted:
        raise PluginPackageError(candidate.reason, status=403)
    operation_id = uuid.uuid4().hex
    with registry_lock(root):
        for existing_stage in (root / "staging").glob("*/operation.json"):
            try:
                existing = _json_object(existing_stage.read_bytes(), "invalid_operation")
            except (OSError, PluginPackageError):
                continue
            if (
                existing.get("actor") == actor
                and existing.get("digest") == candidate.digest
                and existing.get("source") == source
                and existing.get("status") == "staged"
            ):
                return {"operation_id": existing_stage.parent.name, **candidate.public()}
        stage = root / "staging" / operation_id
        stage.mkdir(parents=True, exist_ok=False)
        atomic_bytes(stage / "package.zip", body)
        atomic_bytes(
            stage / "operation.json",
            _canonical_manifest(
                {"actor": actor, "digest": candidate.digest, "status": "staged", "source": source}
            ),
        )
    return {"operation_id": operation_id, **candidate.public()}


def activate_staged(
    root: Path, operation_id: str, digest: str, actor: int, expected_generation: int
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{32}", operation_id) or not SHA256.fullmatch(digest):
        raise PluginPackageError("invalid_operation")
    with registry_lock(root):
        stage = root / "staging" / operation_id
        if not stage.exists():
            state = read_state(root)
            if any(
                item.get("id") == operation_id
                and item.get("actor") == actor
                and item.get("digest") == digest
                and item.get("status") == "completed"
                for item in state.get("operations", [])
            ):
                return state
            raise PluginPackageError("operation_not_found", status=404)
        operation = _json_object((stage / "operation.json").read_bytes(), "invalid_operation")
        if operation.get("actor") != actor or operation.get("digest") != digest:
            raise PluginPackageError("operation_mismatch", status=403)
        state = read_state(root)
        if state["generation"] != expected_generation:
            raise PluginPackageError("generation_conflict", status=409)
        body = (stage / "package.zip").read_bytes()
        candidate = inspect_archive(root, body)
        if candidate.digest != digest or not candidate.trusted:
            raise PluginPackageError("candidate_changed", status=409)
        plugin_id = candidate.manifest["id"]
        installed = state["installations"].get(plugin_id)
        if (
            installed
            and installed["publisher"] != candidate.manifest["publisher"]
            and not (
                (installed.get("source") or {}).get("kind") == "image"
                and (operation.get("source") or {}).get("kind") == "image"
                and actor == 0
            )
        ):
            raise PluginPackageError("publisher_changed", status=409)
        if any(
            point.name == plugin_id for point in metadata.entry_points(group="minishop.plugins")
        ):
            raise PluginPackageError("plugin_managed_by_image", status=409)
        release = root / "releases" / plugin_id / digest
        if not release.exists():
            release.parent.mkdir(parents=True, exist_ok=True)
            temporary = Path(tempfile.mkdtemp(prefix=".release-", dir=release.parent))
            try:
                with zipfile.ZipFile(io.BytesIO(body)) as archive:
                    for name in candidate.manifest["files"]:
                        destination = temporary.joinpath(*PurePosixPath(name).parts)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(archive.read(name))
                    signature = archive.read("signatures/ed25519.sig")
                atomic_bytes(temporary / "plugin.json", _canonical_manifest(candidate.manifest))
                signature_path = temporary / "signatures" / "ed25519.sig"
                atomic_bytes(signature_path, signature)
                os.replace(temporary, release)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
        state["installations"][plugin_id] = {
            "digest": digest,
            "version": candidate.manifest["version"],
            "publisher": candidate.manifest["publisher"],
            "enabled": bool(installed["enabled"]) if installed else False,
            "status": "pending_restart" if installed and installed["enabled"] else "installed",
            "source": operation.get("source"),
        }
        state["generation"] += 1
        state.setdefault("operations", []).append(
            {
                "id": operation_id,
                "actor": actor,
                "plugin": plugin_id,
                "digest": digest,
                "action": "install",
                "status": "completed",
            }
        )
        _write_state(root, state)
        shutil.rmtree(stage)
        return state


def set_enabled(
    root: Path, plugin_id: str, enabled: bool, actor: int, generation: int
) -> dict[str, Any]:
    if not IDENTIFIER.fullmatch(plugin_id):
        raise PluginPackageError("invalid_plugin_id")
    with registry_lock(root):
        state = read_state(root)
        if state["generation"] != generation:
            raise PluginPackageError("generation_conflict", status=409)
        entry = state["installations"].get(plugin_id)
        if entry is None:
            raise PluginPackageError("plugin_not_installed", status=404)
        if entry["enabled"] == enabled:
            return state
        entry["enabled"] = enabled
        entry["status"] = "pending_restart"
        state["generation"] += 1
        state.setdefault("operations", []).append(
            {
                "id": uuid.uuid4().hex,
                "actor": actor,
                "plugin": plugin_id,
                "action": "enable" if enabled else "disable",
            }
        )
        _write_state(root, state)
        return state


def remove_plugin(root: Path, plugin_id: str, actor: int, generation: int) -> dict[str, Any]:
    """Forget a disabled installation while retaining its data and verified release."""
    if not IDENTIFIER.fullmatch(plugin_id):
        raise PluginPackageError("invalid_plugin_id")
    with registry_lock(root):
        state = read_state(root)
        if state["generation"] != generation:
            raise PluginPackageError("generation_conflict", status=409)
        entry = state["installations"].get(plugin_id)
        if entry is None:
            return state
        if (entry.get("source") or {}).get("kind") == "image":
            raise PluginPackageError("image_plugin_cannot_remove", status=409)
        if entry["enabled"]:
            raise PluginPackageError("disable_before_remove", status=409)
        del state["installations"][plugin_id]
        state["generation"] += 1
        state.setdefault("operations", []).append(
            {
                "id": uuid.uuid4().hex,
                "actor": actor,
                "plugin": plugin_id,
                "action": "remove",
                "status": "completed",
            }
        )
        _write_state(root, state)
        return state


def managed_entry_points(root: Path) -> list[metadata.EntryPoint]:
    """Expose only the selected generation to Python's existing Plugin API."""
    if not generation_is_current():
        raise PluginPackageError("plugin_generation_changed", status=409)
    entry_points: list[metadata.EntryPoint] = []
    for plugin_id, entry in sorted(read_state(root)["installations"].items()):
        if not entry["enabled"]:
            continue
        release = root / "releases" / plugin_id / entry["digest"]
        manifest = _json_object((release / "plugin.json").read_bytes(), "invalid_plugin_manifest")
        _validate_manifest(manifest)
        key_base64 = _trust_keys(root).get(manifest["publisher"])
        if not key_base64:
            raise PluginPackageError("publisher_not_trusted")
        try:
            key = Ed25519PublicKey.from_public_bytes(base64.b64decode(key_base64, validate=True))
            key.verify(
                (release / "signatures" / "ed25519.sig").read_bytes(), _canonical_manifest(manifest)
            )
        except (ValueError, TypeError, OSError, InvalidSignature) as exc:
            raise PluginPackageError("invalid_package_signature") from exc
        for name, digest in manifest["files"].items():
            path = release.joinpath(*PurePosixPath(name).parts)
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise PluginPackageError("package_file_hash_mismatch")
        backend = release / "backend"
        if str(backend) not in sys.path:
            sys.path.append(str(backend))
        entry_points.append(
            metadata.EntryPoint(
                name=plugin_id,
                value=manifest["backend"]["entry_point"],
                group="minishop.plugins",
            )
        )
    return entry_points


def package_root() -> Path:
    return Path(os.environ.get("MINISHOP_PLUGIN_STORE", "data/plugin-store")).expanduser()


def bootstrap_image_package(root: Path, role: str) -> None:
    """Seed a signed package shipped inside a derivative image into the shared store.

    Only the backend image selects a generation. The worker verifies that its
    image carries the same archive before it can start work for that generation.
    """
    archive_name = os.environ.get("MINISHOP_BUNDLED_PLUGIN_ARCHIVE")
    key_name = os.environ.get("MINISHOP_BUNDLED_PLUGIN_PUBLIC_KEY")
    if not archive_name and not key_name:
        return
    if not archive_name or not key_name:
        raise PluginPackageError("incomplete_image_package")
    archive_path = Path(archive_name)
    if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise PluginPackageError("archive_too_large", status=413)
    body = archive_path.read_bytes()
    preview = inspect_archive(root, body)
    public_key = Path(key_name).read_text(encoding="ascii").strip()
    try:
        raw_key = base64.b64decode(public_key, validate=True)
    except ValueError as exc:
        raise PluginPackageError("invalid_publisher_key") from exc
    fingerprint = hashlib.sha256(raw_key).hexdigest()
    if preview.manifest.get("publisher_fingerprint") != fingerprint:
        raise PluginPackageError("image_publisher_key_mismatch")
    plugin_id = preview.manifest["id"]
    if role == "worker":
        import time

        for _ in range(120):
            installed = read_state(root)["installations"].get(plugin_id)
            if installed and installed["digest"] == preview.digest:
                if not inspect_archive(root, body).trusted:
                    raise PluginPackageError("image_package_not_trusted")
                return
            time.sleep(0.5)
        raise PluginPackageError("image_package_backend_not_ready")
    if role != "backend":
        raise PluginPackageError("invalid_image_package_role")
    trust_publisher(root, preview.manifest["publisher"], public_key, fingerprint)
    verified = inspect_archive(root, body)
    if not verified.trusted:
        raise PluginPackageError("image_package_not_trusted")
    state = read_state(root)
    installed = state["installations"].get(plugin_id)
    if installed and installed["digest"] == verified.digest:
        return
    if installed and (installed.get("source") or {}).get("kind") != "image":
        raise PluginPackageError("package_source_conflict", status=409)
    should_enable = installed["enabled"] if installed else True
    operation = stage_archive(root, body, actor=0, source={"kind": "image"})
    try:
        state = activate_staged(
            root, operation["operation_id"], verified.digest, 0, state["generation"]
        )
    except PluginPackageError as exc:
        if exc.code != "generation_conflict":
            raise
        state = read_state(root)
        installed = state["installations"].get(plugin_id)
        if not installed or installed["digest"] != verified.digest:
            raise
    if should_enable and not state["installations"][plugin_id]["enabled"]:
        set_enabled(root, plugin_id, True, actor=0, generation=state["generation"])


def generation_is_current() -> bool:
    """Fence work from a superseded process before its next side effect."""
    launched = os.environ.get("MINISHOP_PLUGIN_GENERATION")
    if launched is None:
        return True  # Legacy image or a local development entrypoint.
    try:
        return int(launched) == read_state(package_root())["generation"]
    except (OSError, ValueError, PluginPackageError):
        return False


def observe_role(root: Path, role: str, generation: int, status: str) -> None:
    """Persist one launcher's observation without changing desired generation."""
    if role not in {"backend", "worker"} or status not in {
        "stopped",
        "starting",
        "active",
        "safe_mode",
        "failed",
    }:
        raise ValueError("invalid_runtime_observation")
    with registry_lock(root):
        state = read_state(root)
        state.setdefault("observations", {})[role] = {
            "generation": generation,
            "status": status,
        }
        if all(
            state["observations"].get(name)
            == {"generation": state["generation"], "status": "active"}
            for name in ("backend", "worker")
        ):
            for entry in state["installations"].values():
                entry["status"] = "active" if entry["enabled"] else "disabled"
        _write_state(root, state)


def mark_generation(root: Path, generation: int, *, prepared: bool, error: str = "") -> None:
    """Record migration outcome so interrupted launchers resume deterministically."""
    with registry_lock(root):
        state = read_state(root)
        if state["generation"] != generation:
            raise PluginPackageError("generation_conflict", status=409)
        if prepared:
            state["prepared_generation"] = generation
            state.pop("failed_generation", None)
            state.pop("failure", None)
        else:
            state["failed_generation"] = generation
            state.pop("prepared_generation", None)
            state["failure"] = error[:240]
        _write_state(root, state)
