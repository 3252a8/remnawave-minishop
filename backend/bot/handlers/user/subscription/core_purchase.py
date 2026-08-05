import contextlib

from aiogram import F, types
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import (
    callback_context_from_back_callback,
    callback_suffix_for_context,
    get_back_to_main_menu_markup,
    get_payment_method_keyboard,
    get_subscription_options_keyboard,
    get_tariff_catalog_keyboard,
    sale_mode_with_callback_context,
    tariff_purchase_back_callback,
)
from bot.middlewares.i18n import JsonI18n
from bot.services.behavior_events import emit_plans_viewed
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.utils.callback_answer import (
    callback_data,
    callback_message,
)
from config.settings import Settings
from config.tariffs_config import (
    Tariff,
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
)

from .core_common import (
    _tariff_purchase_markup,
    _tariff_purchase_text,
    _with_subscription_purchase_description,
    router,
)


def _tariff_visible_plan_count(tariff: Tariff, settings: Settings) -> int:
    if getattr(tariff, "billing_model", "") == "period":
        default_currency = default_currency_key_for_settings(settings)
        count = 0
        for months in getattr(tariff, "enabled_periods", []) or []:
            if tariff.period_price(months, default_currency) or tariff.period_price(
                months, "stars"
            ):
                count += 1
        return count or len(getattr(tariff, "enabled_periods", []) or [])
    packages = getattr(tariff, "traffic_packages", None)
    if not packages:
        return 0
    default_currency = default_currency_key_for_settings(settings)
    gb_values = {float(package.gb) for package in packages.for_currency(default_currency)}
    gb_values.update(float(package.gb) for package in packages.for_currency("stars"))
    return len(gb_values)


async def _emit_subscription_options_viewed(
    event: types.Message | types.CallbackQuery,
    settings: Settings,
    *,
    plans_count: int,
    tariff_key: str | None = None,
) -> None:
    from_user = getattr(event, "from_user", None)
    user_id = getattr(from_user, "id", None)
    if user_id is None:
        return
    await emit_plans_viewed(
        settings,
        user_id=int(user_id),
        source="bot",
        plans_count=plans_count,
        tariff_key=tariff_key,
    )


async def display_subscription_options(
    event: types.Message | types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
    back_callback: str = "main_action:back_to_main",
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")

    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    if not i18n:
        err_msg = "Language service error."
        if isinstance(event, types.CallbackQuery):
            with contextlib.suppress(Exception):
                await event.answer(err_msg, show_alert=True)
        elif isinstance(event, types.Message):
            await event.answer(err_msg)
        return

    currency_symbol_val = settings.DEFAULT_CURRENCY_SYMBOL
    tariffs_config = settings.tariffs_config
    if tariffs_config:
        enabled_tariffs = list(tariffs_config.enabled_tariffs)
        callback_context = callback_context_from_back_callback(back_callback)
        if len(enabled_tariffs) == 1:
            tariff = enabled_tariffs[0]
            plans_count = _tariff_visible_plan_count(tariff, settings)
            viewed_tariff_key = tariff.key
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
            plans_count = len(enabled_tariffs)
            viewed_tariff_key = None
        await _emit_subscription_options_viewed(
            event,
            settings,
            plans_count=plans_count,
            tariff_key=viewed_tariff_key,
        )
        if isinstance(event, types.CallbackQuery):
            target_message_obj = callback_message(event)
            try:
                await target_message_obj.edit_text(text_content, reply_markup=reply_markup)
            except Exception:
                await target_message_obj.answer(text_content, reply_markup=reply_markup)
            await event.answer()
        else:
            await event.answer(text_content, reply_markup=reply_markup)
        return

    traffic_packages = settings.traffic_packages or {}
    stars_traffic_packages = settings.stars_traffic_packages or {}
    traffic_mode = bool(settings.traffic_sale_mode or stars_traffic_packages)

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

    await _emit_subscription_options_viewed(event, settings, plans_count=len(options))

    if isinstance(event, types.CallbackQuery):
        target_message_obj = callback_message(event)
        try:
            await target_message_obj.edit_text(text_content, reply_markup=reply_markup)
        except Exception:
            await target_message_obj.answer(text_content, reply_markup=reply_markup)
        with contextlib.suppress(Exception):
            await event.answer()
    else:
        await event.answer(text_content, reply_markup=reply_markup)


@router.callback_query(F.data == "main_action:subscribe")
async def reshow_subscription_options_callback(
    callback: types.CallbackQuery, i18n_data: dict, settings: Settings, session: AsyncSession
) -> None:
    await display_subscription_options(callback, i18n_data, settings, session)


@router.callback_query(F.data.startswith("tariff:select:"))
async def select_tariff_callback(
    callback: types.CallbackQuery, i18n_data: dict, settings: Settings, session: AsyncSession
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        return
    parts = callback_data(callback).split(":")
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
    await callback_message(callback).edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("tariff:period:"))
async def select_tariff_period_callback(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
    subscription_service: SubscriptionService,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        return
    parts = callback_data(callback).split(":")
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
    await callback_message(callback).edit_text(
        get_text("choose_payment_method"), reply_markup=markup
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tariff:package:"))
async def select_tariff_package_callback(
    callback: types.CallbackQuery, i18n_data: dict, settings: Settings, session: AsyncSession
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        return
    parts = callback_data(callback).split(":")
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
    await callback_message(callback).edit_text(
        get_text("choose_payment_method_traffic"), reply_markup=markup
    )
    await callback.answer()
