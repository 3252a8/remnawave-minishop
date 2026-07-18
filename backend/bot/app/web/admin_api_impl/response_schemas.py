"""Typed response DTOs for admin endpoints with dynamic service payloads."""

from __future__ import annotations

from typing import Any, cast

from pydantic import ConfigDict, Field

from bot.app.web.http_contracts import HttpResponseModel
from bot.services.backup_restore_service import BackupArchiveInfo, BackupRestoreResult
from bot.services.backup_worker import BackupResult
from config.webapp_themes_config import WebappThemesConfig


class AdminBackupArchiveOut(HttpResponseModel):
    name: str
    size_bytes: int
    modified_at: str
    created_at: str | None = None
    created_at_local: str | None = None
    has_database: bool
    has_compose: bool
    database_name: str | None = None
    compose_files_count: int
    warnings: list[str] = Field(default_factory=list)
    manifest: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_archive(cls, archive: BackupArchiveInfo) -> AdminBackupArchiveOut:
        return cls.model_validate(archive.to_payload())


class AdminBackupCreateResultOut(HttpResponseModel):
    archive_name: str
    archive_path: str
    started_at: str
    completed_at: str
    db_dump_included: bool
    compose_files_count: int
    size_bytes: int
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_result(cls, result: BackupResult) -> AdminBackupCreateResultOut:
        return cls.model_validate(result.to_payload())


class AdminBackupRestoreResultOut(HttpResponseModel):
    archive_name: str
    started_at: str
    completed_at: str
    database_restored: bool
    compose_files_restored: int
    compose_target_dir: str | None = None
    compose_pre_restore_archive: str | None = None
    database_migrations_applied: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_result(cls, result: BackupRestoreResult) -> AdminBackupRestoreResultOut:
        return cls.model_validate(result.to_payload())


class AdminBackupsListOut(HttpResponseModel):
    backup_dir: str
    archives: list[AdminBackupArchiveOut]


class AdminBackupCreateOut(HttpResponseModel):
    result: AdminBackupCreateResultOut
    archive: AdminBackupArchiveOut


class AdminBackupUploadOut(HttpResponseModel):
    archive: AdminBackupArchiveOut


class AdminBackupRestoreOut(HttpResponseModel):
    result: AdminBackupRestoreResultOut


class AdminBroadcastAudienceOut(HttpResponseModel):
    target: str
    label_key: str
    fallback_label: str
    order: int = 100


class AdminBroadcastAudienceCountsOut(HttpResponseModel):
    counts: dict[str, int | None]
    audiences: list[AdminBroadcastAudienceOut] = Field(default_factory=list)
    email_enabled: bool = False


class AdminBroadcastShortcodeOut(HttpResponseModel):
    name: str
    cost: str
    description: str


class AdminBroadcastShortcodesOut(HttpResponseModel):
    shortcodes: list[AdminBroadcastShortcodeOut]
    allowed_tags: list[str]


class AdminBroadcastPreviewOut(HttpResponseModel):
    rendered_text: str = ""
    rendered_subject: str | None = None
    unknown_shortcodes: list[str] = Field(default_factory=list)
    length: int = 0
    sent: bool = False


class AdminPanelInternalSquadOut(HttpResponseModel):
    uuid: str
    name: str
    members_count: int | float | str | bool | None = None
    active_inbounds_count: int | float | str | bool | None = None


class AdminSyncResultOut(HttpResponseModel):
    status: str


class AdminSyncOut(HttpResponseModel):
    result: AdminSyncResultOut


class AdminThemesOut(HttpResponseModel):
    exists: bool
    themes_dir: str
    catalog: WebappThemesConfig

    def to_legacy_payload(self) -> dict[str, Any]:
        payload = cast(dict[str, Any], self.model_dump(mode="json"))
        payload["catalog"] = self.catalog.model_dump(mode="json", exclude_none=True)
        return payload


class AdminSettingChoiceOut(HttpResponseModel):
    value: Any
    label: str
    i18n_label_key: str | None = None


class AdminSettingsFieldOut(HttpResponseModel):
    model_config = ConfigDict(extra="allow")

    key: str
    type: str
    section: str
    section_order: int
    subsection: str | None = None
    label: str
    description: str | None = None
    i18n_label_key: str | None = None
    i18n_description_key: str | None = None
    i18n_subsection_key: str | None = None
    i18n_placeholder_key: str | None = None
    placeholder: str | None = None
    optional: bool
    secret: bool
    min: float | None = None
    max: float | None = None
    choices: list[AdminSettingChoiceOut] | None = None
    mutually_exclusive_key: str | None = None
    default: Any = None
    webhook_path: str | None = None
    webhook_requires_base_url: bool | None = None
    webhook_hint_i18n_key: str | None = None
    webhook_hint: str | None = None
    provider_id: str | None = None
    provider_label: str | None = None
    provider_info_url: str | None = None
    provider_logo_url: str | None = None
    value: Any = None
    overridden: bool | None = None
    updated_at: str | None = None
    source: str | None = None
    read_error: str | None = None
    has_value: bool | None = None
    webhook_base_url_configured: bool | None = None
    webhook_url: str | None = None


class AdminSettingsSectionOut(HttpResponseModel):
    id: str
    order: int
    fields: list[AdminSettingsFieldOut]


class AdminSettingsOut(HttpResponseModel):
    sections: list[AdminSettingsSectionOut]
    features: list[str]


class AdminTranslationLanguageOut(HttpResponseModel):
    code: str
    label: str
    flag: str
    base: bool


class AdminTranslationValueOut(HttpResponseModel):
    base: str
    fallback: str
    effective: str
    override: str
    overridden: bool
    updated_at: str | None = None
    updated_by: int | None = None


class AdminTranslationItemOut(HttpResponseModel):
    key: str
    audience: str
    values: dict[str, AdminTranslationValueOut]


class AdminTranslationGroupOut(HttpResponseModel):
    id: str
    title: str
    description: str
    audience: str
    title_key: str
    description_key: str
    items: list[AdminTranslationItemOut]


class AdminTranslationsOut(HttpResponseModel):
    languages: list[AdminTranslationLanguageOut]
    groups: list[AdminTranslationGroupOut]
    path: str
    override_count: int
