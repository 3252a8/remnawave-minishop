"""Validated custom buttons shared by the Telegram and Web App menus."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from config.link_targets import is_telegram_button_link, normalize_button_link

logger = logging.getLogger(__name__)

MAX_MENU_BUTTONS = 20
WEBAPP_MENU_SECTIONS = frozenset(
    {
        "home",
        "plans",
        "install",
        "trial",
        "invite",
        "partner",
        "devices",
        "support",
        "settings",
        "notifications",
        "status",
    }
)
LEGACY_ICON_EMOJI: dict[str, str] = {
    "CircleQuestionMark": "❓",
    "ExternalLink": "🔗",
    "Gift": "🎁",
    "Globe2": "🌐",
    "Home": "🏠",
    "Info": "ℹ️",
    "LifeBuoy": "🛟",
    "MessageSquare": "💬",
    "Send": "✈️",
    "Shield": "🛡️",
    "Star": "⭐",
    "Users": "👥",
    "Zap": "⚡",
}
LEGACY_EMOJI_WEBAPP_ICON: dict[str, str] = {
    "❓": "CircleQuestionMark",
    "🔗": "ExternalLink",
    "🎁": "Gift",
    "🌐": "Globe2",
    "🏠": "Home",
    "ℹ️": "Info",
    "🛟": "LifeBuoy",
    "📢": "Megaphone",
    "💬": "MessageSquare",
    "✈️": "Send",
    "🛡️": "Shield",
    "⭐": "Star",
    "👥": "Users",
    "⚡": "Zap",
}

_BUTTON_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_WEBAPP_ICON_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
_LANGUAGE_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def _normalized_language(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _normalize_http_url(value: Any, *, telegram_only: bool = False) -> str:
    raw = str(value or "").strip()
    if len(raw) > 2048:
        raise ValueError("target URL is too long")
    normalized = normalize_button_link(raw, telegram_only=telegram_only)
    if normalized is None:
        if telegram_only and normalize_button_link(raw) is not None:
            raise ValueError("Telegram target must use t.me or telegram.me")
        expected = "a Telegram t.me link" if telegram_only else "an HTTP(S) URL"
        raise ValueError(f"target must be {expected}")
    return normalized


class MenuButton(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    kind: Literal["external", "telegram", "webapp"]
    target: str = Field(min_length=1, max_length=2048)
    webapp_icon: str = Field(default="", max_length=64)
    telegram_emoji: str = Field(default="", max_length=16)
    labels: dict[str, str]
    show_in_bot: bool = True
    show_in_webapp: bool = True

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_icon(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        legacy_icon = str(payload.pop("icon", "") or "").strip()
        if "webapp_icon" not in payload:
            payload["webapp_icon"] = LEGACY_EMOJI_WEBAPP_ICON.get(
                legacy_icon,
                legacy_icon if _WEBAPP_ICON_RE.fullmatch(legacy_icon) else "",
            )
        if "telegram_emoji" not in payload:
            payload["telegram_emoji"] = LEGACY_ICON_EMOJI.get(
                legacy_icon,
                legacy_icon if legacy_icon and not _WEBAPP_ICON_RE.fullmatch(legacy_icon) else "",
            )
        return payload

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip()
        if not _BUTTON_ID_RE.fullmatch(normalized):
            raise ValueError("id must contain only letters, digits, underscores, or hyphens")
        return normalized

    @field_validator("webapp_icon")
    @classmethod
    def validate_webapp_icon(cls, value: str) -> str:
        normalized = value.strip()
        if normalized and not _WEBAPP_ICON_RE.fullmatch(normalized):
            raise ValueError("webapp_icon must be an icon name from the Web App icon library")
        return normalized

    @field_validator("telegram_emoji")
    @classmethod
    def validate_telegram_emoji(cls, value: str) -> str:
        normalized = value.strip()
        return normalized

    @field_validator("labels", mode="before")
    @classmethod
    def validate_labels(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            raise ValueError("labels must be an object keyed by locale")
        labels: dict[str, str] = {}
        for raw_language, raw_text in value.items():
            language = _normalized_language(raw_language)
            text = _normalized_text(raw_text)
            if not _LANGUAGE_RE.fullmatch(language) or len(language) > 16:
                raise ValueError(f"invalid locale code: {raw_language}")
            if not text:
                continue
            if len(text) > 64:
                raise ValueError(f"label for {language} must be at most 64 characters")
            labels[language] = text
        if not labels:
            raise ValueError("at least one localized label is required")
        return dict(sorted(labels.items()))

    @model_validator(mode="after")
    def validate_target(self) -> MenuButton:
        if self.kind == "webapp":
            target = self.target.strip().lower().strip("/")
            if target not in WEBAPP_MENU_SECTIONS:
                raise ValueError(f"unsupported Web App section: {target}")
            self.target = target
        elif self.kind == "telegram":
            self.target = _normalize_http_url(self.target, telegram_only=True)
        else:
            self.target = _normalize_http_url(self.target)
            if is_telegram_button_link(self.target):
                self.kind = "telegram"
        return self


def parse_menu_buttons(raw: Any) -> list[MenuButton]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"MENU_BUTTONS_JSON must be valid JSON: {exc.msg}") from exc
    else:
        payload = raw
    if not isinstance(payload, list):
        raise ValueError("MENU_BUTTONS_JSON must be a JSON array")
    if len(payload) > MAX_MENU_BUTTONS:
        raise ValueError(f"MENU_BUTTONS_JSON supports at most {MAX_MENU_BUTTONS} buttons")
    try:
        buttons = [MenuButton.model_validate(item) for item in payload]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"MENU_BUTTONS_JSON is invalid: {exc}") from exc
    ids = [button.id for button in buttons]
    if len(ids) != len(set(ids)):
        raise ValueError("MENU_BUTTONS_JSON button ids must be unique")
    return buttons


def normalize_menu_buttons_json(raw: Any) -> str:
    buttons = parse_menu_buttons(raw)
    return json.dumps(
        [button.model_dump(mode="json") for button in buttons],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def validate_menu_button_languages(buttons: list[MenuButton], languages: set[str]) -> None:
    required = {_normalized_language(language) for language in languages if language}
    for index, button in enumerate(buttons, start=1):
        missing = sorted(required.difference(button.labels))
        if missing:
            raise ValueError(
                f"button {index} ({button.id}) is missing labels for: {', '.join(missing)}"
            )


def configured_menu_buttons(raw: Any) -> list[MenuButton]:
    try:
        return parse_menu_buttons(raw)
    except ValueError as exc:
        logger.warning("Ignoring invalid MENU_BUTTONS_JSON: %s", exc)
        return []


def localized_menu_button_label(
    button: MenuButton,
    language: str,
    *,
    default_language: str = "ru",
) -> str:
    requested = _normalized_language(language)
    default = _normalized_language(default_language)
    candidates = (
        requested,
        requested.split("-", 1)[0],
        default,
        default.split("-", 1)[0],
        "en",
        "ru",
    )
    for candidate in candidates:
        if candidate and button.labels.get(candidate):
            return button.labels[candidate]
    return next(iter(button.labels.values()))


def telegram_menu_button_text(
    button: MenuButton,
    language: str,
    *,
    default_language: str = "ru",
) -> str:
    label = localized_menu_button_label(button, language, default_language=default_language)
    text = f"{button.telegram_emoji} {label}" if button.telegram_emoji else label
    return text[:64]


def public_menu_buttons(
    raw: Any, language: str, *, default_language: str = "ru"
) -> list[dict[str, str]]:
    return [
        {
            "id": button.id,
            "kind": button.kind,
            "target": button.target,
            "icon": button.webapp_icon,
            "label": localized_menu_button_label(
                button,
                language,
                default_language=default_language,
            ),
        }
        for button in configured_menu_buttons(raw)
        if button.show_in_webapp
    ]
