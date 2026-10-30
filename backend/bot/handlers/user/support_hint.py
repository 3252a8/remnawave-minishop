"""A final private-chat fallback after command, state and plugin handlers."""

from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.utils.text_decorations import html_decoration as hd

from bot.keyboards.inline.menu_appearance import MenuKeyboardBuilder, menu_button
from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from config.support_links import normalize_support_link


async def support_hint(message: types.Message, settings: Settings, i18n_data: dict) -> None:
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if i18n is None:
        return
    lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    text = [i18n.gettext(lang, "bot_text_support_hint")]
    keyboard = MenuKeyboardBuilder(settings)
    support_link = normalize_support_link(settings.support_settings.link)
    if support_link:
        text.append(
            i18n.gettext(lang, "bot_text_support_link_hint", support_url=hd.quote(support_link))
        )
        keyboard.row(
            menu_button("support", text=i18n.gettext(lang, "menu_support_button"), url=support_link)
        )
    if settings.SUBSCRIPTION_MINI_APP_URL:
        text.append(i18n.gettext(lang, "bot_text_mini_app_hint"))
        keyboard.row(
            menu_button(
                "personal_account",
                text=i18n.gettext(lang, "menu_personal_account_button"),
                web_app=types.WebAppInfo(url=settings.SUBSCRIPTION_MINI_APP_URL),
            )
        )
    if not support_link and not settings.SUBSCRIPTION_MINI_APP_URL:
        text.append(i18n.gettext(lang, "bot_text_start_hint"))
    markup = keyboard.as_markup()
    await message.answer(
        "\n\n".join(text),
        parse_mode="HTML",
        reply_markup=markup if markup.inline_keyboard else None,
        link_preview_options=types.LinkPreviewOptions(is_disabled=True),
    )


def build_support_hint_router() -> Router:
    router = Router(name="user_support_hint")
    router.message.register(
        support_hint,
        StateFilter(None),
        F.chat.type == "private",
        F.from_user.is_bot == False,
        F.text,
        ~F.text.lstrip().startswith("/"),
    )
    return router
