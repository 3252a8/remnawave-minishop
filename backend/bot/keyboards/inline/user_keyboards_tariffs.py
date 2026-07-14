from typing import Any

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton

from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from config.tariffs_config import (
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
)

from .user_keyboards_context import (
    callback_context_from_back_callback,
    callback_suffix_for_context,
)


def get_subscription_options_keyboard(
    subscription_options: dict[float, float | None],
    currency_symbol_val: str,
    lang: str,
    i18n_instance: JsonI18n,
    traffic_mode: bool = False,
    back_callback: str = "main_action:back_to_main",
    callback_context: str | None = None,
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
    tariffs: list[Any],
    lang: str,
    i18n_instance: JsonI18n,
    settings: Settings | None = None,
    back_callback: str = "main_action:back_to_main",
    callback_context: str | None = None,
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
                label = f"{label} from {min_price:g}"
        else:
            if hasattr(tariff, "min_traffic_package"):
                package = tariff.min_traffic_package(default_currency)
            elif default_currency == "rub" and hasattr(tariff, "min_traffic_package_rub"):
                package = tariff.min_traffic_package_rub()
            else:
                package = None
            if package:
                label = f"{label} from {package.price:g} / {package.gb:g} GB"
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
    i18n_instance: JsonI18n,
    settings: Settings,
    back_callback: str = "main_action:subscribe",
    callback_context: str | None = None,
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
    packages: list[Any],
    lang: str,
    i18n_instance: JsonI18n,
    currency_symbol: str = "RUB",
    back_callback: str = "main_action:subscribe",
    callback_context: str | None = None,
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
    packages: list[Any],
    lang: str,
    i18n_instance: JsonI18n,
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
