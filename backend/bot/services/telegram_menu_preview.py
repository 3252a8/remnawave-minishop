"""Render drafts through the same builders and visibility rules used by the bot."""

from __future__ import annotations

from typing import cast

from aiogram.types import InlineKeyboardMarkup

from bot.keyboards.inline.user_keyboards_context import telegram_bot_menu_enabled_for_user
from bot.keyboards.inline.user_keyboards_menus import (
    get_bot_interface_inline_keyboard,
    get_information_links_keyboard,
    get_main_menu_inline_keyboard,
)
from bot.middlewares.i18n import JsonI18n
from bot.services.legal_document_links import legal_document_links
from bot.services.telegram_emoji_schemas import (
    HiddenMenuButton,
    MenuButtonInfo,
    MenuPreviewBody,
    MenuPreviewOut,
    PreviewButton,
)
from bot.services.telegram_emoji_storage import read_item
from bot.utils.custom_emoji import split_decorative_emoji
from config.menu_buttons import configured_menu_buttons, telegram_menu_button_text
from config.settings import Settings
from config.telegram_menu import MENU_APPEARANCE_ENTRIES, ButtonStyle


def menu_buttons(settings: Settings, i18n: JsonI18n, language: str) -> list[MenuButtonInfo]:
    result = []
    for entry in MENU_APPEARANCE_ENTRIES:
        label = i18n.gettext(language, entry.label_key)
        fallback, _ = split_decorative_emoji(label)
        result.append(
            MenuButtonInfo(
                id=entry.id,
                label_key=entry.label_key,
                label=label,
                screens=list(entry.screens),
                emoji_fallback=fallback,
            )
        )
    for button in configured_menu_buttons(settings.MENU_BUTTONS_JSON):
        label = telegram_menu_button_text(
            button, language, default_language=settings.DEFAULT_LANGUAGE
        )
        fallback, _ = split_decorative_emoji(label)
        result.append(
            MenuButtonInfo(
                id=f"custom:{button.id}",
                label_key="",
                label=label,
                screens=["main"],
                emoji_fallback=fallback,
            )
        )
    return result


def preview_menu(
    settings: Settings,
    i18n: JsonI18n,
    body: MenuPreviewBody,
    *,
    bot_id: int | None = None,
) -> tuple[MenuPreviewOut, InlineKeyboardMarkup]:
    candidate = settings.model_copy(deep=True)
    candidate.TELEGRAM_MENU_APPEARANCE_JSON = body.appearance.model_dump_json()
    ids: list[list[str]] = []
    show_trial = body.scenario == "new"
    available = True
    if body.screen == "main":
        markup = get_main_menu_inline_keyboard(
            body.language, i18n, candidate, show_trial, button_ids=ids
        )
        text = i18n.gettext(body.language, "main_menu_greeting", user_name="Admin")
    elif body.screen == "bot":
        available = telegram_bot_menu_enabled_for_user(candidate)
        markup = get_bot_interface_inline_keyboard(
            body.language,
            i18n,
            candidate,
            show_trial,
            referral_program_enabled=candidate.REFERRAL_PROGRAM_ENABLED,
            button_ids=ids,
        )
        text = i18n.gettext(body.language, "bot_interface_menu_title")
        if candidate.SUBSCRIPTION_MINI_APP_URL:
            text += "\n\n" + i18n.gettext(body.language, "bot_interface_menu_webapp_hint")
    else:
        privacy, agreement = legal_document_links(candidate)
        available = bool(privacy or agreement)
        markup = get_information_links_keyboard(
            body.language, i18n, privacy, agreement, settings=candidate, button_ids=ids
        )
        text = i18n.gettext(body.language, "info_links_message")
    registry = menu_buttons(candidate, i18n, body.language)
    originals = {button.id: button for button in registry}
    rows = []
    visible_ids: set[str] = set()
    for row_ids, row in zip(ids, markup.inline_keyboard, strict=True):
        rendered = []
        for identifier, button in zip(row_ids, row, strict=True):
            visible_ids.add(identifier)
            original = originals[identifier]
            cached = (
                read_item(bot_id, button.icon_custom_emoji_id)
                if bot_id and button.icon_custom_emoji_id
                else None
            )
            kind = "webapp" if button.web_app else "url" if button.url else "callback"
            target = (
                button.web_app.url if button.web_app else button.url or button.callback_data or ""
            )
            rendered.append(
                PreviewButton(
                    id=identifier,
                    label=button.text,
                    style=cast(ButtonStyle, button.style or "default"),
                    icon_custom_emoji_id=button.icon_custom_emoji_id,
                    emoji_fallback=cached.fallback if cached else original.emoji_fallback,
                    thumbnail_url=cached.thumbnail_url if cached else None,
                    kind=kind,
                    target=target,
                )
            )
        rows.append(rendered)
    hidden = []
    for button in registry:
        if body.screen not in button.screens or (available and button.id in visible_ids):
            continue
        reason = "condition"
        if not available:
            reason = "screen_disabled"
        elif button.id == "trial":
            reason = (
                "trial_unavailable"
                if body.scenario == "trial_unavailable"
                else "subscription"
                if body.scenario == "active"
                else "trial_disabled"
            )
        elif button.id == "bot_interface":
            reason = "screen_disabled"
        elif button.id == "personal_account":
            reason = "mini_app"
        elif button.id == "referral":
            reason = "referral"
        elif button.id == "server_status":
            reason = "status"
        elif button.id == "support":
            reason = "support"
        elif button.id in {"information", "privacy", "user_agreement"}:
            reason = "legal"
        elif button.id.startswith("custom:"):
            reason = "custom_visibility"
        hidden.append(
            HiddenMenuButton(
                id=button.id,
                label=button.label,
                reason=i18n.gettext(body.language, f"admin_tg_menu_hidden_{reason}"),
            )
        )
    return MenuPreviewOut(
        text=text, rows=rows if available else [], hidden=hidden, available=available
    ), markup
