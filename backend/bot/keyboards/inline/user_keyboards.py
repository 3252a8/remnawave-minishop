from typing import Any, Dict, List, Optional, Tuple

from aiogram.types import InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton

from bot.middlewares.i18n import locale_language_options
from bot.utils.channel_subscription import normalize_required_channel_link
from bot.utils.install_links import bot_install_guide_url
from bot.utils.mini_app_url import subscription_mini_app_trial_url
from config.settings import Settings
from config.tariffs_config import (
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
)

BOT_MENU_CONTEXT = "bot"
HWID_RENEWAL_TOKEN = "hwid_renewal"


def sale_mode_tokens(sale_mode: Optional[str]) -> Tuple[str, ...]:
    if not sale_mode or "|" not in sale_mode:
        return ()
    return tuple(token.strip() for token in str(sale_mode).split("|")[1:] if token.strip())


def callback_context_from_back_callback(back_callback: Optional[str]) -> Optional[str]:
    if back_callback == "main_action:bot_interface":
        return BOT_MENU_CONTEXT
    return None


def sale_mode_with_callback_context(sale_mode: str, context: Optional[str]) -> str:
    sale_mode = sale_mode or "subscription"
    if not context or context in sale_mode_tokens(sale_mode):
        return sale_mode
    return f"{sale_mode}|{context}"


def sale_mode_with_token(sale_mode: str, token: str) -> str:
    sale_mode = sale_mode or "subscription"
    token = str(token or "").strip()
    if not token or token in sale_mode_tokens(sale_mode):
        return sale_mode
    return f"{sale_mode}|{token}"


def sale_mode_without_token(sale_mode: str, token: str) -> str:
    sale_mode = sale_mode or "subscription"
    token = str(token or "").strip()
    if not token or "|" not in sale_mode:
        return sale_mode
    base, *tokens = sale_mode.split("|")
    kept = [item for item in tokens if item.strip() and item.strip() != token]
    return "|".join([base, *kept])


def sale_mode_has_token(sale_mode: Optional[str], token: str) -> bool:
    return str(token or "").strip() in sale_mode_tokens(sale_mode)


def callback_context_from_sale_mode(sale_mode: Optional[str]) -> Optional[str]:
    tokens = sale_mode_tokens(sale_mode)
    return BOT_MENU_CONTEXT if BOT_MENU_CONTEXT in tokens else None


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
    if sale_base in {"hwid_device", "hwid_devices", "hwid_devices_renewal"} and tariff_key:
        action = "renewal_package" if sale_base == "hwid_devices_renewal" else "package"
        return f"hwid_devices:{action}:{tariff_key}:{value}"
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
    if sale_base in {"hwid_device", "hwid_devices", "hwid_devices_renewal"}:
        return "hwid_devices:list"
    return subscription_options_callback(context)


def _trial_activation_button(lang: str, i18n_instance, settings: Settings) -> InlineKeyboardButton:
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
    lang: str, i18n_instance, settings: Settings, show_trial_button: bool = False
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

    builder.row(
        InlineKeyboardButton(
            text=_(key="menu_bot_interface_button"), callback_data="main_action:bot_interface"
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
    lang: str, i18n_instance, settings: Settings, show_trial_button: bool = False
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
    settings: Optional[Settings] = None,
    back_callback: str = "main_action:back_to_main",
    callback_context: Optional[str] = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_context = callback_context or callback_context_from_back_callback(back_callback)
    default_currency = default_currency_key_for_settings(settings) if settings else "rub"
    for tariff in tariffs:
        label = tariff.name(lang)
        if tariff.billing_model == "period":
            if hasattr(tariff, "min_period_price"):
                min_price = tariff.min_period_price(default_currency)
            elif default_currency == "rub" and hasattr(tariff, "min_period_price_rub"):
                min_price = tariff.min_period_price_rub()
            else:
                min_price = None
            if min_price is not None:
                label = f"{label} от {min_price:g}"
        else:
            if hasattr(tariff, "min_traffic_package"):
                package = tariff.min_traffic_package(default_currency)
            elif default_currency == "rub" and hasattr(tariff, "min_traffic_package_rub"):
                package = tariff.min_traffic_package_rub()
            else:
                package = None
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
    default_currency = default_currency_key_for_settings(settings)
    currency_code = default_payment_currency_code_for_settings(settings)
    for months in tariff.enabled_periods:
        rub_price = tariff.period_price(months, default_currency)
        if rub_price and rub_price > 0:
            builder.row(
                InlineKeyboardButton(
                    text=_(
                        "subscribe_for_months_button",
                        months=months,
                        price=rub_price,
                        currency_symbol=currency_code,
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
    currency_symbol: str = "RUB",
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
                    currency_symbol=currency_symbol,
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
    renewal: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    currency_code = default_payment_currency_code_for_settings(settings)
    for package in packages:
        builder.row(
            InlineKeyboardButton(
                text=_(
                    "buy_hwid_devices_button",
                    count=package.count,
                    price=package.price,
                    currency_symbol=currency_code,
                ),
                callback_data=(
                    f"hwid_devices:{'renewal_package' if renewal else 'package'}:"
                    f"{tariff.key}:{package.count}"
                ),
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
    user_id: Optional[int] = None,
    is_admin: Optional[bool] = None,
    hwid_renewal_quote: Optional[Dict[str, Any]] = None,
    hwid_renewal_stars_quote: Optional[Dict[str, Any]] = None,
    hwid_renewal_selected: bool = True,
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()

    def _format_value(val: float) -> str:
        return str(int(val)) if float(val).is_integer() else f"{val:g}"

    value_str = _format_value(months)
    payment_sale_mode = sale_mode
    selected_hwid_quote = hwid_renewal_quote or hwid_renewal_stars_quote
    if selected_hwid_quote:
        tariff_key = None
        sale_mode_main = str(sale_mode or "").split("|", 1)[0]
        if "@" in sale_mode_main:
            tariff_key = sale_mode_main.split("@", 1)[1]
        context = callback_context_from_sale_mode(sale_mode)
        toggle_tokens = [f"tariff:period:{tariff_key}:{value_str}"]
        if context:
            toggle_tokens.append(context)
        toggle_tokens.append("no_hwid" if hwid_renewal_selected else "hwid")
        builder.row(
            InlineKeyboardButton(
                text=_(
                    "payment_hwid_renewal_toggle_on"
                    if hwid_renewal_selected
                    else "payment_hwid_renewal_toggle_off",
                    count=int(selected_hwid_quote.get("device_count") or 0),
                    price=(
                        hwid_renewal_quote.get("price")
                        if hwid_renewal_quote
                        else hwid_renewal_stars_quote.get("price")
                    ),
                    currency_symbol=currency_symbol_val,
                ),
                callback_data=":".join(toggle_tokens),
            )
        )
        if hwid_renewal_selected:
            payment_sale_mode = sale_mode_with_token(sale_mode, HWID_RENEWAL_TOKEN)
        else:
            payment_sale_mode = sale_mode_without_token(sale_mode, HWID_RENEWAL_TOKEN)
    from bot.payment_providers import get_provider_spec, provider_telegram_button_text

    for method in settings.payment_methods_order:
        spec = get_provider_spec(method)
        if (
            not spec
            or not spec.callback_prefix
            or not spec.is_usable_for_payment_currency(settings, currency_symbol_val)
            or not spec.is_available_to_user(
                settings,
                user_id=user_id,
                is_admin=is_admin,
                require_configured=False,
            )
        ):
            continue
        callback_data = spec.callback_data(
            value=value_str,
            rub_price=price,
            stars_price=stars_price,
            sale_mode=payment_sale_mode,
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
                callback_data=f"pay_yk_saved_list:{value_str}:{price_str}:0{suffix}",
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
    i18n_instance,
    settings: Settings,
    config_link: Optional[str],
    connect_button_url: Optional[str] = None,
    preserve_message: bool = False,
    install_share_url: Optional[str] = None,
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
