"""File-backed catalog of Web App UI themes.

Models and token resolution live in ``webapp_themes_models``; descriptor
loading/writing and default seeding in ``webapp_themes_store``. This module
keeps the catalog-level API and re-exports the shared surface.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .webapp_themes_models import (  # noqa: F401
    DEFAULT_THEME_ADMIN_TOKEN_KEYS,
    DEFAULT_THEME_KEYS,
    DEFAULT_WEBAPP_THEME_KEY,
    LEGACY_LIGHT_THEME_KEY,
    THEME_DISPLAY_ORDER,
    ColorScheme,
    ThemeTokens,
    WebappTheme,
    WebappThemesConfig,
    _config_with_synced_default_flags,
    _find_theme_data,
    _normalize_legacy_light_alias_data,
    _safe_theme_key,
    _sorted_themes,
    _theme_active_variant,
    _theme_sort_key,
    _theme_with_variant,
    _themes_config_from_list,
    _tokens_to_json,
    _variant_key,
    resolve_webapp_theme_tokens,
)
from .webapp_themes_store import (  # noqa: F401
    DEFAULT_THEMES_SOURCE_DIR,
    THEME_DESCRIPTOR_FILENAME,
    _builtin_theme_assets_need_refresh,
    _copy_default_theme_assets,
    _theme_dir_path,
    _theme_file_path,
    _theme_from_descriptor,
    _write_webapp_theme_file,
    default_webapp_theme_asset_file,
    default_webapp_theme_css_files,
    default_webapp_theme_descriptors,
    ensure_default_webapp_theme_descriptor_files,
    load_webapp_theme_dir,
    load_webapp_theme_file,
    write_webapp_theme_dir,
)

logger = logging.getLogger(__name__)


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
