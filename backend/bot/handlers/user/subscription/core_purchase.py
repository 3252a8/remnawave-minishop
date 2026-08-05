import contextlib
from collections.abc import Callable, Hashable, Sequence

from aiogram import F, types
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra.promo_policies import (
    PromoCheckoutSuggestionContext,
    resolve_promo_checkout_suggestions,
)
from bot.keyboards.inline.user_keyboards import (
    BOT_MENU_CONTEXT,
    PROMO_DISABLED_TOKEN,
    PROMO_ID_TOKEN_PREFIX,
    callback_context_from_back_callback,
    callback_suffix_for_checkout,
    callback_suffix_for_context,
    get_back_to_main_menu_markup,
    get_payment_method_keyboard,
    get_subscription_options_keyboard,
    get_tariff_catalog_keyboard,
    promo_id_token,
    sale_mode_with_callback_context,
    sale_mode_with_token,
    tariff_purchase_back_callback,
)
from bot.middlewares.i18n import JsonI18n
from bot.services.behavior_events import emit_plans_viewed
from bot.services.checkout_promos import (
    CheckoutPromoResult,
    resolve_best_checkout_promo,
    resolve_checkout_promo,
)
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


def _checkout_tokens(event: types.Message | types.CallbackQuery) -> tuple[str, ...]:
    if not isinstance(event, types.CallbackQuery):
        return ()
    return tuple(part for part in callback_data(event).split(":")[2:] if part)


def _promo_enabled_for_event(event: types.Message | types.CallbackQuery) -> bool:
    return PROMO_DISABLED_TOKEN not in _checkout_tokens(event)


def _subscription_toggle_callback(context: str | None, *, enable: bool) -> str:
    action = "main_action:bot_subscribe" if context == BOT_MENU_CONTEXT else "main_action:subscribe"
    return action if enable else f"{action}:{PROMO_DISABLED_TOKEN}"


def _tariff_toggle_callback(tariff_key: str, context: str | None, *, enable: bool) -> str:
    return (
        f"tariff:select:{tariff_key}{callback_suffix_for_checkout(context, promo_enabled=enable)}"
    )


def _with_checkout_promo_notice(
    text: str,
    get_text: Callable[..., str],
    *,
    promo_available: bool,
    promo_enabled: bool,
) -> str:
    if not promo_available:
        return text
    key = "checkout_promo_applied_notice" if promo_enabled else "checkout_promo_available_notice"
    return f"{text}\n\n{get_text(key)}"


async def _promo_candidates(session: AsyncSession, *, user_id: int) -> tuple[str, ...]:
    return await resolve_promo_checkout_suggestions(
        PromoCheckoutSuggestionContext(
            session=session,
            user_id=user_id,
            sale_mode_base="subscription",
        )
    )


async def _period_promo_quotes[QuoteKey: Hashable](
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: int,
    candidates: tuple[str, ...],
    plans: Sequence[tuple[QuoteKey, str, int, float]],
) -> dict[QuoteKey, CheckoutPromoResult]:
    quotes: dict[QuoteKey, CheckoutPromoResult] = {}
    for key, sale_mode, months, price in plans:
        quote = await resolve_best_checkout_promo(
            candidates,
            session=session,
            settings=settings,
            user_id=user_id,
            sale_mode=sale_mode,
            payment_units=months,
            base_amount=price,
        )
        if quote is not None:
            quotes[key] = quote
    return quotes


async def _resolve_period_promo(
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: int,
    sale_mode: str,
    months: int,
    price: float,
    stars_price: int | None,
    requested_promo_code_id: int | None = None,
) -> tuple[CheckoutPromoResult | None, CheckoutPromoResult | None]:
    fiat_quote: CheckoutPromoResult | None = None
    if requested_promo_code_id is not None:
        fiat_quote, _ = await resolve_checkout_promo(
            session=session,
            settings=settings,
            user_id=user_id,
            promo_code_id=requested_promo_code_id,
            sale_mode=sale_mode,
            payment_units=months,
            traffic_gb=None,
            method="telegram",
            base_amount=price,
            base_stars=stars_price,
        )
    if fiat_quote is not None and (
        fiat_quote.discount_amount <= 0 or fiat_quote.effective_amount <= 0
    ):
        fiat_quote = None
    if fiat_quote is None:
        candidates = await _promo_candidates(session, user_id=user_id)
        fiat_quote = await resolve_best_checkout_promo(
            candidates,
            session=session,
            settings=settings,
            user_id=user_id,
            sale_mode=sale_mode,
            payment_units=months,
            base_amount=price,
            base_stars=stars_price,
        )
    if fiat_quote is None or stars_price is None:
        return fiat_quote, None
    stars_quote, _ = await resolve_checkout_promo(
        session=session,
        settings=settings,
        user_id=user_id,
        promo_code_id=fiat_quote.promo_code_id,
        sale_mode=sale_mode,
        payment_units=months,
        traffic_gb=None,
        method="stars",
        base_amount=price,
        base_stars=stars_price,
    )
    if stars_quote is not None and (
        stars_quote.discount_amount <= 0
        or stars_quote.effective_stars is None
        or stars_quote.effective_stars <= 0
    ):
        stars_quote = None
    return fiat_quote, stars_quote


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
    promo_enabled = _promo_enabled_for_event(event)
    from_user = event.from_user
    if from_user is None:
        return
    user_id = int(from_user.id)
    if tariffs_config:
        enabled_tariffs = list(tariffs_config.enabled_tariffs)
        callback_context = callback_context_from_back_callback(back_callback)
        candidates = await _promo_candidates(session, user_id=user_id)
        default_currency = default_currency_key_for_settings(settings)
        promo_plans = [
            (
                (tariff.key, int(months)),
                f"subscription@{tariff.key}",
                int(months),
                float(price),
            )
            for tariff in enabled_tariffs
            if tariff.billing_model == "period"
            for months in tariff.enabled_periods
            if (price := tariff.period_price(months, default_currency)) is not None
            and float(price) > 0
        ]
        all_promo_quotes = await _period_promo_quotes(
            session,
            settings,
            user_id=user_id,
            candidates=candidates,
            plans=promo_plans,
        )
        promo_available = bool(all_promo_quotes)
        if len(enabled_tariffs) == 1:
            tariff = enabled_tariffs[0]
            tariff_promo_quotes = {
                months: quote
                for (tariff_key, months), quote in all_promo_quotes.items()
                if tariff_key == tariff.key
            }
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
                promo_quotes=tariff_promo_quotes,
                promo_available=bool(tariff_promo_quotes),
                promo_enabled=promo_enabled,
                promo_toggle_callback=_subscription_toggle_callback(
                    callback_context,
                    enable=not promo_enabled,
                ),
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
                promo_available=promo_available,
                promo_enabled=promo_enabled,
                promo_toggle_callback=_subscription_toggle_callback(
                    callback_context,
                    enable=not promo_enabled,
                ),
            )
            plans_count = len(enabled_tariffs)
            viewed_tariff_key = None
        text_content = _with_checkout_promo_notice(
            text_content,
            get_text,
            promo_available=promo_available,
            promo_enabled=promo_enabled,
        )
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
        legacy_promo_quotes: dict[object, CheckoutPromoResult] = {}
        if not traffic_mode:
            candidates = await _promo_candidates(session, user_id=user_id)
            legacy_promo_quotes = await _period_promo_quotes(
                session,
                settings,
                user_id=user_id,
                candidates=candidates,
                plans=[
                    (months, "subscription", int(months), float(price))
                    for months, price in options.items()
                    if price is not None and float(price) > 0
                ],
            )
        promo_available = bool(legacy_promo_quotes)
        reply_markup = get_subscription_options_keyboard(
            options,
            currency_symbol_val,
            current_lang,
            i18n,
            traffic_mode=traffic_mode,
            back_callback=back_callback,
            callback_context=callback_context_from_back_callback(back_callback),
            promo_quotes=legacy_promo_quotes,
            promo_available=promo_available,
            promo_enabled=promo_enabled,
            promo_toggle_callback=_subscription_toggle_callback(
                callback_context_from_back_callback(back_callback),
                enable=not promo_enabled,
            ),
        )
        text_content = _with_checkout_promo_notice(
            text_content,
            get_text,
            promo_available=promo_available,
            promo_enabled=promo_enabled,
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


@router.callback_query(F.data.startswith("main_action:subscribe"))
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
    callback_tokens = [part for part in parts[3:] if part]
    callback_context = BOT_MENU_CONTEXT if BOT_MENU_CONTEXT in callback_tokens else None
    promo_enabled = PROMO_DISABLED_TOKEN not in callback_tokens
    try:
        tariff = config.require(tariff_key)
    except Exception:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    default_currency = default_currency_key_for_settings(settings)
    candidates = await _promo_candidates(session, user_id=callback.from_user.id)
    promo_quotes = await _period_promo_quotes(
        session,
        settings,
        user_id=callback.from_user.id,
        candidates=candidates,
        plans=[
            (
                int(months),
                f"subscription@{tariff.key}",
                int(months),
                float(price),
            )
            for months in tariff.enabled_periods
            if tariff.billing_model == "period"
            if (price := tariff.period_price(months, default_currency)) is not None
            and float(price) > 0
        ],
    )
    promo_available = bool(promo_quotes)
    markup = _tariff_purchase_markup(
        tariff,
        current_lang,
        i18n,
        settings,
        back_callback=tariff_purchase_back_callback(callback_context),
        callback_context=callback_context,
        promo_quotes=promo_quotes,
        promo_available=promo_available,
        promo_enabled=promo_enabled,
        promo_toggle_callback=_tariff_toggle_callback(
            tariff.key,
            callback_context,
            enable=not promo_enabled,
        ),
    )
    text = _tariff_purchase_text(tariff, current_lang, i18n, settings)
    text = _with_subscription_purchase_description(
        text,
        settings,
        current_lang,
        include=tariff.billing_model == "period",
    )
    text = _with_checkout_promo_notice(
        text,
        get_text,
        promo_available=promo_available,
        promo_enabled=promo_enabled,
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
    callback_context = BOT_MENU_CONTEXT if BOT_MENU_CONTEXT in callback_tokens else None
    renew_hwid_devices = "no_hwid" not in callback_tokens
    promo_enabled = PROMO_DISABLED_TOKEN not in callback_tokens
    requested_promo_code_id = next(
        (
            int(token.removeprefix(PROMO_ID_TOKEN_PREFIX))
            for token in callback_tokens
            if token.startswith(PROMO_ID_TOKEN_PREFIX)
            and token.removeprefix(PROMO_ID_TOKEN_PREFIX).isdigit()
        ),
        None,
    )
    tariff = config.require(tariff_key)
    months = int(months_raw)
    default_currency = default_currency_key_for_settings(settings)
    currency_code = default_payment_currency_code_for_settings(settings)
    price_rub = tariff.period_price(months, default_currency)
    stars_price = tariff.period_price(months, "stars")
    if price_rub is None:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    sale_mode = sale_mode_with_callback_context(f"subscription@{tariff.key}", callback_context)
    promo_quote: CheckoutPromoResult | None = None
    stars_promo_quote: CheckoutPromoResult | None = None
    if promo_enabled:
        promo_quote, stars_promo_quote = await _resolve_period_promo(
            session,
            settings,
            user_id=callback.from_user.id,
            sale_mode=sale_mode,
            months=months,
            price=float(price_rub),
            stars_price=int(stars_price) if stars_price else None,
            requested_promo_code_id=requested_promo_code_id,
        )
    if promo_quote is not None:
        sale_mode = sale_mode_with_token(sale_mode, promo_id_token(promo_quote.promo_code_id))
    elif not promo_enabled:
        sale_mode = sale_mode_with_token(sale_mode, PROMO_DISABLED_TOKEN)
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
        sale_mode=sale_mode,
        back_callback=(
            f"tariff:select:{tariff.key}"
            f"{callback_suffix_for_checkout(callback_context, promo_enabled=promo_enabled)}"
        ),
        user_id=callback.from_user.id,
        hwid_renewal_quote=hwid_renewal_quote,
        hwid_renewal_stars_quote=hwid_renewal_stars_quote,
        hwid_renewal_selected=bool(renew_hwid_devices),
        checkout_promo=promo_quote,
        checkout_stars_promo=stars_promo_quote,
    )
    payment_text = _with_checkout_promo_notice(
        get_text("choose_payment_method"),
        get_text,
        promo_available=promo_quote is not None,
        promo_enabled=promo_quote is not None,
    )
    await callback_message(callback).edit_text(payment_text, reply_markup=markup)
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
