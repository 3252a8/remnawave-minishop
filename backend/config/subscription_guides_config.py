"""Loader and validator for Remnawave Subscription Page v1 configs."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class SubscriptionGuidesConfigError(ValueError):
    """Raised when the embedded subscription guides config is invalid."""


APP_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = "data/subpage-config/multiapp.json"
DEFAULT_CONFIG_BUNDLED_PATH = (
    Path(__file__).resolve().parent / "defaults" / "subscription_page_multiapp.json"
)
ALLOWED_LOCALES = {
    "az",
    "be",
    "de",
    "en",
    "es",
    "fa",
    "fr",
    "hi",
    "id",
    "ja",
    "pl",
    "pt",
    "ru",
    "th",
    "tk",
    "tr",
    "uk",
    "uz",
    "vi",
    "zh",
}
ALLOWED_PLATFORMS = {
    "android",
    "androidTV",
    "appleTV",
    "ios",
    "linux",
    "macos",
    "windows",
}
ALLOWED_BUTTON_TYPES = {"copyButton", "external", "subscriptionLink"}
BASE_TRANSLATION_KEYS = (
    "active",
    "bandwidth",
    "connectionKeysHeader",
    "copyLink",
    "expired",
    "expires",
    "expiresIn",
    "getLink",
    "inactive",
    "indefinitely",
    "installationGuideHeader",
    "linkCopied",
    "linkCopiedToClipboard",
    "name",
    "scanQrCode",
    "scanQrCodeDescription",
    "scanToImport",
    "status",
    "unknown",
)
ALLOWED_SVG_COLORS = {
    "red",
    "orange",
    "amber",
    "yellow",
    "lime",
    "green",
    "emerald",
    "teal",
    "cyan",
    "sky",
    "blue",
    "indigo",
    "violet",
    "purple",
    "fuchsia",
    "pink",
    "rose",
    "slate",
    "gray",
    "zinc",
    "neutral",
    "stone",
}
UI_SUBSCRIPTION_INFO_TYPES = {"cards", "collapsed", "expanded", "hidden"}
UI_INSTALLATION_GUIDE_TYPES = {"accordion", "cards", "minimal", "timeline"}
SVG_KEY_RE = re.compile(r"^[A-Za-z]+$")
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")
CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
UNSAFE_SVG_RE = re.compile(
    r"(<\s*/?\s*(?:script|foreignObject|iframe|object|embed|image|use|style|a)\b)"
    r"|(\son[a-z]+\s*=)"
    r"|(javascript\s*:)"
    r"|(data\s*:)",
    re.IGNORECASE,
)
_CONFIG_CACHE: dict[tuple[str, str], dict[str, Any]] = {}
PANEL_CONFIG_KEYS = (
    "config",
    "subscriptionPageConfig",
    "subpageConfig",
    "subPageConfig",
    "pageConfig",
)
PANEL_WRAPPER_KEYS = ("response", "data", "result", *PANEL_CONFIG_KEYS)


def validate_subscription_guides_config_text(raw: str) -> dict[str, Any]:
    """Parse and validate a v1 subscription guides config JSON string."""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SubscriptionGuidesConfigError(f"Invalid JSON: {exc.msg}") from exc
    return validate_subscription_guides_config(payload)


def default_subscription_guides_config_text() -> str:
    try:
        return DEFAULT_CONFIG_BUNDLED_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise SubscriptionGuidesConfigError(
            f"Bundled default config is unavailable: {exc}"
        ) from exc


def resolve_subscription_guides_config_path(settings: Any) -> Path:
    configured_path = str(settings.SUBSCRIPTION_PAGE_CONFIG_PATH or DEFAULT_CONFIG_PATH).strip()
    if not configured_path:
        raise SubscriptionGuidesConfigError("SUBSCRIPTION_PAGE_CONFIG_PATH is empty")
    path = Path(configured_path)
    if not path.is_absolute():
        path = APP_ROOT / path
    return path


def ensure_subscription_guides_config_file(settings: Any) -> Path:
    path = resolve_subscription_guides_config_path(settings)
    if not path.exists():
        raise SubscriptionGuidesConfigError(f"Config file does not exist: {path}")
    return path


def subscription_guides_admin_config_json(settings: Any) -> tuple[str, str]:
    admin_json = str(settings.SUBSCRIPTION_PAGE_CONFIG_JSON or "").strip()
    if admin_json:
        return admin_json, "admin_json"
    return "", "empty"


def load_subscription_guides_config(settings: Any) -> tuple[dict[str, Any], str]:
    """Load the enabled guides config from admin JSON or a configured file path."""

    source, raw = _read_config_source(settings)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    cache_key = (source, digest)
    cached = _CONFIG_CACHE.get(cache_key)
    if cached is not None:
        return copy.deepcopy(cached), source
    config = validate_subscription_guides_config_text(raw)
    _CONFIG_CACHE[cache_key] = copy.deepcopy(config)
    return config, source


def subscription_guides_status(settings: Any) -> dict[str, Any]:
    """Return a safe status payload for user-facing guide availability checks."""

    if not bool(settings.SUBSCRIPTION_GUIDES_ENABLED):
        return {"enabled": False, "config": None, "source": None, "error": None}
    try:
        config, source = load_subscription_guides_config(settings)
    except SubscriptionGuidesConfigError as exc:
        return {"enabled": False, "config": None, "source": None, "error": str(exc)}
    return {"enabled": True, "config": config, "source": source, "error": None}


def subscription_guides_available(settings: Any) -> bool:
    if not bool(settings.SUBSCRIPTION_GUIDES_ENABLED):
        return False
    admin_json = str(settings.SUBSCRIPTION_PAGE_CONFIG_JSON or "").strip()
    if (
        not (admin_json and bool(settings.SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED))
        and bool(settings.SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED)
        and settings.PANEL_API_URL
        and settings.PANEL_API_KEY
    ):
        return True
    status = subscription_guides_status(settings)
    return bool(status.get("enabled") and status.get("config"))


def extract_subscription_guides_config_from_panel(payload: Any) -> Any:
    """Extract Subscription Page v1 config from flexible Panel API response shapes."""

    return _extract_config_candidate(payload, set())


def validate_panel_subscription_guides_config(
    payload: Any,
    *,
    allow_default_when_missing: bool = False,
) -> dict[str, Any]:
    config = extract_subscription_guides_config_from_panel(payload)
    if config is None:
        if allow_default_when_missing and panel_subscription_page_allowed(payload):
            default_text = default_subscription_guides_config_text()
            return validate_subscription_guides_config_text(default_text)
        raise SubscriptionGuidesConfigError("Panel response does not contain a v1 config")
    return validate_subscription_guides_config(config)


def panel_subscription_page_allowed(payload: Any) -> bool:
    candidate = _find_panel_response_object(payload, set())
    return bool(candidate and candidate.get("webpageAllowed") is True)


def validate_subscription_guides_config(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise SubscriptionGuidesConfigError("Config root must be an object")
    if payload.get("version") != "1":
        raise SubscriptionGuidesConfigError(
            "Only Subscription Page config version '1' is supported"
        )

    locales = _validate_locales(payload.get("locales"))
    svg_library = _validate_svg_library(payload.get("svgLibrary"))
    branding = _validate_branding(payload.get("brandingSettings"))
    ui_config = _validate_ui_config(payload.get("uiConfig"))
    base_settings = _validate_base_settings(payload.get("baseSettings"))
    base_translations = _validate_base_translations(payload.get("baseTranslations"), locales)
    platforms = _validate_platforms(payload.get("platforms"), locales, svg_library)

    return {
        "version": "1",
        "locales": locales,
        "brandingSettings": branding,
        "uiConfig": ui_config,
        "baseSettings": base_settings,
        "baseTranslations": base_translations,
        "svgLibrary": svg_library,
        "platforms": platforms,
    }


def _read_config_source(settings: Any) -> tuple[str, str]:
    admin_json = str(settings.SUBSCRIPTION_PAGE_CONFIG_JSON or "").strip()
    json_override_enabled = bool(settings.SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED)
    if admin_json and json_override_enabled:
        return "admin_json", admin_json

    path = ensure_subscription_guides_config_file(settings)
    try:
        return "file", path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SubscriptionGuidesConfigError(f"Failed to read config file: {exc}") from exc


def _extract_config_candidate(value: Any, seen: set[int]) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if not text.startswith(("{", "[")):
            return None
        try:
            return _extract_config_candidate(json.loads(text), seen)
        except json.JSONDecodeError as exc:
            raise SubscriptionGuidesConfigError(f"Invalid JSON in Panel config: {exc.msg}") from exc

    if not isinstance(value, Mapping):
        return None

    value_id = id(value)
    if value_id in seen:
        return None
    seen.add(value_id)

    if _looks_like_v1_config(value):
        return value

    for key in PANEL_WRAPPER_KEYS:
        if key not in value:
            continue
        candidate = _extract_config_candidate(value.get(key), seen)
        if candidate is not None:
            return candidate
    return None


def _looks_like_v1_config(value: Mapping[str, Any]) -> bool:
    return (
        value.get("version") == "1"
        and "locales" in value
        and "svgLibrary" in value
        and "platforms" in value
    )


def _find_panel_response_object(value: Any, seen: set[int]) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        return None

    value_id = id(value)
    if value_id in seen:
        return None
    seen.add(value_id)

    if "webpageAllowed" in value:
        return value

    for key in ("response", "data", "result"):
        candidate = _find_panel_response_object(value.get(key), seen)
        if candidate is not None:
            return candidate
    return None


def _validate_locales(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise SubscriptionGuidesConfigError("locales must be a non-empty array")
    locales: list[str] = []
    for index, item in enumerate(value):
        locale = str(item or "").strip()
        if locale not in ALLOWED_LOCALES:
            raise SubscriptionGuidesConfigError(f"Unsupported locale at locales[{index}]: {locale}")
        if locale not in locales:
            locales.append(locale)
    return locales


def _validate_branding(value: Any) -> dict[str, str]:
    data = _require_object(value, "brandingSettings")
    result = {
        "title": _require_text(data, "title", "brandingSettings.title"),
        "logoUrl": _require_text(data, "logoUrl", "brandingSettings.logoUrl"),
        "supportUrl": _require_text(data, "supportUrl", "brandingSettings.supportUrl"),
    }
    _assert_http_url(result["logoUrl"], "brandingSettings.logoUrl")
    _assert_http_url(result["supportUrl"], "brandingSettings.supportUrl")
    return result


def _validate_ui_config(value: Any) -> dict[str, str]:
    data = _require_object(value, "uiConfig")
    subscription_info = _require_text(
        data,
        "subscriptionInfoBlockType",
        "uiConfig.subscriptionInfoBlockType",
    )
    installation_guides = _require_text(
        data,
        "installationGuidesBlockType",
        "uiConfig.installationGuidesBlockType",
    )
    if subscription_info not in UI_SUBSCRIPTION_INFO_TYPES:
        raise SubscriptionGuidesConfigError(
            f"Unsupported uiConfig.subscriptionInfoBlockType: {subscription_info}"
        )
    if installation_guides not in UI_INSTALLATION_GUIDE_TYPES:
        raise SubscriptionGuidesConfigError(
            f"Unsupported uiConfig.installationGuidesBlockType: {installation_guides}"
        )
    return {
        "subscriptionInfoBlockType": subscription_info,
        "installationGuidesBlockType": installation_guides,
    }


def _validate_base_settings(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, Mapping) else {}
    return {
        "metaTitle": _optional_text(data, "metaTitle") or "Subscription",
        "metaDescription": _optional_text(data, "metaDescription") or "Subscription",
        "showConnectionKeys": bool(data.get("showConnectionKeys", False)),
        "hideGetLinkButton": bool(data.get("hideGetLinkButton", False)),
    }


def _validate_base_translations(value: Any, locales: Iterable[str]) -> dict[str, dict[str, str]]:
    data = _require_object(value, "baseTranslations")
    result: dict[str, dict[str, str]] = {}
    for key in BASE_TRANSLATION_KEYS:
        result[key] = _validate_locale_strings(
            data.get(key),
            locales,
            f"baseTranslations.{key}",
        )
    return result


def _validate_svg_library(value: Any) -> dict[str, str]:
    data = _require_object(value, "svgLibrary")
    if not data:
        raise SubscriptionGuidesConfigError("svgLibrary must not be empty")
    result: dict[str, str] = {}
    for key, raw_svg in data.items():
        svg_key = str(key or "").strip()
        if not SVG_KEY_RE.fullmatch(svg_key):
            raise SubscriptionGuidesConfigError(f"Invalid svgLibrary key: {svg_key}")
        result[svg_key] = _sanitize_svg(raw_svg, f"svgLibrary.{svg_key}")
    return result


def _validate_platforms(
    value: Any,
    locales: Iterable[str],
    svg_library: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    data = _require_object(value, "platforms")
    if not data:
        raise SubscriptionGuidesConfigError("platforms must not be empty")
    result: dict[str, dict[str, Any]] = {}
    for platform_key, raw_platform in data.items():
        key = str(platform_key or "").strip()
        if key not in ALLOWED_PLATFORMS:
            raise SubscriptionGuidesConfigError(f"Unsupported platform: {key}")
        platform = _require_object(raw_platform, f"platforms.{key}")
        icon_key = _validate_svg_icon_key(
            platform.get("svgIconKey"),
            svg_library,
            f"platforms.{key}.svgIconKey",
        )
        apps = _validate_apps(platform.get("apps"), locales, svg_library, f"platforms.{key}.apps")
        result[key] = {
            "displayName": _validate_localized_or_text(
                platform.get("displayName"),
                locales,
                f"platforms.{key}.displayName",
            ),
            "svgIconKey": icon_key,
            "apps": apps,
        }
    return result


def _validate_apps(
    value: Any,
    locales: Iterable[str],
    svg_library: Mapping[str, str],
    path: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise SubscriptionGuidesConfigError(f"{path} must be a non-empty array")
    apps: list[dict[str, Any]] = []
    for index, raw_app in enumerate(value):
        app_path = f"{path}[{index}]"
        app = _require_object(raw_app, app_path)
        name = _require_text(app, "name", f"{app_path}.name")
        if len(name) < 2:
            raise SubscriptionGuidesConfigError(f"{app_path}.name must contain at least 2 chars")
        icon_key = _optional_svg_icon_key(
            app.get("svgIconKey"),
            svg_library,
            f"{app_path}.svgIconKey",
        )
        apps.append(
            {
                "name": name,
                "svgIconKey": icon_key,
                "featured": bool(app.get("featured", False)),
                "blocks": _validate_blocks(
                    app.get("blocks"),
                    locales,
                    svg_library,
                    f"{app_path}.blocks",
                ),
            }
        )
    return apps


def _validate_blocks(
    value: Any,
    locales: Iterable[str],
    svg_library: Mapping[str, str],
    path: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise SubscriptionGuidesConfigError(f"{path} must be a non-empty array")
    blocks: list[dict[str, Any]] = []
    for index, raw_block in enumerate(value):
        block_path = f"{path}[{index}]"
        block = _require_object(raw_block, block_path)
        color = _optional_text(block, "svgIconColor")
        if color and color not in ALLOWED_SVG_COLORS and not HEX_COLOR_RE.fullmatch(color):
            raise SubscriptionGuidesConfigError(f"{block_path}.svgIconColor is invalid")
        blocks.append(
            {
                "svgIconKey": _validate_svg_icon_key(
                    block.get("svgIconKey"),
                    svg_library,
                    f"{block_path}.svgIconKey",
                ),
                "svgIconColor": color or "",
                "title": _validate_locale_strings(
                    block.get("title"),
                    locales,
                    f"{block_path}.title",
                ),
                "description": _validate_locale_strings(
                    block.get("description"),
                    locales,
                    f"{block_path}.description",
                ),
                "buttons": _validate_buttons(
                    block.get("buttons"),
                    locales,
                    svg_library,
                    f"{block_path}.buttons",
                ),
            }
        )
    return blocks


def _validate_buttons(
    value: Any,
    locales: Iterable[str],
    svg_library: Mapping[str, str],
    path: str,
) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise SubscriptionGuidesConfigError(f"{path} must be an array")
    buttons: list[dict[str, Any]] = []
    for index, raw_button in enumerate(value):
        button_path = f"{path}[{index}]"
        button = _require_object(raw_button, button_path)
        button_type = _require_text(button, "type", f"{button_path}.type")
        if button_type not in ALLOWED_BUTTON_TYPES:
            raise SubscriptionGuidesConfigError(
                f"Unsupported button type at {button_path}: {button_type}"
            )
        link = _require_text(button, "link", f"{button_path}.link")
        _validate_button_link(link, button_type, f"{button_path}.link")
        buttons.append(
            {
                "type": button_type,
                "link": link,
                "text": _validate_locale_strings(
                    button.get("text"),
                    locales,
                    f"{button_path}.text",
                ),
                "svgIconKey": _validate_svg_icon_key(
                    button.get("svgIconKey"),
                    svg_library,
                    f"{button_path}.svgIconKey",
                ),
            }
        )
    return buttons


def _validate_locale_strings(value: Any, locales: Iterable[str], path: str) -> dict[str, str]:
    data = _require_object(value, path)
    result: dict[str, str] = {}
    for locale in locales:
        text = data.get(locale)
        if not isinstance(text, str) or not text.strip():
            raise SubscriptionGuidesConfigError(f"{path}.{locale} is required")
        result[locale] = text.strip()
    return result


def _validate_localized_or_text(
    value: Any,
    locales: Iterable[str],
    path: str,
) -> str | dict[str, str]:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    return _validate_locale_strings(value, locales, path)


def _validate_svg_icon_key(value: Any, svg_library: Mapping[str, str], path: str) -> str:
    key = _string_value(value)
    if not key:
        raise SubscriptionGuidesConfigError(f"{path} is required")
    if key not in svg_library:
        raise SubscriptionGuidesConfigError(f"{path} references missing svgLibrary key: {key}")
    return key


def _optional_svg_icon_key(value: Any, svg_library: Mapping[str, str], path: str) -> str | None:
    key = _string_value(value)
    if not key:
        return None
    if key not in svg_library:
        raise SubscriptionGuidesConfigError(f"{path} references missing svgLibrary key: {key}")
    return key


def _validate_button_link(link: str, _button_type: str, path: str) -> None:
    _assert_safe_link(link, path)


def _assert_safe_link(value: str, path: str) -> None:
    if CONTROL_CHARS_RE.search(value):
        raise SubscriptionGuidesConfigError(f"{path} contains control characters")
    lower = value.strip().lower()
    if lower.startswith(("javascript:", "data:", "vbscript:")):
        raise SubscriptionGuidesConfigError(f"{path} uses an unsafe URL scheme")


def _assert_http_url(value: str, path: str) -> None:
    _assert_safe_link(value, path)
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise SubscriptionGuidesConfigError(f"{path} must be an http(s) URL")


def _sanitize_svg(value: Any, path: str) -> str:
    svg = _string_value(value)
    if not svg:
        raise SubscriptionGuidesConfigError(f"{path} is required")
    trimmed = svg.strip()
    if not trimmed.lower().startswith("<svg"):
        raise SubscriptionGuidesConfigError(f"{path} must be an SVG document")
    if UNSAFE_SVG_RE.search(trimmed):
        raise SubscriptionGuidesConfigError(f"{path} contains unsafe SVG markup")
    return trimmed


def _require_object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SubscriptionGuidesConfigError(f"{path} must be an object")
    return value


def _require_text(data: Mapping[str, Any], key: str, path: str) -> str:
    value = _string_value(data.get(key))
    if not value:
        raise SubscriptionGuidesConfigError(f"{path} is required")
    return value


def _optional_text(data: Mapping[str, Any], key: str) -> str:
    return _string_value(data.get(key))


def _string_value(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()
