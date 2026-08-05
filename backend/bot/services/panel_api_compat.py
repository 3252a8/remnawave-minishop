"""Compatibility helpers for certified Remnawave API generations.

Remnawave 3.0 removed ``uuid`` from user objects and made the numeric ``id``
the only user identifier accepted by user-scoped API routes and payloads.
Mini Shop deliberately keeps its historical internal names (``uuid`` keys,
``panel_user_uuid`` database columns, and public service methods) so upgrades
do not require an eager local database migration.  At this API boundary, a
3.x ``id`` is exposed internally as a decimal-string ``uuid`` compatibility
alias; outbound requests translate that alias back to an integer ``id``.

Do not use these helpers for node, squad, host, or subscription UUIDs.  Those
identifiers remain UUIDs in Remnawave 3.x.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from bot.services.panel_api_contracts import (
    GENERATION_CAPABILITIES,
    PanelApiCapability,
    PanelApiGeneration,
    certified_panel_versions,
    panel_version_support_status,
)


class PanelUserIdMode(Enum):
    UUID = "uuid"
    NUMERIC_ID = "numeric_id"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class PanelApiCompatibility:
    version: str | None
    generation: PanelApiGeneration
    capabilities: frozenset[PanelApiCapability]

    @classmethod
    def unknown(cls) -> "PanelApiCompatibility":
        return cls(
            version=None,
            generation=PanelApiGeneration.UNKNOWN,
            capabilities=GENERATION_CAPABILITIES[PanelApiGeneration.UNKNOWN],
        )

    @property
    def user_id_mode(self) -> PanelUserIdMode:
        if self.generation is PanelApiGeneration.RW2_UUID:
            return PanelUserIdMode.UUID
        if PanelApiCapability.NUMERIC_USER_IDS in self.capabilities:
            return PanelUserIdMode.NUMERIC_ID
        return PanelUserIdMode.UNKNOWN

    @property
    def support_status(self) -> str:
        return panel_version_support_status(self.version, self.generation)

    @property
    def certified_versions(self) -> tuple[str, ...]:
        return certified_panel_versions(self.generation)

    @property
    def explicitly_unsupported(self) -> bool:
        return self.support_status == "unsupported"

    @property
    def unreviewed_generation(self) -> bool:
        return self.version is not None and self.generation is PanelApiGeneration.UNKNOWN

    def supports(self, capability: PanelApiCapability) -> bool | None:
        if self.generation is PanelApiGeneration.UNKNOWN:
            return None
        return capability in self.capabilities

    @classmethod
    def from_metadata(cls, payload: object) -> "PanelApiCompatibility":
        """Parse ``GET /system/metadata`` from supported panel generations."""
        if not isinstance(payload, dict):
            return cls.unknown()
        response = payload.get("response")
        source = response if isinstance(response, dict) else payload
        raw_version = source.get("version")
        version = str(raw_version or "").strip()
        match = re.search(r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?", version)
        if not match:
            return cls.unknown()
        major = int(match.group(1))
        if major == 2:
            generation = PanelApiGeneration.RW2_UUID
        elif major == 3:
            generation = PanelApiGeneration.RW3_NUMERIC
        else:
            # Future majors must be reviewed explicitly. Assuming that every
            # major after 3 keeps numeric identifiers would make destructive
            # calls unsafe when Remnawave changes its API again.
            generation = PanelApiGeneration.UNKNOWN
        return cls(
            version=version,
            generation=generation,
            capabilities=GENERATION_CAPABILITIES[generation],
        )


def numeric_panel_user_id(value: object) -> int | None:
    """Return a valid 3.x user id, rejecting booleans, zero, and UUIDs."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value).strip()
    if not text.isdecimal():
        return None
    parsed = int(text)
    return parsed if parsed > 0 else None


def compatible_panel_user_reference(
    value: object,
    compatibility: PanelApiCompatibility,
) -> str | None:
    """Return a user reference that is safe for the detected API generation.

    A decimal string is unambiguously a 3.x user id and a non-decimal string
    is the legacy 2.x UUID-shaped reference.  When metadata is unavailable we
    preserve that identifier-derived best effort.  Once the panel generation
    is known, however, sending the wrong shape only creates validation-error
    storms and can make callers mistake an upgrade mismatch for a deleted
    user, so incompatible references fail locally.
    """
    if value is None or isinstance(value, bool):
        return None
    raw_reference = str(value).strip()
    if not raw_reference:
        return None
    numeric_id = numeric_panel_user_id(raw_reference)
    if compatibility.user_id_mode is PanelUserIdMode.NUMERIC_ID:
        return str(numeric_id) if numeric_id is not None else None
    if compatibility.user_id_mode is PanelUserIdMode.UUID:
        return raw_reference if numeric_id is None else None
    return str(numeric_id) if numeric_id is not None else raw_reference


def normalize_panel_user(value: object) -> dict[str, Any] | None:
    """Return a copy with Mini Shop's historical ``uuid`` identity contract."""
    if not isinstance(value, dict):
        return None
    user = dict(value)
    legacy_uuid = str(user.get("uuid") or "").strip()
    if legacy_uuid:
        user["uuid"] = legacy_uuid
        return user
    numeric_id = numeric_panel_user_id(user.get("id"))
    if numeric_id is not None:
        user["uuid"] = str(numeric_id)
    return user


def normalize_panel_users(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalized for value in values if (normalized := normalize_panel_user(value))]
