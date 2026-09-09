"""Upgrade compatibility for server-installed themes without package metadata."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bot.app.web.webapp.assets_theme import _load_theme_css_asset
from config.theme_packages.models import PackageError
from config.theme_packages.preview import preview_installed, render_preview
from config.theme_packages.registry import asset_path, library, read_registry, write_registry
from config.webapp_themes_config import public_theme_payload, resolved_webapp_themes_catalog
from config.webapp_themes_models import WebappTheme, WebappThemesConfig
from config.webapp_themes_store import load_webapp_theme_dir, write_webapp_theme_dir
from tests.unit.test_theme_packages import install, ready


def legacy(root: Path, key: str = "CustomTheme") -> Path:
    folder = root / key
    folder.mkdir(parents=True)
    (folder / "theme.json").write_text(
        json.dumps(
            {
                # Historically the key can be inferred from the folder name.
                "names": {"en": "Existing theme"},
                "default": True,
                "use_primary_accent": False,
                "use_in_admin": False,
                "css_file": "revisions/local/style.css",
                "tokens": {"bg": "#123456", "accent": "#abcdef"},
                "variants": {"light": {"bg": "#ffffff"}},
            }
        ),
        encoding="utf-8",
    )
    styles = folder / "revisions/local"
    styles.mkdir(parents=True)
    (styles / "style.css").write_text(
        ".theme-key-" + key + '{color:#abcdef;background:url("icon.png?v=2")} '
        '.local{background:url("/webapp-theme-assets/' + key + '/revisions/local/icon.png?v=1")} '
        '.missing{background:url("missing.png")} '
        '@import url("https://example.invalid/font.css"); '
        '.remote{background:url("https://example.invalid/background.png")}',
        encoding="utf-8",
    )
    (styles / "icon.png").write_bytes(b"local-image")
    return folder


def test_upgrade_without_metadata_preserves_active_theme_css_and_settings(tmp_path: Path) -> None:
    folder = legacy(tmp_path)
    config = resolved_webapp_themes_catalog(
        theme_dir=tmp_path, primary_accent="#00fe7a", env_default_theme=None
    )
    assert config.default_theme == "CustomTheme"
    theme = config.theme_by_key("CustomTheme")
    assert theme is not None and not theme.use_in_admin and not theme.use_primary_accent
    assert theme.variants["light"].bg == "#ffffff"
    item = next(item for item in library(tmp_path, config).installations if item.key == theme.key)
    assert not item.managed and item.metadata is None and item.preview_url == ""
    assert item.source is None and not item.version
    assert not (folder / "theme-package.json").exists()
    assert not (folder / "preview.webp").exists()
    css, _etag = _load_theme_css_asset(
        tmp_path.as_posix(), Path("CustomTheme/revisions/local/style.css")
    )
    assert "icon.png?v=2" in css and "https://example.invalid" in css
    assert public_theme_payload(theme, "#00fe7a")["key"] == "CustomTheme"


def test_legacy_preview_without_image_tolerates_old_urls_and_missing_resources(
    tmp_path: Path,
) -> None:
    folder = legacy(tmp_path)
    document = preview_installed(tmp_path, "CustomTheme", "light")
    assert "theme-key-CustomTheme" in document and "--bg:#ffffff" in document
    assert "data:image/png;base64,bG9jYWwtaW1hZ2U=" in document
    assert "example.invalid" not in document and "icon.png?v=" not in document
    assert "default-src 'none'" in document
    (folder / "revisions/local/style.css").unlink()
    assert "--bg:#123456" in preview_installed(tmp_path, "CustomTheme", "dark")


def test_legacy_preview_skips_unsafe_tokens_without_weakening_package_validation(
    tmp_path: Path,
) -> None:
    theme = WebappTheme(
        key="custom", tokens={"bg": "url(https://example.invalid/a)", "accent": "#abcdef"}
    )
    document = render_preview(tmp_path, theme, "dark", legacy=True)
    assert "--accent:#abcdef" in document and "example.invalid" not in document
    with pytest.raises(PackageError):
        render_preview(tmp_path, theme, "dark")


def test_manual_edits_and_deletion_remain_visible_after_managed_install(tmp_path: Path) -> None:
    folder = legacy(tmp_path)
    install(tmp_path, ready(tmp_path))
    themes = load_webapp_theme_dir(tmp_path)
    old = next(theme for theme in themes if theme.key == "CustomTheme")
    old.tokens.accent = "#112233"
    old.variants["light"].accent = "#445566"
    write_webapp_theme_dir(
        tmp_path,
        WebappThemesConfig(default_theme="ocean", themes=themes),
        expected_generation=read_registry(tmp_path).generation,
    )
    descriptor = json.loads((folder / "theme.json").read_text(encoding="utf-8"))
    descriptor["tokens"]["bg"] = "#654321"
    descriptor["names"]["en"] = "Edited over SFTP"
    descriptor["variants"]["light"]["bg"] = "#eeeeee"
    (folder / "theme.json").write_text(json.dumps(descriptor), encoding="utf-8")
    config = resolved_webapp_themes_catalog(
        theme_dir=tmp_path, primary_accent="#00fe7a", env_default_theme=None
    )
    old = config.theme_by_key("CustomTheme")
    assert old is not None
    assert old.tokens.bg == "#654321" and old.tokens.accent == "#112233"
    assert old.variants["light"].bg == "#eeeeee" and old.variants["light"].accent == "#445566"
    assert old.names["en"] == "Edited over SFTP"
    assert not old.default and config.default_theme == "ocean"
    (folder / "theme.json").unlink()
    assert "CustomTheme" not in {theme.key for theme in load_webapp_theme_dir(tmp_path)}


def test_registry_without_baselines_keeps_saved_settings_for_existing_theme(tmp_path: Path) -> None:
    folder = legacy(tmp_path)
    state = read_registry(tmp_path)
    theme = load_webapp_theme_dir(tmp_path)[0]
    theme.tokens.accent = "#fedcba"
    state.preferences[theme.key] = theme
    write_registry(tmp_path, state)
    assert load_webapp_theme_dir(tmp_path)[0].tokens.accent == "#fedcba"
    (folder / "theme.json").unlink()
    assert load_webapp_theme_dir(tmp_path) == []


def test_legacy_resource_paths_cannot_escape_volume(tmp_path: Path) -> None:
    with pytest.raises(PackageError, match="unsafe_path"):
        asset_path(tmp_path, Path("../outside.png"))


@pytest.mark.parametrize(
    "descriptor", [{}, {"names": {"en": "Old theme"}}, {"tokens": {"bg": "#102030"}}]
)
def test_minimal_legacy_descriptor_needs_no_optional_files(
    tmp_path: Path, descriptor: dict[str, object]
) -> None:
    folder = tmp_path / "old_theme"
    folder.mkdir()
    (folder / "theme.json").write_text(json.dumps(descriptor), encoding="utf-8")
    themes = load_webapp_theme_dir(tmp_path)
    assert [theme.key for theme in themes] == ["old_theme"]
    item = library(
        tmp_path, WebappThemesConfig(default_theme="old_theme", themes=themes)
    ).installations[0]
    assert item.preview_url == "" and item.metadata is None
    assert "theme-key-old_theme" in preview_installed(tmp_path, "old_theme", "dark")
