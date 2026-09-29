"""Executable themes require consent, intact packages and a current installation."""

from __future__ import annotations

import io
import json
import re
import zipfile
from base64 import b64decode
from pathlib import Path

import pytest

from config.theme_packages.backup import restore_themes, snapshot_themes
from config.theme_packages.effects_preview import effects_preview
from config.theme_packages.effects_runtime import active_effect, change_effects, effect_asset
from config.theme_packages.models import EffectsRequest, ExportRequest, InstallRequest, PackageError
from config.theme_packages.operations import (
    export_themes,
    install_import,
    remove_theme,
    rollback_theme,
)
from config.theme_packages.registry import asset_path, read_registry, write_registry
from tests.unit.test_theme_packages import package, ready


def executable(
    script: bytes = b"export function mount(){return {update(){},dispose(){}}}",
) -> dict[str, bytes]:
    files = package()
    files["ocean/theme-package.json"] = json.dumps(
        {
            "schema_version": 2,
            "version": "1.0.0",
            "effects": {
                "api_version": 1,
                "runtime": "trusted-dom",
                "entry": "effects/main.js",
                "targets": ["home.header.surface"],
            },
        }
    ).encode()
    files["ocean/effects/main.js"] = script
    return files


def install_effect(root: Path, *, allow: bool = False, script: bytes | None = None) -> str:
    record = ready(root, executable() if script is None else executable(script))
    assert not record.candidates[0].error
    state = read_registry(root)
    candidate = record.candidates[0]
    install_import(
        root,
        record.id,
        7,
        InstallRequest.model_validate(
            {
                "expected_generation": state.generation,
                "idempotency_key": record.id,
                "choices": [
                    {
                        "key": "ocean",
                        "action": "update" if "ocean" in state.entries else "install",
                        "effects": "allow" if allow else "disabled",
                        "effects_policy": 1,
                        "effects_digest": candidate.effects_digest,
                    }
                ],
            }
        ),
    )
    return str(candidate.digest)


def permit(root: Path, enabled: bool = True) -> None:
    state = read_registry(root)
    change_effects(
        root,
        "ocean",
        7,
        EffectsRequest(
            expected_generation=state.generation,
            enabled=enabled,
            effects_digest=state.entries["ocean"].effects_digest,
            effects_policy=1,
        ),
    )


def active(root: Path):
    return active_effect(root, "ocean", "#00fe7a")


def test_default_off_consent_integrity_and_emergency_disable(tmp_path: Path) -> None:
    digest = install_effect(tmp_path)
    assert active(tmp_path) is None
    state = read_registry(tmp_path)
    with pytest.raises(PackageError, match="theme_effects_consent_required"):
        change_effects(
            tmp_path,
            "ocean",
            7,
            EffectsRequest(
                expected_generation=state.generation,
                enabled=True,
                effects_digest="bad",
                effects_policy=1,
            ),
        )
    permit(tmp_path)
    effect = active(tmp_path)
    assert effect and effect.digest == digest
    body, mime = effect_asset(tmp_path, effect, "ocean", digest, "effects/main.js")
    assert b"mount" in body and mime == "text/javascript"
    with pytest.raises(PackageError):
        asset_path(tmp_path, Path(f"_packages/{digest}/effects/main.js"))
    with pytest.raises(PackageError):
        effect_asset(tmp_path, effect, "ocean", digest, "theme.json")
    emergency = tmp_path / "_registry/effects-disabled"
    emergency.touch()
    assert active(tmp_path) is None
    emergency.unlink()
    (tmp_path / "_packages" / digest / "effects/main.js").write_text("changed")
    with pytest.raises(PackageError, match="package_corrupted"):
        active(tmp_path)


def test_update_rollback_revoke_and_remove(tmp_path: Path) -> None:
    old = install_effect(tmp_path, allow=True)
    new = install_effect(tmp_path, allow=True, script=b"export const mount = () => null;")
    assert active(tmp_path).digest == new
    rollback_theme(tmp_path, "ocean", read_registry(tmp_path).generation)
    assert active(tmp_path).digest == old
    permit(tmp_path, False)
    rollback_theme(tmp_path, "ocean", read_registry(tmp_path).generation)
    assert active(tmp_path) is None
    remove_theme(tmp_path, "ocean", read_registry(tmp_path).generation, "dark")
    assert active(tmp_path) is None
    assert not read_registry(tmp_path).effects


def test_export_reimport_restore_and_preview_do_not_transfer_consent(tmp_path: Path) -> None:
    root = tmp_path / "source"
    install_effect(root, allow=True)
    archive = export_themes(root, ExportRequest(keys=["ocean"]))
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        assert "ocean/effects/main.js" in zipped.namelist()
        assert not any("registry" in name for name in zipped.namelist())
    preview = effects_preview(root, "ocean", 7)
    assert "data:text/javascript;base64," in preview
    assert "connect-src &#x27;none&#x27;" in preview
    # The preview shows Core's real mock home with the adapter layered on it.
    assert "theme-key-ocean" in preview
    assert "data-theme-effect-target" in preview
    saved = tmp_path / "backup"
    snapshot_themes(root, saved)
    restored = tmp_path / "restored"
    restore_themes(saved, restored)
    assert active(restored) is None
    assert not read_registry(restored).effects


def test_import_effect_preview_includes_styles_assets_and_real_surfaces(tmp_path: Path) -> None:
    files = executable()
    metadata = json.loads(files["ocean/theme-package.json"])
    metadata["effects"]["styles"] = ["effects/main.css"]
    metadata["effects"]["assets"] = ["effects/dot.svg"]
    files["ocean/theme-package.json"] = json.dumps(metadata).encode()
    files["ocean/effects/main.css"] = b".theme-effect-surface{background:url(dot.svg)}"
    files["ocean/effects/dot.svg"] = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
    record = ready(tmp_path, files)
    assert not record.candidates[0].error

    preview = effects_preview(tmp_path, "ocean", 7, record.id)
    match = re.search(r'data:text/css;base64,([^"<]+)', preview)
    assert match
    css = b64decode(match.group(1)).decode()
    assert "data:image/svg+xml;base64," in css
    assert "querySelector('.home-brand')" in preview
    assert "querySelector('.status-card')" in preview
    assert ".theme-effect-surface{position:absolute;inset:0" in preview
    assert not read_registry(tmp_path).entries


@pytest.mark.parametrize("change", ["v1", "extra_script", "missing", "unsafe", "runtime"])
def test_manifest_rejects_undeclared_or_incompatible_code(tmp_path: Path, change: str) -> None:
    files = executable()
    metadata = json.loads(files["ocean/theme-package.json"])
    if change == "v1":
        metadata["schema_version"] = 1
    elif change == "extra_script":
        files["ocean/other.js"] = b"alert(1)"
    elif change == "missing":
        del files["ocean/effects/main.js"]
    elif change == "unsafe":
        metadata["effects"]["entry"] = "../outside.js"
    else:
        metadata["effects"]["runtime"] = "server"
    files["ocean/theme-package.json"] = json.dumps(metadata).encode()
    assert ready(tmp_path, files).candidates[0].error


def test_v1_registry_is_migrated_with_rescue_copy(tmp_path: Path) -> None:
    registry = tmp_path / "_registry/current.json"
    registry.parent.mkdir(parents=True)
    registry.write_text('{"schema_version":1}')
    state = read_registry(tmp_path)
    write_registry(tmp_path, state)
    assert read_registry(tmp_path).schema_version == 2
    assert (registry.parent / "before-effects-v2.json").is_file()


@pytest.mark.parametrize("name", ["tilt"])
def test_bundled_examples_are_installable(tmp_path: Path, name: str) -> None:
    from config.theme_packages.archive import extract_archive, inspect_collection

    archive = Path(__file__).resolve().parents[2] / "examples/theme-effects" / f"{name}.zip"
    extract_archive(archive.read_bytes(), tmp_path / "example")
    candidates = inspect_collection(tmp_path / "example")
    assert len(candidates) == 1
    assert not candidates[0].error, candidates[0].detail
    assert candidates[0].effects_digest
