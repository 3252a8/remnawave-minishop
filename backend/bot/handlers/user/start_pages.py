"""Public bot navigation targets. Each target opens a screen or a prompt."""

from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards_menus import (
    get_information_links_keyboard,
    get_trial_confirmation_keyboard,
)
from bot.middlewares.i18n import JsonI18n
from bot.services.legal_document_links import legal_document_links
from bot.services.referral_service import ReferralService
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.utils.callback_answer import callback_bot, callback_message, message_bot
from bot.utils.mini_app_url import append_query_params
from config.settings import Settings
from config.support_links import normalize_support_link

from .start_menus import send_bot_interface_menu

APP_PAGES = frozenset(
    {
        "invite",
        "partner",
        "partner-links",
        "partner-balance",
        "partner-clients",
        "partner-commissions",
        "partner-withdrawals",
        "gifts",
        "settings",
        "notifications",
        "security",
        "payment-history",
        "status",
        "support",
        "support-new",
        "extensions",
    }
)
BOT_PAGES = APP_PAGES | {
    "ref",
    "plans",
    "subscription",
    "install",
    "devices",
    "language",
    "codes",
    "bot",
    "trial",
    "info",
}


async def open_start_page(
    page: str,
    event: types.Message | types.CallbackQuery,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    subscription_service: SubscriptionService,
    referral_service: ReferralService,
    session: AsyncSession,
) -> bool:
    if page not in BOT_PAGES:
        return False

    from . import promo_user, referral, subscription
    from .start_callbacks import language_command_handler

    if isinstance(event, types.CallbackQuery):
        message = callback_message(event)
        bot = callback_bot(event)
    else:
        message = event
        bot = message_bot(event)
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if i18n is None:
        return False
    _ = lambda key: i18n.gettext(current_lang, key)

    if page == "ref":
        await referral.referral_command_handler(
            event, settings, i18n_data, referral_service, bot, session
        )
    elif page == "plans":
        await subscription.display_subscription_options(event, i18n_data, settings, session)
    elif page in {"subscription", "install", "devices"}:
        handler = (
            subscription.my_devices_command_handler
            if page == "devices"
            else subscription.my_subscription_command_handler
        )
        await handler(
            event,
            i18n_data,
            settings,
            subscription_service.panel_service,
            subscription_service,
            session,
            bot,
        )
    elif page == "language":
        await language_command_handler(event, i18n_data, settings)
    elif page == "codes":
        await promo_user.prompt_promo_code_input(event, state, i18n_data, settings, session)
    elif page == "bot" and not settings.TELEGRAM_BOT_MENU_DISABLED:
        await send_bot_interface_menu(event, settings, i18n_data, subscription_service, session)
    elif page == "info":
        privacy_url, terms_url = legal_document_links(settings)
        if not (privacy_url or terms_url):
            return False
        await message.answer(
            _("info_links_message"),
            reply_markup=get_information_links_keyboard(
                current_lang, i18n, privacy_url, terms_url, settings=settings
            ),
        )
    elif page == "trial":
        if not settings.TRIAL_ENABLED:
            return False
        if not settings.SUBSCRIPTION_MINI_APP_URL:
            await message.answer(
                _("menu_activate_trial_button"),
                reply_markup=get_trial_confirmation_keyboard(current_lang, i18n),
            )
            return True
        await _send_app_page(message, settings.SUBSCRIPTION_MINI_APP_URL, page, _("open_mini_app"))
    elif page == "support" and (
        support_url := normalize_support_link(settings.support_settings.link)
    ):
        label = _("menu_support_button")
        await message.answer(
            label,
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text=label, url=support_url)]]
            ),
        )
    elif page in APP_PAGES and settings.SUBSCRIPTION_MINI_APP_URL:
        await _send_app_page(message, settings.SUBSCRIPTION_MINI_APP_URL, page, _("open_mini_app"))
    else:
        return False
    return True


async def _send_app_page(message: types.Message, base: str, page: str, label: str) -> None:
    url = append_query_params(base, {"startapp": f"page_{page}"})
    await message.answer(
        label,
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text=label, web_app=types.WebAppInfo(url=url))]
            ]
        ),
    )
