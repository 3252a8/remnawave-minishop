from typing import Any

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_settings_manifest import manifest_payload
from bot.app.web.context import (
    get_session_factory,
    get_settings,
)
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    INTEGER_SCHEMA,
    RouteContract,
    ok_envelope_for,
    ok_envelope_with,
    register_contract,
)
from bot.app.web.webapp.cache_helpers import refresh_webapp_runtime_after_settings_change
from bot.services.entitlements import features as entitlement_features
from bot.services.settings_override_service import current_value, update_overrides
from config.settings import Settings
from config.subscription_guides_config import (
    SubscriptionGuidesConfigError,
    subscription_guides_admin_config_json,
)
from db.dal import app_settings_dal

from .auth import (
    _require_admin_user_id,
)
from .common import (
    _error,
    _error_payload,
    _ok,
)
from .response_schemas import AdminSettingsOut
from .schemas import AdminSettingsPatchBody

VALUE_SOURCE_DATABASE_OVERRIDE = "database_override"
VALUE_SOURCE_ENVIRONMENT = "environment"

register_contract(
    "admin_settings_get_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminSettingsOut),
        models=(AdminSettingsOut,),
    ),
)
register_contract(
    "admin_settings_patch_route",
    RouteContract(
        request_model=AdminSettingsPatchBody,
        response_schema=ok_envelope_with({"applied": INTEGER_SCHEMA, "reverted": INTEGER_SCHEMA}),
    ),
)


async def admin_settings_get_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = get_settings(request)
    async_session_factory: sessionmaker = get_session_factory(request)

    async with async_session_factory() as session:
        overrides = await app_settings_dal.get_overrides_with_meta(session)

    overrides_by_key = {entry["key"]: entry for entry in overrides}

    fields = manifest_payload()
    webhook_base_url = str(settings.WEBHOOK_BASE_URL or "").strip().rstrip("/")
    sections: dict[str, dict[str, Any]] = {}
    for field in fields:
        key = field["key"]
        section_id = field["section"]
        if section_id not in sections:
            sections[section_id] = {
                "id": section_id,
                "order": field["section_order"],
                "fields": [],
            }
        override = overrides_by_key.get(key)
        value = current_value(settings, key)
        is_secret = bool(field.get("secret"))
        stored_override = bool(override)
        overridden = stored_override
        source = None
        read_error = None
        if key == "SUBSCRIPTION_PAGE_CONFIG_JSON":
            try:
                value, source = subscription_guides_admin_config_json(settings)
                overridden = source == "admin_json"
            except SubscriptionGuidesConfigError as exc:
                read_error = str(exc)
        value_source = (
            VALUE_SOURCE_DATABASE_OVERRIDE if stored_override else VALUE_SOURCE_ENVIRONMENT
        )
        response_field = {
            **field,
            "value": "" if is_secret else value,
            "overridden": overridden,
            "value_source": value_source,
            "updated_at": override.get("updated_at") if override else None,
        }
        if source:
            response_field["source"] = source
        if read_error:
            response_field["read_error"] = read_error
        if is_secret:
            response_field["has_value"] = bool(value)
        webhook_path = str(response_field.get("webhook_path") or "").strip()
        if webhook_path:
            if not webhook_path.startswith("/"):
                webhook_path = f"/{webhook_path}"
            response_field["webhook_path"] = webhook_path
            response_field["webhook_base_url_configured"] = bool(webhook_base_url)
            if webhook_base_url:
                response_field["webhook_url"] = f"{webhook_base_url}{webhook_path}"
        sections[section_id]["fields"].append(response_field)

    ordered_sections = sorted(sections.values(), key=lambda s: s["order"])
    return _ok({"sections": ordered_sections, "features": sorted(entitlement_features())})


async def admin_settings_patch_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    settings: Settings = get_settings(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    body = await parse_body_or_400(request, AdminSettingsPatchBody)
    updates = body.updates or {}
    deletes = body.deletes or []
    if not isinstance(updates, dict):
        return _error(400, "invalid_updates")
    if not isinstance(deletes, list):
        return _error(400, "invalid_deletes")
    if (
        "SUBSCRIPTION_PAGE_CONFIG_JSON" in updates
        and not str(updates.get("SUBSCRIPTION_PAGE_CONFIG_JSON") or "").strip()
    ):
        updates = dict(updates)
        updates.pop("SUBSCRIPTION_PAGE_CONFIG_JSON", None)
        deletes = [*deletes, "SUBSCRIPTION_PAGE_CONFIG_JSON"]

    result = await update_overrides(
        settings,
        async_session_factory,
        updates=updates,
        deletes=deletes,
        actor_id=actor_id,
    )
    if not result.get("ok"):
        return _error_payload(
            400,
            "validation_failed",
            errors=result.get("errors", {}),
            message=result.get("message", "Validation failed"),
        )

    await refresh_webapp_runtime_after_settings_change(request, updates=updates, deletes=deletes)

    return _ok({"applied": result.get("applied", 0), "reverted": result.get("reverted", 0)})
