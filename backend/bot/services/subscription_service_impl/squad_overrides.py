from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import user_panel_squad_override_dal as override_dal
from db.models import Subscription, UserPanelSquadOverride

from ._typing import SubscriptionServiceMixinContract

logger = logging.getLogger(__name__)

_INTERNAL_SQUAD_KEYS = (
    "activeInternalSquads",
    "active_internal_squads",
    "activeInternalSquadUuids",
    "active_internal_squad_uuids",
)
_EXTERNAL_SQUAD_KEYS = (
    "externalSquadUuid",
    "external_squad_uuid",
    "externalSquadUUID",
)
_SQUAD_VALUE_KEYS = (
    "uuid",
    "internalSquadUuid",
    "internal_squad_uuid",
    "squadUuid",
    "squad_uuid",
    "id",
)
_NESTED_SQUAD_KEYS = ("internalSquad", "internal_squad", "squad")


def _clean_uuid(value: object) -> str:
    return str(value or "").strip()


def _dedupe_squad_uuids(values: Any) -> list[str]:
    if values is None:
        return []
    raw_values = [values] if isinstance(values, str) or not isinstance(values, Iterable) else values
    result: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        squad_uuid = _clean_uuid(value)
        if squad_uuid and squad_uuid not in seen:
            result.append(squad_uuid)
            seen.add(squad_uuid)
    return result


def _uuid_from_squad_item(item: object) -> str:
    if isinstance(item, str):
        return _clean_uuid(item)
    if not isinstance(item, dict):
        return ""
    for key in _SQUAD_VALUE_KEYS:
        value = item.get(key)
        if value:
            return _clean_uuid(value)
    for key in _NESTED_SQUAD_KEYS:
        nested = item.get(key)
        if isinstance(nested, dict):
            nested_uuid = _uuid_from_squad_item(nested)
            if nested_uuid:
                return nested_uuid
    return ""


def normalize_panel_internal_squad_uuids(panel_user: dict[str, Any] | None) -> list[str] | None:
    if not isinstance(panel_user, dict):
        return None
    raw_value: object = None
    field_found = False
    for key in _INTERNAL_SQUAD_KEYS:
        if key in panel_user:
            raw_value = panel_user.get(key)
            field_found = True
            break
    if not field_found:
        return None
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        return _dedupe_squad_uuids([raw_value])
    if not isinstance(raw_value, list | tuple | set):
        return []
    return _dedupe_squad_uuids(_uuid_from_squad_item(item) for item in raw_value)


def normalize_panel_external_squad_uuid(
    panel_user: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    if not isinstance(panel_user, dict):
        return False, None
    for key in _EXTERNAL_SQUAD_KEYS:
        if key not in panel_user:
            continue
        raw_value = panel_user.get(key)
        if isinstance(raw_value, dict):
            raw_value = _uuid_from_squad_item(raw_value)
        cleaned = _clean_uuid(raw_value)
        return True, cleaned or None
    return False, None


def detect_panel_manual_internal_squads(
    panel_internal_squads: list[str] | None,
    managed_internal_squads: list[str] | None,
) -> list[str]:
    if panel_internal_squads is None:
        return []
    managed = set(_dedupe_squad_uuids(managed_internal_squads))
    return [uuid for uuid in _dedupe_squad_uuids(panel_internal_squads) if uuid not in managed]


def _iso_or_none(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def _can_persist_overrides(session: object) -> bool:
    return isinstance(session, AsyncSession)


class SquadOverrideMixin(SubscriptionServiceMixinContract):
    def _default_external_squad_uuid(self, explicit_default: str | None = None) -> str | None:
        return (
            _clean_uuid(explicit_default)
            or _clean_uuid(getattr(self.settings, "parsed_user_external_squad_uuid", None))
            or None
        )

    def _managed_panel_squad_uuids_for_subscription(
        self,
        subscription: Subscription | None,
    ) -> tuple[list[str], str]:
        if subscription is not None:
            provider = str(getattr(subscription, "provider", "") or "").lower()
            status = str(getattr(subscription, "status_from_panel", "") or "").upper()
            if provider == "trial" or status == "TRIAL":
                return self._trial_all_panel_squad_uuids(), "trial"

            tariff_key = getattr(subscription, "tariff_key", None)
            tariff = None
            if tariff_key:
                try:
                    tariff = self._resolve_tariff(str(tariff_key))
                except Exception as exc:
                    logger.warning(
                        "Failed to resolve tariff %s while building squad overrides: %s",
                        tariff_key,
                        exc,
                    )
            if tariff is not None:
                include_premium = not bool(getattr(subscription, "premium_is_limited", False))
                if bool(getattr(subscription, "premium_unlimited_override", False)):
                    include_premium = True
                return (
                    self._panel_squads_for_tariff(tariff, include_premium=include_premium) or [],
                    "tariff",
                )

        return self._panel_squads_for_tariff(None) or [], "settings"

    async def _fetch_panel_user_snapshot_for_squads(
        self,
        panel_user_uuid: str,
        *,
        reason: str,
    ) -> dict[str, Any] | None:
        try:
            panel_user = await self.panel_service.get_user_by_uuid(panel_user_uuid)
        except Exception as exc:
            logger.warning(
                "Unable to fetch panel user %s before squad update (%s): %s",
                panel_user_uuid,
                reason,
                exc,
            )
            return None
        return panel_user if isinstance(panel_user, dict) else None

    async def capture_panel_squad_overrides(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        panel_user_uuid: str,
        managed_internal_squads: list[str] | None,
        panel_user_snapshot: dict[str, Any] | None,
        external_default_uuid: str | None = None,
    ) -> None:
        if not _can_persist_overrides(session):
            return

        now = datetime.now(UTC)
        panel_internal = normalize_panel_internal_squad_uuids(panel_user_snapshot)
        for squad_uuid in detect_panel_manual_internal_squads(
            panel_internal,
            managed_internal_squads,
        ):
            await override_dal.upsert_internal_override(
                session,
                user_id=user_id,
                panel_user_uuid=panel_user_uuid,
                squad_uuid=squad_uuid,
                source=override_dal.OVERRIDE_SOURCE_PANEL,
                last_seen_at=now,
            )

        external_present, panel_external_uuid = normalize_panel_external_squad_uuid(
            panel_user_snapshot
        )
        if not external_present:
            return
        default_external_uuid = self._default_external_squad_uuid(external_default_uuid)
        if panel_external_uuid and panel_external_uuid != default_external_uuid:
            await override_dal.set_external_override(
                session,
                user_id=user_id,
                panel_user_uuid=panel_user_uuid,
                mode=override_dal.OVERRIDE_MODE_SET,
                squad_uuid=panel_external_uuid,
                source=override_dal.OVERRIDE_SOURCE_PANEL,
                last_seen_at=now,
            )
        elif panel_external_uuid is None and default_external_uuid:
            await override_dal.set_external_override(
                session,
                user_id=user_id,
                panel_user_uuid=panel_user_uuid,
                mode=override_dal.OVERRIDE_MODE_CLEARED,
                source=override_dal.OVERRIDE_SOURCE_PANEL,
                last_seen_at=now,
            )

    async def build_effective_panel_squad_fields(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        panel_user_uuid: str,
        managed_internal_squads: list[str] | None,
        override_detection_managed_internal_squads: list[str] | None = None,
        panel_user_snapshot: dict[str, Any] | None = None,
        discover_panel_overrides: bool = True,
        fetch_panel_snapshot: bool = True,
        external_default_uuid: str | None = None,
        include_internal_squads: bool = True,
        source: str = "subscription",
    ) -> dict[str, Any]:
        persist_overrides = _can_persist_overrides(session)
        snapshot = panel_user_snapshot
        if snapshot is None and discover_panel_overrides and fetch_panel_snapshot:
            snapshot = await self._fetch_panel_user_snapshot_for_squads(
                panel_user_uuid,
                reason=source,
            )
        if snapshot is not None and discover_panel_overrides and persist_overrides:
            await self.capture_panel_squad_overrides(
                session,
                user_id=user_id,
                panel_user_uuid=panel_user_uuid,
                managed_internal_squads=(
                    override_detection_managed_internal_squads
                    if override_detection_managed_internal_squads is not None
                    else managed_internal_squads
                ),
                panel_user_snapshot=snapshot,
                external_default_uuid=external_default_uuid,
            )

        manual_internal: list[str] = []
        if persist_overrides:
            manual_internal = await override_dal.get_active_internal_squad_uuids(
                session,
                user_id=user_id,
                panel_user_uuid=panel_user_uuid,
            )
        effective_internal = _dedupe_squad_uuids(
            [*_dedupe_squad_uuids(managed_internal_squads), *manual_internal]
        )
        payload: dict[str, Any] = {}
        if include_internal_squads or effective_internal:
            payload["activeInternalSquads"] = effective_internal

        external_override: UserPanelSquadOverride | None = None
        if persist_overrides:
            external_override = await override_dal.get_active_external_override(
                session,
                user_id=user_id,
                panel_user_uuid=panel_user_uuid,
            )
        external_default = self._default_external_squad_uuid(external_default_uuid)
        if external_override is not None:
            mode = str(getattr(external_override, "mode", "") or "").lower()
            manual_uuid = _clean_uuid(getattr(external_override, "squad_uuid", None))
            if mode == override_dal.OVERRIDE_MODE_SET and manual_uuid:
                payload["externalSquadUuid"] = manual_uuid
            elif mode == override_dal.OVERRIDE_MODE_CLEARED:
                payload["externalSquadUuid"] = None
        elif external_default:
            payload["externalSquadUuid"] = external_default
        return payload

    def _managed_squad_items(
        self,
        managed_internal_squads: list[str],
        source: str,
    ) -> list[dict[str, str | None]]:
        return [
            {"uuid": squad_uuid, "label": None, "source": source}
            for squad_uuid in _dedupe_squad_uuids(managed_internal_squads)
        ]

    def _manual_squad_item(
        self,
        override: UserPanelSquadOverride,
    ) -> dict[str, str | None]:
        return {
            "uuid": _clean_uuid(getattr(override, "squad_uuid", None)),
            "label": None,
            "source": str(getattr(override, "source", "") or ""),
            "last_seen_at": _iso_or_none(getattr(override, "last_seen_at", None)),
        }

    async def panel_squad_overrides_summary(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        panel_user_uuid: str | None,
        subscription: Subscription | None = None,
        panel_user_snapshot: dict[str, Any] | None = None,
        panel_snapshot_available: bool = False,
        discover_panel_overrides: bool = True,
    ) -> dict[str, Any]:
        managed_internal, managed_source = self._managed_panel_squad_uuids_for_subscription(
            subscription
        )
        if not panel_user_uuid:
            return {
                "panel_user_uuid": None,
                "panel_snapshot_available": bool(panel_snapshot_available),
                "managed_internal_squads": self._managed_squad_items(
                    managed_internal,
                    managed_source,
                ),
                "manual_internal_squads": [],
                "effective_internal_squad_uuids": _dedupe_squad_uuids(managed_internal),
                "external": {
                    "mode": "inherit",
                    "default_uuid": self._default_external_squad_uuid(),
                    "manual_uuid": None,
                    "effective_uuid": self._default_external_squad_uuid(),
                    "source": None,
                    "last_seen_at": None,
                },
            }

        persist_overrides = _can_persist_overrides(session)
        if panel_user_snapshot is not None and discover_panel_overrides and persist_overrides:
            await self.capture_panel_squad_overrides(
                session,
                user_id=user_id,
                panel_user_uuid=panel_user_uuid,
                managed_internal_squads=managed_internal,
                panel_user_snapshot=panel_user_snapshot,
            )

        manual_overrides: list[UserPanelSquadOverride] = []
        if persist_overrides:
            manual_overrides = await override_dal.get_active_overrides(
                session,
                user_id=user_id,
                panel_user_uuid=panel_user_uuid,
                kind=override_dal.INTERNAL_KIND,
            )
        manual_items = [
            self._manual_squad_item(override)
            for override in manual_overrides
            if _clean_uuid(getattr(override, "squad_uuid", None))
        ]
        effective_internal = _dedupe_squad_uuids(
            [
                *_dedupe_squad_uuids(managed_internal),
                *(str(item["uuid"]) for item in manual_items if item.get("uuid")),
            ]
        )

        external_default = self._default_external_squad_uuid()
        external_override: UserPanelSquadOverride | None = None
        if persist_overrides:
            external_override = await override_dal.get_active_external_override(
                session,
                user_id=user_id,
                panel_user_uuid=panel_user_uuid,
            )
        external_mode = "inherit"
        external_manual_uuid: str | None = None
        external_effective_uuid = external_default
        external_source: str | None = None
        external_last_seen_at: str | None = None
        if external_override is not None:
            external_mode = str(getattr(external_override, "mode", "") or "inherit")
            external_manual_uuid = _clean_uuid(getattr(external_override, "squad_uuid", None))
            external_manual_uuid = external_manual_uuid or None
            external_source = str(getattr(external_override, "source", "") or "") or None
            external_last_seen_at = _iso_or_none(getattr(external_override, "last_seen_at", None))
            if external_mode == override_dal.OVERRIDE_MODE_SET:
                external_effective_uuid = external_manual_uuid
            elif external_mode == override_dal.OVERRIDE_MODE_CLEARED:
                external_effective_uuid = None
        return {
            "panel_user_uuid": panel_user_uuid,
            "panel_snapshot_available": bool(
                panel_snapshot_available or panel_user_snapshot is not None
            ),
            "managed_internal_squads": self._managed_squad_items(
                managed_internal,
                managed_source,
            ),
            "manual_internal_squads": manual_items,
            "effective_internal_squad_uuids": effective_internal,
            "external": {
                "mode": external_mode
                if external_mode in {"inherit", "set", "cleared"}
                else "inherit",
                "default_uuid": external_default,
                "manual_uuid": external_manual_uuid,
                "effective_uuid": external_effective_uuid,
                "source": external_source,
                "last_seen_at": external_last_seen_at,
            },
        }
