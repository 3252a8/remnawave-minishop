import contextlib
import logging

from aiogram import F, Router, types
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import (
    BOT_MENU_CONTEXT,
    PROMO_DISABLED_TOKEN,
    get_payment_method_keyboard,
    promo_id_token,
    sale_mode_with_callback_context,
    sale_mode_with_token,
    subscription_options_callback,
)
from bot.middlewares.i18n import JsonI18n
from bot.services.checkout_promos import CheckoutPromoResult
from bot.utils.callback_answer import callback_data, callback_message
from config.settings import Settings

from .core_purchase import _resolve_period_promo, _with_checkout_promo_notice

logger = logging.getLogger(__name__)

router = Router(name="user_subscription_payments_selection_router")


@router.callback_query(F.data.startswith("subscribe_period:"))
async def select_subscription_period_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    if not i18n or not callback.message:
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        return

    traffic_packages = settings.traffic_packages or {}
    stars_traffic_packages = settings.stars_traffic_packages or {}
    traffic_mode = bool(settings.traffic_sale_mode or stars_traffic_packages)
    parts = callback_data(callback).split(":")
    callback_tokens = [part for part in parts[2:] if part]
    callback_context = BOT_MENU_CONTEXT if BOT_MENU_CONTEXT in callback_tokens else None
    promo_enabled = PROMO_DISABLED_TOKEN not in callback_tokens
    try:
        months = float(parts[1])
    except (ValueError, IndexError):
        logger.error("Invalid subscription period in callback_data: %s", callback.data)
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_try_again"), show_alert=True)
        return

    price_source = traffic_packages if traffic_mode else settings.subscription_options
    stars_price_source = (
        stars_traffic_packages if traffic_mode else settings.stars_subscription_options
    )

    price_rub = price_source.get(months)
    stars_price = stars_price_source.get(months)
    currency_symbol_val = settings.DEFAULT_CURRENCY_SYMBOL

    if price_rub is None:
        if traffic_mode and not price_source and stars_price is not None:
            from bot.payment_providers import iter_provider_specs

            currency_methods_enabled = any(
                spec.price_source != "stars"
                and spec.is_available_to_user(
                    settings,
                    user_id=callback.from_user.id,
                    require_configured=False,
                )
                for spec in iter_provider_specs()
            )
            if currency_methods_enabled:
                logger.error(
                    "Currency price missing for traffic option %s while fiat providers are enabled.",  # noqa: E501
                    months,
                )
                with contextlib.suppress(Exception):
                    await callback.answer(get_text("error_try_again"), show_alert=True)
                return
            price_rub = 0.0
            currency_symbol_val = "⭐"
        else:
            logger.error(
                "Price not found for option %s using %s.",
                months,
                "traffic_packages" if traffic_mode else "subscription_options",
            )
            with contextlib.suppress(Exception):
                await callback.answer(get_text("error_try_again"), show_alert=True)
            return

    text_content = (
        get_text("choose_payment_method_traffic")
        if traffic_mode
        else get_text("choose_payment_method")
    )
    sale_mode = sale_mode_with_callback_context(
        "traffic" if traffic_mode else "subscription", callback_context
    )
    promo_quote: CheckoutPromoResult | None = None
    stars_promo_quote: CheckoutPromoResult | None = None
    if not traffic_mode and promo_enabled:
        promo_quote, stars_promo_quote = await _resolve_period_promo(
            session,
            settings,
            user_id=callback.from_user.id,
            sale_mode=sale_mode,
            months=int(months),
            price=float(price_rub),
            stars_price=int(stars_price) if stars_price else None,
        )
        if promo_quote is not None:
            sale_mode = sale_mode_with_token(
                sale_mode,
                promo_id_token(promo_quote.promo_code_id),
            )
            text_content = _with_checkout_promo_notice(
                text_content,
                get_text,
                promo_available=True,
                promo_enabled=True,
            )
    elif not traffic_mode:
        sale_mode = sale_mode_with_token(sale_mode, PROMO_DISABLED_TOKEN)
    reply_markup = get_payment_method_keyboard(
        months,
        price_rub,
        stars_price,
        currency_symbol_val,
        current_lang,
        i18n,
        settings,
        sale_mode=sale_mode,
        back_callback=subscription_options_callback(
            callback_context,
            promo_enabled=promo_enabled,
        ),
        user_id=callback.from_user.id,
        checkout_promo=promo_quote,
        checkout_stars_promo=stars_promo_quote,
    )

    try:
        await callback_message(callback).edit_text(text_content, reply_markup=reply_markup)
    except Exception as e_edit:
        logger.warning(
            "Edit message for payment method selection failed: %s. Sending new one.", e_edit
        )
        await callback_message(callback).answer(text_content, reply_markup=reply_markup)
    with contextlib.suppress(Exception):
        await callback.answer()
