# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405

from bot.middlewares.i18n import JsonI18n, locale_language_options, resolve_locale_key
from bot.services.locale_override_service import (
    LOCALE_OVERRIDES_PATH,
    audience_for_locale_key,
    group_id_for_locale_key,
    locale_group_catalog,
    load_locale_overrides,
    update_locale_overrides,
)

def _locale_languages(
    i18n: JsonI18n,
    overrides: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    base_languages = set((i18n.base_locales_data or {}).keys())
    override_languages = {str(entry.get("lang") or "") for entry in overrides or []}
    override_languages.update((i18n.locale_overrides or {}).keys())
    return locale_language_options(
        base_languages | override_languages,
        base_languages=base_languages,
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
    i18n: Optional[JsonI18n] = request.app.get("i18n")
    if i18n is None:
        return _error(503, "i18n_unavailable")
    async_session_factory: sessionmaker = request.app["async_session_factory"]

    await load_locale_overrides(i18n, async_session_factory)
    async with async_session_factory() as session:
        overrides = await locale_overrides_dal.get_overrides_with_meta(session)

    return _ok(_admin_translations_payload(i18n, overrides))


async def admin_translations_patch_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    i18n: Optional[JsonI18n] = request.app.get("i18n")
    if i18n is None:
        return _error(503, "i18n_unavailable")
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    payload = await _read_json(request)
    updates = payload.get("updates") or {}
    deletes = payload.get("deletes") or []
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
        return web.json_response(
            {"ok": False, "error": "validation_failed", "errors": result.get("errors", {})},
            status=400,
        )

    return _ok(
        {
            "applied": result.get("applied", 0),
            "reverted": result.get("reverted", 0),
            "file_written": result.get("file_written", False),
        }
    )
