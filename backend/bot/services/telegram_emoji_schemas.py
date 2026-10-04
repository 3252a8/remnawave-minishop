"""Typed administrative catalog, preview and capability contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from config.telegram_menu import ButtonStyle, TelegramEmojiLibrary, TelegramMenuAppearance


class EmojiItem(BaseModel):
    id: str
    fallback: str
    set_name: str | None = None
    thumbnail_url: str | None = None
    format: Literal["static", "animated", "video"] = "static"


class CachedEmojiItem(EmojiItem):
    file_id: str = ""
    file_unique_id: str = ""
    thumbnail_file_id: str | None = None
    thumbnail_unique_id: str = ""


class EmojiCapability(BaseModel):
    state: Literal["unknown", "supported", "unavailable"] = "unknown"
    tested_at: str | None = None


class EmojiCapabilities(BaseModel):
    icon: EmojiCapability = Field(default_factory=EmojiCapability)
    text: EmojiCapability = Field(default_factory=EmojiCapability)


class MenuButtonInfo(BaseModel):
    id: str
    label_key: str
    label: str
    screens: list[str]
    emoji_fallback: str = ""


class MenuLanguage(BaseModel):
    code: str
    name: str


class TelegramMenuOut(BaseModel):
    appearance: TelegramMenuAppearance
    revision: str
    buttons: list[MenuButtonInfo]
    languages: list[MenuLanguage]
    capabilities: EmojiCapabilities


class MenuSaveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    appearance: TelegramMenuAppearance
    expected_revision: str = Field(min_length=64, max_length=64)


class MenuPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    appearance: TelegramMenuAppearance
    screen: Literal["main", "bot", "information"] = "main"
    language: str = Field(default="ru", min_length=2, max_length=24)
    scenario: Literal["new", "active", "trial_unavailable"] = "new"


class PreviewButton(BaseModel):
    id: str
    label: str
    style: ButtonStyle = "default"
    icon_custom_emoji_id: str | None = None
    emoji_fallback: str = ""
    thumbnail_url: str | None = None
    kind: Literal["callback", "url", "webapp"]
    target: str


class HiddenMenuButton(BaseModel):
    id: str
    label: str
    reason: str


class MenuPreviewOut(BaseModel):
    text: str
    rows: list[list[PreviewButton]]
    hidden: list[HiddenMenuButton]
    available: bool = True


class MenuTestOut(BaseModel):
    sent: bool
    capabilities: EmojiCapabilities
    message_id: int | None = None


class EmojiSetInfo(BaseModel):
    name: str
    title: str
    count: int
    state: Literal["ready", "warming", "partial", "error", "unknown"] = "unknown"
    cached_count: int = 0
    preview_count: int = 0


class EmojiLibraryOut(BaseModel):
    library: TelegramEmojiLibrary
    revision: str
    sets: list[EmojiSetInfo]


class EmojiLibraryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=256)
    expected_revision: str = Field(min_length=64, max_length=64)


class EmojiRefreshBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=256)


class EmojiCatalogOut(BaseModel):
    items: list[EmojiItem]
    total: int
    offset: int
    limit: int


class CachedEmojiSet(BaseModel):
    name: str
    title: str
    saved_at: float
    items: list[CachedEmojiItem]
