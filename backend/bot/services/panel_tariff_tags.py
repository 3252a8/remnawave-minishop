"""Ownership rules for the single Remnawave user ``tag`` field."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

PANEL_TAG_MAX_LENGTH = 16
PANEL_TRIAL_TAG = "TRIAL"
_PANEL_TAG_INVALID_RE = re.compile(r"[^A-Z0-9_]+")
_PANEL_TAG_UNDERSCORES_RE = re.compile(r"_+")


def normalize_panel_tag(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _panel_tag_base(value: str) -> str:
    normalized = _PANEL_TAG_INVALID_RE.sub("_", value.upper())
    return _PANEL_TAG_UNDERSCORES_RE.sub("_", normalized).strip("_") or "TARIFF"


def _configured_tariff_tag_map(tariffs_config: Any | None) -> dict[str, str]:
    raw_keys = sorted(
        {
            key
            for tariff in getattr(tariffs_config, "tariffs", ()) or ()
            for key in (
                normalize_panel_tag(getattr(tariff, "key", None)),
                *(normalize_panel_tag(value) for value in getattr(tariff, "legacy_keys", ()) or ()),
            )
            if key is not None
        }
    )
    bases = {key: _panel_tag_base(key) for key in raw_keys}
    base_counts: dict[str, int] = {}
    for base in bases.values():
        base_counts[base] = base_counts.get(base, 0) + 1

    result: dict[str, str] = {}
    used: set[str] = {PANEL_TRIAL_TAG}
    for key in raw_keys:
        base = bases[key]
        if len(base) <= PANEL_TAG_MAX_LENGTH and base_counts[base] == 1 and base not in used:
            result[key] = base
            used.add(base)

    for key in raw_keys:
        if key in result:
            continue
        base = bases[key]
        prefix = base[:7].rstrip("_") or "TARIFF"
        salt = 0
        while True:
            digest_source = key if salt == 0 else f"{key}\0{salt}"
            digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:8].upper()
            candidate = f"{prefix}_{digest}"
            if candidate not in used:
                result[key] = candidate
                used.add(candidate)
                break
            salt += 1
    return result


def panel_tariff_tag_for_key(
    value: Any, tariffs_config: Any | None = None, *, is_trial: bool = False
) -> str | None:
    """Map an entitlement to a portable tag, reserving TRIAL for trial access."""

    if is_trial:
        return PANEL_TRIAL_TAG
    key = normalize_panel_tag(value)
    if key is None:
        return None
    if tariffs_config is not None:
        configured = _configured_tariff_tag_map(tariffs_config).get(key)
        if configured is not None:
            return configured
    base = _panel_tag_base(key)
    if len(base) <= PANEL_TAG_MAX_LENGTH and base != PANEL_TRIAL_TAG:
        return base
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8].upper()
    return f"{base[:7].rstrip('_') or 'TARIFF'}_{digest}"


def configured_tariff_tags(tariffs_config: Any | None) -> frozenset[str]:
    if tariffs_config is None:
        return frozenset()
    return frozenset(_configured_tariff_tag_map(tariffs_config).values())


@dataclass(frozen=True, slots=True)
class PanelTariffTagPlan:
    current_tag: str | None
    desired_tag: str | None
    managed_tag_after: str | None
    allowed: bool

    @property
    def needs_patch(self) -> bool:
        return self.allowed and self.current_tag != self.desired_tag

    @property
    def verification_payload(self) -> dict[str, str | None]:
        if not self.allowed or (self.desired_tag is None and self.current_tag is None):
            return {}
        return {"tag": self.desired_tag}


def plan_panel_tariff_tag(
    *,
    current_tag: Any,
    managed_tag: Any,
    desired_tag: Any,
    known_tariff_tags: Iterable[str],
) -> PanelTariffTagPlan:
    """Plan a tag mutation without overwriting data owned outside Core.

    TRIAL and configured canonical/legacy tariff keys form a reserved namespace. An
    arbitrary non-empty tag is preserved unless it matches the tag previously
    written by Core.
    """

    current = normalize_panel_tag(current_tag)
    managed = normalize_panel_tag(managed_tag)
    desired = normalize_panel_tag(desired_tag)
    known = {tag for value in known_tariff_tags if (tag := normalize_panel_tag(value))}
    core_owned = current in (None, managed, PANEL_TRIAL_TAG) or current in known
    if not core_owned:
        return PanelTariffTagPlan(
            current_tag=current,
            desired_tag=desired,
            managed_tag_after=None,
            allowed=False,
        )
    return PanelTariffTagPlan(
        current_tag=current,
        desired_tag=desired,
        managed_tag_after=desired,
        allowed=True,
    )
