"""Signed package inspection and selected-generation lifecycle."""

from __future__ import annotations

import asyncio
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

from bot.plugins.packages import (
    PluginPackageError,
    activate_staged,
    bootstrap_image_package,
    inspect_archive,
    managed_entry_points,
    mark_generation,
    read_state,
    remove_plugin,
    set_enabled,
    stage_archive,
    trust_publisher,
)


def _archive(
    private: Ed25519PrivateKey,
    *,
    files: dict[str, bytes] | None = None,
    frontend: dict[str, object] | None = None,
    core_compatibility: dict[str, object] | None = None,
) -> bytes:
    files = files or {"backend/sample_plugin_module.py": b"loaded = 42\n"}
    manifest = {
        "schema_version": 1,
        "id": "sample-plugin",
        "version": "1.0.0",
        "publisher": "sample-publisher",
        "publisher_fingerprint": hashlib.sha256(
            private.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        ).hexdigest(),
        "plugin_api": 1,
        "frontend_host_api": 1,
        "core_revision": "a" * 40,
        "runtime": {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
            "system": platform.system().lower(),
            "machine": platform.machine().lower(),
        },
        "backend": {"entry_point": "sample_plugin_module:loaded"},
        "files": {name: hashlib.sha256(body).hexdigest() for name, body in files.items()},
    }
    if frontend is not None:
        manifest["frontend"] = frontend
    if core_compatibility is not None:
        manifest["core_compatibility"] = core_compatibility
    canonical = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, body in files.items():
            archive.writestr(name, body)
        archive.writestr("plugin.json", canonical)
        archive.writestr("signatures/ed25519.sig", private.sign(canonical))
    return output.getvalue()


def _trust(root: Path, private: Ed25519PrivateKey) -> None:
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    trust_publisher(
        root,
        "sample-publisher",
        base64.b64encode(public).decode(),
        hashlib.sha256(public).hexdigest(),
    )


def test_signed_package_requires_trust_then_activates_exact_generation(tmp_path: Path) -> None:
    private = Ed25519PrivateKey.generate()
    body = _archive(private)
    assert inspect_archive(tmp_path, body).reason == "publisher_not_trusted"
    _trust(tmp_path, private)
    assert inspect_archive(tmp_path, body).trusted
    operation = stage_archive(tmp_path, body, actor=7)
    assert stage_archive(tmp_path, body, actor=7)["operation_id"] == operation["operation_id"]
    state = activate_staged(tmp_path, operation["operation_id"], operation["digest"], 7, 0)
    assert state["generation"] == 1
    assert (
        activate_staged(tmp_path, operation["operation_id"], operation["digest"], 7, 0)[
            "generation"
        ]
        == 1
    )
    assert state["installations"]["sample-plugin"]["enabled"] is False
    assert managed_entry_points(tmp_path) == []
    state = set_enabled(tmp_path, "sample-plugin", True, 7, 1)
    assert state["generation"] == 2
    assert set_enabled(tmp_path, "sample-plugin", True, 7, 2)["generation"] == 2
    try:
        assert managed_entry_points(tmp_path)[0].load() == 42
    finally:
        sys.modules.pop("sample_plugin_module", None)
        sys.path.remove(
            str(tmp_path / "releases" / "sample-plugin" / operation["digest"] / "backend")
        )
    with pytest.raises(PluginPackageError, match="generation_conflict"):
        set_enabled(tmp_path, "sample-plugin", False, 7, 1)
    assert read_state(tmp_path)["installations"]["sample-plugin"]["enabled"]
    with pytest.raises(PluginPackageError, match="disable_before_remove"):
        remove_plugin(tmp_path, "sample-plugin", 7, 2)
    state = set_enabled(tmp_path, "sample-plugin", False, 7, 2)
    state = remove_plugin(tmp_path, "sample-plugin", 7, state["generation"])
    assert "sample-plugin" not in state["installations"]


def test_portable_source_package_accepts_newer_core_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("bot.plugins.packages._running_core_revision", lambda: "b" * 40)
    private = Ed25519PrivateKey.generate()
    with pytest.raises(PluginPackageError, match="incompatible_core_revision"):
        inspect_archive(tmp_path, _archive(private))

    compatibility: dict[str, object] = {
        "mode": "capabilities",
        "requires": {"support_connector": 1},
    }
    candidate = inspect_archive(tmp_path, _archive(private, core_compatibility=compatibility))
    assert candidate.manifest["core_revision"] == "a" * 40
    assert candidate.reason == "publisher_not_trusted"

    with pytest.raises(PluginPackageError, match="incompatible_core_capability"):
        inspect_archive(
            tmp_path,
            _archive(
                private,
                core_compatibility={"mode": "capabilities", "requires": {"support_connector": 2}},
            ),
        )
    with pytest.raises(PluginPackageError, match="portable_backend_requires_python_source"):
        inspect_archive(
            tmp_path,
            _archive(
                private,
                files={"backend/sample_plugin_module.so": b"native"},
                core_compatibility=compatibility,
            ),
        )


def test_archive_rejects_case_collisions_and_bad_signature(tmp_path: Path) -> None:
    private = Ed25519PrivateKey.generate()
    _trust(tmp_path, private)
    body = _archive(
        private,
        files={
            "backend/sample_plugin_module.py": b"loaded = 42\n",
            "backend/SAMPLE_plugin_module.py": b"loaded = 43\n",
        },
    )
    with pytest.raises(PluginPackageError, match="invalid_package_member"):
        inspect_archive(tmp_path, body)
    other = Ed25519PrivateKey.generate()
    with pytest.raises(PluginPackageError, match="invalid_package_signature"):
        inspect_archive(tmp_path, _archive(other))


def test_hidden_runtime_section_requires_boolean_flag(tmp_path: Path) -> None:
    private = Ed25519PrivateKey.generate()
    files = {
        "backend/sample_plugin_module.py": b"loaded = 42\n",
        "frontend/entry.js": b"export function mountView() {}",
    }
    frontend: dict[str, object] = {
        "entry": "entry.js",
        "styles": [],
        "sections": [{"id": "legacy", "view": "legacy", "hideInNavigation": True}],
    }
    assert inspect_archive(tmp_path, _archive(private, files=files, frontend=frontend)).reason == (
        "publisher_not_trusted"
    )
    frontend["sections"] = [{"id": "legacy", "view": "legacy", "hideInNavigation": "true"}]
    with pytest.raises(PluginPackageError, match="invalid_frontend_manifest"):
        inspect_archive(tmp_path, _archive(private, files=files, frontend=frontend))


def test_image_package_bootstrap_is_idempotent_across_roles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private = Ed25519PrivateKey.generate()
    archive = tmp_path / "image-plugin.zip"
    archive.write_bytes(_archive(private))
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_path = tmp_path / "publisher.pub"
    public_path.write_text(base64.b64encode(public).decode(), encoding="ascii")
    monkeypatch.setenv("MINISHOP_BUNDLED_PLUGIN_ARCHIVE", str(archive))
    monkeypatch.setenv("MINISHOP_BUNDLED_PLUGIN_PUBLIC_KEY", str(public_path))
    bootstrap_image_package(tmp_path, "backend")
    assert read_state(tmp_path)["generation"] == 2
    bootstrap_image_package(tmp_path, "worker")
    bootstrap_image_package(tmp_path, "backend")
    assert read_state(tmp_path)["generation"] == 2
    archive.write_bytes(
        _archive(private, files={"backend/sample_plugin_module.py": b"loaded = 43\n"})
    )
    bootstrap_image_package(tmp_path, "backend")
    assert read_state(tmp_path)["generation"] == 3
    assert read_state(tmp_path)["installations"]["sample-plugin"]["enabled"] is True
    bootstrap_image_package(tmp_path, "worker")
    state = set_enabled(tmp_path, "sample-plugin", False, actor=7, generation=3)
    assert state["generation"] == 4
    bootstrap_image_package(tmp_path, "backend")
    bootstrap_image_package(tmp_path, "worker")
    assert read_state(tmp_path)["installations"]["sample-plugin"]["enabled"] is False


def test_one_shot_migrate_selects_image_package_before_plugin_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import main_migrate

    private = Ed25519PrivateKey.generate()
    archive = tmp_path / "image-plugin.zip"
    archive.write_bytes(_archive(private))
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_path = tmp_path / "publisher.pub"
    public_path.write_text(base64.b64encode(public).decode(), encoding="ascii")
    monkeypatch.setenv("MINISHOP_PLUGIN_STORE", str(tmp_path))
    monkeypatch.setenv("MINISHOP_BUNDLED_PLUGIN_ARCHIVE", str(archive))
    monkeypatch.setenv("MINISHOP_BUNDLED_PLUGIN_PUBLIC_KEY", str(public_path))
    bootstrap_image_package(tmp_path, "backend")
    previous = read_state(tmp_path)["installations"]["sample-plugin"]["digest"]
    archive.write_bytes(
        _archive(private, files={"backend/sample_plugin_module.py": b"loaded = 43\n"})
    )

    settings = object()
    session_factory = object()
    monkeypatch.setattr(main_migrate, "get_settings", lambda: settings)
    monkeypatch.setattr(main_migrate, "init_db_connection", lambda _: session_factory)

    async def inspect_before_database_migration(
        actual_settings: object, actual_factory: object
    ) -> None:
        assert actual_settings is settings
        assert actual_factory is session_factory
        assert managed_entry_points(tmp_path)[0].load() == 43

    monkeypatch.setattr(main_migrate, "init_db", inspect_before_database_migration)
    try:
        current = read_state(tmp_path)["generation"]
        mark_generation(tmp_path, current, prepared=False, error="incompatible_core_revision")
        asyncio.run(main_migrate.main())
        state = read_state(tmp_path)
        assert state["installations"]["sample-plugin"]["digest"] != previous
        assert state["prepared_generation"] == state["generation"]
        assert "failed_generation" not in state
        assert "failure" not in state
        mark_generation(tmp_path, state["generation"], prepared=False, error="previous_attempt")
        asyncio.run(main_migrate.main())
        recovered = read_state(tmp_path)
        assert recovered["prepared_generation"] == recovered["generation"]
        assert "failed_generation" not in recovered
        assert "failure" not in recovered
    finally:
        sys.modules.pop("sample_plugin_module", None)
        for entry in read_state(tmp_path)["installations"].values():
            backend = str(tmp_path / "releases" / "sample-plugin" / entry["digest"] / "backend")
            if backend in sys.path:
                sys.path.remove(backend)
