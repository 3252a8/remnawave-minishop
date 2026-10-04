"""Administrator-owned custom emoji registry and token-free preview media."""

from __future__ import annotations

import asyncio

from aiohttp import web

from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    BINARY_RESPONSE_SCHEMA,
    RouteContract,
    ok_envelope_for,
    register_contract,
)
from bot.app.web.telegram_emoji_media import emoji_media_response
from bot.services.telegram_emoji_catalog import (
    TelegramEmojiError,
    catalog,
    library_sets,
    load_set,
    media,
    resolve_ids,
    warm_library,
)
from bot.services.telegram_emoji_schemas import (
    EmojiCatalogOut,
    EmojiLibraryBody,
    EmojiLibraryOut,
    EmojiRefreshBody,
)
from config.telegram_menu import (
    LIBRARY_KEY,
    TelegramEmojiLibrary,
    emoji_source,
    parse_emoji_library,
    telegram_setting_revision,
)

from .common import _ok
from .telegram_common import (
    current_settings,
    persist_setting,
    required_bot,
    telegram_route,
)


async def library_out(request: web.Request) -> EmojiLibraryOut:
    settings = await current_settings(request)
    library = parse_emoji_library(settings.TELEGRAM_CUSTOM_EMOJI_LIBRARY_JSON)
    await warm_library(required_bot(request), library)
    return EmojiLibraryOut(
        library=library,
        revision=telegram_setting_revision(LIBRARY_KEY, library),
        sets=await library_sets(required_bot(request), library),
    )


@telegram_route
async def admin_telegram_emoji_library_route(request: web.Request) -> web.Response:
    result = await library_out(request)
    return _ok(result.model_dump(mode="json"))


@telegram_route
async def admin_telegram_emoji_add_route(request: web.Request) -> web.Response:
    body = await parse_body_or_400(request, EmojiLibraryBody)
    settings = await current_settings(request)
    library = parse_emoji_library(settings.TELEGRAM_CUSTOM_EMOJI_LIBRARY_JSON)
    if body.expected_revision != telegram_setting_revision(LIBRARY_KEY, library):
        raise TelegramEmojiError("telegram_menu_conflict", 409)
    kind, source = emoji_source(body.source)
    bot = required_bot(request)
    if kind == "set":
        cached = await load_set(bot, source, refresh=True)
        if not any(name.casefold() == cached.name.casefold() for name in library.sets):
            library.sets.append(cached.name)
    else:
        await resolve_ids(bot, [source], refresh=True)
        if source not in library.manual_ids:
            library.manual_ids.append(source)
    library = TelegramEmojiLibrary.model_validate(library.model_dump())
    await persist_setting(request, LIBRARY_KEY, library, body.expected_revision)
    await warm_library(bot, library, retry=True)
    return _ok((await library_out(request)).model_dump(mode="json"))


@telegram_route
async def admin_telegram_emoji_remove_route(request: web.Request) -> web.Response:
    body = await parse_body_or_400(request, EmojiLibraryBody)
    settings = await current_settings(request)
    library = parse_emoji_library(settings.TELEGRAM_CUSTOM_EMOJI_LIBRARY_JSON)
    kind, source = emoji_source(body.source)
    if kind == "set":
        library.sets = [name for name in library.sets if name.casefold() != source.casefold()]
    else:
        library.manual_ids = [
            identifier for identifier in library.manual_ids if identifier != source
        ]
    await persist_setting(request, LIBRARY_KEY, library, body.expected_revision)
    # Registry removal does not rewrite selected button icons, texts, or reusable ID metadata.
    return _ok((await library_out(request)).model_dump(mode="json"))


@telegram_route
async def admin_telegram_emoji_refresh_route(request: web.Request) -> web.Response:
    body = await parse_body_or_400(request, EmojiRefreshBody)
    result = await library_out(request)
    kind, source = emoji_source(body.source)
    bot = required_bot(request)
    if kind == "set":
        if not any(name.casefold() == source.casefold() for name in result.library.sets):
            raise TelegramEmojiError("telegram_emoji_unknown_set")
        await load_set(bot, source, refresh=True)
    else:
        if source not in result.library.manual_ids:
            raise TelegramEmojiError("telegram_emoji_not_found")
        await resolve_ids(bot, [source], refresh=True)
    await warm_library(bot, result.library, retry=True)
    return _ok((await library_out(request)).model_dump(mode="json"))


@telegram_route
async def admin_telegram_emoji_catalog_route(request: web.Request) -> web.Response:
    settings = await current_settings(request)
    result = await catalog(
        required_bot(request),
        parse_emoji_library(settings.TELEGRAM_CUSTOM_EMOJI_LIBRARY_JSON),
        set_name=request.query.get("set", ""),
        query=request.query.get("q", ""),
        offset=int(request.query.get("offset", "0")),
        limit=int(request.query.get("limit", "60")),
        identifiers=[value for value in request.query.get("ids", "").split(",") if value],
    )
    return _ok(result.model_dump(mode="json"))


@telegram_route
async def admin_telegram_emoji_media_route(request: web.Request) -> web.Response:
    bot = required_bot(request)
    async with asyncio.timeout(20):
        content, mime = await media(bot, request.match_info["emoji_id"])
    return emoji_media_response(request, content, mime, bot.id, request.match_info["emoji_id"])


register_contract(
    "admin_telegram_emoji_library_route",
    RouteContract(
        response_schema=ok_envelope_for(EmojiLibraryOut),
        models=(EmojiLibraryOut,),
    ),
)
register_contract(
    "admin_telegram_emoji_add_route",
    RouteContract(
        request_model=EmojiLibraryBody,
        response_schema=ok_envelope_for(EmojiLibraryOut),
        models=(EmojiLibraryOut, EmojiLibraryBody),
    ),
)
register_contract(
    "admin_telegram_emoji_remove_route",
    RouteContract(
        request_model=EmojiLibraryBody,
        response_schema=ok_envelope_for(EmojiLibraryOut),
        models=(EmojiLibraryOut, EmojiLibraryBody),
    ),
)
register_contract(
    "admin_telegram_emoji_refresh_route",
    RouteContract(
        request_model=EmojiRefreshBody,
        response_schema=ok_envelope_for(EmojiLibraryOut),
        models=(EmojiLibraryOut, EmojiRefreshBody),
    ),
)
register_contract(
    "admin_telegram_emoji_catalog_route",
    RouteContract(
        response_schema=ok_envelope_for(EmojiCatalogOut),
        models=(EmojiCatalogOut,),
    ),
)
register_contract(
    "admin_telegram_emoji_media_route",
    RouteContract(
        response_schema=BINARY_RESPONSE_SCHEMA,
        response_content_type="application/octet-stream",
    ),
)
