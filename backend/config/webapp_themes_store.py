"""File-backed loading, writing and default seeding of Web App theme descriptors.

Split out of ``webapp_themes_config`` (which re-exports this surface).
"""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path
from typing import Any

from .webapp_themes_models import (
    DEFAULT_THEME_KEYS,
    LEGACY_LIGHT_THEME_KEY,
    WebappTheme,
    WebappThemesConfig,
    _config_with_synced_default_flags,
    _safe_theme_key,
)

logger = logging.getLogger(__name__)

THEME_DESCRIPTOR_FILENAME = "theme.json"
DEFAULT_THEMES_SOURCE_DIR = Path(__file__).resolve().parents[1] / "bot" / "app" / "web" / "themes"


def _theme_dir_path(theme_dir: str | Path, key: str) -> Path:
    safe_key = _safe_theme_key(key)
    if not safe_key:
        raise ValueError(f"invalid theme key: {key!r}")
    return Path(theme_dir).expanduser() / safe_key


def _theme_file_path(theme_dir: str | Path, key: str) -> Path:
    return _theme_dir_path(theme_dir, key) / THEME_DESCRIPTOR_FILENAME


def default_webapp_theme_css_files() -> dict[str, str]:
    """Read default theme CSS from repository files."""
    out: dict[str, str] = {}
    for key in DEFAULT_THEME_KEYS:
        source_dir = DEFAULT_THEMES_SOURCE_DIR / key
        for source_path in sorted(source_dir.rglob("*.css")):
            rel_path = Path(key) / source_path.relative_to(source_dir)
            try:
                content = source_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning(
                    "Default webapp theme CSS source file is missing: %s (%s)",
                    source_path,
                    exc,
                )
                continue
            out[rel_path.as_posix()] = content if content.endswith("\n") else f"{content}\n"
    return out


def default_webapp_theme_asset_file(rel_path: str | Path) -> tuple[bytes, str] | None:
    """Read a default theme asset from the repository theme folder."""
    relative = Path(rel_path)
    if relative.is_absolute() or len(relative.parts) < 2 or ".." in relative.parts:
        return None
    source_path = (DEFAULT_THEMES_SOURCE_DIR / relative).resolve()
    try:
        source_path.relative_to(DEFAULT_THEMES_SOURCE_DIR.resolve())
    except ValueError:
        return None
    try:
        return source_path.read_bytes(), source_path.suffix.lower()
    except OSError:
        return None


def default_webapp_theme_descriptors() -> dict[str, dict[str, Any]]:
    """Read default theme descriptors from repository files."""
    out: dict[str, dict[str, Any]] = {}
    for key in DEFAULT_THEME_KEYS:
        source_path = DEFAULT_THEMES_SOURCE_DIR / key / THEME_DESCRIPTOR_FILENAME
        try:
            raw = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Default webapp theme descriptor is missing or invalid: %s (%s)",
                source_path,
                exc,
            )
            continue
        if not isinstance(raw, dict):
            continue
        safe_key = _safe_theme_key(str(raw.get("key") or source_path.parent.name))
        if safe_key:
            raw["key"] = safe_key
            out[safe_key] = raw
    return out


def _theme_from_descriptor(path: Path, raw: Any) -> WebappTheme | None:
    if not isinstance(raw, dict):
        logger.warning("Ignoring theme descriptor %s: expected JSON object", path)
        return None
    data = dict(raw)
    data["key"] = data.get("key") or (
        path.parent.name if path.name == THEME_DESCRIPTOR_FILENAME else path.stem
    )
    safe_key = _safe_theme_key(str(data["key"]))
    if not safe_key:
        logger.warning("Ignoring theme descriptor %s: invalid theme key %r", path, data["key"])
        return None
    data["key"] = safe_key
    try:
        return WebappTheme.model_validate(data)
    except ValueError as exc:
        logger.warning("Ignoring theme descriptor %s: %s", path, exc)
        return None


def load_webapp_theme_file(path: str | Path) -> WebappTheme | None:
    theme_path = Path(path).expanduser()
    try:
        raw = json.loads(theme_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load webapp theme descriptor from %s: %s", theme_path, exc)
        return None
    return _theme_from_descriptor(theme_path, raw)


def load_webapp_theme_dir(theme_dir: str | Path) -> list[WebappTheme]:
    root = Path(theme_dir).expanduser()
    if not root.exists():
        return []
    themes_by_key: dict[str, WebappTheme] = {}
    for path in sorted(root.glob(f"*/{THEME_DESCRIPTOR_FILENAME}")):
        if path.parent.name.startswith("_"):
            continue
        theme = load_webapp_theme_file(path)
        if theme is None:
            continue
        if theme.key in themes_by_key:
            logger.warning("Ignoring duplicate webapp theme key %s from %s", theme.key, path)
            continue
        themes_by_key[theme.key] = theme
    return list(themes_by_key.values())


def _write_webapp_theme_file(path: Path, theme: WebappTheme) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = theme.model_dump(mode="json", exclude_none=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    try:
        tmp_path.write_text(payload, encoding="utf-8")
        tmp_path.replace(path)
    except PermissionError:
        if tmp_path.exists():
            with contextlib.suppress(OSError):
                tmp_path.unlink()
        path.write_text(payload, encoding="utf-8")


def _copy_default_theme_assets(key: str, target_dir: Path, *, overwrite: bool = False) -> None:
    source_dir = DEFAULT_THEMES_SOURCE_DIR / key
    if not source_dir.exists():
        return
    for source_path in sorted(source_dir.rglob("*")):
        if not source_path.is_file() or source_path.name == THEME_DESCRIPTOR_FILENAME:
            continue
        rel_path = source_path.relative_to(source_dir)
        target_path = target_dir / rel_path
        if target_path.exists() and not overwrite:
            continue
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(source_path.read_bytes())
        except OSError as exc:
            logger.warning("Could not create default webapp theme asset %s: %s", target_path, exc)


def _builtin_theme_assets_need_refresh(key: str, target_dir: Path) -> bool:
    if key == LEGACY_LIGHT_THEME_KEY:
        return False

    style_path = target_dir / "style.css"
    try:
        style = style_path.read_text(encoding="utf-8")
    except OSError:
        return True
    if key == "ascii":
        return (
            ".theme-key-ascii" not in style
            or "ascii-spin" not in style
            or "ascii-skeleton-scan" not in style
            or "ascii-boot-type" not in style
            or "Console-style tables" not in style
            or "New webapp surfaces: support, purchase info, password login" not in style
            or "Install guide theme surfaces" not in style
            or "Admin controls: range sliders and sortable rows" not in style
            or "Admin health config alerts" not in style
        )
    if key != "windows95":
        return False
    required_icons = (
        "arrow-right.png",
        "dashboard.png",
        "megaphone.png",
        "paintbrush.png",
        "sliders.png",
        "sparkles.png",
        "tag.png",
    )
    return (
        "lucide-house" not in style
        or "lucide-earth" not in style
        or "lucide-circle-check" not in style
        or "border-radius: 0 !important" not in style
        or "::-webkit-slider-thumb" not in style
        or "?v=9" not in style
        or "lucide-life-buoy" not in style
        or "lucide-qr-code" not in style
        or "New webapp surfaces: support, purchase info, password login" not in style
        or "Install guide theme surfaces" not in style
        or "Admin controls: range sliders and sortable rows" not in style
        or "Admin health config alerts" not in style
        or any(not (target_dir / "icons" / icon).exists() for icon in required_icons)
    )


def ensure_default_webapp_theme_descriptor_files(theme_dir: str | Path | None) -> None:
    """Seed source-controlled default theme folders into the mounted data directory."""
    if not theme_dir:
        return
    root = Path(theme_dir).expanduser()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Could not create webapp themes directory at %s: %s", root, exc)
        return

    existing_has_default = any(theme.default for theme in load_webapp_theme_dir(root))
    existing_by_key = {theme.key: theme for theme in load_webapp_theme_dir(root)}
    for key, descriptor in default_webapp_theme_descriptors().items():
        theme_dir_path = _theme_dir_path(root, key)
        path = _theme_file_path(root, key)
        existing = existing_by_key.get(key)
        source_assets_version = int(descriptor.get("assets_version") or 1)
        should_sync_assets = (
            existing is not None
            and key in DEFAULT_THEME_KEYS
            and (
                int(existing.assets_version or 0) < source_assets_version
                or _builtin_theme_assets_need_refresh(key, theme_dir_path)
            )
        )
        if not path.exists():
            seed_descriptor = dict(descriptor)
            if existing_has_default:
                seed_descriptor["default"] = False
            theme = _theme_from_descriptor(path, seed_descriptor)
            if theme is not None:
                try:
                    _write_webapp_theme_file(path, theme)
                except OSError as exc:
                    logger.warning(
                        "Could not create default webapp theme descriptor %s: %s",
                        path,
                        exc,
                    )
        elif should_sync_assets and existing is not None:
            data = existing.model_dump(mode="json", exclude_none=True)
            data["assets_version"] = source_assets_version
            if descriptor.get("css_file"):
                data["css_file"] = descriptor["css_file"]
            try:
                theme = WebappTheme.model_validate(data)
                _write_webapp_theme_file(path, theme)
            except (OSError, ValueError) as exc:
                logger.warning("Could not update default webapp theme descriptor %s: %s", path, exc)
        _copy_default_theme_assets(key, theme_dir_path, overwrite=should_sync_assets)


def write_webapp_theme_dir(
    theme_dir: str | Path,
    config: WebappThemesConfig,
    *,
    delete_missing: bool = False,
) -> None:
    """Write one theme.json descriptor per theme into WEBAPP_THEMES_DIR/<key>."""
    root = Path(theme_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    normalized = _config_with_synced_default_flags(config)
    keep_paths = set()
    for theme in normalized.themes:
        path = _theme_file_path(root, theme.key)
        _write_webapp_theme_file(path, theme)
        keep_paths.add(path.resolve())

    if not delete_missing:
        return
    for path in root.glob(f"*/{THEME_DESCRIPTOR_FILENAME}"):
        if path.parent.name.startswith("_") or path.resolve() in keep_paths:
            continue
        try:
            path.unlink()
            if not any(path.parent.iterdir()):
                path.parent.rmdir()
        except OSError as exc:
            logger.warning("Could not delete removed webapp theme descriptor %s: %s", path, exc)
