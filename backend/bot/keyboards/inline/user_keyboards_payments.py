from typing import Any, Dict, List, Optional, Tuple

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton

from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from config.tariffs_config import (
    default_payment_currency_code_for_settings,
    payment_currency_code,
)

from .user_keyboards_context import (
    HWID_RENEWAL_TOKEN,
    callback_context_from_sale_mode,
    payment_methods_back_callback,
    payment_options_back_callback,
    sale_mode_with_token,
    sale_mode_without_token,
)


def _provider_filter_currency_code(settings: Settings, display_currency: str) -> str:
    text = str(display_currency or "").strip()
    if text in {"⭐", "★"}:
        return "XTR"
    return payment_currency_code(
        text,
        default=default_payment_currency_code_for_settings(settings),
    )


def get_payment_method_keyboard(
    months: int,
    price: float,
    stars_price: Optional[int],
    currency_symbol_val: str,
    lang: str,
    i18n_instance: JsonI18n,
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
    provider_currency_code = _provider_filter_currency_code(settings, currency_symbol_val)
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
                    price=selected_hwid_quote.get("price"),
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
            or not spec.is_usable_for_payment(settings, provider_currency_code, price)
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
    i18n_instance: JsonI18n,
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
    i18n_instance: JsonI18n,
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
    i18n_instance: JsonI18n,
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


def get_payment_methods_list_keyboard(
    cards: List[Tuple[str, str]],
    page: int,
    lang: str,
    i18n_instance: JsonI18n,
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
    pm_id: str, lang: str, i18n_instance: JsonI18n
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=_(key="yes_button"), callback_data=f"pm:delete:{pm_id}"),
        InlineKeyboardButton(text=_(key="cancel_button"), callback_data=f"pm:view:{pm_id}"),
    )
    return builder.as_markup()


def get_payment_method_details_keyboard(
    pm_id: str, lang: str, i18n_instance: JsonI18n
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


def get_bind_url_keyboard(
    bind_url: str, lang: str, i18n_instance: JsonI18n
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.button(text=_(key="payment_method_bind_button"), url=bind_url)
    builder.button(text=_(key="back_to_main_menu_button"), callback_data="pm:manage")
    builder.adjust(1)
    return builder.as_markup()


def get_back_to_payment_methods_keyboard(
    lang: str, i18n_instance: JsonI18n
) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=_(key="back_to_main_menu_button"), callback_data="pm:list:0")
    )
    return builder.as_markup()


def get_back_to_payment_method_details_keyboard(
    pm_id: str, lang: str, i18n_instance: JsonI18n
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


def get_autorenew_cancel_keyboard(lang: str, i18n_instance: JsonI18n) -> InlineKeyboardMarkup:
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
    enable: bool, sub_id: int, lang: str, i18n_instance: JsonI18n
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
