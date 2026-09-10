"""Immutable theme versions and the single atomic catalogue commit point."""

from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path

from pydantic import JsonValue, ValidationError

from config.webapp_themes_models import WebappTheme, WebappThemesConfig

from .archive import content_digest
from .models import (
    BUILTINS,
    MAX_STORAGE,
    InstalledTheme,
    LibraryOut,
    PackageError,
    Registry,
    ThemeInstallation,
)
from .paths import atomic_model, confined, registry_lock
from .preview_storage import PREVIEW_NAME, preview_file, preview_url

logger = logging.getLogger(__name__)


def read_registry(root: Path) -> Registry:
    path = confined(root, "_registry/current.json")
    if not path.exists():
        return Registry()
    if path.stat().st_size > 8 * 1024 * 1024:
        raise PackageError("registry_invalid", status=500)
    try:
        return Registry.model_validate_json(path.read_bytes())
    except (ValidationError, ValueError) as exc:
        raise PackageError("registry_invalid", status=500) from exc


def write_registry(root: Path, state: Registry) -> None:
    state.retired = {
        key: {digest: until for digest, until in versions.items() if until > time.time()}
        for key, versions in state.retired.items()
    }
    state.generation += 1
    # Receipts are small and bounded; installed operation records provide the
    # long-lived result after receipt retention.
    state.completed = dict(list(state.completed.items())[-256:])
    atomic_model(confined(root, "_registry/current.json"), state)


def effective_theme(key: str, entry: InstalledTheme) -> WebappTheme:
    data = entry.original.model_dump(mode="json")
    for field, value in entry.overrides.items():
        if field in {"tokens", "variants"} and isinstance(value, dict):
            original = data.get(field) or {}
            if field == "variants":
                for variant, changed in value.items():
                    if variant not in original:
                        # Keep stale editor data for a future package version, but a
                        # one-variant package must remain usable.
                        continue
                    if isinstance(changed, dict):
                        original[variant] = {**original.get(variant, {}), **changed}
            else:
                original.update(value)
            data[field] = original
        elif field not in {
            "key",
            "css_file",
            "css_variables",
            "css_variables_by_variant",
            "assets_version",
        }:
            data[field] = value
    data["key"] = key
    if entry.original.css_file:
        data["css_file"] = f"revisions/{entry.digest}/{entry.original.css_file}"
    data["assets_version"] = max(1, int(entry.digest[:12], 16))
    return WebappTheme.model_validate(data)


def managed_themes(root: Path) -> list[WebappTheme]:
    state = read_registry(root)
    return [effective_theme(key, value) for key, value in state.entries.items()]


def asset_path(root: Path, relative: Path) -> tuple[Path, str, str, str]:
    parts = relative.parts
    state = read_registry(root)
    if (
        len(parts) == 3
        and parts[1] == "previews"
        and parts[2] == PREVIEW_NAME
        and preview_file(root, parts[0]).is_file()
    ):
        return preview_file(root, parts[0]), parts[0], "", ""
    if (
        len(parts) >= 4
        and parts[1] == "revisions"
        and (parts[0] in state.entries or parts[0] in state.retired)
    ):
        key, digest = parts[0], parts[2]
        entry = state.entries.get(key)
        allowed = {entry.digest, *(version.digest for version in entry.history)} if entry else set()
        allowed.update(d for d, until in state.retired.get(key, {}).items() if until > time.time())
        if digest not in allowed:
            raise PackageError("theme_asset_not_found", status=404)
        resource = Path(*parts[3:]).as_posix()
        return confined(root, f"_packages/{digest}/{resource}"), key, digest, resource
    if parts and parts[0] in state.entries:
        entry = state.entries[parts[0]]
        resource = Path(*parts[1:]).as_posix()
        return (
            confined(root, f"_packages/{entry.digest}/{resource}"),
            parts[0],
            entry.digest,
            resource,
        )
    # Server-installed themes retain their original path contract, including
    # symlinks within the theme volume. Uploaded packages use confined() above.
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise PackageError("unsafe_path", relative.as_posix())
    return path, "", "", ""


def owner_overrides(original: WebappTheme, changed: WebappTheme) -> dict[str, object]:
    old = original.model_dump(mode="json")
    new = changed.model_dump(mode="json")
    result: dict[str, object] = {}
    for field, value in new.items():
        if field in {
            "key",
            "css_file",
            "css_variables",
            "css_variables_by_variant",
            "assets_version",
        }:
            continue
        if field in {"default", "enabled", "use_in_admin", "active_variant", "use_primary_accent"}:
            result[field] = value
        elif field == "tokens" and isinstance(value, dict):
            diff = {
                key: item
                for key, item in value.items()
                if item is not None and item != (old.get(field) or {}).get(key)
            }
            if diff:
                result[field] = diff
        elif field == "variants" and isinstance(value, dict):
            variants: dict[str, object] = {}
            for variant, tokens in value.items():
                diff = {
                    key: item
                    for key, item in tokens.items()
                    if item is not None and item != (old.get(field, {}).get(variant) or {}).get(key)
                }
                if diff:
                    variants[variant] = diff
            if variants:
                result[field] = variants
        elif value != old.get(field):
            result[field] = value
    return result


def preserve_unchanged_overrides(
    owned: dict[str, JsonValue],
    before: dict[str, object],
    after: dict[str, object],
    changes: dict[str, object],
) -> None:
    """An unrelated save must not erase a color that now matches the author's default."""
    for key, value in owned.items():
        old, new = before.get(key), after.get(key)
        if isinstance(value, dict) and isinstance(old, dict) and isinstance(new, dict):
            nested = changes.get(key)
            if not isinstance(nested, dict):
                nested = {}
            preserve_unchanged_overrides(value, old, new, nested)
            if nested:
                changes[key] = nested
        elif new is not None and new == old:
            changes[key] = value


def legacy_preferences(
    current: WebappTheme, saved: WebappTheme, base: WebappTheme | None
) -> WebappTheme:
    """Keep admin edits while allowing subsequent edits to the original descriptor."""
    if base is None:
        # Catalogues written before source baselines existed keep their settings.
        return saved

    def merge(current: JsonValue, saved: JsonValue, base: JsonValue) -> JsonValue:
        if current == base:
            return saved
        if isinstance(current, dict) and isinstance(saved, dict) and isinstance(base, dict):
            return {
                key: merge(current.get(key), saved.get(key, current.get(key)), base.get(key))
                for key in current.keys() | saved.keys()
                if key in current or key not in base
            }
        return current

    return WebappTheme.model_validate(
        merge(
            current.model_dump(mode="json"),
            saved.model_dump(mode="json"),
            base.model_dump(mode="json"),
        )
    )


def save_preferences(root: Path, state: Registry, config: WebappThemesConfig) -> None:
    from config.webapp_themes_store import load_webapp_theme_file

    sources: dict[str, WebappTheme] = {}
    for path in sorted(root.glob("*/theme.json")):
        if not path.parent.name.startswith("_") and (source := load_webapp_theme_file(path)):
            sources.setdefault(source.key, source)
    state.preferences.clear()
    state.preference_bases.clear()
    for theme in config.themes:
        if entry := state.entries.get(theme.key):
            data = entry.model_dump(mode="json")
            overrides = owner_overrides(entry.original, theme)
            preserve_unchanged_overrides(
                entry.overrides,
                effective_theme(theme.key, entry).model_dump(mode="json"),
                theme.model_dump(mode="json"),
                overrides,
            )
            data["overrides"] = overrides
            state.entries[theme.key] = InstalledTheme.model_validate(data)
        else:
            state.preferences[theme.key] = theme
            if theme.key in sources:
                state.preference_bases[theme.key] = sources[theme.key]
    write_registry(root, state)


def check_generation(state: Registry, expected: int | None) -> None:
    if expected is not None and state.generation != expected:
        raise PackageError("catalog_changed", status=409)
    if expected is None and state.entries:
        raise PackageError("catalog_reload_required", status=409)


def library(root: Path, catalog: WebappThemesConfig) -> LibraryOut:
    state = read_registry(root)
    writable = os.access(root if root.exists() else root.parent, os.W_OK)
    result = LibraryOut(
        generation=state.generation,
        writable=writable,
        reason="" if writable else "themes_read_only",
    )
    for theme in catalog.themes:
        if theme.hidden or theme.variant_alias_for:
            continue
        entry = state.entries.get(theme.key)
        item = ThemeInstallation(key=theme.key, protected=theme.key in BUILTINS)
        if entry:
            item.managed = True
            item.version = entry.metadata.version
            item.digest = entry.digest
            item.source = entry.source
            item.metadata = entry.metadata
            item.can_rollback = bool(entry.history)
            item.modified = (
                content_digest(confined(root, f"_packages/{entry.digest}")) != entry.digest
            )
            if entry.preview_override and preview_file(root, theme.key).is_file():
                item.preview_url = preview_url(theme.key, state.generation)
            elif entry.metadata.preview:
                item.preview_url = (
                    f"/webapp-theme-assets/{theme.key}/revisions/{entry.digest}/"
                    f"{entry.metadata.preview}"
                )
            legacy = root / theme.key
            if entry.adopted_digest and legacy.is_dir():
                item.modified = item.modified or content_digest(legacy) != entry.adopted_digest
        else:
            override = preview_file(root, theme.key)
            preview = root / theme.key / "preview.webp"
            if override.is_file():
                item.preview_url = preview_url(theme.key, state.generation)
            elif preview.is_file():
                item.preview_url = (
                    f"/webapp-theme-assets/{theme.key}/preview.webp?v={theme.assets_version}"
                )
        result.installations.append(item)
    return result


def require_capacity(root: Path, additional: int) -> None:
    used = sum(
        path.stat().st_size
        for directory in ("_packages", "_imports")
        for path in (root / directory).rglob("*")
        if path.is_file()
    )
    if used + additional > MAX_STORAGE:
        raise PackageError("theme_storage_full", status=507)
    if shutil.disk_usage(root).free < additional + 32 * 1024 * 1024:
        raise PackageError("insufficient_disk_space", status=507)


def collect_garbage(root: Path, *, now: float | None = None) -> None:
    now = time.time() if now is None else now
    with registry_lock(root):
        state = read_registry(root)
        referenced = {
            digest
            for entry in state.entries.values()
            for digest in (entry.digest, *(version.digest for version in entry.history))
        }
        referenced.update(
            digest
            for versions in state.retired.values()
            for digest, until in versions.items()
            if until > now
        )
        folder = confined(root, "_packages")
        if not folder.exists():
            return
        for package in folder.iterdir():
            if (
                package.name not in referenced
                and package.is_dir()
                and not package.is_symlink()
                and now - package.stat().st_mtime > 7 * 86400
            ):
                shutil.rmtree(confined(root, f"_packages/{package.name}"))
