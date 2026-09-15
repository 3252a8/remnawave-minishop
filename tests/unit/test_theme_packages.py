"""Theme package security and all-or-nothing catalogue lifecycle."""

from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from config.theme_packages.archive import deterministic_zip, extract_archive, inspect_collection
from config.theme_packages.css import fork_css, validate_css, validate_token
from config.theme_packages.models import (
    ExportRequest,
    InstallChoice,
    InstallRequest,
    PackageError,
    RepositoryRequest,
    ThemeSource,
)
from config.theme_packages.operations import (
    cancel_import,
    create_import,
    export_themes,
    get_import,
    inspect_import,
    install_import,
    remove_theme,
    rollback_theme,
)
from config.theme_packages.preview_storage import save_preview
from config.theme_packages.providers import repository_parts, safe_url
from config.theme_packages.registry import (
    asset_path,
    effective_theme,
    read_registry,
    write_registry,
)
from config.webapp_themes_models import WebappThemesConfig
from config.webapp_themes_store import load_webapp_theme_dir, write_webapp_theme_dir


def package(
    key: str = "ocean", *, color: str = "#112233", version: str = "1.0.0", prefix: str | None = None
) -> dict[str, bytes]:
    prefix = key + "/" if prefix is None else prefix
    return {
        prefix + "theme.json": json.dumps(
            {
                "key": key,
                "names": {"en": key.title()},
                "css_file": "theme.css",
                "tokens": {"bg": color},
                "enabled": True,
                "default": True,
                "use_in_admin": True,
            }
        ).encode(),
        prefix + "theme-package.json": json.dumps(
            {
                "schema_version": 1,
                "version": version,
                "compatibility": {"theme_api": 1},
            }
        ).encode(),
        prefix + "theme.css": ("html.theme-key-" + key + "{color:" + color + "}").encode(),
    }


def ready(root: Path, files: dict[str, bytes] | None = None):
    return inspect_import(
        root,
        create_import(root, 7, ThemeSource(label="sample.zip")),
        deterministic_zip(files or package()),
    )


def install(
    root: Path,
    record,
    *,
    action: str = "install",
    keys: tuple[str, ...] = ("ocean",),
    generation: int | None = None,
    identity: str = "test-install-0001",
):
    body = InstallRequest.model_validate(
        {
            "choices": [{"key": key, "action": action} for key in keys],
            "expected_generation": read_registry(root).generation
            if generation is None
            else generation,
            "idempotency_key": identity,
        }
    )
    return install_import(root, record.id, 7, body)


def test_install_update_preserves_overrides_rollback_delete_and_export(tmp_path: Path) -> None:
    record = ready(tmp_path)
    assert record.state == "ready", record
    result = install(tmp_path, record)
    assert result.generation == 1
    installed = load_webapp_theme_dir(tmp_path)[0]
    assert not installed.default and installed.use_in_admin
    original_digest = read_registry(tmp_path).entries["ocean"].digest
    installed.tokens.bg = "#abcdef"
    write_webapp_theme_dir(
        tmp_path,
        WebappThemesConfig(
            default_theme="ocean",
            themes=[installed],
        ),
        expected_generation=1,
    )
    assert read_registry(tmp_path).entries["ocean"].overrides["tokens"] == {"bg": "#abcdef"}

    update = ready(tmp_path, package(color="#445566", version="2.0.0"))
    install(tmp_path, update, action="update")
    state = read_registry(tmp_path)
    assert effective_theme("ocean", state.entries["ocean"]).tokens.bg == "#abcdef"
    assert state.entries["ocean"].metadata.version == "2.0.0"
    assert asset_path(tmp_path, Path("ocean/revisions") / original_digest / "theme.css")[
        0
    ].is_file()

    exported = export_themes(tmp_path, ExportRequest(keys=["ocean"], new_key="my-ocean"))
    target = tmp_path / "exported"
    extract_archive(exported, target)
    candidate = inspect_collection(target)[0]
    assert candidate.key == "my-ocean" and not candidate.error
    assert candidate.theme and candidate.theme.tokens.bg == "#445566"
    assert "theme-key-my-ocean" in (target / "my-ocean/theme.css").read_text()

    rollback_theme(tmp_path, "ocean", state.generation)
    state = read_registry(tmp_path)
    assert state.entries["ocean"].digest == original_digest
    assert effective_theme("ocean", state.entries["ocean"]).tokens.bg == "#abcdef"
    with pytest.raises(PackageError, match="active_theme"):
        remove_theme(tmp_path, "ocean", state.generation, "ocean")
    remove_theme(tmp_path, "ocean", state.generation, "dark")
    assert not read_registry(tmp_path).entries


def test_install_preserves_package_admin_usage_preference(tmp_path: Path) -> None:
    files = package()
    descriptor = json.loads(files["ocean/theme.json"])
    descriptor["use_in_admin"] = False
    files["ocean/theme.json"] = json.dumps(descriptor).encode()

    install(tmp_path, ready(tmp_path, files))

    installed = load_webapp_theme_dir(tmp_path)[0]
    assert not installed.use_in_admin


def test_missing_variant_override_does_not_break_managed_theme_loading(tmp_path: Path) -> None:
    files = package()
    descriptor = json.loads(files["ocean/theme.json"])
    descriptor["variants"] = {"dark": {"bg": "#111111"}}
    files["ocean/theme.json"] = json.dumps(descriptor).encode()
    install(tmp_path, ready(tmp_path, files))

    state = read_registry(tmp_path)
    state.entries["ocean"].overrides = {
        "variants": {"dark": {"bg": "#abcdef"}, "light": {"bg": "#ffffff"}}
    }
    write_registry(tmp_path, state)

    theme = next(theme for theme in load_webapp_theme_dir(tmp_path) if theme.key == "ocean")
    assert theme.variants["dark"].bg == "#abcdef"
    assert "light" not in theme.variants


def test_preview_override_is_outside_digest_and_is_exported(tmp_path: Path) -> None:
    record = ready(tmp_path)
    install(tmp_path, record)
    digest = read_registry(tmp_path).entries["ocean"].digest

    from PIL import Image

    image = io.BytesIO()
    Image.new("RGB", (32, 20), "#112233").save(image, format="PNG")
    url, _generation = save_preview(tmp_path, "ocean", image.getvalue())

    state = read_registry(tmp_path)
    assert state.entries["ocean"].digest == digest
    assert state.entries["ocean"].preview_override == "desktop.webp"
    assert url.startswith("/webapp-theme-assets/ocean/previews/")
    exported = export_themes(tmp_path, ExportRequest(keys=["ocean"], new_key="copy"))
    target = tmp_path / "preview-export"
    extract_archive(exported, target)
    assert (target / "copy/preview.webp").is_file()


def test_replay_is_idempotent_and_stale_generations_do_not_write(tmp_path: Path) -> None:
    record = ready(tmp_path)
    install(tmp_path, record, generation=0)
    assert install(tmp_path, record, generation=0).generation == 1
    with pytest.raises(PackageError, match="idempotency_conflict"):
        install(tmp_path, record, generation=1)
    next_record = ready(tmp_path, package(version="2.0.0"))
    with pytest.raises(PackageError, match="catalog_changed"):
        install(tmp_path, next_record, action="update", generation=0)
    assert read_registry(tmp_path).generation == 1


def test_collection_is_atomic_and_duplicate_keys_are_reported(tmp_path: Path) -> None:
    record = ready(tmp_path, {**package(), **package("forest")})
    with pytest.raises(PackageError, match="invalid_theme_selection"):
        install(tmp_path, record, keys=("ocean", "absent"))
    assert not read_registry(tmp_path).entries
    duplicate = ready(tmp_path, {**package(prefix="one/"), **package(prefix="two/")})
    assert all(item.error == "duplicate_theme_key" for item in duplicate.candidates)


def test_actor_ttl_cancel_and_tampering(tmp_path: Path) -> None:
    record = ready(tmp_path)
    with pytest.raises(PackageError, match="import_not_found"):
        get_import(tmp_path, record.id, 8)
    path = tmp_path / "_imports" / record.id / "files/ocean/theme.css"
    path.write_text("body{color:red}")
    with pytest.raises(PackageError, match="import_changed"):
        install(tmp_path, record)
    cancel_import(tmp_path, record.id, 7)
    assert not path.exists()
    with pytest.raises(PackageError, match="import_not_ready"):
        install(tmp_path, record)
    record.created_at = time.time() - 1900
    (tmp_path / "_imports" / record.id / "record.json").write_text(record.model_dump_json())
    with pytest.raises(PackageError, match="import_expired"):
        get_import(tmp_path, record.id, 7)


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "/absolute",
        "C:/outside",
        "ocean/../escape",
        "ocean\\escape",
        "ocean/CON",
        "ocean/theme.json.",
        "ocean/a:b",
        "ocean/\x01file",
    ],
)
def test_archive_paths_are_confined(tmp_path: Path, name: str) -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        info = zipfile.ZipInfo(name)
        info.filename = name
        archive.writestr(info, "{}")
    with pytest.raises(PackageError):
        extract_archive(stream.getvalue(), tmp_path / "files")


def test_symlink_zip_and_case_collisions(tmp_path: Path) -> None:
    for index, entries in enumerate(([("link", 0o120777)], [("a", 0o100644), ("A", 0o100644)])):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for name, mode in entries:
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = mode << 16
                archive.writestr(info, b"target")
        with pytest.raises(PackageError):
            extract_archive(stream.getvalue(), tmp_path / str(index))


def test_safe_svg_asset_is_accepted_and_can_be_referenced_from_css(tmp_path: Path) -> None:
    files = package()
    files["ocean/theme.css"] = b'html.theme-key-ocean{background-image:url("icons/mark.svg")}'
    files["ocean/icons/mark.svg"] = b"""\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs><linearGradient id="paint"><stop offset="0" stop-color="#fff"/></linearGradient></defs>
  <path fill="url(#paint)" d="M2 2h20v20H2z"/>
</svg>
"""

    candidate = ready(tmp_path, files).candidates[0]

    assert not candidate.error
    assert candidate.files == 4


@pytest.mark.parametrize(
    ("svg", "reason"),
    [
        ('<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>', "element script"),
        ('<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>', "attribute onload"),
        (
            '<svg xmlns="http://www.w3.org/2000/svg"><use href="https://example.org/x.svg#x"/></svg>',
            "local fragment",
        ),
        (
            '<svg xmlns="http://www.w3.org/2000/svg" xml:base="https://example.org/"/>',
            "attribute xml:base",
        ),
        ('<!DOCTYPE svg [<!ENTITY x "x">]><svg>&x;</svg>', "DTD and entity"),
    ],
)
def test_unsafe_svg_asset_is_rejected(tmp_path: Path, svg: str, reason: str) -> None:
    files = package()
    files["ocean/icons/mark.svg"] = svg.encode()

    candidate = ready(tmp_path, files).candidates[0]

    assert candidate.error == "unsafe_svg"
    assert candidate.detail.startswith("icons/mark.svg: ")
    assert reason in candidate.detail


@pytest.mark.parametrize(
    "css",
    [
        '@import "https://example.org/a.css";',
        '@\\69mport "https://example.org/a.css";',
        "body{background:url(//example.org/x)}",
        'body{background:url("data:image/svg+xml,x")}',
        'body{background:url("../../secret")}',
        "body{background:u\\72l(https://example.org/x)}",
        "body{background:url(var(--secret))}",
        "body{behavior:url(x.htc)}",
        "body{color:expression(alert(1))}",
    ],
)
def test_external_css_is_rejected(tmp_path: Path, css: str) -> None:
    with pytest.raises(PackageError):
        validate_css(css, tmp_path, "theme.css")


@pytest.mark.parametrize(
    "value", ["red;}body{color:red", "</style><script>", "url(https://x.test/a)"]
)
def test_token_injection_is_rejected(value: str) -> None:
    with pytest.raises(PackageError):
        validate_token(value)


def test_protected_keys_aliases_and_raw_root_packages(tmp_path: Path) -> None:
    assert ready(tmp_path, package("ascii")).candidates[0].error == "protected_theme"
    record = ready(tmp_path, package(prefix=""))
    assert record.candidates[0].path == "."
    install(tmp_path, record)
    assert "ocean" in read_registry(tmp_path).entries


def test_provider_wrappers_and_subdirectory_selection(tmp_path: Path) -> None:
    files = package(prefix="repo-abcd/themes/ocean/")
    extract_archive(deterministic_zip(files), tmp_path / "files")
    assert inspect_collection(tmp_path / "files", "themes/ocean")[0].key == "ocean"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "https://localhost/a/b",
        "https://127.0.0.1/a/b",
        "https://github.com.evil.test/a/b",
        "https://user:secret@github.com/a/b",
        "https://github.com:444/a/b",
        "file:///etc/passwd",
    ],
)
def test_repository_ssrf_boundaries(url: str) -> None:
    with pytest.raises(PackageError):
        repository_parts(RepositoryRequest(url=url))


def test_redirect_allowlist_and_builtin_fork() -> None:
    with pytest.raises(PackageError):
        safe_url("https://169.254.169.254/latest")
    css = fork_css(
        '@import "https://fonts.test/a"; html.theme-key-ascii{color:red}',
        "ascii",
        "mine",
        "theme.css",
    )
    assert "@import" not in css and "theme-key-mine" in css
    with pytest.raises(ValidationError):
        InstallChoice(key="../bad")
    with pytest.raises(ValidationError):
        RepositoryRequest(url="x" * 501)


def test_preview_uses_runtime_logo_units_and_inline_owner_tokens(tmp_path: Path) -> None:
    from config.theme_packages.preview import render_preview
    from config.webapp_themes_models import WebappTheme

    theme = WebappTheme.model_validate(
        {
            "key": "ocean",
            "tokens": {"home_logo_scale": "125", "bg": "#abcdef"},
        }
    )
    document = render_preview(tmp_path, theme, "dark")
    assert "--home-logo-scale:1.25" in document
    assert 'style="' in document and "--bg:#abcdef" in document
    assert "THEME_KEY_PLACEHOLDER" not in document
