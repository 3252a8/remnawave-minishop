"""Validate theme effects and bind explicit trust to executable content and source."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .models import (
    EffectsGrant,
    EffectsPermission,
    InstalledVersion,
    PackageError,
    PackageMetadata,
    Registry,
    ThemeEffectsManifest,
)
from .paths import confined, relative_path

EFFECTS_POLICY = 1
MAX_EFFECT_SCRIPT = 2 * 1024 * 1024
MAX_EFFECT_RESOURCES = 5 * 1024 * 1024
EFFECT_RESOURCE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".svg",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
}


def effect_files(manifest: ThemeEffectsManifest) -> list[str]:
    return [manifest.entry, *manifest.styles, *manifest.assets]


def validate_effects(folder: Path, metadata: PackageMetadata) -> str:
    effect = metadata.effects
    if effect is None:
        return ""
    names = effect_files(effect)
    if len({name.casefold() for name in names}) != len(names):
        raise PackageError("invalid_theme_effects")
    if Path(effect.entry).suffix != ".js" or any(Path(p).suffix != ".css" for p in effect.styles):
        raise PackageError("invalid_theme_effects")
    if any(Path(p).suffix.lower() not in EFFECT_RESOURCE_SUFFIXES for p in effect.assets):
        raise PackageError("invalid_theme_effects")
    resources = 0
    digest = hashlib.sha256(
        json.dumps(effect.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    )
    for name in sorted(names):
        relative_path(name)
        path = confined(folder, name)
        if not path.is_file():
            raise PackageError("invalid_theme_effects", name)
        size = path.stat().st_size
        if name == effect.entry:
            if size > MAX_EFFECT_SCRIPT:
                raise PackageError("theme_effects_too_large")
            script = path.read_text(encoding="utf-8")
            if not script.strip() or "\x00" in script:
                raise PackageError("invalid_theme_effects")
        else:
            resources += size
        digest.update(name.encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    if resources > MAX_EFFECT_RESOURCES:
        raise PackageError("theme_effects_too_large")
    return digest.hexdigest()


def trust_fingerprint(entry: InstalledVersion) -> str:
    source = entry.source.model_dump(exclude={"commit", "label"})
    data = {
        "digest": entry.effects_digest,
        "source": source,
        "author": entry.metadata.author.model_dump() if entry.metadata.author else None,
        "policy": EFFECTS_POLICY,
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def effects_allowed(state: Registry, key: str, entry: InstalledVersion) -> bool:
    permission = state.effects.get(key)
    return bool(
        entry.effects_digest
        and entry.metadata.effects
        and permission
        and permission.enabled
        and any(grant.fingerprint == trust_fingerprint(entry) for grant in permission.grants)
    )


def set_permission(
    state: Registry,
    key: str,
    entry: InstalledVersion,
    *,
    enabled: bool,
    digest: str,
    policy: int,
    actor: int,
) -> None:
    if not enabled:
        # Explicit disable revokes previous approvals, including rollback versions.
        state.effects.pop(key, None)
        return
    if not entry.effects_digest or digest != entry.effects_digest or policy != EFFECTS_POLICY:
        raise PackageError("theme_effects_consent_required", status=409)
    permission = state.effects.setdefault(key, EffectsPermission())
    fingerprint = trust_fingerprint(entry)
    permission.grants = [grant for grant in permission.grants if grant.fingerprint != fingerprint]
    permission.grants = [
        *permission.grants[-7:],
        EffectsGrant(fingerprint=fingerprint, actor=actor, accepted_at=time.time()),
    ]
    permission.enabled = True
