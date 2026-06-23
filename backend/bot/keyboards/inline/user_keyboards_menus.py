from typing import Optional

from aiogram.types import InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton

from bot.middlewares.i18n import JsonI18n, locale_language_options
from bot.utils.mini_app_url import subscription_mini_app_trial_url
from config.settings import Settings

from .user_keyboards_context import telegram_bot_menu_enabled_for_user


def _trial_activation_button(
    lang: str, i18n_instance: JsonI18n, settings: Settings
) -> InlineKeyboardButton:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    if settings.SUBSCRIPTION_MINI_APP_URL:
        trial_url = subscription_mini_app_trial_url(settings) or settings.SUBSCRIPTION_MINI_APP_URL
        return InlineKeyboardButton(
            text=_(key="menu_activate_trial_button"),
            web_app=WebAppInfo(url=trial_url),
        )
    return InlineKeyboardButton(
        text=_(key="menu_activate_trial_button"),
        callback_data="main_action:request_trial",
    )


def get_main_menu_inline_keyboard(
    lang: str,
    i18n_instance: JsonI18n,
    settings: Settings,
    show_trial_button: bool = False,
    *,
    user_id: Optional[int] = None,
    is_admin: bool = False,
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()

    if show_trial_button and settings.TRIAL_ENABLED:
        builder.row(_trial_activation_button(lang, i18n_instance, settings))

    if settings.SUBSCRIPTION_MINI_APP_URL:
        builder.row(
            InlineKeyboardButton(
                text=_(key="menu_personal_account_button"),
                web_app=WebAppInfo(url=settings.SUBSCRIPTION_MINI_APP_URL),
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text=_(key="menu_personal_account_button"),
                callback_data="main_action:my_subscription",
            )
        )

    if telegram_bot_menu_enabled_for_user(settings, user_id=user_id, is_admin=is_admin):
        builder.row(
            InlineKeyboardButton(
                text=_(key="menu_bot_interface_button"), callback_data="main_action:bot_interface"
            )
        )

    if settings.SERVER_STATUS_URL:
        builder.row(
            InlineKeyboardButton(
                text=_(key="menu_server_status_button"), url=settings.SERVER_STATUS_URL
            )
        )

    if settings.SUPPORT_LINK:
        builder.row(
            InlineKeyboardButton(text=_(key="menu_support_button"), url=settings.SUPPORT_LINK)
        )

    if settings.PRIVACY_POLICY_URL or settings.USER_AGREEMENT_URL:
        builder.row(
            InlineKeyboardButton(text=_(key="menu_info_button"), callback_data="main_action:info")
        )

    return builder.as_markup()


def get_bot_interface_inline_keyboard(
    lang: str, i18n_instance: JsonI18n, settings: Settings, show_trial_button: bool = False
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()

    if show_trial_button and settings.TRIAL_ENABLED:
        builder.row(_trial_activation_button(lang, i18n_instance, settings))

    if settings.SUBSCRIPTION_MINI_APP_URL:
        builder.row(
            InlineKeyboardButton(
                text=_(key="menu_personal_account_button"),
                web_app=WebAppInfo(url=settings.SUBSCRIPTION_MINI_APP_URL),
            )
        )

    builder.row(
        InlineKeyboardButton(
            text=_(key="menu_subscribe_inline"), callback_data="main_action:bot_subscribe"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_(key="menu_my_subscription_inline"),
            callback_data="main_action:bot_my_subscription",
        )
    )

    referral_button = InlineKeyboardButton(
        text=_(key="menu_referral_inline"), callback_data="main_action:bot_referral"
    )
    promo_button = InlineKeyboardButton(
        text=_(key="menu_apply_promo_button"), callback_data="main_action:bot_apply_promo"
    )
    builder.row(referral_button)
    builder.row(promo_button)

    language_button = InlineKeyboardButton(
        text=_(key="menu_language_settings_inline"), callback_data="main_action:bot_language"
    )
    builder.row(language_button)

    if settings.SERVER_STATUS_URL:
        builder.row(
            InlineKeyboardButton(
                text=_(key="menu_server_status_button"), url=settings.SERVER_STATUS_URL
            )
        )

    if settings.SUPPORT_LINK:
        builder.row(
            InlineKeyboardButton(text=_(key="menu_support_button"), url=settings.SUPPORT_LINK)
        )

    if settings.PRIVACY_POLICY_URL or settings.USER_AGREEMENT_URL:
        builder.row(
            InlineKeyboardButton(
                text=_(key="menu_info_button"), callback_data="main_action:bot_info"
            )
        )

    builder.row(
        InlineKeyboardButton(
            text=_(key="back_to_main_menu_button"), callback_data="main_action:back_to_main"
        )
    )

    return builder.as_markup()


def get_information_links_keyboard(
    lang: str,
    i18n_instance: JsonI18n,
    privacy_policy_url: Optional[str],
    user_agreement_url: Optional[str],
    back_callback: str = "main_action:back_to_main",
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    if privacy_policy_url:
        builder.row(
            InlineKeyboardButton(text=_(key="privacy_policy_button"), url=privacy_policy_url)
        )
    if user_agreement_url:
        builder.row(
            InlineKeyboardButton(text=_(key="user_agreement_button"), url=user_agreement_url)
        )
    builder.row(
        InlineKeyboardButton(text=_(key="back_to_main_menu_button"), callback_data=back_callback)
    )
    return builder.as_markup()


def get_language_selection_keyboard(
    i18n_instance: JsonI18n, current_lang: str, back_callback: str = "main_action:back_to_main"
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(current_lang, key, **kwargs)
    callback_suffix = ":bot" if back_callback == "main_action:bot_interface" else ""
    builder = InlineKeyboardBuilder()
    if hasattr(i18n_instance, "language_options"):
        languages = i18n_instance.language_options()
    else:
        locales_data = getattr(i18n_instance, "locales_data", {}) or {"ru": {}, "en": {}}
        languages = locale_language_options(locales_data.keys(), base_languages=locales_data.keys())
    for language in languages:
        lang_code = language["code"]
        checked = " ✅" if current_lang == lang_code else ""
        builder.button(
            text=f"{language['flag']} {language['label']}{checked}",
            callback_data=f"set_lang_{lang_code}{callback_suffix}",
        )
    builder.button(text=_(key="back_to_main_menu_button"), callback_data=back_callback)
    builder.adjust(1)
    return builder.as_markup()


def get_trial_confirmation_keyboard(lang: str, i18n_instance: JsonI18n) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.button(
        text=_(key="trial_confirm_activate_button"), callback_data="trial_action:confirm_activate"
    )
    builder.button(text=_(key="cancel_button"), callback_data="main_action:back_to_main")
    builder.adjust(1)
    return builder.as_markup()
