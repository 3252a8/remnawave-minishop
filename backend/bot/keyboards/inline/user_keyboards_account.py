from aiogram.types import InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton

from bot.middlewares.i18n import JsonI18n
from bot.utils.channel_subscription import normalize_required_channel_link
from bot.utils.install_links import bot_install_guide_url
from bot.utils.mini_app_url import subscription_mini_app_renew_url
from config.settings import Settings


def get_referral_link_keyboard(
    lang: str, i18n_instance: JsonI18n, back_callback: str = "main_action:back_to_main"
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.button(
        text=_(key="referral_share_message_button"), callback_data="referral_action:share_message"
    )
    builder.button(text=_(key="back_to_main_menu_button"), callback_data=back_callback)
    builder.adjust(1)
    return builder.as_markup()


def get_back_to_main_menu_markup(
    lang: str, i18n_instance: JsonI18n, callback_data: str | None = None
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    if callback_data:
        builder.button(text=_(key="back_to_main_menu_button"), callback_data=callback_data)
    else:
        builder.button(
            text=_(key="back_to_main_menu_button"), callback_data="main_action:back_to_main"
        )
    return builder.as_markup()


def get_subscribe_only_markup(
    lang: str,
    i18n_instance: JsonI18n,
    settings: Settings | None = None,
    *,
    tariff_key: str | None = None,
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    renew_url = (
        subscription_mini_app_renew_url(settings, tariff_key)
        if settings and bool(settings.TELEGRAM_BOT_MENU_DISABLED)
        else None
    )
    if renew_url:
        builder.button(
            text=_(key="menu_subscribe_inline"),
            web_app=WebAppInfo(url=renew_url),
        )
    else:
        builder.button(text=_(key="menu_subscribe_inline"), callback_data="main_action:subscribe")
    return builder.as_markup()


def get_user_banned_keyboard(
    support_link: str | None, lang: str, i18n_instance: JsonI18n
) -> InlineKeyboardMarkup | None:
    if not support_link:
        return None
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.button(text=_(key="menu_support_button"), url=support_link)
    return builder.as_markup()


def get_channel_subscription_keyboard(
    lang: str,
    i18n_instance: JsonI18n | None,
    channel_link: str | None,
    include_check_button: bool = True,
) -> InlineKeyboardMarkup | None:
    """
    Return keyboard with buttons to open the required channel and trigger a subscription re-check.
    """
    if i18n_instance is None:
        return None

    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()

    has_buttons = False

    channel_url = normalize_required_channel_link(channel_link)
    if channel_url:
        builder.button(
            text=_(key="channel_subscription_join_button"),
            url=channel_url,
        )
        has_buttons = True

    if include_check_button:
        builder.button(
            text=_(key="channel_subscription_verify_button"),
            callback_data="channel_subscription:verify",
        )
        has_buttons = True

    if not has_buttons:
        return None

    builder.adjust(1)
    return builder.as_markup()


def get_connect_and_main_keyboard(
    lang: str,
    i18n_instance: JsonI18n,
    settings: Settings,
    config_link: str | None,
    connect_button_url: str | None = None,
    preserve_message: bool = False,
    install_share_url: str | None = None,
) -> InlineKeyboardMarkup:
    """Keyboard with a connect button and a back to main menu button."""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    install_url = bot_install_guide_url(settings)
    button_target = connect_button_url or config_link

    if install_url:
        builder.row(
            InlineKeyboardButton(
                text=_("connect_button"),
                web_app=WebAppInfo(url=install_url),
            )
        )
        if install_share_url:
            builder.row(
                InlineKeyboardButton(
                    text=_("install_guide_share_button"),
                    url=install_share_url,
                )
            )
    elif button_target:
        builder.row(InlineKeyboardButton(text=_("connect_button"), url=button_target))
    elif settings.SUBSCRIPTION_MINI_APP_URL:
        builder.row(
            InlineKeyboardButton(
                text=_("connect_button"),
                web_app=WebAppInfo(url=settings.SUBSCRIPTION_MINI_APP_URL),
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text=_("connect_button"),
                callback_data="main_action:my_subscription",
            )
        )

    back_callback = (
        "main_action:back_to_main_keep" if preserve_message else "main_action:back_to_main"
    )
    builder.row(
        InlineKeyboardButton(
            text=_("back_to_main_menu_button"),
            callback_data=back_callback,
        )
    )

    return builder.as_markup()
