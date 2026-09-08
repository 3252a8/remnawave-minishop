"""Versioned package, installation and import contracts."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, field_validator

from config.webapp_themes_models import WebappTheme

THEME_API = 1
MAX_ARCHIVE = 20 * 1024 * 1024
MAX_EXPANDED = 100 * 1024 * 1024
MAX_FILE = 10 * 1024 * 1024
MAX_FILES = 2000
MAX_THEMES = 20
MAX_DEPTH = 5
IMPORT_TTL = 1800
MAX_STORAGE = 1024 * 1024 * 1024
BUILTINS = frozenset({"dark", "light", "ascii", "windows95"})
ThemeKey = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class PackageError(ValueError):
    def __init__(self, code: str, detail: str = "", status: int = 400) -> None:
        self.code = code
        self.detail = detail or code
        self.status = status
        super().__init__(code + (": " + detail if detail else ""))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Author(StrictModel):
    name: str = Field(max_length=120)


class Compatibility(StrictModel):
    theme_api: int = Field(default=THEME_API, ge=1)


class PackageMetadata(StrictModel):
    schema_version: Literal[1] = 1
    version: str = Field(default="", max_length=64)
    description: dict[str, str] = Field(default_factory=dict, max_length=12)
    author: Author | None = None
    license: str = Field(default="", max_length=120)
    homepage: str = Field(default="", max_length=500)
    preview: str = Field(default="", max_length=180)
    compatibility: Compatibility = Field(default_factory=Compatibility)

    @field_validator("description")
    @classmethod
    def bounded_description(cls, value: dict[str, str]) -> dict[str, str]:
        if any(len(key) > 20 or len(text) > 500 for key, text in value.items()):
            raise ValueError("description_too_long")
        return value

    @field_validator("version")
    @classmethod
    def version_string(cls, value: str) -> str:
        if not value:
            return value
        match = re.fullmatch(
            r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
            r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
            r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?",
            value,
        )
        if not match or any(
            part.isdecimal() and len(part) > 1 and part.startswith("0")
            for part in (match.group(4) or "").split(".")
        ):
            raise ValueError("version_must_be_semver")
        return value


class CollectionEntry(StrictModel):
    path: str = Field(max_length=180)


class Collection(StrictModel):
    schema_version: Literal[1] = 1
    themes: list[CollectionEntry] = Field(min_length=1, max_length=MAX_THEMES)


class ThemeSource(StrictModel):
    kind: Literal["archive", "github", "gitlab"] = "archive"
    label: str = Field(default="", max_length=500)
    url: str = Field(default="", max_length=500)
    ref: str = Field(default="", max_length=200)
    commit: str = Field(default="", max_length=64)
    subdir: str = Field(default="", max_length=180)


class Candidate(StrictModel):
    key: str = ""
    path: str
    theme: WebappTheme | None = None
    metadata: PackageMetadata = Field(default_factory=PackageMetadata)
    digest: str = ""
    size: int = 0
    files: int = 0
    error: str = ""
    detail: str = ""
    warnings: list[str] = Field(default_factory=list)


class InstalledVersion(StrictModel):
    digest: Digest
    metadata: PackageMetadata = Field(default_factory=PackageMetadata)
    source: ThemeSource = Field(default_factory=ThemeSource)
    installed_at: float
    original: WebappTheme


class InstalledTheme(InstalledVersion):
    overrides: dict[str, JsonValue] = Field(default_factory=dict)
    history: list[InstalledVersion] = Field(default_factory=list)
    adopted_digest: str = ""


class Registry(StrictModel):
    schema_version: Literal[1] = 1
    generation: int = 0
    entries: dict[str, InstalledTheme] = Field(default_factory=dict)
    preferences: dict[str, WebappTheme] = Field(default_factory=dict)
    removed: list[str] = Field(default_factory=list)
    retired: dict[str, dict[str, float]] = Field(default_factory=dict)
    completed: dict[str, list[str]] = Field(default_factory=dict)


class ImportRecord(StrictModel):
    id: str
    actor: int
    created_at: float
    state: Literal["downloading", "validating", "ready", "installed", "cancelled", "failed"] = (
        "validating"
    )
    source: ThemeSource = Field(default_factory=ThemeSource)
    generation: int = 0
    candidates: list[Candidate] = Field(default_factory=list)
    error: str = ""
    detail: str = ""
    installed: list[str] = Field(default_factory=list)


class RepositoryRequest(StrictModel):
    source_type: Literal["repository"] = "repository"
    url: str = Field(min_length=1, max_length=500)
    ref: str = Field(default="", max_length=200)
    subdir: str = Field(default="", max_length=180)


class InstallChoice(StrictModel):
    key: ThemeKey
    action: Literal["install", "update", "adopt"] = "install"


class InstallRequest(StrictModel):
    choices: list[InstallChoice] = Field(min_length=1, max_length=MAX_THEMES)
    expected_generation: int = Field(ge=0)
    idempotency_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,80}$")


class MutationRequest(StrictModel):
    expected_generation: int = Field(ge=0)


class ExportRequest(StrictModel):
    keys: list[ThemeKey] = Field(min_length=1, max_length=MAX_THEMES)
    include_overrides: bool = False
    new_key: ThemeKey | None = None


class ThemeInstallation(StrictModel):
    key: str
    managed: bool = False
    protected: bool = False
    version: str = ""
    digest: str = ""
    source: ThemeSource | None = None
    metadata: PackageMetadata | None = None
    can_rollback: bool = False
    modified: bool = False
    preview_url: str = ""


class LibraryOut(StrictModel):
    generation: int
    writable: bool
    reason: str = ""
    max_archive_bytes: int = MAX_ARCHIVE
    installations: list[ThemeInstallation] = Field(default_factory=list)


class ImportOut(StrictModel):
    operation: ImportRecord


class MutationOut(StrictModel):
    generation: int
    keys: list[str] = Field(default_factory=list)
