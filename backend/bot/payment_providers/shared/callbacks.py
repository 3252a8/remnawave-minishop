from __future__ import annotations

import contextlib
import logging
import math
from dataclasses import dataclass
from typing import Any

from aiogram import types
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import (
    HWID_RENEWAL_TOKEN,
    get_payment_url_keyboard,
    payment_methods_back_callback,
    sale_mode_has_token,
)
from bot.middlewares.i18n import JsonI18n
from bot.utils.callback_answer import callback_message_or_none
from db.dal import payment_dal, subscription_dal
from db.models import Payment

from .common import (
    Translator,
    build_payment_description,
    format_human_units,
    mark_payment_failed_creation,
    parse_positive_int_units,
    sale_mode_base,
    sale_mode_is_hwid_devices,
    sale_mode_tariff_key,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PaymentCallbackParts:
    months: float
    price: float
    sale_mode: str

    @property
    def human_value(self) -> str:
        return format_human_units(self.months)

    @property
    def sale_base(self) -> str:
        return sale_mode_base(self.sale_mode)


def _short_repr(value: Any, *, max_length: int = 2000) -> str:
    text = repr(value)
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def parse_payment_callback(callback_data: str) -> PaymentCallbackParts | None:
    """Parse the ``<prefix>:<value>:<price>:<sale_mode>`` payload all providers use.

    Returns ``None`` if the payload doesn't have the expected shape — callers
    answer with ``error_try_again`` in that case.
    """
    try:
        _, data_payload = callback_data.split(":", 1)
        parts = data_payload.split(":")
        months = float(parts[0])
        price = float(parts[1])
        sale_mode = parts[2] if len(parts) > 2 else "subscription"
    except (ValueError, IndexError):
        return None
    return PaymentCallbackParts(months=months, price=price, sale_mode=sale_mode)


async def safe_callback_answer(
    callback: types.CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
) -> None:
    """``callback.answer`` that never raises (Telegram occasionally 400s)."""
    try:
        if text is None:
            await callback.answer()
        else:
            await callback.answer(text, show_alert=show_alert)
    except Exception:
        pass


async def edit_or_answer(
    callback: types.CallbackQuery,
    text: str,
    *,
    reply_markup: Any = None,
    disable_web_page_preview: bool = False,
    log_prefix: str = "payment_providers",
) -> None:
    """Edit the callback message if possible, else send a fresh reply."""
    message = callback_message_or_none(callback)
    if message is None:
        return
    try:
        await message.edit_text(
            text,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
        )
        return
    except Exception as exc:
        logger.warning("%s: failed to edit message (%s), sending new one.", log_prefix, exc)
    with contextlib.suppress(Exception):
        await message.answer(
            text,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
        )


def describe_payment(translator: Translator, parts: PaymentCallbackParts) -> str:
    """Shortcut around ``build_payment_description`` for callback usage."""
    return build_payment_description(
        translator,
        months=parts.months,
        sale_mode=parts.sale_mode,
        human_value=parts.human_value,
    )


async def quote_hwid_callback_parts(
    *,
    session: AsyncSession,
    user_id: int,
    parts: PaymentCallbackParts,
    subscription_service: Any,
    currency: str = "rub",
    settings: Any | None = None,
) -> tuple[PaymentCallbackParts | None, dict[str, Any] | None]:
    if settings is not None:
        quoted_parts = await _quote_configured_callback_parts(
            session=session,
            user_id=user_id,
            parts=parts,
            subscription_service=subscription_service,
            settings=settings,
            currency=currency,
        )
        if quoted_parts is None:
            return None, None
        parts = quoted_parts

    base = sale_mode_base(parts.sale_mode)
    if base == "subscription" and sale_mode_has_token(parts.sale_mode, HWID_RENEWAL_TOKEN):
        try:
            months = int(parts.months)
        except (TypeError, ValueError):
            return None, None
        quote = await subscription_service.quote_hwid_device_renewal_for_subscription(
            session,
            user_id=user_id,
            target_tariff_key=sale_mode_tariff_key(parts.sale_mode),
            months=months,
            currency=currency,
        )
        if not quote:
            return parts, None
        quoted_parts = PaymentCallbackParts(
            months=months,
            price=float(parts.price or 0) + float(quote.get("price") or 0),
            sale_mode=parts.sale_mode,
        )
        return quoted_parts, quote
    if not sale_mode_is_hwid_devices(parts.sale_mode):
        return parts, None
    device_count = parse_positive_int_units(parts.months)
    if device_count is None:
        return None, None
    quote = await subscription_service.quote_hwid_device_topup(
        session,
        user_id=user_id,
        device_count=device_count,
        tariff_key=sale_mode_tariff_key(parts.sale_mode),
        renewal=sale_mode_base(parts.sale_mode) == "hwid_devices_renewal",
        currency=currency,
    )
    if not quote:
        return None, None
    quoted_parts = PaymentCallbackParts(
        months=device_count,
        price=float(quote.get("price") or 0),
        sale_mode=parts.sale_mode,
    )
    return quoted_parts, quote


def _matching_package_price(packages: Any, units: float, currency: str) -> float | None:
    if not math.isfinite(units) or units <= 0 or packages is None:
        return None
    try:
        configured = packages.for_currency(currency)
    except (AttributeError, KeyError, TypeError, ValueError):
        configured = getattr(packages, currency, [])
    for package in configured or []:
        try:
            if abs(float(package.gb) - units) < 0.000001:
                price = float(package.price)
                return price if math.isfinite(price) and price > 0 else None
        except (AttributeError, TypeError, ValueError):
            continue
    return None


def _matching_legacy_price(options: Any, units: float) -> float | None:
    if not math.isfinite(units) or units <= 0:
        return None
    for configured_units, configured_price in (options or {}).items():
        try:
            if abs(float(configured_units) - units) < 0.000001:
                price = float(configured_price)
                return price if math.isfinite(price) and price > 0 else None
        except (TypeError, ValueError):
            continue
    return None


async def _quote_configured_callback_parts(
    *,
    session: AsyncSession,
    user_id: int,
    parts: PaymentCallbackParts,
    subscription_service: Any,
    settings: Any,
    currency: str,
) -> PaymentCallbackParts | None:
    """Rebuild a Telegram callback quote from current server configuration.

    Inline keyboard payloads are user-visible, long-lived input.  Their price
    is display state, not an authority: old messages must not keep an outdated
    tariff price and provider adapters must never persist a client-supplied
    amount without re-quoting it here.
    """
    base = sale_mode_base(parts.sale_mode)
    tariff_key = sale_mode_tariff_key(parts.sale_mode)
    tariffs_config = settings.tariffs_config
    normalized_currency = str(currency or "rub").strip().lower()

    if tariffs_config is None:
        if base == "subscription":
            if bool(settings.traffic_sale_mode):
                return None
            months = parse_positive_int_units(parts.months)
            if months is None:
                return None
            options = (
                settings.stars_subscription_options
                if normalized_currency == "stars"
                else settings.subscription_options
            )
            price = _matching_legacy_price(options, float(months))
            units: float = float(months)
        elif base == "traffic":
            options = (
                settings.stars_traffic_packages
                if normalized_currency == "stars"
                else settings.traffic_packages
            )
            units = float(parts.months)
            price = _matching_legacy_price(options, units)
        else:
            return None
        if price is None:
            return None
        return PaymentCallbackParts(months=units, price=price, sale_mode=parts.sale_mode)

    if base == "tariff_upgrade":
        if not tariff_key or normalized_currency == "stars":
            return None
        try:
            target = tariffs_config.require(tariff_key)
        except Exception:
            return None
        active_sub = await subscription_dal.get_active_subscription_by_user_id(session, user_id)
        if not active_sub:
            return None
        options = await subscription_service.calculate_tariff_switch_options_with_hwid(
            session,
            active_sub,
            target,
        )
        price = float(options.get("paid_diff_rub") or 0)
        if not math.isfinite(price) or price <= 0:
            return None
        return PaymentCallbackParts(months=1, price=price, sale_mode=parts.sale_mode)

    if base in {"hwid_device", "hwid_devices", "hwid_devices_renewal"}:
        return parts
    if not tariff_key:
        return None
    try:
        tariff = tariffs_config.require(tariff_key)
    except Exception:
        return None

    if base == "subscription":
        if tariff.billing_model != "period":
            return None
        months = parse_positive_int_units(parts.months)
        if months is None or months not in tariff.enabled_periods:
            return None
        configured_price = tariff.period_price(months, normalized_currency)
        if configured_price is None:
            return None
        price = float(configured_price)
        units = float(months)
    elif base in {"traffic_package", "topup", "premium_topup"}:
        try:
            units = float(parts.months)
        except (TypeError, ValueError):
            return None
        if base == "traffic_package":
            if tariff.billing_model != "traffic":
                return None
            packages = tariff.traffic_packages
        else:
            active_sub = await subscription_dal.get_active_subscription_by_user_id(session, user_id)
            if not active_sub or active_sub.tariff_key != tariff.key:
                return None
            packages = (
                tariff.premium_topup_packages
                if base == "premium_topup"
                else tariffs_config.topup_packages_for(tariff)
            )
            if base == "premium_topup" and not tariff.premium_squad_uuids:
                return None
        price = _matching_package_price(packages, units, normalized_currency)
        if price is None:
            return None
    else:
        return None

    if not math.isfinite(price) or price <= 0:
        return None
    return PaymentCallbackParts(months=units, price=price, sale_mode=parts.sale_mode)


def payment_link_message_text(
    translator: Translator,
    parts: PaymentCallbackParts,
    *,
    lead_text: str | None = None,
) -> str:
    """Build the ``payment_link_message`` text (with optional lead block)."""
    traffic_like = sale_mode_base(parts.sale_mode) in {
        "traffic",
        "traffic_package",
        "topup",
        "premium_topup",
    }
    key = "payment_link_message_traffic" if traffic_like else "payment_link_message"
    body = translator(
        key,
        months=int(parts.months),
        traffic_gb=parts.human_value,
    )
    if lead_text:
        return f"{lead_text}\n\n{body}"
    return body


async def render_payment_link(
    callback: types.CallbackQuery,
    *,
    translator: Translator,
    current_lang: str,
    i18n: JsonI18n | None,
    parts: PaymentCallbackParts,
    payment_url: str,
    lead_text: str | None = None,
    back_text_key: str = "back_to_payment_methods_button",
    log_prefix: str = "payment_providers",
) -> None:
    """Show the payment link with the standard back button and shared fallbacks."""
    text = payment_link_message_text(translator, parts, lead_text=lead_text)
    keyboard = get_payment_url_keyboard(
        payment_url,
        current_lang,
        i18n,
        back_callback=payment_methods_back_callback(
            parts.human_value, parts.sale_mode, parts.price
        ),
        back_text_key=back_text_key,
    )
    await edit_or_answer(
        callback,
        text,
        reply_markup=keyboard,
        log_prefix=log_prefix,
    )
    await safe_callback_answer(callback)


async def notify_service_unavailable(
    callback: types.CallbackQuery,
    translator: Translator,
) -> None:
    """Render the standard ``payment_service_unavailable`` UX."""
    await safe_callback_answer(
        callback,
        translator("payment_service_unavailable_alert"),
        show_alert=True,
    )
    message = callback_message_or_none(callback)
    if message is not None:
        with contextlib.suppress(Exception):
            await message.edit_text(translator("payment_service_unavailable"))


async def notify_callback_parse_error(
    callback: types.CallbackQuery,
    translator: Translator,
) -> None:
    """The 4-line "callback payload looked wrong" guard every provider repeats."""
    await safe_callback_answer(callback, translator("error_try_again"), show_alert=True)


async def notify_payment_record_failure(
    callback: types.CallbackQuery,
    translator: Translator,
) -> None:
    """Both error_creating_payment_record + error_try_again shown after DB failure."""
    message = callback_message_or_none(callback)
    if message is not None:
        with contextlib.suppress(Exception):
            await message.edit_text(translator("error_creating_payment_record"))
    await safe_callback_answer(callback, translator("error_try_again"), show_alert=True)


async def notify_payment_gateway_failure(
    callback: types.CallbackQuery,
    translator: Translator,
) -> None:
    """``error_payment_gateway`` shown both inline and as alert."""
    message = callback_message_or_none(callback)
    if message is not None:
        with contextlib.suppress(Exception):
            await message.edit_text(translator("error_payment_gateway"))
    await safe_callback_answer(
        callback,
        translator("error_payment_gateway"),
        show_alert=True,
    )


async def safe_store_provider_payment_id(
    session: AsyncSession,
    payment: Payment,
    *,
    provider_payment_id: str,
    provider_payment_url: str | None = None,
    new_status: str | None = None,
    log_prefix: str,
) -> bool:
    """Persist ``(provider_payment_id, status)`` on the payment with rollback-on-fail.

    Returns True on success; logs and rolls back on failure. ``new_status``
    defaults to the payment's existing status (used after a successful API call
    that doesn't change the pending state).
    """
    try:
        await payment_dal.update_provider_payment_and_status(
            session,
            payment.payment_id,
            str(provider_payment_id),
            new_status or payment.status,
            provider_payment_url=provider_payment_url,
        )
        await session.commit()
        return True
    except Exception:
        await session.rollback()
        logger.exception(
            "%s: failed to store provider payment id for payment %s.",
            log_prefix,
            payment.payment_id,
        )
        return False


async def safe_mark_failed_creation(
    session: AsyncSession,
    payment: Payment,
    *,
    log_prefix: str,
) -> None:
    """Mark the payment as ``failed_creation``; swallow + log on failure."""
    try:
        await mark_payment_failed_creation(session, payment.payment_id)
    except Exception:
        await session.rollback()
        logger.exception(
            "%s: failed to mark payment %s as failed_creation.",
            log_prefix,
            payment.payment_id,
        )


async def render_link_or_fail(
    callback: types.CallbackQuery,
    *,
    translator: Translator,
    current_lang: str,
    i18n: JsonI18n | None,
    parts: PaymentCallbackParts,
    session: AsyncSession,
    payment: Payment,
    api_success: bool,
    payment_url: str | None,
    provider_payment_id: str | None = None,
    provider_response: Any | None = None,
    new_status: str | None = None,
    lead_text: str | None = None,
    log_prefix: str,
) -> None:
    """Finalize the link-based callback flow after the provider API responded.

    Persists the provider payment id (when one was returned), shows the
    payment link, or falls through to ``error_payment_gateway`` and marks the
    payment as ``failed_creation``. Every link-style provider used to inline
    this same sequence.
    """
    if api_success and provider_payment_id and payment_url:
        await safe_store_provider_payment_id(
            session,
            payment,
            provider_payment_id=provider_payment_id,
            provider_payment_url=payment_url,
            new_status=new_status,
            log_prefix=log_prefix,
        )

    if api_success and payment_url:
        await render_payment_link(
            callback,
            translator=translator,
            current_lang=current_lang,
            i18n=i18n,
            parts=parts,
            payment_url=payment_url,
            lead_text=lead_text,
            log_prefix=log_prefix,
        )
        return

    logger.error(
        "%s: payment creation failed for payment %s "
        "(user_id=%s, api_success=%s, has_payment_url=%s, "
        "has_provider_payment_id=%s, provider_response=%s).",
        log_prefix,
        getattr(payment, "payment_id", None),
        getattr(payment, "user_id", None),
        api_success,
        bool(payment_url),
        bool(provider_payment_id),
        _short_repr(provider_response),
    )
    await safe_mark_failed_creation(session, payment, log_prefix=log_prefix)
    await notify_payment_gateway_failure(callback, translator)
