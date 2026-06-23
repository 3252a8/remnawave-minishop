"""Apply persisted setting overrides on top of the env-based Settings.

The runtime treats DB overrides as the source of truth: env values are
loaded once via pydantic, then any matching keys from the
``app_setting_overrides`` table replace those attributes in-process.
This way the admin can flip flags, adjust prices or rename labels
without restarting the container.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_settings_manifest import (
    SettingField,
    coerce_value,
    get_field_by_key,
    manifest_keys,
)
from config.settings import Settings
from db.dal import app_settings_dal

logger = logging.getLogger(__name__)

APPEARANCE_OVERRIDE_KEYS = {
    "WEBAPP_LOGO_URL",
    "WEBAPP_FAVICON_USE_CUSTOM",
    "WEBAPP_FAVICON_URL",
    "WEBAPP_LOGO_FAVICON_URL",
    "WEBAPP_PRIMARY_COLOR",
}
APP_ROOT = Path(__file__).resolve().parents[3]
APPEARANCE_OVERRIDES_BACKUP_PATH = APP_ROOT / "data" / "webapp-logo" / "appearance-settings.json"


def _resolve_attribute_name(settings: Settings, key: str) -> Optional[str]:
    """Resolve the actual attribute name on the Settings model.

    Some settings expose their env name via ``alias`` (e.g. MONTH_1_ENABLED is
    aliased to "1_MONTH_ENABLED"). Lookups by either alias or attribute name
    should both succeed, with the attribute name returned in either case.
    """

    if hasattr(settings, key):
        return key

    fields = type(settings).model_fields
    for attr_name, field_info in fields.items():
        alias = getattr(field_info, "alias", None)
        if alias and alias == key:
            return str(attr_name)
    return None


def _apply_to_provider_bundle(key: str, value: Any) -> bool:
    """Route an override into the matching provider config/presentation model.

    Provider modules own their env-config via BaseSettings subclasses; here
    we look up which one owns ``key`` and write the value into the right
    attribute on the right model.
    """
    from bot.payment_providers import (
        find_manifest_owner,
        get_provider_bundle,
        get_spec_presentation,
    )

    owner = find_manifest_owner(key)
    if owner is None:
        return False
    spec, manifest_field = owner
    if manifest_field.target == "presentation":
        target = get_spec_presentation(spec.id)
        if target is None:
            bundle = get_provider_bundle(spec.service_key)
            target = bundle.presentation if bundle else None
    else:
        bundle = get_provider_bundle(spec.service_key)
        target = bundle.config if bundle else None
    if target is None:
        return False
    attr_name = manifest_field.attr or key
    try:
        setattr(target, attr_name, value)
        return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to apply provider override %s=%r: %s", key, value, exc)
        return False


def _apply_value(settings: Settings, key: str, value: Any) -> bool:
    # Provider-owned keys go to provider models, not the central Settings.
    if _apply_to_provider_bundle(key, value):
        return True
    attr_name = _resolve_attribute_name(settings, key)
    if not attr_name:
        return False
    try:
        setattr(settings, attr_name, value)
        return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to apply override %s=%r: %s", key, value, exc)
        return False


def apply_overrides(settings: Settings, overrides: Dict[str, Any]) -> int:
    applied = 0
    for key, raw_value in overrides.items():
        field = get_field_by_key(key)
        if not field:
            continue
        try:
            coerced = coerce_value(field, raw_value)
        except ValueError as exc:
            logger.warning("Skipping override %s: %s", key, exc)
            continue
        if _apply_value(settings, key, coerced):
            applied += 1
    return applied


def _normalize_exclusive_provider_toggles(
    updates: Dict[str, Any],
    deletes: list,
) -> tuple[Dict[str, Any], list]:
    """When a provider is enabled for admins only, turn off its public toggle."""

    from bot.payment_providers import provider_admin_only_pairs

    exclusive_map = {
        key: opposite
        for public_key, admin_key in provider_admin_only_pairs()
        for key, opposite in ((public_key, admin_key), (admin_key, public_key))
    }
    if not exclusive_map:
        return updates, deletes

    normalized = dict(updates)
    normalized_deletes = list(deletes)
    for key, value in updates.items():
        if value is not True or key not in exclusive_map:
            continue
        opposite = exclusive_map[key]
        normalized[opposite] = False
        normalized_deletes = [item for item in normalized_deletes if item != opposite]
    return normalized, normalized_deletes


def _appearance_snapshot(settings: Settings) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {}
    logo_url = settings.WEBAPP_LOGO_URL
    logo_favicon_url = settings.WEBAPP_LOGO_FAVICON_URL
    favicon_url = settings.WEBAPP_FAVICON_URL
    if logo_url:
        snapshot["WEBAPP_LOGO_URL"] = logo_url
    if logo_favicon_url:
        snapshot["WEBAPP_LOGO_FAVICON_URL"] = logo_favicon_url
    if favicon_url:
        snapshot["WEBAPP_FAVICON_URL"] = favicon_url
    if settings.WEBAPP_FAVICON_USE_CUSTOM:
        snapshot["WEBAPP_FAVICON_USE_CUSTOM"] = True
    primary_color = settings.WEBAPP_PRIMARY_COLOR
    if primary_color and primary_color != "#00fe7a":
        snapshot["WEBAPP_PRIMARY_COLOR"] = primary_color
    return snapshot


def _read_appearance_backup() -> Dict[str, Any]:
    try:
        payload = json.loads(APPEARANCE_OVERRIDES_BACKUP_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read appearance settings backup: %s", exc)
        return {}
    if not isinstance(payload, dict):
        return {}
    raw_values = payload.get("settings")
    values: dict[str, Any] = raw_values if isinstance(raw_values, dict) else payload
    restored: Dict[str, Any] = {}
    for key, value in values.items():
        if key not in APPEARANCE_OVERRIDE_KEYS:
            continue
        if value in (None, "") or value is False:
            continue
        field = get_field_by_key(key)
        if not field:
            continue
        try:
            restored[key] = coerce_value(field, value)
        except ValueError as exc:
            logger.warning("Skipping appearance backup key %s: %s", key, exc)
    return restored


def write_appearance_backup(settings: Settings) -> None:
    payload = {
        "version": 1,
        "settings": _appearance_snapshot(settings),
    }
    try:
        APPEARANCE_OVERRIDES_BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
        APPEARANCE_OVERRIDES_BACKUP_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Failed to write appearance settings backup: %s", exc)


async def load_overrides_from_db(settings: Settings, async_session_factory: sessionmaker) -> int:
    """Fetch overrides from the DB and apply them to the in-memory settings.

    Provider env-configs live on per-provider BaseSettings bundles instead of
    the central Settings model. Apply needs those bundles to already exist,
    otherwise provider-owned overrides (e.g. ``HELEKET_ENABLED``) silently
    drop on the floor. Build them up-front; the call is idempotent so the
    later ``build_core_services`` invocation reuses these same instances.
    """
    from bot.payment_providers import build_provider_configs

    build_provider_configs()

    try:
        async with async_session_factory() as session:
            overrides = await app_settings_dal.get_all_overrides(session)
            backup_overrides = _read_appearance_backup()
            missing_backup_overrides = {
                key: value for key, value in backup_overrides.items() if key not in overrides
            }
            if missing_backup_overrides:
                for key, value in missing_backup_overrides.items():
                    await app_settings_dal.upsert_override(
                        session, key=key, value=value, updated_by=None
                    )
                await session.commit()
                overrides.update(missing_backup_overrides)
                logger.info(
                    "Restored %s appearance setting overrides from %s",
                    len(missing_backup_overrides),
                    APPEARANCE_OVERRIDES_BACKUP_PATH,
                )
    except Exception as exc:
        logger.warning("Could not load setting overrides from DB: %s", exc)
        return 0

    applied = apply_overrides(settings, overrides)
    if applied:
        logger.info("Applied %s setting overrides from DB", applied)
    return applied


async def refresh_overrides_from_db(
    settings: Settings,
    async_session_factory: sessionmaker,
    *,
    keys: Optional[set[str]] = None,
) -> int:
    """Refresh already-known runtime overrides without startup restore side effects."""

    try:
        async with async_session_factory() as session:
            overrides = await app_settings_dal.get_all_overrides(session)
    except Exception as exc:
        logger.warning("Could not refresh setting overrides from DB: %s", exc)
        return 0
    if keys is not None:
        try:
            env_only = Settings()
            for key in keys:
                if key in overrides:
                    continue
                attr_name = _resolve_attribute_name(env_only, key)
                if attr_name and hasattr(env_only, attr_name):
                    setattr(settings, attr_name, getattr(env_only, attr_name))
        except Exception as exc:
            logger.warning("Failed to restore env defaults while refreshing overrides: %s", exc)
        overrides = {key: value for key, value in overrides.items() if key in keys}
    return apply_overrides(settings, overrides)


async def update_overrides(
    settings: Settings,
    async_session_factory: sessionmaker,
    *,
    updates: Dict[str, Any],
    deletes: Optional[list] = None,
    actor_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Persist + apply a batch of changes coming from the admin UI."""

    deletes = list(deletes or [])
    coerced_updates: Dict[str, Any] = {}
    errors: Dict[str, str] = {}

    for key, raw in updates.items():
        field: Optional[SettingField] = get_field_by_key(key)
        if not field:
            errors[key] = "unknown_setting"
            continue
        try:
            coerced_updates[key] = coerce_value(field, raw)
        except ValueError as exc:
            errors[key] = str(exc)

    valid_deletes = []
    for key in deletes:
        if get_field_by_key(key) is None:
            errors.setdefault(key, "unknown_setting")
            continue
        valid_deletes.append(key)

    if errors:
        return {"ok": False, "errors": errors}

    coerced_updates, valid_deletes = _normalize_exclusive_provider_toggles(
        coerced_updates,
        valid_deletes,
    )

    async with async_session_factory() as raw_session:
        session: AsyncSession = raw_session
        async with session.begin():
            for key, value in coerced_updates.items():
                await app_settings_dal.upsert_override(
                    session, key=key, value=value, updated_by=actor_id
                )
            for key in valid_deletes:
                await app_settings_dal.delete_override(session, key)

    # Apply locally; deletes need an env-default fallback. We re-read the env
    # default by instantiating a fresh Settings() / provider-config model
    # (cheap; just a few ms) and copying the matching attributes back over.
    if valid_deletes:
        from bot.payment_providers import (
            find_manifest_owner,
            get_provider_bundle,
            get_spec_presentation,
        )

        try:
            env_only = Settings()
            for key in valid_deletes:
                owner = find_manifest_owner(key)
                if owner is not None:
                    spec, manifest_field = owner
                    if manifest_field.target == "presentation":
                        target = get_spec_presentation(spec.id)
                        if target is None:
                            bundle = get_provider_bundle(spec.service_key)
                            target = bundle.presentation if bundle else None
                    else:
                        bundle = get_provider_bundle(spec.service_key)
                        target = bundle.config if bundle else None
                    if target is None:
                        continue
                    cls = type(target)
                    try:
                        fresh = cls()
                    except Exception as exc:
                        logger.warning(
                            "Failed to reload provider env defaults for %s: %s",
                            key,
                            exc,
                        )
                        continue
                    attr = manifest_field.attr or key
                    if hasattr(fresh, attr):
                        setattr(target, attr, getattr(fresh, attr))
                    continue
                attr_name = _resolve_attribute_name(env_only, key) or key
                if hasattr(env_only, attr_name):
                    setattr(settings, attr_name, getattr(env_only, attr_name))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to restore env defaults: %s", exc)

    apply_overrides(settings, coerced_updates)
    appearance_changed = APPEARANCE_OVERRIDE_KEYS.intersection(
        coerced_updates
    ) or APPEARANCE_OVERRIDE_KEYS.intersection(valid_deletes)
    if appearance_changed:
        write_appearance_backup(settings)

    return {"ok": True, "applied": len(coerced_updates), "reverted": len(valid_deletes)}


def overridable_keys() -> list:
    return list(manifest_keys())


def current_value(settings: Settings, key: str) -> Any:
    # Provider-owned keys live on per-provider BaseSettings bundles, not the
    # central Settings — check there first.
    from bot.payment_providers import (
        find_manifest_owner,
        get_provider_bundle,
        get_spec_presentation,
    )

    owner = find_manifest_owner(key)
    if owner is not None:
        spec, manifest_field = owner
        if manifest_field.target == "presentation":
            target = get_spec_presentation(spec.id)
            if target is None:
                bundle = get_provider_bundle(spec.service_key)
                target = bundle.presentation if bundle else None
        else:
            bundle = get_provider_bundle(spec.service_key)
            target = bundle.config if bundle else None
        if target is not None:
            attr = manifest_field.attr or key
            return getattr(target, attr, None)
        return None

    attr_name = _resolve_attribute_name(settings, key)
    if not attr_name:
        return None
    return getattr(settings, attr_name, None)
