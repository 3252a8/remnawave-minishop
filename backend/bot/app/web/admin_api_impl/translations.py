from typing import Any, Dict, List, Optional, Tuple, cast

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_i18n,
    get_session_factory,
)
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    BOOLEAN_SCHEMA,
    INTEGER_SCHEMA,
    STRING_SCHEMA,
    RouteContract,
    loose_array_schema,
    ok_envelope_with,
    register_contract,
)
from bot.middlewares.i18n import JsonI18n, locale_language_options, resolve_locale_key
from bot.services.locale_override_service import (
    LOCALE_OVERRIDES_PATH,
    audience_for_locale_key,
    group_id_for_locale_key,
    load_locale_overrides,
    locale_group_catalog,
    update_locale_overrides,
)
from db.dal import locale_overrides_dal

from .auth import (
    _require_admin_user_id,
)
from .common import (
    _error,
    _error_payload,
    _ok,
)
from .schemas import AdminTranslationsPatchBody

register_contract(
    "admin_translations_get_route",
    RouteContract(
        response_schema=ok_envelope_with(
            {
                "languages": loose_array_schema(),
                "groups": loose_array_schema(),
                "path": STRING_SCHEMA,
                "override_count": INTEGER_SCHEMA,
            }
        )
    ),
)
register_contract(
    "admin_translations_patch_route",
    RouteContract(
        request_model=AdminTranslationsPatchBody,
        response_schema=ok_envelope_with(
            {
                "applied": INTEGER_SCHEMA,
                "reverted": INTEGER_SCHEMA,
                "file_written": BOOLEAN_SCHEMA,
            }
        ),
    ),
)


def _locale_languages(
    i18n: JsonI18n,
    overrides: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    base_languages = set((i18n.base_locales_data or {}).keys())
    override_languages = {str(entry.get("lang") or "") for entry in overrides or []}
    override_languages.update((i18n.locale_overrides or {}).keys())
    return cast(
        List[Dict[str, Any]],
        locale_language_options(
            base_languages | override_languages,
            base_languages=base_languages,
        ),
    )


def _locale_override_meta_map(overrides: List[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict]:
    result: Dict[Tuple[str, str], Dict] = {}
    for entry in overrides:
        lang = str(entry.get("lang") or "")
        raw_key = str(entry.get("key") or "")
        key = resolve_locale_key(raw_key)
        if lang and key:
            if raw_key != key and (lang, key) in result:
                continue
            result[(lang, key)] = entry
    return result


def _admin_translations_payload(
    i18n: JsonI18n,
    overrides: List[Dict[str, Any]],
) -> Dict[str, Any]:
    base_data = i18n.base_locales_data or i18n.locales_data or {}
    effective_data = i18n.locales_data or {}
    override_meta = _locale_override_meta_map(overrides)
    language_items = _locale_languages(i18n, overrides)
    languages = [item["code"] for item in language_items]
    all_keys = sorted(
        {key for messages in base_data.values() for key in messages.keys()}
        | {key for _, key in override_meta.keys()}
    )

    groups_by_id = {
        group["id"]: {
            **group,
            "items": [],
        }
        for group in locale_group_catalog()
    }

    for key in all_keys:
        values: Dict[str, Dict[str, Any]] = {}
        for lang in languages:
            meta = override_meta.get((lang, key))
            fallback_base = base_data.get(i18n.default_lang, {}).get(key, "")
            values[lang] = {
                "base": base_data.get(lang, {}).get(key, ""),
                "fallback": fallback_base,
                "effective": effective_data.get(lang, {}).get(key, ""),
                "override": meta.get("value") if meta else "",
                "overridden": bool(meta),
                "updated_at": meta.get("updated_at") if meta else None,
                "updated_by": meta.get("updated_by") if meta else None,
            }
        group_id = group_id_for_locale_key(key)
        groups_by_id.setdefault(
            group_id,
            {"id": group_id, "title": group_id, "description": "", "items": []},
        )
        groups_by_id[group_id]["items"].append(
            {
                "key": key,
                "audience": audience_for_locale_key(key),
                "values": values,
            }
        )

    groups = [group for group in groups_by_id.values() if group["items"]]
    return {
        "languages": language_items,
        "groups": groups,
        "path": str(LOCALE_OVERRIDES_PATH),
        "override_count": len(overrides),
    }


async def admin_translations_get_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    i18n: Optional[JsonI18n] = get_i18n(request)
    if i18n is None:
        return _error(503, "i18n_unavailable")
    async_session_factory: sessionmaker = get_session_factory(request)

    await load_locale_overrides(i18n, async_session_factory)
    async with async_session_factory() as session:
        overrides = await locale_overrides_dal.get_overrides_with_meta(session)

    return _ok(_admin_translations_payload(i18n, overrides))


async def admin_translations_patch_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    i18n: Optional[JsonI18n] = get_i18n(request)
    if i18n is None:
        return _error(503, "i18n_unavailable")
    async_session_factory: sessionmaker = get_session_factory(request)
    body = await parse_body_or_400(request, AdminTranslationsPatchBody)
    updates = body.updates or {}
    deletes = body.deletes or []
    if not isinstance(updates, dict):
        return _error(400, "invalid_updates")
    if not isinstance(deletes, list):
        return _error(400, "invalid_deletes")

    result = await update_locale_overrides(
        i18n,
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

    return _ok(
        {
            "applied": result.get("applied", 0),
            "reverted": result.get("reverted", 0),
            "file_written": result.get("file_written", False),
        }
    )
