from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel


class AdminUserSquadOverridesPatchBody(HttpBodyModel):
    add_internal_squad_uuids: list[str] = Field(default_factory=list)
    remove_internal_squad_uuids: list[str] = Field(default_factory=list)
    external_mode: str | None = None
    external_squad_uuid: str | None = None
    sync_panel: bool = True

    @field_validator("add_internal_squad_uuids", "remove_internal_squad_uuids", mode="before")
    @classmethod
    def _normalize_uuid_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        raw_items = value if isinstance(value, list | tuple | set) else [value]
        result: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            cleaned = str(item or "").strip()
            if cleaned and cleaned not in seen:
                result.append(cleaned)
                seen.add(cleaned)
        return result

    @field_validator("external_mode", mode="before")
    @classmethod
    def _normalize_external_mode(cls, value: Any) -> str | None:
        mode = str(value or "").strip().lower()
        return mode if mode else None

    @field_validator("external_squad_uuid", mode="before")
    @classmethod
    def _normalize_external_squad_uuid(cls, value: Any) -> str | None:
        cleaned = str(value or "").strip()
        return cleaned or None

    @model_validator(mode="after")
    def _validate_external_mode(self) -> AdminUserSquadOverridesPatchBody:
        if self.external_mode is None:
            return self
        if self.external_mode not in {"inherit", "set", "cleared"}:
            raise ValueError("external_mode must be inherit, set or cleared")
        if self.external_mode == "set" and not self.external_squad_uuid:
            raise ValueError("external_squad_uuid is required when external_mode is set")
        return self


class AdminPanelSquadItemOut(HttpResponseModel):
    uuid: str
    label: str | None = None
    source: str
    last_seen_at: str | None = None


class AdminPanelExternalSquadOverrideOut(HttpResponseModel):
    mode: str
    default_uuid: str | None = None
    manual_uuid: str | None = None
    effective_uuid: str | None = None
    source: str | None = None
    last_seen_at: str | None = None


class AdminPanelSquadOverridesOut(HttpResponseModel):
    panel_user_uuid: str | None = None
    panel_snapshot_available: bool = False
    managed_internal_squads: list[AdminPanelSquadItemOut] = Field(default_factory=list)
    manual_internal_squads: list[AdminPanelSquadItemOut] = Field(default_factory=list)
    effective_internal_squad_uuids: list[str] = Field(default_factory=list)
    external: AdminPanelExternalSquadOverrideOut
