"""Only the active, intact and explicitly approved theme exposes executable assets."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from config.webapp_themes_config import resolved_webapp_themes_catalog

from .archive import content_digest
from .effects import effect_files, effects_allowed, set_permission, validate_effects
from .models import EffectsRequest, MutationOut, PackageError, ThemeEffectsDescriptor
from .paths import confined, registry_lock
from .registry import check_generation, read_registry, write_registry


def change_effects(root: Path, key: str, actor: int, request: EffectsRequest) -> MutationOut:
    with registry_lock(root):
        state = read_registry(root)
        check_generation(state, request.expected_generation)
        entry = state.entries.get(key)
        if entry is None:
            raise PackageError("theme_not_managed", status=404)
        folder = confined(root, f"_packages/{entry.digest}")
        if request.enabled and (
            content_digest(folder) != entry.digest
            or validate_effects(folder, entry.metadata) != entry.effects_digest
        ):
            raise PackageError("package_corrupted", status=409)
        set_permission(
            state,
            key,
            entry,
            enabled=request.enabled,
            digest=request.effects_digest,
            policy=request.effects_policy,
            actor=actor,
        )
        write_registry(root, state)
        return MutationOut(generation=state.generation, keys=[key])


def active_effect(
    root: Path, default_theme: str | None, accent: str
) -> ThemeEffectsDescriptor | None:
    # An operator can create this file without starting the UI or executing theme code.
    if (root / "_registry/effects-disabled").exists():
        return None
    state = read_registry(root)
    catalog = resolved_webapp_themes_catalog(
        primary_accent=accent, env_default_theme=default_theme, theme_dir=str(root)
    )
    key = catalog.default_theme
    entry = state.entries.get(key)
    if not entry or not effects_allowed(state, key, entry) or not entry.metadata.effects:
        return None
    if not any(theme.key == key and theme.enabled for theme in catalog.themes):
        return None
    folder = confined(root, f"_packages/{entry.digest}")
    if (
        content_digest(folder) != entry.digest
        or validate_effects(folder, entry.metadata) != entry.effects_digest
    ):
        raise PackageError("package_corrupted", status=409)
    manifest = entry.metadata.effects
    prefix = f"/api/theme-effects/assets/{key}/{entry.digest}/"
    return ThemeEffectsDescriptor(
        key=key,
        digest=entry.digest,
        effects_digest=entry.effects_digest,
        manifest=manifest,
        entry=prefix + manifest.entry,
        styles=[prefix + path for path in manifest.styles],
        assets={path: prefix + path for path in manifest.assets},
    )


def effect_asset(
    root: Path, effect: ThemeEffectsDescriptor, key: str, digest: str, relative: str
) -> tuple[bytes, str]:
    if (
        key != effect.key
        or digest != effect.digest
        or relative not in effect_files(effect.manifest)
    ):
        raise PackageError("theme_asset_not_found", status=404)
    path = confined(root, f"_packages/{digest}/{relative}")
    content_type = (
        "text/javascript"
        if relative == effect.manifest.entry
        else (mimetypes.guess_type(relative)[0] or "application/octet-stream")
    )
    return path.read_bytes(), content_type
