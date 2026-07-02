"""Manifest of settings editable from the admin web app.

Each entry describes a single overridable attribute on the global
``Settings`` instance. The manifest is the only contract between the
admin UI and the backend: keys not listed here cannot be changed via
the API, even by an admin.
"""

from __future__ import annotations

import re
from typing import Any

from bot.app.web.admin_settings_manifest_fields import SETTINGS_MANIFEST, SettingField


def _provider_field_to_setting_field(spec: Any, manifest_field: Any) -> SettingField:
    return SettingField(
        key=manifest_field.key,
        type=manifest_field.type,
        section="payments",
        label=manifest_field.label,
        description=manifest_field.description,
        placeholder=manifest_field.placeholder,
        optional=manifest_field.optional,
        secret=manifest_field.secret,
        min=manifest_field.min,
        max=manifest_field.max,
        choices=tuple(manifest_field.choices) if manifest_field.choices else None,
        subsection=manifest_field.subsection,
        i18n_label_key=getattr(manifest_field, "i18n_label_key", None),
        i18n_description_key=getattr(manifest_field, "i18n_description_key", None),
        i18n_subsection_key=getattr(manifest_field, "i18n_subsection_key", None),
    )


def aggregated_manifest() -> list[SettingField]:
    """SETTINGS_MANIFEST + per-provider fragments declared in provider SPECs."""
    from bot.payment_providers import iter_provider_manifest_fields  # local to avoid cycle

    fields: list[SettingField] = list(SETTINGS_MANIFEST)
    for spec, manifest_field in iter_provider_manifest_fields():
        fields.append(_provider_field_to_setting_field(spec, manifest_field))
    return fields


def get_field_by_key(key: str) -> SettingField | None:
    for field in aggregated_manifest():
        if field.key == key:
            return field
    return None


def manifest_keys() -> list[str]:
    return [f.key for f in aggregated_manifest()]


def coerce_value(field: SettingField, raw: Any) -> Any:
    """Coerce a value coming from JSON to the type declared by the field."""

    if field.type == "json":
        if raw is None:
            return ""
        text = raw if isinstance(raw, str) else str(raw)
        text = text.strip()
        if not text:
            return ""
        from config.subscription_guides_config import validate_subscription_guides_config_text

        validate_subscription_guides_config_text(text)
        return text

    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        if not field.optional:
            raise ValueError(f"{field.key}: value required")
        return None

    if field.type == "bool":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        if isinstance(raw, str):
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        return bool(raw)

    if field.type == "int":
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field.key}: integer expected") from exc
        if field.min is not None and value < field.min:
            raise ValueError(f"{field.key}: must be >= {field.min:g}")
        if field.max is not None and value > field.max:
            raise ValueError(f"{field.key}: must be <= {field.max:g}")
        return value

    if field.type == "float":
        try:
            float_value = float(str(raw).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field.key}: number expected") from exc
        if field.min is not None and float_value < field.min:
            raise ValueError(f"{field.key}: must be >= {field.min:g}")
        if field.max is not None and float_value > field.max:
            raise ValueError(f"{field.key}: must be <= {field.max:g}")
        return float_value

    if isinstance(raw, str):
        return raw.strip()
    return str(raw)


def _i18n_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "default"


def manifest_payload() -> list[dict]:
    """Serialize the manifest for the admin UI.

    For provider presentation fields we resolve the SPEC-declared default
    (e.g. the button text the bot would use if the admin leaves the override
    blank) and expose it as ``default``; ``placeholder`` falls back to the
    same value so existing UIs that only read ``placeholder`` also show the
    hint inside the empty input.
    """
    from bot.payment_providers import (
        find_manifest_owner,
        manifest_field_default,
        provider_admin_only_pairs,
        provider_webhook_metadata,
    )

    sections_order = {
        "general": 1,
        "appearance": 2,
        "remnawave": 3,
        "pricing": 11,
        "payments": 4,
        "trial": 5,
        "referral": 6,
        "notifications": 7,
        "support": 8,
        "backups": 9,
        "devices": 10,
        "subscription_guides": 10,
        "system": 12,
        "migrations": 13,
    }
    exclusive_map = {
        key: opposite
        for public_key, admin_key in provider_admin_only_pairs()
        for key, opposite in ((public_key, admin_key), (admin_key, public_key))
    }
    items: list[dict] = []
    for field in aggregated_manifest():
        auto_label_i18n_key = f"admin_settings_field_{field.key.lower()}_label"
        auto_description_i18n_key = f"admin_settings_field_{field.key.lower()}_description"
        auto_subsection_i18n_key = (
            f"admin_settings_subsection_{_i18n_slug(field.subsection)}"
            if field.subsection
            else None
        )

        default_value: str | None = None
        webhook_metadata: dict | None = None
        owner = find_manifest_owner(field.key)
        if owner is not None:
            spec, manifest_field = owner
            default_value = manifest_field_default(spec, manifest_field)
            webhook_metadata = provider_webhook_metadata(spec)

        placeholder = field.placeholder
        if not placeholder and default_value:
            placeholder = default_value

        item = {
            "key": field.key,
            "type": field.type,
            "section": field.section,
            "section_order": sections_order.get(field.section, 99),
            "subsection": field.subsection,
            "label": field.label,
            "description": field.description,
            "i18n_label_key": field.i18n_label_key or auto_label_i18n_key,
            "i18n_description_key": field.i18n_description_key
            or (auto_description_i18n_key if field.description else None),
            "i18n_subsection_key": field.i18n_subsection_key or auto_subsection_i18n_key,
            "i18n_placeholder_key": (
                f"admin_settings_field_{field.key.lower()}_placeholder" if placeholder else None
            ),
            "placeholder": placeholder,
            "optional": field.optional,
            "secret": field.secret,
        }
        if field.min is not None:
            item["min"] = field.min
        if field.max is not None:
            item["max"] = field.max
        if field.key in exclusive_map:
            item["mutually_exclusive_key"] = exclusive_map[field.key]
        if default_value is not None:
            item["default"] = default_value
        if webhook_metadata:
            item.update(webhook_metadata)
        if field.webhook_path:
            item["webhook_path"] = field.webhook_path
            item["webhook_requires_base_url"] = field.webhook_requires_base_url
            if field.webhook_provider_id:
                item["provider_id"] = field.webhook_provider_id
            if field.webhook_hint_i18n_key:
                item["webhook_hint_i18n_key"] = field.webhook_hint_i18n_key
            if field.webhook_hint:
                item["webhook_hint"] = field.webhook_hint
        if field.choices:
            item["choices"] = [
                {
                    "value": v,
                    "label": lbl,
                    "i18n_label_key": (
                        f"admin_settings_field_{field.key.lower()}_choice_{_i18n_slug(str(v))}"
                    ),
                }
                for v, lbl in field.choices
            ]
        items.append(item)
    return items
