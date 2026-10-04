"""Versioned cosmetic Telegram menu settings, independent of navigation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from config.telegram_emoji import CUSTOM_EMOJI_ID_RE

APPEARANCE_KEY = "TELEGRAM_MENU_APPEARANCE_JSON"
LIBRARY_KEY = "TELEGRAM_CUSTOM_EMOJI_LIBRARY_JSON"
TELEGRAM_MENU_SETTING_KEYS = {APPEARANCE_KEY, LIBRARY_KEY}
_SET_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")
_BUTTON_ID_RE = re.compile(r"^(?:[a-z][a-z_]*|custom:[A-Za-z0-9_-]{1,64})$")
MAX_SETTING_BYTES = 64 * 1024
ButtonStyle = Literal["default", "primary", "success", "danger"]


@dataclass(frozen=True)
class MenuAppearanceEntry:
    id: str
    label_key: str
    screens: tuple[str, ...]
    emoji_fallback: str = ""


MENU_APPEARANCE_ENTRIES = (
    MenuAppearanceEntry("trial", "menu_activate_trial_button", ("main", "bot"), "🎁"),
    MenuAppearanceEntry("personal_account", "menu_personal_account_button", ("main", "bot"), "🔑"),
    MenuAppearanceEntry("bot_interface", "menu_bot_interface_button", ("main",), "🤖"),
    MenuAppearanceEntry("subscribe", "menu_subscribe_inline", ("bot",), "🚀"),
    MenuAppearanceEntry("my_subscription", "menu_my_subscription_inline", ("bot",), "📋"),
    MenuAppearanceEntry("promo", "menu_apply_promo_button", ("bot",), "🎟️"),
    MenuAppearanceEntry("referral", "menu_referral_inline", ("bot",), "🎁"),
    MenuAppearanceEntry("language", "menu_language_settings_inline", ("bot",), "🌐"),
    MenuAppearanceEntry("server_status", "menu_server_status_button", ("main", "bot"), "📊"),
    MenuAppearanceEntry("support", "menu_support_button", ("main", "bot"), "💬"),
    MenuAppearanceEntry("information", "menu_info_button", ("main", "bot"), "ℹ️"),
    MenuAppearanceEntry("back_to_main", "back_to_main_menu_button", ("bot", "information"), "⬅️"),
    MenuAppearanceEntry("privacy", "privacy_policy_button", ("information",), "🔒"),
    MenuAppearanceEntry("user_agreement", "user_agreement_button", ("information",), "📄"),
)
BUILTIN_APPEARANCE_IDS = frozenset(entry.id for entry in MENU_APPEARANCE_ENTRIES)


class ButtonAppearance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: ButtonStyle = "default"
    icon_custom_emoji_id: str | None = None
    icon_mode: Literal["inherit", "none", "custom"] = "inherit"

    @field_validator("icon_custom_emoji_id")
    @classmethod
    def validate_emoji_id(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not CUSTOM_EMOJI_ID_RE.fullmatch(value):
            raise ValueError(
                "custom emoji ID must be a positive decimal string of at most 20 digits"
            )
        return value

    @model_validator(mode="after")
    def resolve_mode(self) -> ButtonAppearance:
        if self.icon_custom_emoji_id and self.icon_mode == "inherit":
            self.icon_mode = "custom"
        if self.icon_mode == "custom" and not self.icon_custom_emoji_id:
            raise ValueError("custom icon requires a custom emoji ID")
        if self.icon_mode == "none":
            self.icon_custom_emoji_id = None
        return self


class TelegramMenuAppearance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    buttons: dict[str, ButtonAppearance] = Field(default_factory=dict, max_length=64)

    @field_validator("buttons")
    @classmethod
    def validate_buttons(cls, value: dict[str, ButtonAppearance]) -> dict[str, ButtonAppearance]:
        for key in value:
            if not _BUTTON_ID_RE.fullmatch(key):
                raise ValueError("invalid menu appearance ID")
            if not key.startswith("custom:") and key not in BUILTIN_APPEARANCE_IDS:
                raise ValueError("unknown system menu button")
        return value


class TelegramEmojiLibrary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    sets: list[str] = Field(default_factory=list, max_length=20)
    manual_ids: list[str] = Field(default_factory=list, max_length=500)

    @field_validator("sets")
    @classmethod
    def validate_sets(cls, value: list[str]) -> list[str]:
        if any(not _SET_NAME_RE.fullmatch(name) for name in value):
            raise ValueError("invalid custom emoji set name")
        if len({name.casefold() for name in value}) != len(value):
            raise ValueError("duplicate custom emoji set")
        return value

    @field_validator("manual_ids")
    @classmethod
    def validate_ids(cls, value: list[str]) -> list[str]:
        if any(not CUSTOM_EMOJI_ID_RE.fullmatch(identifier) for identifier in value):
            raise ValueError("invalid custom emoji ID")
        if len(set(value)) != len(value):
            raise ValueError("duplicate custom emoji ID")
        return value


def _payload(raw: Any) -> Any:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, str):
        if len(raw.encode("utf-8")) > MAX_SETTING_BYTES:
            raise ValueError("Telegram setting is too large")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Telegram setting must be valid JSON") from exc
    if isinstance(raw, BaseModel):
        return raw.model_dump(mode="json")
    return raw


def parse_menu_appearance(raw: Any) -> TelegramMenuAppearance:
    return TelegramMenuAppearance.model_validate(_payload(raw))


def parse_emoji_library(raw: Any) -> TelegramEmojiLibrary:
    return TelegramEmojiLibrary.model_validate(_payload(raw))


def normalized_telegram_setting(key: str, raw: Any) -> str:
    model = parse_menu_appearance(raw) if key == APPEARANCE_KEY else parse_emoji_library(raw)
    result = json.dumps(model.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    if len(result.encode("utf-8")) > MAX_SETTING_BYTES:
        raise ValueError("Telegram setting is too large")
    return result


def telegram_setting_revision(key: str, raw: Any) -> str:
    return hashlib.sha256(normalized_telegram_setting(key, raw).encode("utf-8")).hexdigest()


def emoji_source(value: str) -> tuple[Literal["set", "emoji"], str]:
    source = value.strip()
    if CUSTOM_EMOJI_ID_RE.fullmatch(source):
        return "emoji", source
    if source.startswith(("https://", "http://", "tg://")):
        parsed = urlsplit(source)
        if parsed.scheme != "https" or parsed.netloc.lower() != "t.me":
            raise ValueError("use a t.me/addemoji link or set name")
        if parsed.query or parsed.fragment:
            raise ValueError("unexpected emoji set URL parameters")
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 2 or parts[0] != "addemoji":
            raise ValueError("use a t.me/addemoji link")
        source = unquote(parts[1])
    if not _SET_NAME_RE.fullmatch(source):
        raise ValueError("invalid custom emoji set name")
    return "set", source
