"""Portable snapshots of verified, installed plugin packages."""

from __future__ import annotations

import base64
import hashlib
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from bot.plugins.packages import (
    IDENTIFIER,
    SHA256,
    PluginPackageError,
    _canonical_manifest,
    _json_object,
    _trust_keys,
    _validate_manifest,
    read_state,
)
from config.theme_packages.paths import registry_lock

BACKUP_PREFIX = "config/plugin-store/"


def _selected_releases(root: Path) -> list[Path]:
    state = read_state(root)
    releases: list[Path] = []
    for plugin_id, entry in sorted(state["installations"].items()):
        if not isinstance(plugin_id, str) or not IDENTIFIER.fullmatch(plugin_id):
            raise PluginPackageError("invalid_plugin_state")
        if not isinstance(entry, dict) or not isinstance(entry.get("digest"), str):
            raise PluginPackageError("invalid_plugin_state")
        digest = entry["digest"]
        if not SHA256.fullmatch(digest):
            raise PluginPackageError("invalid_plugin_state")
        releases.append(root / "releases" / plugin_id / digest)
    return releases


def _copy_regular_tree(source: Path, target: Path) -> None:
    if not source.is_dir() or source.is_symlink():
        raise PluginPackageError("invalid_plugin_backup")
    target.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        if path.is_symlink():
            raise PluginPackageError("invalid_plugin_backup")
        relative = path.relative_to(source)
        destination = target / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        else:
            raise PluginPackageError("invalid_plugin_backup")


def snapshot_packages(source: Path, target: Path) -> bool:
    """Copy only active installation metadata and exact selected releases."""
    if not source.is_dir():
        return False
    with registry_lock(source):
        releases = _selected_releases(source)
        if not releases:
            return False
        for name in ("state.json", "trusted-publishers.json"):
            path = source / name
            if not path.is_file() or path.is_symlink():
                raise PluginPackageError("invalid_plugin_backup")
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target / name)
        for release in releases:
            _copy_regular_tree(source=release, target=target / release.relative_to(source))
    return True


def _validate_packages(root: Path) -> None:
    keys = _trust_keys(root)
    state = read_state(root)
    if not isinstance(state.get("installations"), dict):
        raise PluginPackageError("invalid_plugin_backup")
    for release in _selected_releases(root):
        manifest_path = release / "plugin.json"
        signature_path = release / "signatures" / "ed25519.sig"
        if not manifest_path.is_file() or not signature_path.is_file():
            raise PluginPackageError("invalid_plugin_backup")
        manifest = _json_object(manifest_path.read_bytes(), "invalid_plugin_backup")
        _validate_manifest(manifest)
        plugin_id = release.parent.name
        digest = release.name
        entry = state["installations"][plugin_id]
        if (
            manifest["id"] != plugin_id
            or manifest["publisher"] != entry.get("publisher")
            or manifest["version"] != entry.get("version")
            or not SHA256.fullmatch(digest)
        ):
            raise PluginPackageError("invalid_plugin_backup")
        expected = set(manifest["files"]) | {"plugin.json", "signatures/ed25519.sig"}
        actual = {
            path.relative_to(release).as_posix() for path in release.rglob("*") if path.is_file()
        }
        if actual != expected:
            raise PluginPackageError("invalid_plugin_backup")
        for name, expected_digest in manifest["files"].items():
            file_path = release.joinpath(*PurePosixPath(name).parts)
            if hashlib.sha256(file_path.read_bytes()).hexdigest() != expected_digest:
                raise PluginPackageError("package_file_hash_mismatch")
        encoded_key = keys.get(manifest["publisher"])
        if not encoded_key:
            raise PluginPackageError("publisher_not_trusted")
        try:
            public_key = base64.b64decode(encoded_key, validate=True)
            if hashlib.sha256(public_key).hexdigest() != manifest["publisher_fingerprint"]:
                raise PluginPackageError("publisher_fingerprint_mismatch")
            Ed25519PublicKey.from_public_bytes(public_key).verify(
                signature_path.read_bytes(), _canonical_manifest(manifest)
            )
        except (ValueError, TypeError, InvalidSignature) as exc:
            raise PluginPackageError("invalid_package_signature") from exc


def prepare_package_restore(archive: zipfile.ZipFile, staging: Path) -> Path | None:
    members = [item for item in archive.infolist() if item.filename.startswith(BACKUP_PREFIX)]
    if not members:
        return None
    target = staging / "restored-plugin-store"
    target.mkdir()
    for member in members:
        relative = member.filename.removeprefix(BACKUP_PREFIX)
        if member.is_dir():
            relative = relative.rstrip("/")
            if not relative:
                continue
        parts = relative.split("/")
        if (
            not relative
            or relative.startswith("/")
            or "\\" in relative
            or any(part in {"", ".", ".."} for part in parts)
            or stat.S_ISLNK(member.external_attr >> 16)
        ):
            raise PluginPackageError("invalid_plugin_backup")
        destination = target.joinpath(*parts)
        if member.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, destination.open("xb") as output:
            shutil.copyfileobj(source, output, length=64 * 1024)
    _validate_packages(target)
    return target
