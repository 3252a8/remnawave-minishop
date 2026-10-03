from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path

import pytest

from config.theme_packages.archive import deterministic_zip
from config.theme_packages.backup import prepare_restore, restore_themes, snapshot_themes
from config.theme_packages.css import validate_css
from config.theme_packages.models import PackageError
from config.theme_packages.operations import install_import, remove_theme
from config.theme_packages.registry import asset_path, collect_garbage, read_registry
from tests.unit.test_theme_packages import install, package, ready


def test_snapshot_restore_keeps_versions_and_excludes_imports(tmp_path: Path) -> None:
    root = tmp_path / "source"
    record = ready(root)
    install(root, record)
    install(root, ready(root, package(version="2.0.0")), action="update")
    snapshot = tmp_path / "snapshot"
    assert snapshot_themes(root, snapshot)
    assert not (snapshot / "_imports").exists()
    files = {
        "config/themes/" + file.relative_to(snapshot).as_posix(): file.read_bytes()
        for file in snapshot.rglob("*")
        if file.is_file()
    }
    with zipfile.ZipFile(io.BytesIO(deterministic_zip(files))) as archive:
        temporary = tmp_path / "temp"
        temporary.mkdir()
        prepared = prepare_restore(archive, temporary)
    assert prepared is not None
    target = tmp_path / "target"
    restore_themes(prepared, target)
    entry = read_registry(target).entries["ocean"]
    assert entry.metadata.version == "2.0.0"
    assert len(entry.history) == 1
    assert (target / "_packages" / entry.digest / "theme.json").exists()
    files["config/themes/_packages/" + entry.digest + "/theme.css"] = b"body{color:red}"
    with zipfile.ZipFile(io.BytesIO(deterministic_zip(files))) as archive:
        second = tmp_path / "invalid"
        second.mkdir()
        with pytest.raises(PackageError, match="invalid_theme_backup"):
            prepare_restore(archive, second)


def test_grace_period_and_garbage_collection(tmp_path: Path) -> None:
    install(tmp_path, ready(tmp_path))
    state = read_registry(tmp_path)
    digest = state.entries["ocean"].digest
    remove_theme(tmp_path, "ocean", state.generation, "dark")
    assert asset_path(tmp_path, Path("ocean/revisions") / digest / "theme.css")[0].exists()
    collect_garbage(tmp_path, now=time.time() + 8 * 86400)
    assert not (tmp_path / "_packages" / digest).exists()


def test_snapshot_excludes_deleted_legacy_and_orphan_packages(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    for name, content in {**package(), **package("forest")}.items():
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)
    install(root, ready(root), action="adopt")
    install(root, ready(root, package(version="2.0.0")), action="update")
    deleted = read_registry(root).entries["ocean"]
    remove_theme(root, "ocean", read_registry(root).generation, "dark")
    install(root, ready(root, package("forest")), action="adopt", keys=("forest",))
    install(
        root, ready(root, package("forest", version="2.0.0")), action="update", keys=("forest",)
    )
    orphan = root / "_packages" / ("a" * 64)
    orphan.mkdir()
    (orphan / "unused.webp").write_bytes(b"orphaned package")
    (root / "_registry/before-effects-v2.json").write_bytes(b"old registry")
    generation = read_registry(root).generation
    snapshot = tmp_path / "snapshot"

    assert snapshot_themes(root, snapshot)
    state = read_registry(snapshot)
    assert state.generation == generation
    assert set(state.entries) == {"forest"}
    assert state.removed == ["ocean"]
    assert not state.retired
    assert read_registry(root).retired
    entry = state.entries["forest"]
    assert {path.name for path in (snapshot / "_packages").iterdir()} == {
        version.digest for version in [entry, *entry.history]
    }
    assert not (snapshot / "ocean").exists()
    assert (snapshot / "forest/theme.json").is_file()
    assert {path.name for path in (snapshot / "_registry").iterdir()} == {"current.json"}
    for version in [deleted, *deleted.history]:
        assert (root / "_packages" / version.digest / "theme.json").is_file()
        assert not (snapshot / "_packages" / version.digest).exists()


def test_failed_atomic_commit_does_not_publish_partial_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import config.theme_packages.operations as operations

    record = ready(tmp_path, {**package(), **package("forest")})

    def fail(*_args: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(operations, "write_registry", fail)
    from config.theme_packages.models import InstallRequest

    request = InstallRequest.model_validate(
        {
            "choices": [{"key": "ocean"}, {"key": "forest"}],
            "expected_generation": 0,
            "idempotency_key": "disk-full-test-001",
        }
    )
    with pytest.raises(OSError, match="disk full"):
        install_import(tmp_path, record.id, 7, request)
    assert not read_registry(tmp_path).entries


@pytest.mark.parametrize(
    "css",
    [
        'body{background:image-set("https://evil.test/x" 1x)}',
        "body{color:" + "f(" * 70 + "red" + ")" * 70 + "}",
    ],
)
def test_css_string_resources_and_excessive_nesting(tmp_path: Path, css: str) -> None:
    with pytest.raises(PackageError):
        validate_css(css, tmp_path, "theme.css")


def test_owner_intent_survives_matching_author_defaults(tmp_path: Path) -> None:
    import json

    from config.webapp_themes_models import WebappThemesConfig
    from config.webapp_themes_store import load_webapp_theme_dir, write_webapp_theme_dir

    install(tmp_path, ready(tmp_path))
    theme = load_webapp_theme_dir(tmp_path)[0]
    theme.tokens.bg = "#abcdef"
    write_webapp_theme_dir(
        tmp_path,
        WebappThemesConfig(default_theme="ocean", themes=[theme]),
        expected_generation=read_registry(tmp_path).generation,
    )
    files = package(color="#abcdef", version="2.0.0")
    manifest = json.loads(files["ocean/theme.json"])
    manifest["default"] = False
    files["ocean/theme.json"] = json.dumps(manifest).encode()
    install(tmp_path, ready(tmp_path, files), action="update")
    theme = load_webapp_theme_dir(tmp_path)[0]
    assert theme.default
    theme.use_in_admin = True
    write_webapp_theme_dir(
        tmp_path,
        WebappThemesConfig(default_theme="ocean", themes=[theme]),
        expected_generation=read_registry(tmp_path).generation,
    )
    install(tmp_path, ready(tmp_path, package(color="#445566", version="3.0.0")), action="update")
    theme = load_webapp_theme_dir(tmp_path)[0]
    assert theme.default and theme.tokens.bg == "#abcdef"
