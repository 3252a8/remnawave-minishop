import hashlib
import html
import logging
from datetime import datetime
from typing import Optional, Union

from aiogram import Bot, F, Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import (
    callback_context_from_back_callback,
    callback_suffix_for_context,
    get_autorenew_confirm_keyboard,
    get_back_to_main_menu_markup,
    get_hwid_device_packages_keyboard,
    get_payment_method_keyboard,
    get_subscription_options_keyboard,
    get_tariff_catalog_keyboard,
    get_tariff_packages_keyboard,
    get_tariff_periods_keyboard,
    sale_mode_with_callback_context,
    tariff_purchase_back_callback,
)
from bot.middlewares.i18n import JsonI18n
from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service import SubscriptionService
from bot.utils.install_links import (
    append_install_share_link_text,
    ensure_user_install_guide_links,
)
from config.settings import Settings
from config.tariffs_config import (
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
)
from db.dal import subscription_dal, user_billing_dal
from db.models import Subscription

router = Router(name="user_subscription_core_router")


def _shorten_hwid_for_display(hwid: Optional[str], max_length: int = 24) -> str:
    """Trim HWID for button text to keep within Telegram limits."""
    if not hwid:
        return "-"
    hwid_str = str(hwid)
    if len(hwid_str) <= max_length:
        return hwid_str
    return f"{hwid_str[:8]}...{hwid_str[-6:]}"


def _hwid_callback_token(hwid: Optional[str]) -> str:
    """Stable short token for callback_data; avoids 64b limit with raw HWID."""
    hwid_str = str(hwid or "")
    return hashlib.sha256(hwid_str.encode()).hexdigest()[:32]


def _enabled_tariffs(settings: Settings) -> list:
    config = getattr(settings, "tariffs_config", None)
    return list(config.enabled_tariffs) if config else []


def _has_multiple_enabled_tariffs(settings: Settings) -> bool:
    return len(_enabled_tariffs(settings)) > 1


def _tariff_purchase_markup(
    tariff,
    current_lang: str,
    i18n: JsonI18n,
    settings: Settings,
    back_callback: str = "main_action:subscribe",
    callback_context: Optional[str] = None,
) -> InlineKeyboardMarkup:
    if tariff.billing_model == "period":
        return get_tariff_periods_keyboard(
            tariff,
            current_lang,
            i18n,
            settings,
            back_callback=back_callback,
            callback_context=callback_context,
        )
    default_currency = default_currency_key_for_settings(settings)
    return get_tariff_packages_keyboard(
        tariff,
        tariff.traffic_packages.for_currency(default_currency),
        current_lang,
        i18n,
        currency_symbol=default_payment_currency_code_for_settings(settings),
        back_callback=back_callback,
        callback_context=callback_context,
    )


def _tariff_purchase_text(tariff, current_lang: str, i18n: JsonI18n, settings: Settings) -> str:
    if not _has_multiple_enabled_tariffs(settings):
        if tariff.billing_model == "period":
            return i18n.gettext(current_lang, "select_subscription_period")
        return i18n.gettext(current_lang, "select_traffic_package")
    return f"{tariff.name(current_lang)}\n{tariff.description(current_lang)}".strip()


def _with_subscription_purchase_description(
    text: str,
    settings: Settings,
    current_lang: str,
    *,
    include: bool,
) -> str:
    if not include:
        return text
    description_resolver = getattr(settings, "subscription_purchase_description", None)
    description = description_resolver(current_lang) if callable(description_resolver) else ""
    if not description:
        return text
    return f"{description}\n\n{text}"


def _format_premium_bytes(value: object) -> str:
    try:
        bytes_value = max(0, int(value or 0))
    except (TypeError, ValueError):
        bytes_value = 0
    return f"{bytes_value / 2**30:.2f} GB"


def _format_premium_usage_limit(active: dict[str, object]) -> str:
    used = _format_premium_bytes(active.get("premium_used_bytes"))
    limit = _format_premium_bytes(active.get("premium_limit_bytes"))
    return f"{used} из {limit}"


async def display_subscription_options(
    event: Union[types.Message, types.CallbackQuery],
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
    back_callback: str = "main_action:back_to_main",
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")

    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    if not i18n:
        err_msg = "Language service error."
        if isinstance(event, types.CallbackQuery):
            try:
                await event.answer(err_msg, show_alert=True)
            except Exception:
                pass
        elif isinstance(event, types.Message):
            await event.answer(err_msg)
        return

    currency_symbol_val = settings.DEFAULT_CURRENCY_SYMBOL
    tariffs_config = getattr(settings, "tariffs_config", None)
    if tariffs_config:
        enabled_tariffs = list(tariffs_config.enabled_tariffs)
        callback_context = callback_context_from_back_callback(back_callback)
        if len(enabled_tariffs) == 1:
            tariff = enabled_tariffs[0]
            text_content = _tariff_purchase_text(tariff, current_lang, i18n, settings)
            text_content = _with_subscription_purchase_description(
                text_content,
                settings,
                current_lang,
                include=tariff.billing_model == "period",
            )
            reply_markup = _tariff_purchase_markup(
                tariff,
                current_lang,
                i18n,
                settings,
                back_callback=back_callback,
                callback_context=callback_context,
            )
        else:
            text_content = get_text("select_subscription_period")
            text_content = _with_subscription_purchase_description(
                text_content,
                settings,
                current_lang,
                include=any(tariff.billing_model == "period" for tariff in enabled_tariffs),
            )
            reply_markup = get_tariff_catalog_keyboard(
                enabled_tariffs,
                current_lang,
                i18n,
                settings=settings,
                back_callback=back_callback,
                callback_context=callback_context,
            )
        target_message_obj = event.message if isinstance(event, types.CallbackQuery) else event
        if isinstance(event, types.CallbackQuery):
            try:
                await target_message_obj.edit_text(text_content, reply_markup=reply_markup)
            except Exception:
                await target_message_obj.answer(text_content, reply_markup=reply_markup)
            await event.answer()
        else:
            await target_message_obj.answer(text_content, reply_markup=reply_markup)
        return

    traffic_packages = getattr(settings, "traffic_packages", {}) or {}
    stars_traffic_packages = getattr(settings, "stars_traffic_packages", {}) or {}
    traffic_mode = bool(getattr(settings, "traffic_sale_mode", False) or stars_traffic_packages)

    if traffic_mode:
        if traffic_packages:
            options = traffic_packages
        elif stars_traffic_packages:
            options = stars_traffic_packages
            currency_symbol_val = "⭐"
        else:
            options = {}
    else:
        options = settings.subscription_options

    if options:
        text_content = (
            get_text("select_traffic_package")
            if traffic_mode
            else get_text("select_subscription_period")
        )
        text_content = _with_subscription_purchase_description(
            text_content,
            settings,
            current_lang,
            include=not traffic_mode,
        )
        reply_markup = get_subscription_options_keyboard(
            options,
            currency_symbol_val,
            current_lang,
            i18n,
            traffic_mode=traffic_mode,
            back_callback=back_callback,
            callback_context=callback_context_from_back_callback(back_callback),
        )
    else:
        text_content = get_text("no_subscription_options_available")
        reply_markup = get_back_to_main_menu_markup(
            current_lang,
            i18n,
            callback_data=back_callback,
        )

    target_message_obj = event.message if isinstance(event, types.CallbackQuery) else event
    if not target_message_obj:
        if isinstance(event, types.CallbackQuery):
            try:
                await event.answer(get_text("error_occurred_try_again"), show_alert=True)
            except Exception:
                pass
        return

    if isinstance(event, types.CallbackQuery):
        try:
            await target_message_obj.edit_text(text_content, reply_markup=reply_markup)
        except Exception:
            await target_message_obj.answer(text_content, reply_markup=reply_markup)
        try:
            await event.answer()
        except Exception:
            pass
    else:
        await target_message_obj.answer(text_content, reply_markup=reply_markup)


@router.callback_query(F.data == "main_action:subscribe")
async def reshow_subscription_options_callback(
    callback: types.CallbackQuery, i18n_data: dict, settings: Settings, session: AsyncSession
):
    await display_subscription_options(callback, i18n_data, settings, session)


@router.callback_query(F.data.startswith("tariff:select:"))
async def select_tariff_callback(
    callback: types.CallbackQuery, i18n_data: dict, settings: Settings, session: AsyncSession
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        return
    parts = callback.data.split(":")
    tariff_key = parts[2] if len(parts) > 2 else ""
    callback_context = parts[3] if len(parts) > 3 else None
    try:
        tariff = config.require(tariff_key)
    except Exception:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    markup = _tariff_purchase_markup(
        tariff,
        current_lang,
        i18n,
        settings,
        back_callback=tariff_purchase_back_callback(callback_context),
        callback_context=callback_context,
    )
    text = _tariff_purchase_text(tariff, current_lang, i18n, settings)
    text = _with_subscription_purchase_description(
        text,
        settings,
        current_lang,
        include=tariff.billing_model == "period",
    )
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("tariff:period:"))
async def select_tariff_period_callback(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
    subscription_service: SubscriptionService,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        return
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    tariff_key, months_raw = parts[2], parts[3]
    callback_tokens = [part for part in parts[4:] if part]
    callback_context = "bot" if "bot" in callback_tokens else None
    renew_hwid_devices = "no_hwid" not in callback_tokens
    tariff = config.require(tariff_key)
    months = int(months_raw)
    default_currency = default_currency_key_for_settings(settings)
    currency_code = default_payment_currency_code_for_settings(settings)
    price_rub = tariff.period_price(months, default_currency)
    stars_price = tariff.period_price(months, "stars")
    if price_rub is None:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    hwid_renewal_quote = await subscription_service.quote_hwid_device_renewal_for_subscription(
        session,
        user_id=callback.from_user.id,
        target_tariff_key=tariff.key,
        months=months,
        currency=default_currency,
    )
    hwid_renewal_stars_quote = (
        await subscription_service.quote_hwid_device_renewal_for_subscription(
            session,
            user_id=callback.from_user.id,
            target_tariff_key=tariff.key,
            months=months,
            currency="stars",
        )
    )
    markup = get_payment_method_keyboard(
        months,
        price_rub,
        int(stars_price) if stars_price else None,
        currency_code,
        current_lang,
        i18n,
        settings,
        sale_mode=sale_mode_with_callback_context(f"subscription@{tariff.key}", callback_context),
        back_callback=f"tariff:select:{tariff.key}{callback_suffix_for_context(callback_context)}",
        user_id=callback.from_user.id,
        hwid_renewal_quote=hwid_renewal_quote,
        hwid_renewal_stars_quote=hwid_renewal_stars_quote,
        hwid_renewal_selected=bool(renew_hwid_devices),
    )
    await callback.message.edit_text(get_text("choose_payment_method"), reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("tariff:package:"))
async def select_tariff_package_callback(
    callback: types.CallbackQuery, i18n_data: dict, settings: Settings, session: AsyncSession
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        return
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    tariff_key, gb_raw = parts[2], parts[3]
    callback_context = parts[4] if len(parts) > 4 else None
    tariff = config.require(tariff_key)
    gb = float(gb_raw)
    default_currency = default_currency_key_for_settings(settings)
    currency_code = default_payment_currency_code_for_settings(settings)
    packages = (
        tariff.traffic_packages.for_currency(default_currency)
        if tariff.billing_model == "traffic"
        else (
            config.topup_packages_for(tariff).for_currency(default_currency)
            if config.topup_packages_for(tariff)
            else []
        )
    )
    package = next((pkg for pkg in packages if float(pkg.gb) == gb), None)
    if not package:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    sale_mode = (
        f"{'traffic_package' if tariff.billing_model == 'traffic' else 'topup'}@{tariff.key}"
    )
    sale_mode = sale_mode_with_callback_context(sale_mode, callback_context)
    back_callback = (
        f"tariff:select:{tariff.key}{callback_suffix_for_context(callback_context)}"
        if tariff.billing_model == "traffic"
        else "tariff_topup:list"
    )
    markup = get_payment_method_keyboard(
        gb,
        package.price,
        None,
        currency_code,
        current_lang,
        i18n,
        settings,
        sale_mode=sale_mode,
        back_callback=back_callback,
        user_id=callback.from_user.id,
    )
    await callback.message.edit_text(get_text("choose_payment_method_traffic"), reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data == "tariff_topup:list")
async def tariff_topup_list_callback(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    subscription_service: SubscriptionService,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    config = settings.tariffs_config
    active = await subscription_service.get_active_subscription_details(
        session, callback.from_user.id
    )
    if not config or not active or not active.get("tariff_key") or not callback.message:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    tariff = config.require(active["tariff_key"])
    packages = config.topup_packages_for(tariff)
    default_currency = default_currency_key_for_settings(settings)
    currency = default_payment_currency_code_for_settings(settings)
    currency_packages = packages.for_currency(default_currency) if packages else []
    premium_packages = (
        tariff.premium_topup_packages.for_currency(default_currency)
        if tariff.premium_topup_packages
        else []
    )
    if not currency_packages and not premium_packages:
        await callback.answer(get_text("no_subscription_options_available"), show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    for package in currency_packages:
        builder.row(
            InlineKeyboardButton(
                text=f"Обычный трафик +{package.gb:g} GB — {package.price:g} {currency}",
                callback_data=f"tariff:package:{tariff.key}:{package.gb:g}",
            )
        )
    for package in premium_packages:
        builder.row(
            InlineKeyboardButton(
                text=f"Premium-серверы +{package.gb:g} GB — {package.price:g} {currency}",
                callback_data=f"tariff:premium_package:{tariff.key}:{package.gb:g}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=get_text("back_to_main_menu_button"), callback_data="main_action:my_subscription"
        )
    )

    premium_lines = []
    carryover_lines = []
    if currency_packages or premium_packages:
        carryover_lines.append(
            "Докупленный трафик не сгорает: сначала расходуется месячный лимит, затем докупленный остаток."  # noqa: E501
        )
    if int(active.get("premium_limit_bytes") or 0) > 0:
        premium_left = max(
            0,
            int(active.get("premium_limit_bytes") or 0)
            - int(active.get("premium_used_bytes") or 0),
        )
        labels = active.get("premium_node_labels") or active.get("premium_squad_labels") or []
        if labels:
            visible = [str(label) for label in labels[:8]]
            premium_lines.append("Premium-лимит действует на:")
            premium_lines.extend(f"• {label}" for label in visible)
            if len(labels) > len(visible):
                premium_lines.append(f"• ... еще {len(labels) - len(visible)}")
        premium_lines.append(
            f"Premium использовано: {_format_premium_usage_limit(active)}. Осталось: {premium_left / 2**30:.2f} GB."  # noqa: E501
        )
    text = get_text("choose_payment_method_traffic")
    if carryover_lines:
        text = text + "\n\n" + "\n".join(carryover_lines)
    if premium_lines:
        text = text + "\n\n" + "\n".join(premium_lines)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("tariff:premium_package:"))
async def select_tariff_premium_package_callback(
    callback: types.CallbackQuery, i18n_data: dict, settings: Settings, session: AsyncSession
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        return
    _, _, tariff_key, gb_raw = callback.data.split(":", 3)
    tariff = config.require(tariff_key)
    gb = float(gb_raw)
    default_currency = default_currency_key_for_settings(settings)
    currency_code = default_payment_currency_code_for_settings(settings)
    packages = (
        tariff.premium_topup_packages.for_currency(default_currency)
        if tariff.premium_topup_packages
        else []
    )
    package = next((pkg for pkg in packages if float(pkg.gb) == gb), None)
    if not package:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    markup = get_payment_method_keyboard(
        gb,
        package.price,
        None,
        currency_code,
        current_lang,
        i18n,
        settings,
        sale_mode=f"premium_topup@{tariff.key}",
        back_callback="tariff_topup:list",
        user_id=callback.from_user.id,
    )
    await callback.message.edit_text(get_text("choose_payment_method_traffic"), reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data == "hwid_devices:list")
async def hwid_devices_list_callback(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    subscription_service: SubscriptionService,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    config = settings.tariffs_config
    active = await subscription_service.get_active_subscription_details(
        session, callback.from_user.id
    )
    if not config or not active or not active.get("tariff_key") or not callback.message:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    max_devices = active.get("max_devices")
    if max_devices == 0:
        await callback.answer(get_text("hwid_devices_unlimited_no_topup"), show_alert=True)
        return
    tariff = config.require(active["tariff_key"])
    if tariff.billing_model != "period":
        await callback.answer(get_text("no_hwid_device_packages_available"), show_alert=True)
        return
    default_currency = default_currency_key_for_settings(settings)
    packages = (
        tariff.hwid_device_packages.for_currency(default_currency)
        if tariff.hwid_device_packages
        else []
    )
    if not packages:
        await callback.answer(get_text("no_hwid_device_packages_available"), show_alert=True)
        return
    markup = get_hwid_device_packages_keyboard(
        tariff,
        packages,
        current_lang,
        i18n,
        settings,
        back_callback="main_action:my_devices",
        renewal=False,
    )
    await callback.message.edit_text(
        get_text(
            "select_hwid_device_package",
            date=active.get("extra_hwid_devices_valid_until_text") or "",
        ),
        reply_markup=markup,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("hwid_devices:package:"))
@router.callback_query(F.data.startswith("hwid_devices:renewal_package:"))
async def hwid_devices_package_callback(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
    subscription_service: SubscriptionService,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        return
    _, action, tariff_key, count_raw = callback.data.split(":", 3)
    tariff = config.require(tariff_key)
    if tariff.billing_model != "period":
        await callback.answer(get_text("no_hwid_device_packages_available"), show_alert=True)
        return
    count = int(count_raw)
    package = next(
        (
            pkg
            for pkg in (
                tariff.hwid_device_packages.for_currency(
                    default_currency_key_for_settings(settings)
                )
                if tariff.hwid_device_packages
                else []
            )
            if int(pkg.count) == count
        ),
        None,
    )
    if not package:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    sale_mode_base = "hwid_devices_renewal" if action == "renewal_package" else "hwid_devices"
    renewal = action == "renewal_package"
    default_currency = default_currency_key_for_settings(settings)
    currency_code = default_payment_currency_code_for_settings(settings)
    currency_quote = await subscription_service.quote_hwid_device_topup(
        session,
        user_id=callback.from_user.id,
        device_count=count,
        tariff_key=tariff.key,
        renewal=renewal,
        currency=default_currency,
    )
    stars_quote = await subscription_service.quote_hwid_device_topup(
        session,
        user_id=callback.from_user.id,
        device_count=count,
        tariff_key=tariff.key,
        renewal=renewal,
        currency="stars",
    )
    if not currency_quote and not stars_quote:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    markup = get_payment_method_keyboard(
        count,
        float(currency_quote.get("price") if currency_quote else 0),
        int(stars_quote["price"])
        if stars_quote and int(stars_quote.get("price") or 0) > 0
        else None,
        currency_code,
        current_lang,
        i18n,
        settings,
        sale_mode=f"{sale_mode_base}@{tariff.key}",
        back_callback="hwid_devices:list",
        user_id=callback.from_user.id,
    )
    await callback.message.edit_text(
        get_text("choose_payment_method_hwid_devices"), reply_markup=markup
    )
    await callback.answer()


@router.callback_query(F.data == "tariff_change:list")
async def tariff_change_list_callback(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    subscription_service: SubscriptionService,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    config = settings.tariffs_config
    active = await subscription_service.get_active_subscription_details(
        session, callback.from_user.id
    )
    if not config or not active or not callback.message:
        await callback.answer("Error", show_alert=True)
        return
    if len(config.enabled_tariffs) <= 1:
        await callback.answer(
            "Смена тарифа недоступна: сейчас включен только один тариф.", show_alert=True
        )
        return
    rows = []
    for tariff in config.enabled_tariffs:
        if tariff.key == active.get("tariff_key"):
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=tariff.name(current_lang),
                    callback_data=f"tariff_change:select:{tariff.key}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.gettext(current_lang, "back_to_main_menu_button"),
                callback_data="main_action:my_subscription",
            )
        ]
    )
    await callback.message.edit_text(
        "Выберите тариф", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tariff_change:select:"))
async def tariff_change_select_callback(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    subscription_service: SubscriptionService,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer("Error", show_alert=True)
        return
    tariff_key = callback.data.split(":", 2)[2]
    target = config.require(tariff_key)
    db_sub = await subscription_dal.get_active_subscription_by_user_id(
        session, callback.from_user.id
    )
    if not db_sub:
        await callback.answer("Error", show_alert=True)
        return
    options = await subscription_service.calculate_tariff_switch_options_with_hwid(
        session, db_sub, target
    )
    default_currency = default_currency_key_for_settings(settings)
    currency_code = default_payment_currency_code_for_settings(settings)
    rows = []
    if options["mode"] == "period_to_period":
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Без доплаты, дней станет {options['recalc_days']}",
                    callback_data=f"tariff_change:confirm_apply:{target.key}:recalc_days",
                )
            ]
        )
        if options.get("paid_diff_rub", 0) > 0:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"Доплатить {options['paid_diff_rub']} {currency_code}",
                        callback_data=f"tariff_change:confirm_pay:{target.key}:{options['paid_diff_rub']}",
                    )
                ]
            )
    elif options["mode"] == "period_to_traffic":
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Перейти без доплаты, получить {options['converted_gb']} GB",
                    callback_data=f"tariff_change:confirm_apply:{target.key}:convert_days_to_gb",
                )
            ]
        )
        for package in target.traffic_packages.for_currency(default_currency):
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"+ {package.gb:g} GB за {package.price:g} {currency_code}",
                        callback_data=f"tariff:package:{target.key}:{package.gb:g}",
                    )
                ]
            )
    else:
        for months in target.enabled_periods:
            price = target.period_price(months, default_currency)
            if price:
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=f"{months} мес. за {price:g} {currency_code}",
                            callback_data=f"tariff:period:{target.key}:{months}",
                        )
                    ]
                )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.gettext(current_lang, "back_to_main_menu_button"),
                callback_data="tariff_change:list",
            )
        ]
    )
    await callback.message.edit_text(
        f"{target.name(current_lang)}\n{target.description(current_lang)}".strip(),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tariff_change:confirm_apply:"))
async def tariff_change_confirm_apply_callback(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    subscription_service: SubscriptionService,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer("Error", show_alert=True)
        return
    _, _, tariff_key, mode = callback.data.split(":", 3)
    target = config.require(tariff_key)
    db_sub = await subscription_dal.get_active_subscription_by_user_id(
        session, callback.from_user.id
    )
    if not db_sub:
        await callback.answer("Error", show_alert=True)
        return
    options = await subscription_service.calculate_tariff_switch_options_with_hwid(
        session, db_sub, target
    )
    if mode == "recalc_days":
        action_text = f"после перехода останется {options.get('recalc_days', 0)} дн."
    elif mode == "convert_days_to_gb":
        action_text = f"будет начислено {options.get('converted_gb', 0)} GB трафика"
    else:
        action_text = "тариф будет изменен без доплаты"
    rows = [
        [
            InlineKeyboardButton(
                text="✅ Подтвердить", callback_data=f"tariff_change:apply:{target.key}:{mode}"
            )
        ],
        [
            InlineKeyboardButton(
                text=i18n.gettext(current_lang, "back_to_main_menu_button"),
                callback_data=f"tariff_change:select:{target.key}",
            )
        ],
    ]
    await callback.message.edit_text(
        f"Подтвердите смену тарифа\n\nНовый тариф: {target.name(current_lang)}\nИзменение: {action_text}",  # noqa: E501
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tariff_change:confirm_pay:"))
async def tariff_change_confirm_pay_callback(
    callback: types.CallbackQuery, i18n_data: dict, settings: Settings
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer("Error", show_alert=True)
        return
    _, _, tariff_key, amount_raw = callback.data.split(":", 3)
    target = config.require(tariff_key)
    currency_code = default_payment_currency_code_for_settings(settings)
    rows = [
        [
            InlineKeyboardButton(
                text="✅ Подтвердить и оплатить",
                callback_data=f"tariff_change:pay:{target.key}:{amount_raw}",
            )
        ],
        [
            InlineKeyboardButton(
                text=i18n.gettext(current_lang, "back_to_main_menu_button"),
                callback_data=f"tariff_change:select:{target.key}",
            )
        ],
    ]
    await callback.message.edit_text(
        f"Подтвердите смену тарифа\n\nНовый тариф: {target.name(current_lang)}\nБудет создана оплата на {amount_raw} {currency_code}.",  # noqa: E501
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tariff_change:apply:"))
async def tariff_change_apply_callback(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    subscription_service: SubscriptionService,
    session: AsyncSession,
):
    _, _, tariff_key, mode = callback.data.split(":", 3)
    result = await subscription_service.switch_tariff_without_payment(
        session, callback.from_user.id, tariff_key, mode
    )
    if result:
        await session.commit()
        await callback.answer("Готово", show_alert=True)
        await my_subscription_command_handler(
            callback,
            i18n_data,
            settings,
            subscription_service.panel_service,
            subscription_service,
            session,
            callback.bot,
        )
    else:
        await callback.answer("Error", show_alert=True)


@router.callback_query(F.data.startswith("tariff_change:pay:"))
async def tariff_change_pay_callback(
    callback: types.CallbackQuery, i18n_data: dict, settings: Settings, session: AsyncSession
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    _, _, tariff_key, amount_raw = callback.data.split(":", 3)
    amount = float(amount_raw)
    currency_code = default_payment_currency_code_for_settings(settings)
    markup = get_payment_method_keyboard(
        1,
        amount,
        None,
        currency_code,
        current_lang,
        i18n,
        settings,
        sale_mode=f"tariff_upgrade@{tariff_key}",
        back_callback=f"tariff_change:confirm_pay:{tariff_key}:{amount_raw}",
        user_id=callback.from_user.id,
    )
    await callback.message.edit_text("Выберите способ оплаты", reply_markup=markup)
    await callback.answer()


async def my_subscription_command_handler(
    event: Union[types.Message, types.CallbackQuery],
    i18n_data: dict,
    settings: Settings,
    panel_service: PanelApiService,
    subscription_service: SubscriptionService,
    session: AsyncSession,
    bot: Bot,
    back_callback: str = "main_action:back_to_main",
):
    target = event.message if isinstance(event, types.CallbackQuery) else event
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)

    if not i18n or not target:
        if isinstance(event, types.Message):
            await event.answer(get_text("error_occurred_try_again"))
        return

    if not panel_service or not subscription_service:
        await target.answer(get_text("error_service_unavailable"))
        return

    active = await subscription_service.get_active_subscription_details(session, event.from_user.id)

    if not active:
        text = get_text("subscription_not_active")

        buy_button = InlineKeyboardButton(
            text=get_text("menu_subscribe_inline"), callback_data="main_action:subscribe"
        )
        back_markup = get_back_to_main_menu_markup(
            current_lang,
            i18n,
            callback_data=back_callback,
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[[buy_button], *back_markup.inline_keyboard])

        if isinstance(event, types.CallbackQuery):
            try:
                await event.answer()
            except Exception:
                pass
            try:
                await event.message.edit_text(text, reply_markup=kb)
            except Exception:
                await event.message.answer(text, reply_markup=kb)
        else:
            await event.answer(text, reply_markup=kb)
        return

    end_date = active.get("end_date")
    days_left = (end_date.date() - datetime.now().date()).days if end_date else 0
    traffic_mode = bool(getattr(settings, "traffic_sale_mode", False))
    config_link_display = active.get("config_link")
    connect_button_url = active.get("connect_button_url")
    config_link_value = config_link_display or get_text("config_link_not_available")

    def _fmt_gb(val: Optional[float]) -> str:
        if val is None:
            return get_text("traffic_na")
        try:
            if isinstance(val, (int, float)):
                val_gb = float(val) / (2**30)
                return f"{val_gb:.2f} GB"
        except Exception:
            pass
        return str(val)

    def _format_traffic_period(strategy: Optional[str]) -> Optional[str]:
        if not strategy:
            return None
        strategy_upper = str(strategy).upper()
        key_map = {
            "MONTH": "traffic_period_month",
            "WEEK": "traffic_period_week",
            "DAY": "traffic_period_day",
            "NO_RESET": "traffic_period_no_reset",
        }
        label_key = key_map.get(strategy_upper)
        return get_text(label_key) if label_key else strategy_upper

    def _format_used_with_period(used_display: str, period_label: Optional[str]) -> str:
        if not period_label:
            return used_display
        return get_text(
            "traffic_used_with_period", traffic_used=used_display, traffic_period=period_label
        )

    period_label = _format_traffic_period(active.get("traffic_limit_strategy"))
    period_label = period_label or get_text("traffic_period_unknown")

    if traffic_mode:
        limit_display = _fmt_gb(active.get("traffic_limit_bytes"))
        used_display = _format_used_with_period(
            _fmt_gb(active.get("traffic_used_bytes")), period_label
        )
        remaining_display = get_text("traffic_na")
        try:
            limit_val = active.get("traffic_limit_bytes") or 0
            used_val = active.get("traffic_used_bytes") or 0
            remaining_val = max(0, float(limit_val) - float(used_val))
            remaining_display = _fmt_gb(remaining_val)
        except Exception:
            pass
        text = get_text(
            "my_traffic_details",
            status=active.get("status_from_panel", get_text("status_active")).capitalize(),
            end_date=end_date.strftime("%Y-%m-%d") if end_date else get_text("traffic_no_expiry"),
            traffic_limit=limit_display,
            traffic_used=used_display,
            traffic_left=remaining_display,
            traffic_period=period_label,
            config_link=config_link_value,
        )
    else:
        tariff_prefix = ""
        if _has_multiple_enabled_tariffs(settings) and active.get("tariff_name"):
            tariff_prefix = f"🎟 {active.get('tariff_name')}\n"
            if active.get("tariff_description"):
                tariff_prefix += f"{active.get('tariff_description')}\n"
        text = get_text(
            "my_subscription_details",
            end_date=end_date.strftime("%Y-%m-%d") if end_date else "N/A",
            days_left=max(0, days_left),
            status=active.get("status_from_panel", get_text("status_active")).capitalize(),
            config_link=config_link_value,
            traffic_limit=(
                f"{active['traffic_limit_bytes'] / 2**30:.2f} GB"
                if active.get("traffic_limit_bytes")
                else get_text("traffic_unlimited")
            ),
            traffic_used=(
                _format_used_with_period(
                    f"{active['traffic_used_bytes'] / 2**30:.2f} GB"
                    if active.get("traffic_used_bytes") is not None
                    else get_text("traffic_na"),
                    period_label,
                )
            ),
            traffic_period=period_label,
        )
        if tariff_prefix:
            text = tariff_prefix + "\n" + text

    if int(active.get("premium_limit_bytes") or 0) > 0:
        premium_limit = int(active.get("premium_limit_bytes") or 0)
        premium_used = int(active.get("premium_used_bytes") or 0)
        premium_left = max(0, premium_limit - premium_used)
        premium_balance = int(active.get("premium_topup_balance_bytes") or 0)
        premium_status = "ограничен" if active.get("premium_is_limited") else "активен"
        labels = active.get("premium_node_labels") or active.get("premium_squad_labels") or []
        if labels:
            visible = [html.escape(str(label)) for label in labels[:8]]
            label_block = "\n".join(f"• {label}" for label in visible)
            if len(labels) > len(visible):
                label_block += f"\n• ... еще {len(labels) - len(visible)}"
        else:
            label_block = "• premium-серверы тарифа"
        text += (
            "\n\n🚀 <b>Premium-серверы</b>\n"
            f"Статус: <b>{premium_status}</b>\n"
            f"Лимит: <b>{_format_premium_usage_limit(active)}</b>\n"
            f"Осталось: <b>{premium_left / 2**30:.2f} GB</b>\n"
            f"Докупленный остаток: <b>{premium_balance / 2**30:.2f} GB</b>\n"
            "Отдельный лимит действует на:\n"
            f"{label_block}\n\n"
            "Premium-докупка не сгорает: сначала расходуется месячный лимит premium-серверов, затем докупленный premium-трафик."  # noqa: E501
        )

    base_markup = get_back_to_main_menu_markup(
        current_lang,
        i18n,
        callback_data=back_callback,
    )
    kb = base_markup.inline_keyboard
    try:
        local_sub = await subscription_dal.get_active_subscription_by_user_id(
            session, event.from_user.id
        )
        install_links = await ensure_user_install_guide_links(
            session,
            settings,
            event.from_user.id,
            local_subscription=local_sub,
        )
        install_url = install_links.personal_url
        install_share_url = install_links.public_share_url
        if install_share_url:
            try:
                await session.commit()
                text = append_install_share_link_text(text, get_text, install_share_url)
            except Exception:
                await session.rollback()
                logging.exception(
                    "Failed to persist install guide share token for user %s.",
                    event.from_user.id,
                )
                install_share_url = None

        # Build rows to prepend above the base "back" markup
        prepend_rows = []

        # 1) Connect button: prefer the actual subscription URL; fall back to mini-app
        cfg_link_val = connect_button_url or config_link_display
        if install_url:
            prepend_rows.append(
                [
                    InlineKeyboardButton(
                        text=get_text("connect_button"),
                        web_app=WebAppInfo(url=install_url),
                    )
                ]
            )
            if install_share_url:
                prepend_rows.append(
                    [
                        InlineKeyboardButton(
                            text=get_text("install_guide_share_button"),
                            url=install_share_url,
                        )
                    ]
                )
        elif cfg_link_val:
            prepend_rows.append(
                [
                    InlineKeyboardButton(
                        text=get_text("connect_button"),
                        url=cfg_link_val,
                    )
                ]
            )
        elif settings.SUBSCRIPTION_MINI_APP_URL:
            prepend_rows.append(
                [
                    InlineKeyboardButton(
                        text=get_text("connect_button"),
                        web_app=WebAppInfo(url=settings.SUBSCRIPTION_MINI_APP_URL),
                    )
                ]
            )

        if settings.MY_DEVICES_SECTION_ENABLED:
            max_devices_value = active.get("max_devices")
            max_devices_display = get_text("devices_unlimited_label")
            if max_devices_value not in (None, 0):
                try:
                    max_devices_int = int(max_devices_value)
                    if max_devices_int >= 0:
                        max_devices_display = str(max_devices_int)
                except (TypeError, ValueError):
                    max_devices_display = str(max_devices_value)
            current_devices_display = "?"
            user_uuid = active.get("user_id")
            devices_response = None
            if user_uuid:
                try:
                    devices_response = await panel_service.get_user_devices(user_uuid)
                except Exception:
                    logging.exception("Failed to load devices for user %s", user_uuid)
            if devices_response:
                devices_count: Optional[int] = None
                if isinstance(devices_response, dict):
                    devices_list = devices_response.get("devices")
                    if isinstance(devices_list, list):
                        devices_count = len(devices_list)
                    elif isinstance(devices_list, int):
                        devices_count = devices_list
                    else:
                        try:
                            devices_count = len(devices_list)  # type: ignore[arg-type]
                        except Exception:
                            devices_count = None
                    if devices_count is None:
                        total_value = devices_response.get("total")
                        if isinstance(total_value, int):
                            devices_count = total_value
                elif isinstance(devices_response, list):
                    devices_count = len(devices_response)
                if devices_count is not None:
                    current_devices_display = str(devices_count)
            devices_button_text = get_text(
                "devices_button",
                current_devices=current_devices_display,
                max_devices=max_devices_display,
            )
            prepend_rows.append(
                [
                    InlineKeyboardButton(
                        text=devices_button_text,
                        callback_data="main_action:my_devices",
                    )
                ]
            )
            # Skip the buy-devices button entirely when the user has unlimited
            # devices (max_devices == 0). Otherwise the button leads to an
            # alert "hwid_devices_unlimited_no_topup" — confusing dead end.
            devices_topup_allowed = (
                settings.tariffs_config
                and local_sub
                and local_sub.tariff_key
                and max_devices_value not in (None, 0)
            )
            if devices_topup_allowed:
                try:
                    tariff_for_devices = settings.tariffs_config.require(local_sub.tariff_key)
                    if (
                        tariff_for_devices.billing_model == "period"
                        and tariff_for_devices.hwid_device_packages
                        and tariff_for_devices.hwid_device_packages.for_currency(
                            default_currency_key_for_settings(settings)
                        )
                    ):
                        prepend_rows.append(
                            [
                                InlineKeyboardButton(
                                    text=get_text("buy_hwid_devices_menu_button"),
                                    callback_data="hwid_devices:list",
                                )
                            ]
                        )
                except Exception:
                    pass

        # 2) Auto-renew toggle (YooKassa only)
        if (
            not traffic_mode
            and local_sub
            and local_sub.provider == "yookassa"
            and settings.yookassa_autopayments_active
        ):
            toggle_text = (
                get_text("autorenew_disable_button")
                if local_sub.auto_renew_enabled
                else get_text("autorenew_enable_button")
            )
            prepend_rows.append(
                [
                    InlineKeyboardButton(
                        text=toggle_text,
                        callback_data=f"toggle_autorenew:{local_sub.subscription_id}:{1 if not local_sub.auto_renew_enabled else 0}",  # noqa: E501
                    )
                ]
            )

        # 3) Payment methods management (when autopayments enabled)
        if not traffic_mode and settings.yookassa_autopayments_active:
            prepend_rows.append(
                [
                    InlineKeyboardButton(
                        text=get_text("payment_methods_manage_button"), callback_data="pm:manage"
                    )
                ]
            )

        if settings.tariffs_config and local_sub and local_sub.tariff_key:
            tariff_actions = []
            if _has_multiple_enabled_tariffs(settings):
                tariff_actions.append(
                    InlineKeyboardButton(text="Сменить тариф", callback_data="tariff_change:list")
                )
            try:
                tariff = settings.tariffs_config.require(local_sub.tariff_key)
                topup_packages = settings.tariffs_config.topup_packages_for(tariff)
                has_topup_packages = bool(
                    (topup_packages and topup_packages.has_any())
                    or (tariff.premium_topup_packages and tariff.premium_topup_packages.has_any())
                )
            except Exception:
                has_topup_packages = False
            if has_topup_packages:
                tariff_actions.append(
                    InlineKeyboardButton(text="Докупить трафик", callback_data="tariff_topup:list")
                )
            if tariff_actions:
                prepend_rows.append(tariff_actions)

        if prepend_rows:
            kb = prepend_rows + kb
    except Exception:
        pass
    markup = InlineKeyboardMarkup(inline_keyboard=kb)

    if isinstance(event, types.CallbackQuery):
        try:
            await event.answer()
        except Exception:
            pass
        try:
            await event.message.edit_text(
                text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True
            )
        except Exception:
            await bot.send_message(
                chat_id=target.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
    else:
        await target.answer(
            text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True
        )


@router.callback_query(F.data == "main_action:my_devices")
async def my_devices_command_handler(
    event: Union[types.Message, types.CallbackQuery],
    i18n_data: dict,
    settings: Settings,
    panel_service: PanelApiService,
    subscription_service: SubscriptionService,
    session: AsyncSession,
    bot: Bot,
):
    target = event.message if isinstance(event, types.CallbackQuery) else event
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)

    if not i18n or not target:
        if isinstance(event, types.Message):
            await event.answer(get_text("error_occurred_try_again"))
        return

    if not settings.MY_DEVICES_SECTION_ENABLED:
        if isinstance(event, types.CallbackQuery):
            try:
                await event.answer(get_text("my_devices_feature_disabled"), show_alert=True)
            except Exception:
                pass
        else:
            await target.answer(get_text("my_devices_feature_disabled"))
        return

    # TODO: context?
    active = await subscription_service.get_active_subscription_details(session, event.from_user.id)
    if not active or not active.get("user_id"):
        message = get_text("subscription_not_active")
        if isinstance(event, types.CallbackQuery):
            try:
                await event.answer(message, show_alert=True)
            except Exception:
                pass
        else:
            await target.answer(message)
        return

    devices = await panel_service.get_user_devices(active.get("user_id")) if active else None
    if not devices:
        if isinstance(event, types.CallbackQuery):
            try:
                await event.answer(get_text("no_devices_found"), show_alert=True)
            except Exception:
                pass
        else:
            await target.answer(get_text("no_devices_found"))
        return

    devices_list_raw = []
    if isinstance(devices, dict):
        devices_list_raw = devices.get("devices") or []
    elif isinstance(devices, list):
        devices_list_raw = devices

    max_devices_value = active.get("max_devices")
    max_devices_display = get_text("devices_unlimited_label")
    if max_devices_value not in (None, 0):
        try:
            max_devices_int = int(max_devices_value)
            if max_devices_int >= 0:
                max_devices_display = str(max_devices_int)
        except (TypeError, ValueError):
            max_devices_display = str(max_devices_value)

    if not devices_list_raw:
        text = get_text("no_devices_details_found_message", max_devices=max_devices_display)
    else:
        devices_list = []
        current_devices = len(devices_list_raw)
        for index, device in enumerate(devices_list_raw, start=1):
            device_model = device.get("deviceModel") or None
            platform = device.get("platform") or None
            user_agent = device.get("userAgent") or None
            os_version = device.get("osVersion") or None
            created_at = device.get("createdAt")
            hwid = device.get("hwid")
            try:
                created_at_str = (
                    datetime.fromisoformat(created_at).strftime("%d.%m.%Y %H:%M")
                    if created_at
                    else "-"
                )
            except Exception:
                created_at_str = str(created_at)

            device_details = get_text(
                "device_details",
                index=index,
                device_model=device_model,
                platform=platform,
                os_version=os_version,
                created_at_str=created_at_str,
                user_agent=user_agent,
                hwid=hwid,
            )
            devices_list.append(device_details)

        text = get_text(
            "my_devices_details",
            devices="\n\n".join(devices_list),
            current_devices=current_devices,
            max_devices=max_devices_display,
        )

    base_markup = get_back_to_main_menu_markup(
        current_lang, i18n, callback_data="main_action:my_subscription"
    )
    kb = base_markup.inline_keyboard

    devices_kb = []
    if settings.tariffs_config and active.get("tariff_key") and max_devices_value != 0:
        try:
            tariff_for_devices = settings.tariffs_config.require(active["tariff_key"])
            if (
                tariff_for_devices.billing_model == "period"
                and tariff_for_devices.hwid_device_packages
                and tariff_for_devices.hwid_device_packages.for_currency(
                    default_currency_key_for_settings(settings)
                )
            ):
                devices_kb.append(
                    [
                        InlineKeyboardButton(
                            text=get_text("buy_hwid_devices_menu_button"),
                            callback_data="hwid_devices:list",
                        )
                    ]
                )
        except Exception:
            pass
    for index, device in enumerate(devices_list_raw, start=1):
        hwid = device.get("hwid")
        if not hwid:
            continue
        device_button_text = get_text(
            "disconnect_device_button", hwid=_shorten_hwid_for_display(hwid), index=index
        )
        hwid_token = _hwid_callback_token(hwid)

        devices_kb.append(
            [
                InlineKeyboardButton(
                    text=device_button_text, callback_data=f"disconnect_device:{hwid_token}"
                )
            ]
        )
    kb = devices_kb + kb
    markup = InlineKeyboardMarkup(inline_keyboard=kb)

    if isinstance(event, types.CallbackQuery):
        try:
            await event.answer()
        except Exception:
            pass
        try:
            await event.message.edit_text(text, reply_markup=markup)
        except Exception:
            await event.message.answer(text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("disconnect_device:"))
async def disconnect_device_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
    bot: Bot,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    if not settings.MY_DEVICES_SECTION_ENABLED:
        try:
            await callback.answer(get_text("my_devices_feature_disabled"), show_alert=True)
        except Exception:
            pass
        return

    try:
        _, hwid_token = callback.data.split(":", 1)
    except Exception:
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    active = await subscription_service.get_active_subscription_details(
        session, callback.from_user.id
    )
    if not active or not active.get("user_id"):
        await callback.answer(get_text("subscription_not_active"), show_alert=True)
        return

    devices = await panel_service.get_user_devices(active.get("user_id"))
    if not devices:
        await callback.answer(get_text("no_devices_found"), show_alert=True)
        return

    devices_list_raw = []
    if isinstance(devices, dict):
        devices_list_raw = devices.get("devices") or []
    elif isinstance(devices, list):
        devices_list_raw = devices

    hwid = None
    for device in devices_list_raw:
        hwid_candidate = device.get("hwid")
        if hwid_candidate and _hwid_callback_token(hwid_candidate) == hwid_token:
            hwid = hwid_candidate
            break

    if not hwid:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return

    success = await panel_service.disconnect_device(active.get("user_id"), hwid)
    if not success:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    await session.commit()
    try:
        await callback.answer(get_text("device_disconnected"))
    except Exception:
        pass
    await my_devices_command_handler(
        callback, i18n_data, settings, panel_service, subscription_service, session, bot
    )


@router.callback_query(F.data.startswith("toggle_autorenew:"))
async def toggle_autorenew_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
    bot: Bot,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    try:
        _, payload = callback.data.split(":", 1)
        sub_id_str, enable_str = payload.split(":")
        sub_id = int(sub_id_str)
        enable = bool(int(enable_str))
    except Exception:
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    sub = await session.get(Subscription, sub_id)
    if not sub or sub.user_id != callback.from_user.id:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    if sub.provider != "yookassa":
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    if enable:
        has_saved_card = await user_billing_dal.user_has_saved_payment_method(
            session, callback.from_user.id
        )
        if not has_saved_card:
            try:
                await callback.answer(get_text("autorenew_enable_requires_card"), show_alert=True)
            except Exception:
                pass
            return

    # Show confirmation popup and inline buttons
    confirm_text = (
        get_text("autorenew_confirm_enable") if enable else get_text("autorenew_confirm_disable")
    )
    kb = get_autorenew_confirm_keyboard(enable, sub.subscription_id, current_lang, i18n)
    try:
        await callback.message.edit_text(confirm_text, reply_markup=kb)
    except Exception:
        try:
            await callback.message.answer(confirm_text, reply_markup=kb)
        except Exception:
            pass
    try:
        await callback.answer()
    except Exception:
        pass
    return


@router.callback_query(F.data.startswith("autorenew:confirm:"))
async def confirm_autorenew_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
    bot: Bot,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    try:
        _, _, sub_id_str, enable_str = callback.data.split(":", 3)
        sub_id = int(sub_id_str)
        enable = bool(int(enable_str))
    except Exception:
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    sub = await session.get(Subscription, sub_id)
    if not sub or sub.user_id != callback.from_user.id:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    if sub.provider != "yookassa":
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    if enable:
        has_saved_card = await user_billing_dal.user_has_saved_payment_method(
            session, callback.from_user.id
        )
        if not has_saved_card:
            try:
                await callback.answer(get_text("autorenew_enable_requires_card"), show_alert=True)
            except Exception:
                pass
            try:
                await my_subscription_command_handler(
                    callback, i18n_data, settings, panel_service, subscription_service, session, bot
                )
            except Exception:
                pass
            return

    await subscription_dal.update_subscription(
        session, sub.subscription_id, {"auto_renew_enabled": enable}
    )
    await session.commit()
    try:
        await callback.answer(get_text("subscription_autorenew_updated"))
    except Exception:
        pass
    await my_subscription_command_handler(
        callback, i18n_data, settings, panel_service, subscription_service, session, bot
    )


@router.callback_query(F.data == "autorenew:cancel")
async def autorenew_cancel_from_webhook_button(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
    bot: Bot,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    # Disable auto-renew on the active subscription
    from db.dal import subscription_dal

    sub = await subscription_dal.get_active_subscription_by_user_id(session, callback.from_user.id)
    if not sub:
        try:
            await callback.answer(get_text("subscription_not_active"), show_alert=True)
        except Exception:
            pass
        return
    if sub.provider != "yookassa":
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return
    await subscription_dal.update_subscription(
        session, sub.subscription_id, {"auto_renew_enabled": False}
    )
    await session.commit()
    try:
        await callback.answer(get_text("subscription_autorenew_updated"))
    except Exception:
        pass
    await my_subscription_command_handler(
        callback, i18n_data, settings, panel_service, subscription_service, session, bot
    )


@router.message(Command("connect"))
async def connect_command_handler(
    message: types.Message,
    i18n_data: dict,
    settings: Settings,
    panel_service: PanelApiService,
    subscription_service: SubscriptionService,
    session: AsyncSession,
    bot: Bot,
):
    logging.info(f"User {message.from_user.id} used /connect command.")
    await my_subscription_command_handler(
        message, i18n_data, settings, panel_service, subscription_service, session, bot
    )
