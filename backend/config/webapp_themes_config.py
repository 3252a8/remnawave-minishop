"""File-backed catalog of Web App UI themes."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

ColorScheme = Literal["light", "dark"]
DEFAULT_WEBAPP_THEME_KEY = "dark"
LEGACY_LIGHT_THEME_KEY = "light"
DEFAULT_THEME_ADMIN_TOKEN_KEYS = {
    "admin_bg",
    "admin_surface",
    "admin_surface_2",
    "admin_elev",
    "admin_border",
    "admin_border_strong",
    "admin_text",
    "admin_muted",
    "admin_dim",
    "admin_chart_stroke",
    "admin_chart_fill",
}


class ThemeTokens(BaseModel):
    """CSS design tokens for the subscription Mini App shell."""

    model_config = {"extra": "ignore"}

    color_scheme: ColorScheme = "dark"
    style_preset: str | None = None
    accent: str | None = None
    bg: str | None = None
    panel: str | None = None
    panel_2: str | None = None
    panel_3: str | None = None
    border: str | None = None
    border_strong: str | None = None
    text: str | None = None
    muted: str | None = None
    dim: str | None = None
    danger: str | None = None
    danger_text: str | None = None
    danger_soft: str | None = None
    danger_border: str | None = None
    success: str | None = None
    success_text: str | None = None
    success_soft: str | None = None
    success_border: str | None = None
    warning: str | None = None
    warning_text: str | None = None
    warning_soft: str | None = None
    warning_border: str | None = None
    info: str | None = None
    info_text: str | None = None
    info_soft: str | None = None
    info_border: str | None = None
    blue: str | None = None
    radius: str | None = None
    accent_contrast: str | None = None
    surface_sheen: str | None = None
    surface_sheen_soft: str | None = None
    surface_hover: str | None = None
    surface_muted: str | None = None
    surface_subtle: str | None = None
    surface_subtle_border: str | None = None
    overlay_scrim: str | None = None
    nav_bg: str | None = None
    rail_bg: str | None = None
    shadow_soft: str | None = None
    shadow_strong: str | None = None
    shadow_popover: str | None = None
    inset_highlight: str | None = None
    font_sans: str | None = None
    font_logo: str | None = None
    font_mono: str | None = None
    home_logo_scale: int | None = None
    home_logo_scale_desktop: int | None = None
    home_logo_scale_mobile: int | None = None
    admin_bg: str | None = None
    admin_surface: str | None = None
    admin_surface_2: str | None = None
    admin_elev: str | None = None
    admin_border: str | None = None
    admin_border_strong: str | None = None
    admin_text: str | None = None
    admin_muted: str | None = None
    admin_dim: str | None = None
    admin_chart_stroke: str | None = None
    admin_chart_fill: str | None = None

    @field_validator("accent")
    @classmethod
    def _normalize_accent_hex(cls, value: str | None) -> str | None:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return None
        match = re.fullmatch(r"#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", raw)
        if not match:
            raise ValueError("accent must be a hex color (#RGB or #RRGGBB)")
        hex_value = match.group(1).lower()
        if len(hex_value) == 3:
            hex_value = "".join(char * 2 for char in hex_value)
        return f"#{hex_value}"

    @field_validator("home_logo_scale", "home_logo_scale_desktop", "home_logo_scale_mobile")
    @classmethod
    def _normalize_home_logo_scale(cls, value: int | None) -> int | None:
        if value is None:
            return None
        scale = int(value)
        if scale < 50 or scale > 300:
            raise ValueError("home logo scale must be between 50 and 300 percent")
        return scale


class WebappTheme(BaseModel):
    """Single theme descriptor loaded from WEBAPP_THEMES_DIR/<key>/theme.json."""

    model_config = {"extra": "ignore"}

    key: str = Field(min_length=1, max_length=64)
    names: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    default: bool = False
    use_primary_accent: bool = True
    use_in_admin: bool = True
    css_file: str | None = None
    assets_version: int = 1
    active_variant: ColorScheme | None = None
    variants: dict[str, ThemeTokens] = Field(default_factory=dict)
    variant_alias_for: str | None = None
    hidden: bool = False
    tokens: ThemeTokens = Field(default_factory=ThemeTokens)

    @field_validator("variant_alias_for")
    @classmethod
    def _normalize_variant_alias_for(cls, value: str | None) -> str | None:
        safe_key = _safe_theme_key(value or "")
        return safe_key

    @field_validator("variants", mode="before")
    @classmethod
    def _normalize_variants(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        out: dict[str, Any] = {}
        for raw_key, raw_tokens in value.items():
            key = str(raw_key or "").strip().lower()
            if key in {"dark", "light"}:
                out[key] = raw_tokens
        return out


class WebappThemesConfig(BaseModel):
    """Runtime catalog assembled from individual theme descriptor files."""

    model_config = {"extra": "ignore"}

    default_theme: str = "dark"
    themes: list[WebappTheme] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_default_and_keys(self) -> WebappThemesConfig:
        keys = [t.key for t in self.themes]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate theme keys")
        if self.themes and self.default_theme not in keys:
            raise ValueError("default_theme must match a theme key")
        return self

    def theme_by_key(self, key: str) -> WebappTheme | None:
        for theme in self.themes:
            if theme.key == key:
                return theme
        return None

    def enabled_themes(self) -> list[WebappTheme]:
        return [theme for theme in self.themes if theme.enabled]


DEFAULT_THEME_KEYS = ("dark", "light", "windows95", "ascii")
THEME_DESCRIPTOR_FILENAME = "theme.json"
DEFAULT_THEMES_SOURCE_DIR = Path(__file__).resolve().parents[1] / "bot" / "app" / "web" / "themes"


def _safe_theme_key(value: str) -> str | None:
    key = str(value or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key):
        return key
    return None


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


def _tokens_to_json(tokens: ThemeTokens | dict[str, Any] | None) -> dict[str, Any]:
    if tokens is None:
        return {}
    if isinstance(tokens, ThemeTokens):
        return tokens.model_dump(mode="json", exclude_none=True)
    if isinstance(tokens, dict):
        return {k: v for k, v in tokens.items() if v is not None}
    return {}


def _variant_key(value: Any) -> ColorScheme | None:
    raw = str(value or "").strip().lower()
    if raw in {"dark", "light"}:
        return raw  # type: ignore[return-value]
    return None


def _theme_active_variant(theme: WebappTheme, variant: Any = None) -> ColorScheme | None:
    requested = _variant_key(variant)
    if requested and requested in theme.variants:
        return requested
    active = _variant_key(theme.active_variant)
    if active and active in theme.variants:
        return active
    scheme = _variant_key(theme.tokens.color_scheme)
    if scheme and scheme in theme.variants:
        return scheme
    if theme.variants:
        if "dark" in theme.variants:
            return "dark"
        if "light" in theme.variants:
            return "light"
    return active


def resolve_webapp_theme_tokens(theme: WebappTheme, variant: Any = None) -> ThemeTokens:
    """Return the effective token set for a theme, merging active variant overrides."""
    data = _tokens_to_json(theme.tokens)
    active = _theme_active_variant(theme, variant)
    if active and active in theme.variants:
        data.update(_tokens_to_json(theme.variants.get(active)))
    return ThemeTokens.model_validate(data)


def _theme_with_variant(theme: WebappTheme, variant: ColorScheme) -> WebappTheme:
    data = theme.model_dump(mode="json", exclude_none=True)
    data["active_variant"] = variant
    return WebappTheme.model_validate(data)


def _find_theme_data(themes: list[Any], key: str) -> dict[str, Any] | None:
    for theme in themes:
        if isinstance(theme, dict) and str(theme.get("key") or "") == key:
            return theme
    return None


def _normalize_legacy_light_alias_data(data: dict[str, Any]) -> dict[str, Any]:
    themes = data.get("themes", [])
    if not isinstance(themes, list):
        return data
    dark = _find_theme_data(themes, DEFAULT_WEBAPP_THEME_KEY)
    light = _find_theme_data(themes, LEGACY_LIGHT_THEME_KEY)
    if light is not None:
        light.setdefault("variant_alias_for", DEFAULT_WEBAPP_THEME_KEY)
        light.setdefault("active_variant", "light")
        light.setdefault("hidden", True)

    if str(data.get("default_theme") or "") == LEGACY_LIGHT_THEME_KEY and dark is not None:
        data["default_theme"] = DEFAULT_WEBAPP_THEME_KEY
        dark["active_variant"] = "light"
        if light is not None:
            light["default"] = False
    return data


def _config_with_synced_default_flags(config: WebappThemesConfig) -> WebappThemesConfig:
    data = config.model_dump(mode="json", exclude_none=True)
    data = _normalize_legacy_light_alias_data(data)
    default_theme = str(data.get("default_theme") or "dark")
    themes = data.get("themes", [])
    for theme in themes:
        if isinstance(theme, dict):
            theme["default"] = theme.get("key") == default_theme

    def _sort_key(item: tuple[int, Any]) -> tuple[int, int]:
        idx, theme = item
        if not isinstance(theme, dict):
            return (len(THEME_DISPLAY_ORDER), idx)
        try:
            priority = THEME_DISPLAY_ORDER.index(str(theme.get("key") or ""))
        except ValueError:
            priority = len(THEME_DISPLAY_ORDER)
        return (priority, idx)

    data["themes"] = [theme for _, theme in sorted(enumerate(themes), key=_sort_key)]
    return WebappThemesConfig.model_validate(data)


THEME_DISPLAY_ORDER = ("dark", "light")


def _theme_sort_key(theme: WebappTheme, index: int) -> tuple[int, int]:
    try:
        priority = THEME_DISPLAY_ORDER.index(theme.key)
    except ValueError:
        priority = len(THEME_DISPLAY_ORDER)
    return (priority, index)


def _sorted_themes(themes: list[WebappTheme]) -> list[WebappTheme]:
    return [
        theme
        for _, theme in sorted(
            ((_theme_sort_key(t, i), t) for i, t in enumerate(themes)),
            key=lambda pair: pair[0],
        )
    ]


def _themes_config_from_list(
    default_theme: str | None,
    themes: list[WebappTheme],
) -> WebappThemesConfig:
    keys = {theme.key for theme in themes}
    descriptor_default = next(
        (theme.key for theme in themes if theme.default and theme.key not in DEFAULT_THEME_KEYS),
        None,
    ) or next((theme.key for theme in themes if theme.default), None)
    resolved_default = default_theme or descriptor_default or "dark"
    if themes and resolved_default not in keys:
        resolved_default = "dark" if "dark" in keys else themes[0].key
    config = WebappThemesConfig(default_theme=resolved_default, themes=_sorted_themes(themes))
    return _config_with_synced_default_flags(config)


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
            try:
                tmp_path.unlink()
            except OSError:
                pass
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


def _strip_default_theme_admin_tokens(theme_data: dict[str, Any]) -> bool:
    """Remove legacy default-theme admin palette overrides."""
    changed = False
    token_sets: list[dict[str, Any]] = []
    tokens = theme_data.get("tokens")
    if isinstance(tokens, dict):
        token_sets.append(tokens)
    variants = theme_data.get("variants")
    if isinstance(variants, dict):
        token_sets.extend(value for value in variants.values() if isinstance(value, dict))
    for token_set in token_sets:
        for key in DEFAULT_THEME_ADMIN_TOKEN_KEYS:
            if key in token_set:
                token_set.pop(key, None)
                changed = True
    return changed


def ensure_webapp_core_themes(
    config: WebappThemesConfig, primary_accent: str
) -> tuple[WebappThemesConfig, bool]:
    """Keep the built-in themes available without clobbering custom edits."""
    data = config.model_dump(mode="json", exclude_none=True)
    themes = data.setdefault("themes", [])
    by_key = {str(theme.get("key")): theme for theme in themes if isinstance(theme, dict)}
    changed = False
    builtin_by_key = {
        theme.key: theme.model_dump(mode="json", exclude_none=True)
        for theme in builtin_webapp_themes_config(primary_accent).themes
    }

    for builtin_data in builtin_by_key.values():
        builtin_key = str(builtin_data.get("key") or "")
        existing = by_key.get(builtin_key)
        if existing is None:
            themes.append(builtin_data)
            by_key[builtin_key] = builtin_data
            changed = True
            continue

        if existing.get("enabled") is False:
            existing["enabled"] = True
            changed = True

        if "use_primary_accent" not in existing:
            existing["use_primary_accent"] = builtin_data.get("use_primary_accent", True)
            changed = True

        if "use_in_admin" not in existing:
            existing["use_in_admin"] = builtin_data.get("use_in_admin", True)
            changed = True

        if int(existing.get("assets_version") or 0) < int(builtin_data.get("assets_version") or 1):
            existing["assets_version"] = builtin_data.get("assets_version", 1)
            changed = True

        if builtin_key in {"windows95", "ascii"} and not existing.get("css_file"):
            existing["css_file"] = builtin_data.get("css_file")
            changed = True

        if builtin_key == LEGACY_LIGHT_THEME_KEY:
            for key, value in {
                "variant_alias_for": DEFAULT_WEBAPP_THEME_KEY,
                "active_variant": "light",
                "hidden": True,
            }.items():
                if existing.get(key) != value:
                    existing[key] = value
                    changed = True
            if existing.get("css_file"):
                existing.pop("css_file", None)
                changed = True

        if builtin_key == DEFAULT_WEBAPP_THEME_KEY and _strip_default_theme_admin_tokens(existing):
            changed = True

        tokens = existing.setdefault("tokens", {})
        builtin_tokens = builtin_data.get("tokens", {})
        for token_key in ("color_scheme", "style_preset"):
            if token_key in builtin_tokens and not tokens.get(token_key):
                tokens[token_key] = builtin_tokens[token_key]
                changed = True

        if builtin_key == DEFAULT_WEBAPP_THEME_KEY:
            variants = existing.setdefault("variants", {})
            if not isinstance(variants, dict):
                existing["variants"] = variants = {}
                changed = True
            builtin_variants = builtin_data.get("variants", {})
            existing_tokens_snapshot = dict(tokens)
            if "dark" not in variants:
                variants["dark"] = existing_tokens_snapshot or builtin_variants.get("dark", {})
                changed = True
            if "light" not in variants and isinstance(builtin_variants, dict):
                variants["light"] = builtin_variants.get("light", {})
                changed = True
            if not existing.get("active_variant"):
                existing["active_variant"] = _variant_key(tokens.get("color_scheme")) or "dark"
                changed = True

    keys = {str(theme.get("key")) for theme in themes if isinstance(theme, dict)}
    if themes and data.get("default_theme") not in keys:
        data["default_theme"] = "dark" if "dark" in keys else str(themes[0].get("key") or "dark")
        changed = True

    normalized = _config_with_synced_default_flags(WebappThemesConfig.model_validate(data))
    if normalized.model_dump(mode="json", exclude_none=True) != data:
        changed = True
    return normalized, changed


def builtin_webapp_themes_config(primary_accent: str) -> WebappThemesConfig:
    """Default catalog backed by repository theme descriptor files."""
    accent = (primary_accent or "#00fe7a").strip() or "#00fe7a"
    themes: list[WebappTheme] = []
    descriptors = default_webapp_theme_descriptors()
    for key in DEFAULT_THEME_KEYS:
        raw = descriptors.get(key)
        if not raw:
            continue
        theme = _theme_from_descriptor(
            DEFAULT_THEMES_SOURCE_DIR / key / THEME_DESCRIPTOR_FILENAME,
            raw,
        )
        if theme is None:
            continue
        if theme.key == "dark" and not theme.tokens.accent:
            theme.tokens.accent = accent
        themes.append(theme)
    return _themes_config_from_list(None, themes)


def apply_webapp_theme_env_overrides(
    config: WebappThemesConfig, env_default_theme: str | None
) -> WebappThemesConfig:
    """If WEBAPP_DEFAULT_THEME is set and matches a theme key, override the default theme."""
    raw = (env_default_theme or "").strip()
    if not raw:
        return config
    data = config.model_dump(mode="json", exclude_none=True)
    if raw == LEGACY_LIGHT_THEME_KEY:
        dark = _find_theme_data(data.get("themes", []), DEFAULT_WEBAPP_THEME_KEY)
        if dark is None:
            logger.warning("WEBAPP_DEFAULT_THEME=%r ignored: default theme is missing", raw)
            return config
        data["default_theme"] = DEFAULT_WEBAPP_THEME_KEY
        dark["active_variant"] = "light"
        return _config_with_synced_default_flags(WebappThemesConfig.model_validate(data))
    if config.theme_by_key(raw) is None:
        logger.warning("WEBAPP_DEFAULT_THEME=%r ignored: no such theme in catalog", raw)
        return config
    data["default_theme"] = raw
    return _config_with_synced_default_flags(WebappThemesConfig.model_validate(data))


def resolved_webapp_themes_catalog(
    *,
    theme_dir: str | Path,
    primary_accent: str,
    env_default_theme: str | None,
) -> WebappThemesConfig:
    """Load themes from WEBAPP_THEMES_DIR, seeding defaults when possible."""
    ensure_default_webapp_theme_descriptor_files(theme_dir)

    themes = load_webapp_theme_dir(theme_dir)
    config = _themes_config_from_list(None, themes)
    config, changed = ensure_webapp_core_themes(config, primary_accent)
    if changed:
        try:
            write_webapp_theme_dir(theme_dir, config, delete_missing=False)
        except OSError as exc:
            logger.warning("Could not update webapp theme descriptors in %s: %s", theme_dir, exc)
    return apply_webapp_theme_env_overrides(config, env_default_theme)


def merge_primary_accent_into_tokens(
    tokens: ThemeTokens, primary_accent: str, *, only_if_token_missing: bool = True
) -> ThemeTokens:
    """Fill accent from WEBAPP_PRIMARY_COLOR when a token set omits accent."""
    base = tokens.model_copy(deep=True)
    accent = (primary_accent or "").strip()
    if not accent:
        return base
    if only_if_token_missing and base.accent:
        return base
    base.accent = accent
    return base


def merge_primary_accent_into_theme_tokens(
    theme: WebappTheme, primary_accent: str, *, only_if_token_missing: bool = True
) -> ThemeTokens:
    """Fill accent from WEBAPP_PRIMARY_COLOR when theme tokens omit accent."""
    return merge_primary_accent_into_tokens(
        resolve_webapp_theme_tokens(theme),
        primary_accent,
        only_if_token_missing=only_if_token_missing,
    )


def effective_webapp_theme_tokens(theme: WebappTheme, primary_accent: str) -> ThemeTokens:
    tokens = resolve_webapp_theme_tokens(theme)
    return (
        merge_primary_accent_into_tokens(tokens, primary_accent)
        if theme.use_primary_accent
        else tokens
    )


def resolve_webapp_theme_selection(
    config: WebappThemesConfig,
    theme_key: str | None = None,
) -> WebappTheme | None:
    """Resolve a requested/default theme, including legacy variant aliases."""
    raw_key = str(theme_key or "").strip()
    if raw_key == LEGACY_LIGHT_THEME_KEY:
        dark = config.theme_by_key(DEFAULT_WEBAPP_THEME_KEY)
        if dark is not None and dark.enabled:
            return _theme_with_variant(dark, "light")

    theme: WebappTheme | None = None
    if raw_key:
        theme = config.theme_by_key(raw_key)
        if theme is not None and not theme.enabled:
            theme = None

    if theme is None:
        default_key = config.default_theme
        if default_key == LEGACY_LIGHT_THEME_KEY:
            dark = config.theme_by_key(DEFAULT_WEBAPP_THEME_KEY)
            if dark is not None and dark.enabled:
                return _theme_with_variant(dark, "light")
        theme = config.theme_by_key(default_key)

    if theme is None:
        enabled = config.enabled_themes()
        theme = enabled[0] if enabled else None

    if theme is None:
        return None

    if theme.variant_alias_for:
        target = config.theme_by_key(theme.variant_alias_for)
        variant = _variant_key(theme.active_variant) or _variant_key(theme.tokens.color_scheme)
        if target is not None and target.enabled and variant is not None:
            return _theme_with_variant(target, variant)
    return theme


def effective_webapp_theme_accent(
    config: WebappThemesConfig,
    primary_accent: str,
    *,
    theme_key: str | None = None,
) -> str:
    """Return the accent color users see for the selected/default Web App theme."""
    try:
        fallback = ThemeTokens(accent=primary_accent or "#00fe7a").accent or "#00fe7a"
    except ValueError:
        fallback = "#00fe7a"
    theme = resolve_webapp_theme_selection(config, theme_key)
    if theme is None:
        return fallback

    tokens = effective_webapp_theme_tokens(theme, fallback)
    return tokens.accent or fallback


def public_theme_payload(theme: WebappTheme, primary_accent: str) -> dict[str, object]:
    tokens = effective_webapp_theme_tokens(theme, primary_accent)
    payload: dict[str, object] = {
        "key": theme.key,
        "names": dict(theme.names),
        "enabled": bool(theme.enabled),
        "use_primary_accent": bool(theme.use_primary_accent),
        "use_in_admin": bool(theme.use_in_admin),
        "assets_version": int(theme.assets_version or 1),
        "active_variant": _theme_active_variant(theme) or tokens.color_scheme,
        "tokens": tokens.model_dump(mode="json", exclude_none=True),
    }
    if theme.css_file:
        payload["css_file"] = theme.css_file
    if theme.variant_alias_for:
        payload["variant_alias_for"] = theme.variant_alias_for
    if theme.hidden:
        payload["hidden"] = True
    return payload


def public_themes_catalog_payload(
    config: WebappThemesConfig, primary_accent: str, *, enabled_only: bool = False
) -> dict[str, object]:
    themes = [
        theme
        for theme in config.themes
        if not enabled_only or (theme.enabled and not theme.hidden and not theme.variant_alias_for)
    ]
    return {
        "default_theme": config.default_theme,
        "themes": [public_theme_payload(theme, primary_accent) for theme in themes],
    }
