from typing import Any, Dict, List, Optional, Tuple

from aiogram.types import InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton

from config.settings import Settings

BOT_MENU_CONTEXT = "bot"


def callback_context_from_back_callback(back_callback: Optional[str]) -> Optional[str]:
    if back_callback == "main_action:bot_interface":
        return BOT_MENU_CONTEXT
    return None


def sale_mode_with_callback_context(sale_mode: str, context: Optional[str]) -> str:
    sale_mode = sale_mode or "subscription"
    if not context or "|" in sale_mode:
        return sale_mode
    return f"{sale_mode}|{context}"


def callback_context_from_sale_mode(sale_mode: Optional[str]) -> Optional[str]:
    if not sale_mode or "|" not in sale_mode:
        return None
    context = str(sale_mode).split("|", 1)[1].strip()
    return context or None


def callback_suffix_for_context(context: Optional[str]) -> str:
    return f":{context}" if context else ""


def subscription_options_callback(context: Optional[str]) -> str:
    return "main_action:bot_subscribe" if context == BOT_MENU_CONTEXT else "main_action:subscribe"


def payment_methods_back_callback(
    value: str, sale_mode: str = "subscription", price: Optional[float] = None
) -> str:
    sale_mode = sale_mode or "subscription"
    context = callback_context_from_sale_mode(sale_mode)
    context_suffix = callback_suffix_for_context(context)
    sale_mode_main = sale_mode.split("|", 1)[0]
    sale_base = sale_mode_main.split("@", 1)[0]
    tariff_key = sale_mode_main.split("@", 1)[1] if "@" in sale_mode_main else None

    if sale_base == "subscription" and tariff_key:
        return f"tariff:period:{tariff_key}:{value}{context_suffix}"
    if sale_base == "traffic_package" and tariff_key:
        return f"tariff:package:{tariff_key}:{value}{context_suffix}"
    if sale_base == "topup" and tariff_key:
        return f"tariff:package:{tariff_key}:{value}"
    if sale_base == "premium_topup" and tariff_key:
        return f"tariff:premium_package:{tariff_key}:{value}"
    if sale_base in {"hwid_device", "hwid_devices"} and tariff_key:
        return f"hwid_devices:package:{tariff_key}:{value}"
    if sale_base == "tariff_upgrade" and tariff_key:
        amount = str(price) if price is not None else value
        return f"tariff_change:pay:{tariff_key}:{amount}"
    if sale_base in {"subscription", "traffic"}:
        return f"subscribe_period:{value}{context_suffix}"
    return subscription_options_callback(context)


def payment_options_back_callback(sale_mode: str = "subscription") -> str:
    sale_mode = sale_mode or "subscription"
    context = callback_context_from_sale_mode(sale_mode)
    context_suffix = callback_suffix_for_context(context)
    sale_mode_main = sale_mode.split("|", 1)[0]
    sale_base = sale_mode_main.split("@", 1)[0]
    tariff_key = sale_mode_main.split("@", 1)[1] if "@" in sale_mode_main else None

    if sale_base in {"subscription", "traffic_package"} and tariff_key:
        return f"tariff:select:{tariff_key}{context_suffix}"
    if sale_base in {"topup", "premium_topup"}:
        return "tariff_topup:list"
    if sale_base in {"hwid_device", "hwid_devices"}:
        return "hwid_devices:list"
    return subscription_options_callback(context)


def get_main_menu_inline_keyboard(
    lang: str, i18n_instance, settings: Settings, show_trial_button: bool = False
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()

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

    builder.row(
        InlineKeyboardButton(
            text=_(key="menu_bot_interface_button"), callback_data="main_action:bot_interface"
        )
    )

    if settings.SUPPORT_LINK:
        builder.row(
            InlineKeyboardButton(text=_(key="menu_support_button"), url=settings.SUPPORT_LINK)
        )

    user_agreement_url = settings.USER_AGREEMENT_URL or settings.TERMS_OF_SERVICE_URL
    if settings.PRIVACY_POLICY_URL or user_agreement_url:
        builder.row(
            InlineKeyboardButton(text=_(key="menu_info_button"), callback_data="main_action:info")
        )

    return builder.as_markup()


def get_bot_interface_inline_keyboard(
    lang: str, i18n_instance, settings: Settings, show_trial_button: bool = False
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()

    if show_trial_button and settings.TRIAL_ENABLED:
        builder.row(
            InlineKeyboardButton(
                text=_(key="menu_activate_trial_button"), callback_data="main_action:request_trial"
            )
        )

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
    status_button_list = []
    if settings.SERVER_STATUS_URL:
        status_button_list.append(
            InlineKeyboardButton(
                text=_(key="menu_server_status_button"), url=settings.SERVER_STATUS_URL
            )
        )

    if status_button_list:
        builder.row(language_button, *status_button_list)
    else:
        builder.row(language_button)

    if settings.SUPPORT_LINK:
        builder.row(
            InlineKeyboardButton(text=_(key="menu_support_button"), url=settings.SUPPORT_LINK)
        )

    user_agreement_url = settings.USER_AGREEMENT_URL or settings.TERMS_OF_SERVICE_URL
    if settings.PRIVACY_POLICY_URL or user_agreement_url:
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
    i18n_instance,
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
    i18n_instance, current_lang: str, back_callback: str = "main_action:back_to_main"
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(current_lang, key, **kwargs)
    callback_suffix = ":bot" if back_callback == "main_action:bot_interface" else ""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"🇬🇧 English {'✅' if current_lang == 'en' else ''}",
        callback_data=f"set_lang_en{callback_suffix}",
    )
    builder.button(
        text=f"🇷🇺 Русский {'✅' if current_lang == 'ru' else ''}",
        callback_data=f"set_lang_ru{callback_suffix}",
    )
    builder.button(text=_(key="back_to_main_menu_button"), callback_data=back_callback)
    builder.adjust(1)
    return builder.as_markup()


def get_trial_confirmation_keyboard(lang: str, i18n_instance) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.button(
        text=_(key="trial_confirm_activate_button"), callback_data="trial_action:confirm_activate"
    )
    builder.button(text=_(key="cancel_button"), callback_data="main_action:back_to_main")
    builder.adjust(1)
    return builder.as_markup()


def get_subscription_options_keyboard(
    subscription_options: Dict[float, Optional[float]],
    currency_symbol_val: str,
    lang: str,
    i18n_instance,
    traffic_mode: bool = False,
    back_callback: str = "main_action:back_to_main",
    callback_context: Optional[str] = None,
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    callback_context = callback_context or callback_context_from_back_callback(back_callback)

    def _format_gb(val: float) -> str:
        return str(int(val)) if float(val).is_integer() else f"{val:g}"

    if subscription_options:
        for months, price in subscription_options.items():
            if price is not None:
                if traffic_mode:
                    button_text = _(
                        "buy_traffic_package_button",
                        traffic_gb=_format_gb(months),
                        price=price,
                        currency_symbol=currency_symbol_val,
                    )
                    callback_data = (
                        f"subscribe_period:{_format_gb(months)}"
                        f"{callback_suffix_for_context(callback_context)}"
                    )
                else:
                    button_text = _(
                        "subscribe_for_months_button",
                        months=months,
                        price=price,
                        currency_symbol=currency_symbol_val,
                    )
                    callback_data = (
                        f"subscribe_period:{months}{callback_suffix_for_context(callback_context)}"
                    )
                builder.button(text=button_text, callback_data=callback_data)
        builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text=_(key="back_to_main_menu_button"), callback_data=back_callback)
    )
    return builder.as_markup()


def get_tariff_catalog_keyboard(
    tariffs: List[Any],
    lang: str,
    i18n_instance,
    back_callback: str = "main_action:back_to_main",
    callback_context: Optional[str] = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_context = callback_context or callback_context_from_back_callback(back_callback)
    for tariff in tariffs:
        label = tariff.name(lang)
        if tariff.billing_model == "period":
            min_price = tariff.min_period_price_rub()
            if min_price is not None:
                label = f"{label} от {min_price:g}"
        else:
            package = tariff.min_traffic_package_rub()
            if package:
                label = f"{label} от {package.price:g} / {package.gb:g} GB"
        builder.row(
            InlineKeyboardButton(
                text=label,
                callback_data=f"tariff:select:{tariff.key}"
                f"{callback_suffix_for_context(callback_context)}",
            )
        )
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder.row(
        InlineKeyboardButton(text=_(key="back_to_main_menu_button"), callback_data=back_callback)
    )
    return builder.as_markup()


def get_tariff_periods_keyboard(
    tariff: Any,
    lang: str,
    i18n_instance,
    settings: Settings,
    back_callback: str = "main_action:subscribe",
    callback_context: Optional[str] = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_context = callback_context or callback_context_from_back_callback(back_callback)
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    for months in tariff.enabled_periods:
        rub_price = tariff.period_price(months, "rub")
        if rub_price and rub_price > 0:
            builder.row(
                InlineKeyboardButton(
                    text=_(
                        "subscribe_for_months_button",
                        months=months,
                        price=rub_price,
                        currency_symbol=settings.DEFAULT_CURRENCY_SYMBOL,
                    ),
                    callback_data=f"tariff:period:{tariff.key}:{months}"
                    f"{callback_suffix_for_context(callback_context)}",
                )
            )
    builder.row(
        InlineKeyboardButton(text=_(key="back_to_main_menu_button"), callback_data=back_callback)
    )
    return builder.as_markup()


def get_tariff_packages_keyboard(
    tariff: Any,
    packages: List[Any],
    lang: str,
    i18n_instance,
    back_callback: str = "main_action:subscribe",
    callback_context: Optional[str] = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_context = callback_context or callback_context_from_back_callback(back_callback)
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    for package in packages:
        builder.row(
            InlineKeyboardButton(
                text=_(
                    "buy_traffic_package_button",
                    traffic_gb=f"{package.gb:g}",
                    price=package.price,
                    currency_symbol="RUB",
                ),
                callback_data=f"tariff:package:{tariff.key}:{package.gb:g}"
                f"{callback_suffix_for_context(callback_context)}",
            )
        )
    builder.row(
        InlineKeyboardButton(text=_(key="back_to_main_menu_button"), callback_data=back_callback)
    )
    return builder.as_markup()


def get_hwid_device_packages_keyboard(
    tariff: Any,
    packages: List[Any],
    lang: str,
    i18n_instance,
    settings: Settings,
    back_callback: str = "main_action:my_subscription",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    for package in packages:
        builder.row(
            InlineKeyboardButton(
                text=_(
                    "buy_hwid_devices_button",
                    count=package.count,
                    price=package.price,
                    currency_symbol=settings.DEFAULT_CURRENCY_SYMBOL,
                ),
                callback_data=f"hwid_devices:package:{tariff.key}:{package.count}",
            )
        )
    builder.row(
        InlineKeyboardButton(text=_(key="back_to_main_menu_button"), callback_data=back_callback)
    )
    return builder.as_markup()


def get_payment_method_keyboard(
    months: int,
    price: float,
    stars_price: Optional[int],
    currency_symbol_val: str,
    lang: str,
    i18n_instance,
    settings: Settings,
    sale_mode: str = "subscription",
    back_callback: Optional[str] = None,
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()

    def _format_value(val: float) -> str:
        return str(int(val)) if float(val).is_integer() else f"{val:g}"

    value_str = _format_value(months)
    import logging as _kbd_logging

    _kbd_logging.info(
        "payment_method_keyboard build: order=%s",
        settings.payment_methods_order,
    )
    from bot.payment_providers import get_provider_spec, provider_telegram_button_text

    for method in settings.payment_methods_order:
        spec = get_provider_spec(method)
        if not spec or not spec.callback_prefix or not spec.is_enabled(settings):
            continue
        callback_data = spec.callback_data(
            value=value_str,
            rub_price=price,
            stars_price=stars_price,
            sale_mode=sale_mode,
        )
        if not callback_data:
            continue
        builder.button(
            text=provider_telegram_button_text(spec, settings, language=lang),
            callback_data=callback_data,
        )
    builder.button(
        text=_(key="cancel_button"),
        callback_data=back_callback or payment_options_back_callback(sale_mode),
    )
    builder.adjust(1)
    return builder.as_markup()


def get_payment_url_keyboard(
    payment_url: str,
    lang: str,
    i18n_instance,
    back_callback: Optional[str] = None,
    back_text_key: str = "back_to_main_menu_button",
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.button(text=_(key="pay_button"), url=payment_url)
    if back_callback:
        builder.button(text=_(key=back_text_key), callback_data=back_callback)
    else:
        builder.button(
            text=_(key="back_to_main_menu_button"), callback_data="main_action:back_to_main"
        )
    builder.adjust(1)
    return builder.as_markup()


def get_yk_autopay_choice_keyboard(
    months: int,
    price: float,
    lang: str,
    i18n_instance,
    has_saved_cards: bool = True,
    sale_mode: str = "subscription",
    back_callback: Optional[str] = None,
) -> InlineKeyboardMarkup:
    """Keyboard for choosing between saved card charge or new card payment when auto-renew is enabled."""  # noqa: E501
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    price_str = str(price)

    def _format_value(val: float) -> str:
        return str(int(val)) if float(val).is_integer() else f"{val:g}"

    value_str = _format_value(months)
    suffix = f":{sale_mode}"
    if has_saved_cards:
        builder.row(
            InlineKeyboardButton(
                text=_(key="yookassa_autopay_pay_saved_card_button"),
                callback_data=f"pay_yk_saved_list:{value_str}:{price_str}{suffix}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=_(key="yookassa_autopay_pay_new_card_button"),
            callback_data=f"pay_yk_new:{value_str}:{price_str}{suffix}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_(key="back_to_payment_methods_button"),
            callback_data=back_callback or payment_methods_back_callback(value_str, sale_mode),
        )
    )
    return builder.as_markup()


def get_yk_saved_cards_keyboard(
    cards: List[Tuple[str, str]],
    months: int,
    price: float,
    lang: str,
    i18n_instance,
    page: int = 0,
    sale_mode: str = "subscription",
) -> InlineKeyboardMarkup:
    """Paginated keyboard for selecting a saved YooKassa card."""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    per_page = 5
    total = len(cards)
    start = page * per_page
    end = min(total, start + per_page)
    price_str = str(price)

    def _format_value(val: float) -> str:
        return str(int(val)) if float(val).is_integer() else f"{val:g}"

    value_str = _format_value(months)
    suffix = f":{sale_mode}"

    for method_id, title in cards[start:end]:
        builder.row(
            InlineKeyboardButton(
                text=title,
                callback_data=f"pay_yk_use_saved:{value_str}:{price_str}:{method_id}{suffix}",
            )
        )

    nav_buttons: List[InlineKeyboardButton] = []
    if start > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"pay_yk_saved_list:{value_str}:{price_str}:{page - 1}{suffix}",
            )
        )
    if end < total:
        nav_buttons.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"pay_yk_saved_list:{value_str}:{price_str}:{page + 1}{suffix}",
            )
        )
    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(
        InlineKeyboardButton(
            text=_(key="yookassa_autopay_pay_new_card_button"),
            callback_data=f"pay_yk_new:{value_str}:{price_str}{suffix}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_(key="back_to_autopay_method_choice_button"),
            callback_data=f"pay_yk:{value_str}:{price_str}{suffix}",
        )
    )
    return builder.as_markup()


def get_referral_link_keyboard(
    lang: str, i18n_instance, back_callback: str = "main_action:back_to_main"
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
    lang: str, i18n_instance, callback_data: Optional[str] = None
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


def get_subscribe_only_markup(lang: str, i18n_instance) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.button(text=_(key="menu_subscribe_inline"), callback_data="main_action:subscribe")
    return builder.as_markup()


def get_user_banned_keyboard(
    support_link: Optional[str], lang: str, i18n_instance
) -> Optional[InlineKeyboardMarkup]:
    if not support_link:
        return None
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.button(text=_(key="menu_support_button"), url=support_link)
    return builder.as_markup()


def get_channel_subscription_keyboard(
    lang: str, i18n_instance, channel_link: Optional[str], include_check_button: bool = True
) -> Optional[InlineKeyboardMarkup]:
    """
    Return keyboard with buttons to open the required channel and trigger a subscription re-check.
    """
    if i18n_instance is None:
        return None

    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()

    has_buttons = False

    if channel_link:
        builder.button(
            text=_(key="channel_subscription_join_button"),
            url=channel_link,
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
    i18n_instance,
    settings: Settings,
    config_link: Optional[str],
    connect_button_url: Optional[str] = None,
    preserve_message: bool = False,
) -> InlineKeyboardMarkup:
    """Keyboard with a connect button and a back to main menu button."""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    button_target = connect_button_url or config_link

    if button_target:
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


def get_payment_methods_manage_keyboard(
    lang: str, i18n_instance, has_card: bool
) -> InlineKeyboardMarkup:
    """Deprecated in favor of get_payment_methods_list_keyboard. Kept for backward compatibility."""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=_(key="payment_method_bind_button"), callback_data="pm:bind")
    )
    builder.row(
        InlineKeyboardButton(
            text=_(key="back_to_main_menu_button"), callback_data="main_action:back_to_main"
        )
    )
    return builder.as_markup()


def get_payment_methods_list_keyboard(
    cards: List[Tuple[str, str]],
    page: int,
    lang: str,
    i18n_instance,
) -> InlineKeyboardMarkup:
    """
    Build a paginated list of saved payment methods.
    cards: list of tuples (payment_method_id, display_title)
    page: 0-based page index
    """
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    per_page = 5
    total = len(cards)
    start = page * per_page
    end = start + per_page
    for pm_id, title in cards[start:end]:
        builder.row(InlineKeyboardButton(text=title, callback_data=f"pm:view:{pm_id}"))

    # Pagination controls if needed
    nav_buttons: List[InlineKeyboardButton] = []
    if start > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"pm:list:{page - 1}"))
    if end < total:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"pm:list:{page + 1}"))
    if nav_buttons:
        builder.row(*nav_buttons)

    # Bind new card and back
    builder.row(
        InlineKeyboardButton(text=_(key="payment_method_bind_button"), callback_data="pm:bind")
    )
    builder.row(
        InlineKeyboardButton(
            text=_(key="back_to_main_menu_button"), callback_data="main_action:back_to_main"
        )
    )
    return builder.as_markup()


def get_payment_method_delete_confirm_keyboard(
    pm_id: str, lang: str, i18n_instance
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=_(key="yes_button"), callback_data=f"pm:delete:{pm_id}"),
        InlineKeyboardButton(text=_(key="cancel_button"), callback_data=f"pm:view:{pm_id}"),
    )
    return builder.as_markup()


def get_payment_method_details_keyboard(
    pm_id: str, lang: str, i18n_instance
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=_(key="payment_method_tx_history_title"), callback_data=f"pm:history:{pm_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_(key="payment_method_delete_button"), callback_data=f"pm:delete_confirm:{pm_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(text=_(key="back_to_main_menu_button"), callback_data="pm:list:0")
    )
    return builder.as_markup()


def get_bind_url_keyboard(bind_url: str, lang: str, i18n_instance) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.button(text=_(key="payment_method_bind_button"), url=bind_url)
    builder.button(text=_(key="back_to_main_menu_button"), callback_data="pm:manage")
    builder.adjust(1)
    return builder.as_markup()


def get_back_to_payment_methods_keyboard(lang: str, i18n_instance) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=_(key="back_to_main_menu_button"), callback_data="pm:list:0")
    )
    return builder.as_markup()


def get_back_to_payment_method_details_keyboard(
    pm_id: str, lang: str, i18n_instance
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    # Back one step: return to specific payment method details
    builder.row(
        InlineKeyboardButton(
            text=_(key="back_to_main_menu_button"), callback_data=f"pm:view:{pm_id}"
        )
    )
    return builder.as_markup()


def get_autorenew_cancel_keyboard(lang: str, i18n_instance) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=_(key="autorenew_disable_button"), callback_data="autorenew:cancel"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_(key="menu_my_subscription_inline"), callback_data="main_action:my_subscription"
        )
    )
    return builder.as_markup()


def get_autorenew_confirm_keyboard(
    enable: bool, sub_id: int, lang: str, i18n_instance
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=_(key="yes_button"),
            callback_data=f"autorenew:confirm:{sub_id}:{1 if enable else 0}",
        ),
        InlineKeyboardButton(text=_(key="no_button"), callback_data="main_action:my_subscription"),
    )
    return builder.as_markup()
