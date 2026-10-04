"""Draft previews, optimistic saves, and an explicitly requested test to the admin's own chat."""

from __future__ import annotations

import asyncio
import html

from aiogram.exceptions import TelegramAPIError
from aiohttp import web

from bot.app.factories.telegram_custom_emoji import CUSTOM_EMOJI_PROBE
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from bot.services.telegram_emoji_catalog import TelegramEmojiError, resolve_ids
from bot.services.telegram_emoji_schemas import (
    EmojiCapabilities,
    MenuLanguage,
    MenuPreviewBody,
    MenuPreviewOut,
    MenuSaveBody,
    MenuTestOut,
    TelegramMenuOut,
)
from bot.services.telegram_emoji_storage import capabilities, observe_capability
from bot.services.telegram_menu_preview import menu_buttons, preview_menu
from config.settings import Settings
from config.telegram_menu import APPEARANCE_KEY, parse_menu_appearance, telegram_setting_revision

from .common import _ok
from .telegram_common import (
    current_settings,
    menu_i18n,
    optional_bot,
    persist_setting,
    required_bot,
    telegram_route,
)


async def menu_out(request: web.Request) -> TelegramMenuOut:
    settings = await current_settings(request)
    i18n = menu_i18n(request)
    appearance = parse_menu_appearance(settings.TELEGRAM_MENU_APPEARANCE_JSON)
    bot = optional_bot(request)
    return TelegramMenuOut(
        appearance=appearance,
        revision=telegram_setting_revision(APPEARANCE_KEY, appearance),
        buttons=menu_buttons(settings, i18n, settings.DEFAULT_LANGUAGE),
        languages=[
            MenuLanguage(code=item["code"], name=item["label"]) for item in i18n.language_options()
        ],
        capabilities=await asyncio.to_thread(capabilities, bot.id) if bot else EmojiCapabilities(),
    )


def validate_draft(
    request: web.Request, settings: Settings, body: MenuPreviewBody | MenuSaveBody
) -> None:
    registry = {
        button.id
        for button in menu_buttons(settings, menu_i18n(request), settings.DEFAULT_LANGUAGE)
    }
    saved = parse_menu_appearance(settings.TELEGRAM_MENU_APPEARANCE_JSON)
    if set(body.appearance.buttons) - registry - set(saved.buttons):
        raise TelegramEmojiError("telegram_menu_unknown_button")
    if isinstance(body, MenuPreviewBody) and body.language not in menu_i18n(request).locales_data:
        raise TelegramEmojiError("telegram_menu_unknown_language")


@telegram_route
async def admin_telegram_menu_route(request: web.Request) -> web.Response:
    return _ok((await menu_out(request)).model_dump(mode="json"))


@telegram_route
async def admin_telegram_menu_save_route(request: web.Request) -> web.Response:
    body = await parse_body_or_400(request, MenuSaveBody)
    settings = await current_settings(request)
    validate_draft(request, settings, body)
    if (
        telegram_setting_revision(APPEARANCE_KEY, settings.TELEGRAM_MENU_APPEARANCE_JSON)
        != body.expected_revision
    ):
        raise TelegramEmojiError("telegram_menu_conflict", 409)
    identifiers = [
        entry.icon_custom_emoji_id
        for entry in body.appearance.buttons.values()
        if entry.icon_custom_emoji_id
    ]
    if identifiers:
        await resolve_ids(required_bot(request), identifiers)
    await persist_setting(request, APPEARANCE_KEY, body.appearance, body.expected_revision)
    return _ok((await menu_out(request)).model_dump(mode="json"))


@telegram_route
async def admin_telegram_menu_preview_route(request: web.Request) -> web.Response:
    body = await parse_body_or_400(request, MenuPreviewBody)
    settings = await current_settings(request)
    validate_draft(request, settings, body)
    bot = optional_bot(request)
    result, _ = await asyncio.to_thread(
        preview_menu, settings, menu_i18n(request), body, bot_id=bot.id if bot else None
    )
    return _ok(result.model_dump(mode="json"))


@telegram_route
async def admin_telegram_menu_test_route(request: web.Request) -> web.Response:
    body = await parse_body_or_400(request, MenuPreviewBody)
    settings = await current_settings(request)
    validate_draft(request, settings, body)
    telegram_id = request.get("admin_telegram_id")
    if not isinstance(telegram_id, int) or telegram_id <= 0:
        raise TelegramEmojiError("telegram_menu_test_telegram_required")
    bot = required_bot(request)
    i18n = menu_i18n(request)
    preview, markup = await asyncio.to_thread(preview_menu, settings, i18n, body, bot_id=bot.id)
    if not preview.available:
        raise TelegramEmojiError("telegram_menu_screen_unavailable")
    identifiers = [
        button.icon_custom_emoji_id
        for row in markup.inline_keyboard
        for button in row
        if button.icon_custom_emoji_id
    ]
    emoji_items = await resolve_ids(bot, identifiers) if identifiers else []
    probe = CUSTOM_EMOJI_PROBE.set(True)
    try:
        message = await bot.send_message(
            telegram_id,
            i18n.gettext(body.language, "admin_tg_menu_test_message") + "\n\n" + preview.text,
            reply_markup=markup,
        )
        if identifiers:
            returned_icons = bool(
                message.reply_markup
                and any(
                    button.icon_custom_emoji_id
                    for row in message.reply_markup.inline_keyboard
                    for button in row
                )
            )
            await asyncio.to_thread(observe_capability, bot.id, "icon", returned_icons)
        if emoji_items:
            item = emoji_items[0]
            text_message = await bot.send_message(
                telegram_id,
                i18n.gettext(body.language, "admin_tg_menu_test_text")
                + " "
                + f'<tg-emoji emoji-id="{item.id}">{html.escape(item.fallback)}</tg-emoji>',
                parse_mode="HTML",
            )
            returned_entity = any(
                entity.type == "custom_emoji" for entity in text_message.entities or []
            )
            await asyncio.to_thread(observe_capability, bot.id, "text", returned_entity)
    except TelegramAPIError as exc:
        raise TelegramEmojiError("telegram_menu_test_failed", 503) from exc
    finally:
        CUSTOM_EMOJI_PROBE.reset(probe)
    return _ok(
        MenuTestOut(
            sent=True,
            capabilities=await asyncio.to_thread(capabilities, bot.id),
            message_id=message.message_id,
        ).model_dump(mode="json")
    )


register_contract(
    "admin_telegram_menu_route",
    RouteContract(
        response_schema=ok_envelope_for(TelegramMenuOut),
        models=(TelegramMenuOut,),
    ),
)
register_contract(
    "admin_telegram_menu_save_route",
    RouteContract(
        request_model=MenuSaveBody,
        response_schema=ok_envelope_for(TelegramMenuOut),
        models=(TelegramMenuOut, MenuSaveBody),
    ),
)
register_contract(
    "admin_telegram_menu_preview_route",
    RouteContract(
        request_model=MenuPreviewBody,
        response_schema=ok_envelope_for(MenuPreviewOut),
        models=(MenuPreviewOut, MenuPreviewBody),
    ),
)
register_contract(
    "admin_telegram_menu_test_route",
    RouteContract(
        request_model=MenuPreviewBody,
        response_schema=ok_envelope_for(MenuTestOut),
        models=(MenuTestOut, MenuPreviewBody),
    ),
)
