"""Shared admin settings manifest value objects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SettingField:
    key: str
    type: str  # "string" | "int" | "float" | "bool" | "text" | "url" | "color" | "icon" | "json"
    section: str
    label: str
    description: str = ""
    placeholder: str = ""
    optional: bool = True
    secret: bool = False
    min: float | None = None
    max: float | None = None
    choices: tuple[tuple[str, str], ...] | None = None
    subsection: str | None = None  # group label inside a section
    i18n_label_key: str | None = None
    i18n_description_key: str | None = None
    i18n_subsection_key: str | None = None
    webhook_path: str | None = None
    webhook_requires_base_url: bool = False
    webhook_provider_id: str | None = None
    webhook_hint_i18n_key: str | None = None
    webhook_hint: str = ""


TRAFFIC_STRATEGY_CHOICES: tuple[tuple[str, str], ...] = (
    ("NO_RESET", "NO_RESET"),
    ("DAY", "DAY"),
    ("WEEK", "WEEK"),
    ("MONTH", "MONTH"),
    ("MONTH_ROLLING", "MONTH_ROLLING"),
)
