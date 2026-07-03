"""Pydantic models, token resolution and catalog normalization for Web App themes.

Split out of ``webapp_themes_config`` (which re-exports this surface).
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

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

THEME_DISPLAY_ORDER = ("dark", "light")


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


def _safe_theme_key(value: str) -> str | None:
    key = str(value or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key):
        return key
    return None


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
    if raw == "dark":
        return "dark"
    if raw == "light":
        return "light"
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


DEFAULT_THEME_KEYS = ("dark", "light", "windows95", "ascii")
