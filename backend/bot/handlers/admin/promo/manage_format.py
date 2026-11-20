"""Shared formatting and validation helpers for promo management handlers.

Split out of ``manage.py`` (which re-exports this surface).
"""

from datetime import UTC, datetime
from typing import Any

from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services.promo_effects import (
    PromoEffects,
    summarize_effects,
    validate_effects,
)
from db.dal import promo_code_dal
from db.models import PromoCode

PROMO_EDIT_FIELD_LABELS = {
    "bonus_days": "Bonus days",
    "discount_percent": "Discount %",
    "duration_multiplier": "Duration multiplier",
    "traffic_multiplier": "Traffic multiplier",
    "applies_to": "Scope",
    "min_subscription_months": "Min months",
    "min_traffic_gb": "Min GB",
    "max_activations": "Max uses",
    "valid_until": "Validity days",
}
PROMO_EFFECT_FIELDS = {
    "bonus_days",
    "discount_percent",
    "duration_multiplier",
    "traffic_multiplier",
}


def _none_like(value: str) -> bool:
    return value.strip().lower() in {"", "0", "none", "null", "unlimited", "forever", "indefinite"}


def _optional_float(value: str) -> float | None:
    if _none_like(value):
        return None
    return float(value)


def _optional_int(value: str) -> int | None:
    if _none_like(value):
        return None
    return int(value)


def _number_text(value: Any) -> str:
    if value is None:
        return "-"
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def _money_text(amount: Any, currency: str | None) -> str:
    if amount is None:
        return "-"
    suffix = f" {currency}" if currency else ""
    return f"{float(amount):.2f}{suffix}"


def _promo_effects_for_update(promo: PromoCode, update_data: dict[str, Any]) -> PromoEffects:
    payload = {
        "bonus_days": promo.bonus_days,
        "discount_percent": promo.discount_percent,
        "duration_multiplier": promo.duration_multiplier,
        "traffic_multiplier": promo.traffic_multiplier,
        "applies_to": promo.applies_to,
        "min_subscription_months": promo.min_subscription_months,
        "min_traffic_gb": promo.min_traffic_gb,
    }
    payload.update(update_data)
    effects = PromoEffects.from_payload(payload)
    validate_effects(effects)
    return effects


def _single_effect_update(field: str, update_data: dict[str, Any]) -> None:
    if field not in PROMO_EFFECT_FIELDS:
        return
    if field == "bonus_days" and int(update_data.get("bonus_days") or 0) > 0:
        update_data.update(
            {
                "discount_percent": None,
                "duration_multiplier": None,
                "traffic_multiplier": None,
            }
        )
    elif field == "discount_percent" and float(update_data.get("discount_percent") or 0) > 0:
        update_data.update(
            {
                "bonus_days": 0,
                "duration_multiplier": None,
                "traffic_multiplier": None,
            }
        )
    elif field == "duration_multiplier" and float(update_data.get("duration_multiplier") or 1) > 1:
        update_data.update(
            {
                "bonus_days": 0,
                "discount_percent": None,
                "traffic_multiplier": None,
            }
        )
    elif field == "traffic_multiplier" and float(update_data.get("traffic_multiplier") or 1) > 1:
        update_data.update(
            {
                "bonus_days": 0,
                "discount_percent": None,
                "duration_multiplier": None,
            }
        )


def _threshold_text(effects: PromoEffects) -> str:
    parts: list[str] = []
    if effects.min_subscription_months:
        parts.append(f"from {effects.min_subscription_months} months")
    if effects.min_traffic_gb:
        parts.append(f"from {effects.min_traffic_gb:g} GB")
    return ", ".join(parts) or "-"


def _activation_effect_text(activation: Any) -> str:
    if activation.effect_summary:
        return str(activation.effect_summary)
    effects = PromoEffects.from_model(activation)
    return summarize_effects(effects)


def _activation_grant_text(activation: Any) -> str:
    parts: list[str] = []
    if activation.granted_days:
        parts.append(f"+{activation.granted_days} days")
    if activation.granted_gb is not None:
        if activation.charged_gb is not None:
            charged = _number_text(activation.charged_gb)
            granted = _number_text(activation.granted_gb)
            parts.append(f"{charged} -> {granted} GB")
        else:
            parts.append(f"{_number_text(activation.granted_gb)} GB")
    if getattr(activation, "granted_regular_traffic_gb", None) is not None:
        parts.append(f"+{_number_text(activation.granted_regular_traffic_gb)} GB regular")
    if getattr(activation, "granted_premium_traffic_gb", None) is not None:
        parts.append(f"+{_number_text(activation.granted_premium_traffic_gb)} GB premium")
    return ", ".join(parts) or "-"


def _activation_line(activation: Any) -> str:
    payment = getattr(activation, "payment", None)
    payment_id = activation.payment_id or getattr(payment, "payment_id", None)
    payment_status = getattr(payment, "status", None)
    payment_provider = getattr(payment, "provider", None)
    currency = getattr(payment, "currency", None)
    amount = getattr(payment, "amount", None)
    base_amount = activation.base_amount
    discount_amount = activation.discount_amount
    if base_amount is None:
        base_amount = getattr(payment, "checkout_base_amount", None)
    if discount_amount is None:
        discount_amount = getattr(payment, "checkout_discount_amount", None)
    payment_text = f"payment #{payment_id}" if payment_id else "standalone"
    if payment_status:
        payment_text = f"{payment_text} {payment_status}"
    if payment_provider:
        payment_text = f"{payment_text}/{payment_provider}"
    return " | ".join(
        [
            f"User {activation.user_id}",
            activation.activated_at.strftime("%d.%m.%Y %H:%M"),
            payment_text,
            f"amount {_money_text(amount, currency)}",
            f"base {_money_text(base_amount, currency)}",
            f"discount {_money_text(discount_amount, currency)}",
            f"grant {_activation_grant_text(activation)}",
            f"effect {_activation_effect_text(activation)}",
        ]
    )


def _active_promo_list_line(
    promo: PromoCode,
    i18n: JsonI18n,
    current_lang: str,
    gettext: Any,
) -> str:
    status = get_promo_status_emoji_and_text(promo, i18n, current_lang)[0]
    validity = (
        promo.valid_until.strftime("%d.%m.%Y")
        if promo.valid_until
        else gettext("admin_promo_valid_indefinitely")
    )
    effects = summarize_effects(PromoEffects.from_model(promo))
    return (
        f"{status} <code>{promo.code}</code> | {effects} | "
        f"{promo.current_activations}/{promo.max_activations} | {validity}"
    )


def get_promo_status_emoji_and_text(
    promo: PromoCode, i18n: JsonI18n, current_lang: str
) -> tuple[str, str]:
    """Determine promo code status and return emoji + text"""
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    if promo.valid_until and promo.valid_until < datetime.now(UTC):
        return "⏰", _("admin_promo_status_expired")
    elif promo.current_activations >= promo.max_activations:
        return "🔄", _("admin_promo_status_used_up")
    elif promo.is_active:
        return "✅", _("admin_promo_status_active")
    else:
        return "🚫", _("admin_promo_status_inactive")


def promo_list_page(parts: list[str], index: int) -> int:
    token = parts[index] if len(parts) > index else ""
    return int(token) if token.isascii() and token.isdecimal() else 0


async def get_promo_detail_text_and_keyboard(
    promo_id: int, session: AsyncSession, i18n: JsonI18n, current_lang: str, *, list_page: int = 0
) -> tuple[str | None, types.InlineKeyboardMarkup | None]:
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)
    promo = await promo_code_dal.get_promo_code_by_id(session, promo_id)
    if not promo:
        return None, None

    _status_emoji, status = get_promo_status_emoji_and_text(promo, i18n, current_lang)

    validity = _("admin_promo_valid_indefinitely")
    if promo.valid_until:
        validity = promo.valid_until.strftime("%d.%m.%Y %H:%M")

    created = promo.created_at.strftime("%d.%m.%Y %H:%M") if promo.created_at else "N/A"
    effects = PromoEffects.from_model(promo)

    text = "\n".join(
        [
            _("admin_promo_card_title", code=promo.code),
            _("admin_promo_card_bonus_days", days=promo.bonus_days),
            f"Effect: {summarize_effects(effects)}",
            f"Scope: {effects.applies_to}",
            f"Eligibility: {_threshold_text(effects)}",
            _(
                "admin_promo_card_activations",
                current=promo.current_activations,
                max=promo.max_activations,
            ),
            _("admin_promo_card_validity", validity=validity),
            _("admin_promo_card_status", status=status),
            _("admin_promo_card_created", created=created),
            _("admin_promo_card_created_by", creator=promo.created_by_admin_id),
        ]
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_edit_button"),
            callback_data=f"promo_edit_select:{promo_id}:{list_page}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_toggle_status_button"),
            callback_data=f"promo_toggle:{promo_id}:{list_page}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_view_activations_button"),
            callback_data=f"promo_activations:{promo_id}:0:{list_page}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_delete_button"),
            callback_data=f"promo_delete:{promo_id}:{list_page}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_back_to_list_button"), callback_data=f"promo_management:{list_page}"
        )
    )

    return text, builder.as_markup()
