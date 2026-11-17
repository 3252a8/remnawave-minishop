from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import (
    get_hwid_device_packages_keyboard,
    get_payment_method_keyboard,
)
from bot.keyboards.inline.user_keyboards_context import (
    HWID_SUBSCRIPTION_ORIGIN,
    TARIFF_SWITCH_ORIGIN,
    TELEGRAM_SUBSCRIPTION_CHECKOUT,
    callback_suffix_for_context,
    hwid_origin_suffix,
    sale_mode_with_callback_context,
    sale_mode_with_token,
    split_callback_context,
    subscription_menu_back_callback,
    subscription_status_callback,
)
from bot.middlewares.confirmation import edit_confirmation
from bot.middlewares.i18n import JsonI18n
from bot.services.device_topup_availability import (
    device_topup_reason_locale_key,
    resolve_device_topup_availability,
)
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.services.telegram_account import require_telegram_account_id
from bot.services.traffic_topup_availability import (
    TRAFFIC_TOPUP_UNLOCK_PERCENT,
    resolve_traffic_topup_availability,
)
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
    _assigned_tariff_key,
    _format_premium_usage_limit,
    router,
)
from .core_status import my_subscription_command_handler

_SWITCH_MODES = {"d": "recalc_days", "g": "convert_days_to_gb"}


@router.callback_query(F.data.in_({"tariff_topup:list", "tariff_topup:list:bot"}))
async def tariff_topup_list_callback(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    subscription_service: SubscriptionService,
    session: AsyncSession,
) -> None:
    account_user_id = await require_telegram_account_id(session, callback.from_user.id)
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = (
        (lambda key, **kw: i18n.gettext(current_lang, key, **kw))
        if i18n
        else (lambda key, **kw: "Error")
    )
    _, context = split_callback_context(callback_data(callback))
    suffix = callback_suffix_for_context(context)
    config = settings.tariffs_config
    active = await subscription_service.get_active_subscription_details(session, account_user_id)
    if not config or not active or not active.get("tariff_key") or not callback.message:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    availability = resolve_traffic_topup_availability(settings, active)
    if availability.has_offers and not availability.unlocked:
        # The user clicked a stale menu rendered before the offer got locked
        # (or before the unlock gate existed): explain and refresh the menu.
        limit_bytes = int(active.get("traffic_limit_bytes") or 0)
        used_bytes = int(active.get("traffic_used_bytes") or 0)
        traffic_left = max(0, limit_bytes - used_bytes)
        await callback.answer(
            get_text(
                "traffic_topup_not_needed_alert",
                traffic_left=f"{traffic_left / 2**30:.2f} GB",
                unlock_percent=TRAFFIC_TOPUP_UNLOCK_PERCENT,
            ),
            show_alert=True,
        )
        await my_subscription_command_handler(
            callback,
            i18n_data,
            settings,
            subscription_service.panel_service,
            subscription_service,
            session,
            callback_bot(callback),
            back_callback=subscription_menu_back_callback(context),
        )
        return
    tariff = config.require_configured(active["tariff_key"])
    packages = config.topup_packages_for(tariff)
    default_currency = default_currency_key_for_settings(settings)
    currency = default_payment_currency_code_for_settings(settings)
    currency_packages = (
        packages.for_currency(default_currency)
        if packages and availability.regular_unlocked
        else []
    )
    premium_packages = (
        tariff.premium_topup_packages.for_currency(default_currency)
        if tariff.premium_topup_packages and availability.premium_unlocked
        else []
    )
    if not currency_packages and not premium_packages:
        await callback.answer(get_text("no_subscription_options_available"), show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    for package in currency_packages:
        builder.row(
            InlineKeyboardButton(
                text=get_text(
                    "traffic_topup_regular_package_button",
                    gb=f"{package.gb:g}",
                    price=f"{package.price:g}",
                    currency=currency,
                ),
                callback_data=f"tariff:package:{tariff.key}:{package.gb:g}{suffix}",
            )
        )
    for package in premium_packages:
        builder.row(
            InlineKeyboardButton(
                text=get_text(
                    "traffic_topup_premium_package_button",
                    gb=f"{package.gb:g}",
                    price=f"{package.price:g}",
                    currency=currency,
                ),
                callback_data=f"tariff:premium_package:{tariff.key}:{package.gb:g}{suffix}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=get_text("back_to_main_menu_button"),
            callback_data=subscription_status_callback(context),
        )
    )

    premium_lines = []
    carryover_lines = []
    if currency_packages or premium_packages:
        carryover_lines.append(get_text("traffic_topup_carryover_note"))
    if int(active.get("premium_limit_bytes") or 0) > 0:
        premium_left = max(
            0,
            int(active.get("premium_limit_bytes") or 0)
            - int(active.get("premium_used_bytes") or 0),
        )
        labels = active.get("premium_node_labels") or active.get("premium_squad_labels") or []
        if labels:
            visible = [str(label) for label in labels[:8]]
            premium_lines.append(get_text("premium_limit_scope"))
            premium_lines.extend(f"• {label}" for label in visible)
            if len(labels) > len(visible):
                premium_lines.append(
                    get_text("premium_servers_more", count=len(labels) - len(visible))
                )
        premium_lines.append(
            get_text(
                "premium_topup_usage",
                usage=_format_premium_usage_limit(active, get_text),
                remaining=f"{premium_left / 2**30:.2f} GB",
            )
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
    account_user_id = await require_telegram_account_id(session, callback.from_user.id)
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        return
    data, context = split_callback_context(callback_data(callback))
    _, _, tariff_key, gb_raw = data.split(":", 3)
    try:
        assigned_tariff_key = await _assigned_tariff_key(session, account_user_id)
        tariff = config.require_for_user(tariff_key, assigned_tariff_key)
        gb = float(gb_raw)
    except (KeyError, ValueError):
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
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
        sale_mode=sale_mode_with_token(
            sale_mode_with_callback_context(f"premium_topup@{tariff.key}", context),
            TELEGRAM_SUBSCRIPTION_CHECKOUT,
        ),
        user_id=account_user_id,
    )
    await callback_message(callback).edit_text(
        get_text("choose_payment_method_traffic"), reply_markup=markup
    )
    await callback.answer()


@router.callback_query(
    F.data.in_(
        {
            "hwid_devices:list",
            "hwid_devices:list:bot",
            "hwid_devices:list:s",
            "hwid_devices:list:s:bot",
        }
    )
)
async def hwid_devices_list_callback(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    subscription_service: SubscriptionService,
    session: AsyncSession,
) -> None:
    account_user_id = await require_telegram_account_id(session, callback.from_user.id)
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    active = await subscription_service.get_active_subscription_details(session, account_user_id)
    if not callback.message:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    availability = resolve_device_topup_availability(
        settings,
        subscription_active=active is not None,
        tariff_key=active.get("tariff_key") if active else None,
        max_devices=active.get("max_devices") if active else None,
    )
    tariff = availability.tariff
    if not availability.allowed or tariff is None:
        await callback.answer(
            get_text(device_topup_reason_locale_key(availability.reason)),
            show_alert=True,
        )
        return
    packages = (
        tariff.hwid_device_packages.for_currency(availability.default_currency)
        if tariff.hwid_device_packages
        else []
    )
    stars_packages = (
        tariff.hwid_device_packages.for_currency("stars") if tariff.hwid_device_packages else []
    )
    data, context = split_callback_context(callback_data(callback))
    from_subscription = data.endswith(f":{HWID_SUBSCRIPTION_ORIGIN}")
    markup = get_hwid_device_packages_keyboard(
        tariff,
        packages,
        current_lang,
        i18n,
        settings,
        back_callback=(
            subscription_status_callback(context)
            if from_subscription
            else f"main_action:my_devices{callback_suffix_for_context(context)}"
        ),
        renewal=False,
        stars_packages=stars_packages,
        origin_suffix=hwid_origin_suffix(context, from_subscription=from_subscription),
    )
    await callback_message(callback).edit_text(
        get_text(
            "select_hwid_device_package",
            date=(active or {}).get("extra_hwid_devices_valid_until_text") or "",
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
    account_user_id = await require_telegram_account_id(session, callback.from_user.id)
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    if not callback.message:
        await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        return
    try:
        data, context = split_callback_context(callback_data(callback))
        base = data.removesuffix(f":{HWID_SUBSCRIPTION_ORIGIN}")
        _, action, tariff_key, count_raw = base.split(":", 3)
        count = int(count_raw)
    except (TypeError, ValueError):
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    if action not in {"package", "renewal_package"}:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    active = await subscription_service.get_active_subscription_details(
        session,
        account_user_id,
    )
    availability = resolve_device_topup_availability(
        settings,
        subscription_active=active is not None,
        tariff_key=active.get("tariff_key") if active else None,
        max_devices=active.get("max_devices") if active else None,
        expected_tariff_key=tariff_key,
    )
    tariff = availability.tariff
    if not availability.allowed or tariff is None or count not in availability.package_counts:
        await callback.answer(
            get_text(device_topup_reason_locale_key(availability.reason)),
            show_alert=True,
        )
        return
    sale_mode_base = "hwid_devices_renewal" if action == "renewal_package" else "hwid_devices"
    renewal = action == "renewal_package"
    default_currency = availability.default_currency
    currency_code = default_payment_currency_code_for_settings(settings)
    currency_quote = (
        await subscription_service.quote_hwid_device_topup(
            session,
            user_id=account_user_id,
            device_count=count,
            tariff_key=tariff.key,
            renewal=renewal,
            currency=default_currency,
        )
        if count in availability.default_currency_counts
        else None
    )
    stars_quote = (
        await subscription_service.quote_hwid_device_topup(
            session,
            user_id=account_user_id,
            device_count=count,
            tariff_key=tariff.key,
            renewal=renewal,
            currency="stars",
        )
        if count in availability.stars_counts
        else None
    )
    if not currency_quote and not stars_quote:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    sale_mode = sale_mode_with_callback_context(f"{sale_mode_base}@{tariff.key}", context)
    sale_mode = sale_mode_with_token(
        sale_mode, HWID_SUBSCRIPTION_ORIGIN if base != data else TELEGRAM_SUBSCRIPTION_CHECKOUT
    )
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
        sale_mode=sale_mode,
        user_id=account_user_id,
    )
    await callback_message(callback).edit_text(
        get_text("choose_payment_method_hwid_devices"), reply_markup=markup
    )
    await callback.answer()


@router.callback_query(F.data.in_({"tariff_change:list", "tariff_change:list:bot"}))
async def tariff_change_list_callback(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    subscription_service: SubscriptionService,
    session: AsyncSession,
) -> None:
    account_user_id = await require_telegram_account_id(session, callback.from_user.id)
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    config = settings.tariffs_config
    active = await subscription_service.get_active_subscription_details(session, account_user_id)
    if not config or not active or not callback.message:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    current_tariff = config.get(str(active.get("tariff_key") or ""))
    targets = [
        tariff
        for tariff in config.enabled_tariffs
        if current_tariff is None or tariff.key != current_tariff.key
    ]
    if not targets:
        await callback.answer(get_text("wa_no_tariff_change_options"), show_alert=True)
        return
    _, context = split_callback_context(callback_data(callback))
    suffix = callback_suffix_for_context(context)
    rows = [
        [
            InlineKeyboardButton(
                text=tariff.name(current_lang),
                callback_data=f"tariff_change:select:{tariff.key}{suffix}",
            )
        ]
        for tariff in targets
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.gettext(current_lang, "back_to_main_menu_button"),
                callback_data=subscription_status_callback(context),
            )
        ]
    )
    await callback_message(callback).edit_text(
        get_text("wa_tariffs_choose"), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
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
    account_user_id = await require_telegram_account_id(session, callback.from_user.id)
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    data, context = split_callback_context(callback_data(callback))
    suffix = callback_suffix_for_context(context)
    tariff_key = data.split(":", 2)[2]
    target = config.require(tariff_key)
    db_sub = await subscription_dal.get_active_subscription_by_user_id(session, account_user_id)
    if not db_sub:
        await callback.answer(get_text("error_try_again"), show_alert=True)
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
                    text=get_text("wa_tariff_change_recalc_days", days=options["recalc_days"]),
                    callback_data=f"tariff_change:confirm_apply:{target.key}:d{suffix}",
                )
            ]
        )
        if options.get("paid_diff_rub", 0) > 0:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=get_text(
                            "wa_tariff_change_pay_diff",
                            price=f"{options['paid_diff_rub']} {currency_code}",
                        ),
                        callback_data=f"tariff_change:confirm_pay:{target.key}:{options['paid_diff_rub']}{suffix}",
                    )
                ]
            )
    elif options["mode"] == "period_to_traffic":
        rows.append(
            [
                InlineKeyboardButton(
                    text=get_text("wa_tariff_change_convert_gb", gb=options["converted_gb"]),
                    callback_data=f"tariff_change:confirm_apply:{target.key}:g{suffix}",
                )
            ]
        )
        rows.extend(
            [
                InlineKeyboardButton(
                    text=get_text(
                        "wa_tariff_change_buy_package",
                        gb=f"{package.gb:g}",
                        price=f"{package.price:g} {currency_code}",
                    ),
                    callback_data=f"tariff:package:{target.key}:{package.gb:g}{suffix}:{TARIFF_SWITCH_ORIGIN}",
                )
            ]
            for package in target.traffic_packages.for_currency(default_currency)
        )
    else:
        for months in target.enabled_periods:
            price = target.period_price(months, default_currency)
            if price:
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=get_text(
                                "subscribe_for_months_button",
                                months=months,
                                price=f"{price:g}",
                                currency_symbol=currency_code,
                            ),
                            callback_data=f"tariff:period:{target.key}:{months}{suffix}:{TARIFF_SWITCH_ORIGIN}",
                        )
                    ]
                )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.gettext(current_lang, "back_to_main_menu_button"),
                callback_data=f"tariff_change:list{suffix}",
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
    state: FSMContext | None = None,
) -> None:
    account_user_id = await require_telegram_account_id(session, callback.from_user.id)
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    data, context = split_callback_context(callback_data(callback))
    suffix = callback_suffix_for_context(context)
    _, _, tariff_key, mode = data.split(":", 3)
    target = config.require(tariff_key)
    db_sub = await subscription_dal.get_active_subscription_by_user_id(session, account_user_id)
    if not db_sub:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    options = await subscription_service.calculate_tariff_switch_options_with_hwid(
        session, db_sub, target
    )
    switch_mode = _SWITCH_MODES.get(mode, mode)
    if switch_mode == "recalc_days":
        action_text = get_text(
            "wa_tariff_change_confirm_recalc", days=options.get("recalc_days", 0)
        )
    elif switch_mode == "convert_days_to_gb":
        action_text = get_text(
            "wa_tariff_change_confirm_convert", gb=options.get("converted_gb", 0)
        )
    else:
        action_text = get_text("tariff_change_confirm_no_payment")
    rows = [
        [
            InlineKeyboardButton(
                text=get_text("tariff_change_confirm_button"),
                callback_data=f"tariff_change:apply:{target.key}:{mode}{suffix}",
            )
        ],
        [
            InlineKeyboardButton(
                text=i18n.gettext(current_lang, "back_to_main_menu_button"),
                callback_data=f"tariff_change:select:{target.key}{suffix}",
            )
        ],
    ]
    message_text = "\n".join(
        [
            get_text("wa_tariff_change_confirm_title"),
            "",
            get_text("wa_tariff_change_confirm_target", tariff=target.name(current_lang)),
            get_text("wa_tariff_change_confirm_action", action=action_text),
        ]
    )
    await edit_confirmation(
        callback_message(callback),
        state,
        message_text,
        InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tariff_change:confirm_pay:"))
async def tariff_change_confirm_pay_callback(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    state: FSMContext | None = None,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    config = settings.tariffs_config
    if not config or not callback.message:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    data, context = split_callback_context(callback_data(callback))
    suffix = callback_suffix_for_context(context)
    _, _, tariff_key, amount_raw = data.split(":", 3)
    target = config.require(tariff_key)
    currency_code = default_payment_currency_code_for_settings(settings)
    rows = [
        [
            InlineKeyboardButton(
                text=get_text("tariff_change_confirm_pay_button"),
                callback_data=f"tariff_change:pay:{target.key}:{amount_raw}{suffix}",
            )
        ],
        [
            InlineKeyboardButton(
                text=i18n.gettext(current_lang, "back_to_main_menu_button"),
                callback_data=f"tariff_change:select:{target.key}{suffix}",
            )
        ],
    ]
    payment_text = get_text(
        "wa_tariff_change_confirm_payment", price=f"{amount_raw} {currency_code}"
    )
    message_text = "\n".join(
        [
            get_text("wa_tariff_change_confirm_title"),
            "",
            get_text("wa_tariff_change_confirm_target", tariff=target.name(current_lang)),
            get_text("wa_tariff_change_confirm_action", action=payment_text),
        ]
    )
    await edit_confirmation(
        callback_message(callback),
        state,
        message_text,
        InlineKeyboardMarkup(inline_keyboard=rows),
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
    account_user_id = await require_telegram_account_id(session, callback.from_user.id)
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = (
        (lambda key, **kw: i18n.gettext(current_lang, key, **kw))
        if i18n
        else (lambda key, **kw: "Error")
    )
    data, context = split_callback_context(callback_data(callback))
    _, _, tariff_key, mode = data.split(":", 3)
    result = await subscription_service.switch_tariff_without_payment(
        session, account_user_id, tariff_key, _SWITCH_MODES.get(mode, mode)
    )
    if result:
        await session.commit()
        await callback.answer(get_text("wa_tariff_change_applied"), show_alert=True)
        await my_subscription_command_handler(
            callback,
            i18n_data,
            settings,
            subscription_service.panel_service,
            subscription_service,
            session,
            callback_bot(callback),
            back_callback=subscription_menu_back_callback(context),
        )
    else:
        await session.rollback()
        await callback.answer(get_text("wa_tariff_change_failed"), show_alert=True)


@router.callback_query(F.data.startswith("tariff_change:pay:"))
async def tariff_change_pay_callback(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
    subscription_service: SubscriptionService,
) -> None:
    account_user_id = await require_telegram_account_id(session, callback.from_user.id)
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)
    data, context = split_callback_context(callback_data(callback))
    _, _, tariff_key, amount_raw = data.split(":", 3)
    config = settings.tariffs_config
    active = await subscription_dal.get_active_subscription_by_user_id(session, account_user_id)
    if not config or not active:
        await callback.answer(get_text("telegram_confirmation_expired"), show_alert=True)
        return
    target = config.require(tariff_key)
    options = await subscription_service.calculate_tariff_switch_options_with_hwid(
        session, active, target
    )
    amount = float(options.get("paid_diff_rub") or 0)
    if options.get("mode") != "period_to_period" or amount <= 0 or amount != float(amount_raw):
        await callback.answer(get_text("telegram_confirmation_expired"), show_alert=True)
        return
    currency_code = default_payment_currency_code_for_settings(settings)
    markup = get_payment_method_keyboard(
        1,
        amount,
        None,
        currency_code,
        current_lang,
        i18n,
        settings,
        sale_mode=sale_mode_with_token(
            sale_mode_with_callback_context(f"tariff_upgrade@{tariff_key}", context),
            TELEGRAM_SUBSCRIPTION_CHECKOUT,
        ),
        back_callback=f"tariff_change:confirm_pay:{tariff_key}:{amount_raw}{callback_suffix_for_context(context)}",
        user_id=account_user_id,
    )
    await callback_message(callback).edit_text(
        get_text("choose_payment_method"), reply_markup=markup
    )
    await callback.answer()
