from aiogram import F, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import (
    get_hwid_device_packages_keyboard,
    get_payment_method_keyboard,
)
from bot.middlewares.i18n import JsonI18n
from bot.services.subscription_service import SubscriptionService
from bot.utils.callback_answer import (
    callback_bot,
    callback_data,
    callback_message,
)
from config.settings import Settings
from config.tariffs_config import (
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
)
from db.dal import subscription_dal

from .core_common import (
    _format_premium_usage_limit,
    router,
)
from .core_status import my_subscription_command_handler


async def tariff_topup_list_callback(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    subscription_service: SubscriptionService,
    session: AsyncSession,
) -> None:
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
    await callback_message(callback).edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("tariff:premium_package:"))
async def select_tariff_premium_package_callback(
    callback: types.CallbackQuery, i18n_data: dict, settings: Settings, session: AsyncSession
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        return
    _, _, tariff_key, gb_raw = callback_data(callback).split(":", 3)
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
    await callback_message(callback).edit_text(
        get_text("choose_payment_method_traffic"), reply_markup=markup
    )
    await callback.answer()


@router.callback_query(F.data == "hwid_devices:list")
async def hwid_devices_list_callback(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    subscription_service: SubscriptionService,
    session: AsyncSession,
) -> None:
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
    await callback_message(callback).edit_text(
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
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        return
    _, action, tariff_key, count_raw = callback_data(callback).split(":", 3)
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
    await callback_message(callback).edit_text(
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
) -> None:
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
    await callback_message(callback).edit_text(
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
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer("Error", show_alert=True)
        return
    tariff_key = callback_data(callback).split(":", 2)[2]
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
    await callback_message(callback).edit_text(
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
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer("Error", show_alert=True)
        return
    _, _, tariff_key, mode = callback_data(callback).split(":", 3)
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
    await callback_message(callback).edit_text(
        f"Подтвердите смену тарифа\n\nНовый тариф: {target.name(current_lang)}\nИзменение: {action_text}",  # noqa: E501
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tariff_change:confirm_pay:"))
async def tariff_change_confirm_pay_callback(
    callback: types.CallbackQuery, i18n_data: dict, settings: Settings
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer("Error", show_alert=True)
        return
    _, _, tariff_key, amount_raw = callback_data(callback).split(":", 3)
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
    await callback_message(callback).edit_text(
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
) -> None:
    _, _, tariff_key, mode = callback_data(callback).split(":", 3)
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
            callback_bot(callback),
        )
    else:
        await callback.answer("Error", show_alert=True)


@router.callback_query(F.data.startswith("tariff_change:pay:"))
async def tariff_change_pay_callback(
    callback: types.CallbackQuery, i18n_data: dict, settings: Settings, session: AsyncSession
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    _, _, tariff_key, amount_raw = callback_data(callback).split(":", 3)
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
    await callback_message(callback).edit_text("Выберите способ оплаты", reply_markup=markup)
    await callback.answer()
