"""First-use publisher verification and minimum Core version behavior."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import platform
import sys
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from bot.plugins.packages import PluginPackageError, inspect_archive, trust_publisher


def _package(
    private: Ed25519PrivateKey,
    *,
    minimum: str | None = None,
    embedded_key: bool = True,
    signature_key: Ed25519PrivateKey | None = None,
    backend_name: str = "backend/sample_plugin.py",
) -> bytes:
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    payload = b"value = 1\n"
    manifest: dict[str, object] = {
        "schema_version": 1,
        "id": "sample-plugin",
        "version": "1.0.0",
        "publisher": "sample-publisher",
        "publisher_fingerprint": hashlib.sha256(public).hexdigest(),
        "plugin_api": 1,
        "frontend_host_api": 1,
        "core_revision": "a" * 40,
        "runtime": {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
            "system": platform.system().lower(),
            "machine": platform.machine().lower(),
        },
        "backend": {"entry_point": "sample_plugin:entry"},
        "files": {backend_name: hashlib.sha256(payload).hexdigest()},
    }
    if embedded_key:
        manifest["publisher_public_key"] = base64.b64encode(public).decode("ascii")
    if minimum is not None:
        manifest["core_compatibility"] = {"mode": "minimum_version", "version": minimum}
    canonical = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("plugin.json", canonical)
        archive.writestr(backend_name, payload)
        archive.writestr("signatures/ed25519.sig", (signature_key or private).sign(canonical))
    return output.getvalue()


def test_embedded_key_verifies_before_first_trust_and_remains_pinned(tmp_path: Path) -> None:
    private = Ed25519PrivateKey.generate()
    body = _package(private)
    candidate = inspect_archive(tmp_path, body)
    assert not candidate.trusted
    assert candidate.reason == "publisher_not_trusted"
    with pytest.raises(PluginPackageError, match="invalid_package_signature"):
        inspect_archive(
            tmp_path,
            _package(private, signature_key=Ed25519PrivateKey.generate()),
        )
    key = candidate.manifest["publisher_public_key"]
    fingerprint = candidate.manifest["publisher_fingerprint"]
    trust_publisher(tmp_path, "sample-publisher", key, fingerprint)
    assert inspect_archive(tmp_path, body).trusted

    with pytest.raises(PluginPackageError, match="publisher_key_rotation_requires_recovery"):
        inspect_archive(tmp_path, _package(Ed25519PrivateKey.generate()))


def test_legacy_archive_requires_existing_trust(tmp_path: Path) -> None:
    private = Ed25519PrivateKey.generate()
    body = _package(private, embedded_key=False)
    assert not inspect_archive(tmp_path, body).trusted
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    trust_publisher(
        tmp_path,
        "sample-publisher",
        base64.b64encode(public).decode("ascii"),
        hashlib.sha256(public).hexdigest(),
    )
    assert inspect_archive(tmp_path, body).trusted


def test_minimum_core_version_accepts_current_and_newer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private = Ed25519PrivateKey.generate()
    monkeypatch.setattr("bot.plugins.packages.resolve_app_version_tag", lambda: "v3.4.4")
    assert inspect_archive(tmp_path, _package(private, minimum="3.4.4")).reason == (
        "publisher_not_trusted"
    )
    assert inspect_archive(tmp_path, _package(private, minimum="3.4.3")).reason == (
        "publisher_not_trusted"
    )
    with pytest.raises(PluginPackageError, match="incompatible_core_version"):
        inspect_archive(tmp_path, _package(private, minimum="3.4.5"))
    with pytest.raises(PluginPackageError, match="invalid_core_compatibility"):
        inspect_archive(tmp_path, _package(private, minimum="3.4"))
    with pytest.raises(PluginPackageError, match="portable_backend_requires_python_source"):
        inspect_archive(
            tmp_path, _package(private, minimum="3.4.4", backend_name="backend/sample_plugin.so")
        )
    monkeypatch.setattr("bot.plugins.packages.resolve_app_version_tag", lambda: "dev+unknown")
    with pytest.raises(PluginPackageError, match="incompatible_core_version"):
        inspect_archive(tmp_path, _package(private, minimum="3.4.4"))
