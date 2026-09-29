import json
import time
from typing import Any, cast
from weakref import WeakKeyDictionary

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
    RouteContract,
    ok_envelope_for,
    ok_envelope_with,
    register_contract,
)
from bot.middlewares.i18n import JsonI18n, locale_language_options, resolve_locale_key
from bot.plugins.spec import PluginLocaleGroup
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
from .response_schemas import AdminTranslationsOut
from .schemas import AdminTranslationsPatchBody

TranslationCacheSignature = tuple[int, tuple[tuple[str, str, str, str, str], ...]]
TranslationCacheEntry = tuple[TranslationCacheSignature, dict[str, Any]]

_TRANSLATIONS_PAYLOAD_CACHE: WeakKeyDictionary[JsonI18n, TranslationCacheEntry] = (
    WeakKeyDictionary()
)
_TRANSLATIONS_FILE_SYNC_CACHE: WeakKeyDictionary[JsonI18n, tuple[int, int, float]] = (
    WeakKeyDictionary()
)
_FILE_SYNC_INTERVAL_SECONDS = 30.0

register_contract(
    "admin_translations_get_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminTranslationsOut),
        models=(AdminTranslationsOut,),
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
    overrides: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    base_languages = set((i18n.base_locales_data or {}).keys())
    override_languages = {str(entry.get("lang") or "") for entry in overrides or []}
    override_languages.update((i18n.locale_overrides or {}).keys())
    return cast(
        list[dict[str, Any]],
        locale_language_options(
            base_languages | override_languages,
            base_languages=base_languages,
        ),
    )


def _locale_override_meta_map(overrides: list[dict[str, Any]]) -> dict[tuple[str, str], dict]:
    result: dict[tuple[str, str], dict] = {}
    for entry in overrides:
        lang = str(entry.get("lang") or "")
        raw_key = str(entry.get("key") or "")
        key = resolve_locale_key(raw_key)
        if lang and key:
            if raw_key != key and (lang, key) in result:
                continue
            result[(lang, key)] = entry
    return result


def _plugin_group_for_key(i18n: JsonI18n, plugin: str, key: str) -> PluginLocaleGroup | None:
    matches = (
        (len(prefix), group)
        for group in i18n.plugin_locale_groups.get(plugin, ())
        if isinstance(group, PluginLocaleGroup) and group.path
        for prefix in group.prefixes
        if prefix and key.startswith(prefix)
    )
    return max(matches, key=lambda match: match[0], default=(0, None))[1]


def _admin_translations_payload(
    i18n: JsonI18n,
    overrides: list[dict[str, Any]],
) -> dict[str, Any]:
    base_data = i18n.base_locales_data or i18n.locales_data or {}
    effective_data = i18n.locales_data or {}
    override_meta = _locale_override_meta_map(overrides)
    language_items = _locale_languages(i18n, overrides)
    languages = [item["code"] for item in language_items]
    all_keys = sorted(
        {key for messages in base_data.values() for key in messages}
        | {key for _, key in override_meta}
    )

    groups_by_id = {
        group["id"]: {
            **group,
            "items": [],
        }
        for group in locale_group_catalog()
    }

    for key in all_keys:
        values: dict[str, dict[str, Any]] = {}
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
        plugin = i18n.plugin_locale_sources.get(key)
        plugin_group = _plugin_group_for_key(i18n, plugin, key) if plugin else None
        path = plugin_group.path if plugin_group else ()
        group_id = f"plugin:{plugin}:{path!r}" if plugin else group_id_for_locale_key(key)
        groups_by_id.setdefault(
            group_id,
            {
                "id": group_id,
                "title": path[-1] if path else "Other",
                "title_key": "" if path else "translations_plugin_other",
                "description": "",
                "description_key": "",
                "audience": "user",
                "plugin": plugin,
                "path": list(path),
                "path_keys": list(plugin_group.path_keys) if plugin_group else [],
                "items": [],
            },
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


def _translations_cache_signature(
    i18n: JsonI18n, overrides: list[dict[str, Any]]
) -> TranslationCacheSignature:
    return i18n.catalog_version, tuple(
        (
            str(entry.get("lang") or ""),
            str(entry.get("key") or ""),
            repr(entry.get("value")),
            repr(entry.get("updated_at")),
            repr(entry.get("updated_by")),
        )
        for entry in overrides
    )


def _cached_admin_translations_payload(
    i18n: JsonI18n,
    overrides: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reuse the validated multi-megabyte editor payload until overrides change."""

    signature = _translations_cache_signature(i18n, overrides)
    cached = _TRANSLATIONS_PAYLOAD_CACHE.get(i18n)
    if cached is not None and cached[0] == signature:
        return cached[1]

    payload = cast(
        dict[str, Any],
        AdminTranslationsOut.model_validate(
            _admin_translations_payload(i18n, overrides)
        ).model_dump(mode="json"),
    )
    _TRANSLATIONS_PAYLOAD_CACHE[i18n] = (signature, payload)
    return payload


def _overrides_file_fingerprint() -> tuple[int, int] | None:
    try:
        stat = LOCALE_OVERRIDES_PATH.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


async def _ensure_locale_overrides_loaded(
    i18n: JsonI18n, async_session_factory: sessionmaker
) -> None:
    """Reconcile the file with DB only when it changes or the sync lease expires."""

    fingerprint = _overrides_file_fingerprint()
    previous = _TRANSLATIONS_FILE_SYNC_CACHE.get(i18n)
    if (
        fingerprint is not None
        and previous is not None
        and fingerprint == previous[:2]
        and time.monotonic() - previous[2] < _FILE_SYNC_INTERVAL_SECONDS
    ):
        return

    await load_locale_overrides(i18n, async_session_factory)
    if fingerprint is None:
        _TRANSLATIONS_FILE_SYNC_CACHE.pop(i18n, None)
        return
    try:
        json.loads(LOCALE_OVERRIDES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _TRANSLATIONS_FILE_SYNC_CACHE.pop(i18n, None)
        return
    if _overrides_file_fingerprint() == fingerprint:
        _TRANSLATIONS_FILE_SYNC_CACHE[i18n] = (*fingerprint, time.monotonic())


async def admin_translations_get_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    i18n: JsonI18n | None = get_i18n(request)
    if i18n is None:
        return _error(503, "i18n_unavailable")
    async_session_factory: sessionmaker = get_session_factory(request)

    await _ensure_locale_overrides_loaded(i18n, async_session_factory)
    async with async_session_factory() as session:
        overrides = await locale_overrides_dal.get_overrides_with_meta(session)

    return _ok(_cached_admin_translations_payload(i18n, overrides))


async def admin_translations_patch_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    i18n: JsonI18n | None = get_i18n(request)
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

    _TRANSLATIONS_FILE_SYNC_CACHE.pop(i18n, None)

    return _ok(
        {
            "applied": result.get("applied", 0),
            "reverted": result.get("reverted", 0),
            "file_written": result.get("file_written", False),
        }
    )
