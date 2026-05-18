from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from aiogram import types
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import (
    get_payment_url_keyboard,
    payment_methods_back_callback,
)
from bot.middlewares.i18n import JsonI18n
from db.dal import payment_dal
from db.models import Payment

from .common import (
    Translator,
    build_payment_description,
    format_human_units,
    mark_payment_failed_creation,
    sale_mode_base,
)


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


def parse_payment_callback(callback_data: str) -> Optional[PaymentCallbackParts]:
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
    text: Optional[str] = None,
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
    reply_markup=None,
    disable_web_page_preview: bool = False,
    log_prefix: str = "payment_providers",
) -> None:
    """Edit the callback message if possible, else send a fresh reply."""
    if not callback.message:
        return
    try:
        await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
        )
        return
    except Exception as exc:
        logging.warning("%s: failed to edit message (%s), sending new one.", log_prefix, exc)
    try:
        await callback.message.answer(
            text,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
        )
    except Exception:
        pass


def describe_payment(translator: Translator, parts: PaymentCallbackParts) -> str:
    """Shortcut around ``build_payment_description`` for callback usage."""
    return build_payment_description(
        translator,
        months=parts.months,
        sale_mode=parts.sale_mode,
        human_value=parts.human_value,
    )


def payment_link_message_text(
    translator: Translator,
    parts: PaymentCallbackParts,
    *,
    lead_text: Optional[str] = None,
) -> str:
    """Build the ``payment_link_message`` text (with optional lead block)."""
    traffic_like = sale_mode_base(parts.sale_mode) in {
        "traffic",
        "traffic_package",
        "topup",
        "premium_topup",
    }
    key = (
        "payment_link_message_traffic"
        if traffic_like
        else "payment_link_message"
    )
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
    i18n: Optional[JsonI18n],
    parts: PaymentCallbackParts,
    payment_url: str,
    lead_text: Optional[str] = None,
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
    if callback.message:
        try:
            await callback.message.edit_text(translator("payment_service_unavailable"))
        except Exception:
            pass


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
    if callback.message:
        try:
            await callback.message.edit_text(translator("error_creating_payment_record"))
        except Exception:
            pass
    await safe_callback_answer(callback, translator("error_try_again"), show_alert=True)


async def notify_payment_gateway_failure(
    callback: types.CallbackQuery,
    translator: Translator,
) -> None:
    """``error_payment_gateway`` shown both inline and as alert."""
    if callback.message:
        try:
            await callback.message.edit_text(translator("error_payment_gateway"))
        except Exception:
            pass
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
    new_status: Optional[str] = None,
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
        )
        await session.commit()
        return True
    except Exception:
        await session.rollback()
        logging.exception(
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
        logging.exception(
            "%s: failed to mark payment %s as failed_creation.",
            log_prefix,
            payment.payment_id,
        )


async def render_link_or_fail(
    callback: types.CallbackQuery,
    *,
    translator: Translator,
    current_lang: str,
    i18n: Optional[JsonI18n],
    parts: "PaymentCallbackParts",
    session: AsyncSession,
    payment: Payment,
    api_success: bool,
    payment_url: Optional[str],
    provider_payment_id: Optional[str] = None,
    new_status: Optional[str] = None,
    lead_text: Optional[str] = None,
    log_prefix: str,
) -> None:
    """Finalize the link-based callback flow after the provider API responded.

    Persists the provider payment id (when one was returned), shows the
    payment link, or falls through to ``error_payment_gateway`` and marks the
    payment as ``failed_creation``. Every link-style provider used to inline
    this same sequence.
    """
    if api_success and provider_payment_id:
        await safe_store_provider_payment_id(
            session,
            payment,
            provider_payment_id=provider_payment_id,
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

    await safe_mark_failed_creation(session, payment, log_prefix=log_prefix)
    await notify_payment_gateway_failure(callback, translator)
