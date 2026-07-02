import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.admin_keyboards import get_back_to_admin_panel_keyboard
from bot.middlewares.i18n import JsonI18n
from bot.services.promo_effects import (
    ALLOWED_PROMO_SCOPES,
    PromoEffects,
    summarize_effects,
    validate_effects,
)
from bot.states.admin_states import AdminStates
from bot.utils.callback_answer import callback_data, callback_message
from config.settings import Settings
from db.dal import promo_code_dal
from db.models import PromoCode

router = Router(name="promo_manage_router")

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


async def get_promo_detail_text_and_keyboard(
    promo_id: int, session: AsyncSession, i18n: JsonI18n, current_lang: str
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
            text=_("admin_promo_edit_button"), callback_data=f"promo_edit_select:{promo_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_toggle_status_button"), callback_data=f"promo_toggle:{promo_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_view_activations_button"),
            callback_data=f"promo_activations:{promo_id}:0",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_delete_button"), callback_data=f"promo_delete:{promo_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_back_to_list_button"), callback_data="admin_action:promo_management"
        )
    )

    return text, builder.as_markup()


async def view_promo_codes_handler(
    callback: types.CallbackQuery, i18n_data: dict, settings: Settings, session: AsyncSession
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await callback.answer("Error processing request.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    promo_models = await promo_code_dal.get_all_active_promo_codes(session, limit=20, offset=0)
    text = (
        f"{_('admin_active_promos_list_header')}\n\n{_('admin_no_active_promos')}"
        if not promo_models
        else "\n".join(
            [_("admin_active_promos_list_header"), ""]
            + [_active_promo_list_line(p, i18n, current_lang, _) for p in promo_models]
        )
    )

    await callback_message(callback).edit_text(
        text, reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n), parse_mode="HTML"
    )
    await callback.answer()


async def promo_management_handler(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
    page: int = 0,
) -> None:
    current_lang = i18n_data.get("current_language", "ru")
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await callback.answer("Error processing request.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    page_size = 10  # Количество промокодов на странице
    offset = page * page_size

    # Получаем общее количество промокодов
    total_count = await promo_code_dal.get_promo_codes_count(session)
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    promo_models = await promo_code_dal.get_all_promo_codes_with_details(
        session, limit=page_size, offset=offset
    )
    if not promo_models and page == 0:
        await callback_message(callback).edit_text(
            _("admin_promo_management_empty"),
            reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    for promo in promo_models:
        status_emoji, _status_text = get_promo_status_emoji_and_text(promo, i18n, current_lang)
        button_text = (
            f"{status_emoji} {promo.code} ({promo.current_activations}/{promo.max_activations})"
        )
        builder.row(
            InlineKeyboardButton(
                text=button_text, callback_data=f"promo_detail:{promo.promo_code_id}"
            )
        )

    # Добавляем кнопки пагинации если есть больше одной страницы
    if total_pages > 1:
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(
                InlineKeyboardButton(
                    text=_("prev_page_button"), callback_data=f"promo_management:{page - 1}"
                )
            )
        if page < total_pages - 1:
            pagination_buttons.append(
                InlineKeyboardButton(
                    text=_("next_page_button"), callback_data=f"promo_management:{page + 1}"
                )
            )

        if pagination_buttons:
            builder.row(*pagination_buttons)

    # Добавляем кнопки экспорта и возврата
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_export_csv_button"), callback_data="promo_export_all"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("back_to_admin_panel_button"), callback_data="admin_action:main"
        )
    )

    # Формируем заголовок с информацией о страницах
    title = _("admin_promo_management_title")
    if total_pages > 1:
        title += f"\n{_('admin_promo_list_page_info', current=page + 1, total=total_pages, count=total_count)}"  # noqa: E501

    await callback_message(callback).edit_text(
        title, reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("promo_management:"))
async def promo_management_pagination_handler(
    callback: types.CallbackQuery, i18n_data: dict, settings: Settings, session: AsyncSession
) -> None:
    try:
        page = int(callback_data(callback).split(":")[1])
        await promo_management_handler(callback, i18n_data, settings, session, page)
    except (ValueError, IndexError):
        await callback.answer("Error processing pagination.", show_alert=True)


@router.callback_query(F.data.startswith("promo_detail:"))
async def promo_detail_handler(
    callback: types.CallbackQuery, i18n_data: dict, session: AsyncSession
) -> None:
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    current_lang = i18n_data.get("current_language")
    if not i18n or not callback.message or not current_lang:
        await callback.answer("Error processing request.", show_alert=True)
        return

    try:
        promo_id = int(callback_data(callback).split(":")[1])
        text, keyboard = await get_promo_detail_text_and_keyboard(
            promo_id, session, i18n, current_lang
        )
        if text:
            await callback_message(callback).edit_text(
                text, reply_markup=keyboard, parse_mode="HTML"
            )
        else:
            await callback.answer(
                i18n.gettext(current_lang, "admin_promo_not_found"), show_alert=True
            )
    except (ValueError, IndexError):
        await callback.answer(i18n.gettext(current_lang, "admin_promo_not_found"), show_alert=True)
    await callback.answer()


@router.callback_query(F.data.startswith("promo_toggle:"))
async def promo_toggle_handler(
    callback: types.CallbackQuery, i18n_data: dict, session: AsyncSession
) -> None:
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    current_lang = i18n_data.get("current_language")
    if not i18n or not callback.message or not current_lang:
        await callback.answer("Language service error.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    try:
        promo_id = int(callback_data(callback).split(":")[1])
        promo = await promo_code_dal.get_promo_code_by_id(session, promo_id)
        if not promo:
            await callback.answer(_("admin_promo_not_found"), show_alert=True)
            return

        new_status = not promo.is_active
        if await promo_code_dal.update_promo_code(session, promo_id, {"is_active": new_status}):
            await session.commit()
            status_text = (
                _("admin_promo_status_activated")
                if new_status
                else _("admin_promo_status_deactivated")
            )
            await callback.answer(
                _("admin_promo_toggle_success", code=promo.code, status=status_text)
            )

            text, keyboard = await get_promo_detail_text_and_keyboard(
                promo_id, session, i18n, current_lang
            )
            if text:
                await callback_message(callback).edit_text(
                    text, reply_markup=keyboard, parse_mode="HTML"
                )
        else:
            await callback.answer(_("error_occurred_try_again"), show_alert=True)
    except (ValueError, IndexError):
        await callback.answer(_("admin_promo_not_found"), show_alert=True)


@router.callback_query(F.data.startswith("promo_activations:"))
async def promo_activations_handler(
    callback: types.CallbackQuery, i18n_data: dict, settings: Settings, session: AsyncSession
) -> None:
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    current_lang = i18n_data.get("current_language")
    if not i18n or not callback.message or not current_lang:
        await callback.answer("Error processing request.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    try:
        parts = callback_data(callback).split(":")
        promo_id = int(parts[1])
        page = int(parts[2])
        page_size = settings.LOGS_PAGE_SIZE

        promo = await promo_code_dal.get_promo_code_by_id(session, promo_id)
        if not promo:
            await callback.answer(_("admin_promo_not_found"), show_alert=True)
            return

        total_activations = await promo_code_dal.count_promo_activations_by_code_id(
            session, promo_id
        )
        activations = await promo_code_dal.get_promo_activations_by_code_id(
            session, promo_id, limit=page_size, offset=page * page_size
        )

        builder = InlineKeyboardBuilder()
        if not activations:
            text = _("admin_promo_no_activations", code=promo.code)
        else:
            text = _("admin_promo_activations_header", code=promo.code) + "\n\n"
            text += "\n".join([_activation_line(a) for a in activations])

        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="⬅️", callback_data=f"promo_activations:{promo_id}:{page - 1}"
                )
            )
        if (page + 1) * page_size < total_activations:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="➡️", callback_data=f"promo_activations:{promo_id}:{page + 1}"
                )
            )
        if nav_buttons:
            builder.row(*nav_buttons)

        builder.row(
            InlineKeyboardButton(
                text=_("admin_promo_export_csv_button"), callback_data=f"promo_export:{promo_id}"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=_("admin_promo_back_to_detail_button"),
                callback_data=f"promo_detail:{promo_id}",
            )
        )

        await callback_message(callback).edit_text(
            text, reply_markup=builder.as_markup(), parse_mode="HTML"
        )
    except (ValueError, IndexError):
        await callback.answer(_("admin_promo_not_found"), show_alert=True)
    await callback.answer()


@router.callback_query(F.data.startswith("promo_export:"))
async def promo_export_activations_handler(
    callback: types.CallbackQuery, i18n_data: dict, session: AsyncSession
) -> None:
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    current_lang = i18n_data.get("current_language")
    if not i18n or not callback.message or not current_lang:
        await callback.answer("Error processing request.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)
    export_lang = "en"

    try:
        promo_id = int(callback_data(callback).split(":")[1])
        promo = await promo_code_dal.get_promo_code_by_id(session, promo_id)
        if not promo:
            await callback.answer(_("admin_promo_not_found"), show_alert=True)
            return

        activations = await promo_code_dal.get_promo_activations_by_code_id(session, promo_id)
        if not activations:
            await callback.answer(_("admin_promo_no_activations", code=promo.code), show_alert=True)
            return

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "User ID",
                "Activation Date",
                "Payment ID",
                "Payment Status",
                "Provider",
                "Amount",
                "Currency",
                "Base Amount",
                "Discount Amount",
                "Charged Months",
                "Charged GB",
                "Granted Days",
                "Granted GB",
                "Effect",
            ]
        )
        for act in activations:
            payment = getattr(act, "payment", None)
            writer.writerow(
                [
                    act.user_id,
                    act.activated_at.strftime("%Y-%m-%d %H:%M:%S"),
                    act.payment_id or "",
                    getattr(payment, "status", "") or "",
                    getattr(payment, "provider", "") or "",
                    getattr(payment, "amount", "") or "",
                    getattr(payment, "currency", "") or "",
                    act.base_amount
                    if act.base_amount is not None
                    else getattr(payment, "checkout_base_amount", "") or "",
                    act.discount_amount
                    if act.discount_amount is not None
                    else getattr(payment, "checkout_discount_amount", "") or "",
                    act.charged_months or "",
                    act.charged_gb or "",
                    act.granted_days or "",
                    act.granted_gb or "",
                    _activation_effect_text(act),
                ]
            )

        output.seek(0)
        file = types.BufferedInputFile(
            output.getvalue().encode("utf-8"), filename=f"promo_{promo.code}_activations.csv"
        )
        # Force English caption for exports
        await callback_message(callback).answer_document(
            file, caption=i18n.gettext(export_lang, "admin_promo_export_caption", code=promo.code)
        )

    except (ValueError, IndexError):
        await callback.answer(_("admin_promo_not_found"), show_alert=True)
    await callback.answer()


@router.callback_query(F.data == "promo_export_all")
async def promo_export_all_handler(
    callback: types.CallbackQuery, i18n_data: dict, session: AsyncSession
) -> None:
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    current_lang = i18n_data.get("current_language")
    if not i18n or not callback.message or not current_lang:
        await callback.answer("Error processing request.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)
    export_lang = "en"

    try:
        await callback.answer(
            i18n.gettext(export_lang, "admin_promo_export_all_generating"), show_alert=True
        )

        # Получаем все промокоды
        all_promos = await promo_code_dal.get_all_promo_codes_with_details(
            session, limit=10000, offset=0
        )

        output = io.StringIO()
        writer = csv.writer(output)

        # CSV headers (forced to English)
        writer.writerow(
            [
                i18n.gettext(export_lang, "admin_promo_csv_code"),
                "Effect",
                "Scope",
                "Discount %",
                "Duration Multiplier",
                "Traffic Multiplier",
                "Min Months",
                "Min GB",
                i18n.gettext(export_lang, "admin_promo_csv_bonus_days"),
                i18n.gettext(export_lang, "admin_promo_csv_max_activations"),
                i18n.gettext(export_lang, "admin_promo_csv_current_activations"),
                i18n.gettext(export_lang, "admin_promo_csv_status"),
                i18n.gettext(export_lang, "admin_promo_csv_is_active"),
                i18n.gettext(export_lang, "admin_promo_csv_valid_until"),
                i18n.gettext(export_lang, "admin_promo_csv_created_at"),
                i18n.gettext(export_lang, "admin_promo_csv_created_by_admin_id"),
            ]
        )

        for promo in all_promos:
            # Определяем статус
            _status_emoji, status_text = get_promo_status_emoji_and_text(promo, i18n, export_lang)
            effects = PromoEffects.from_model(promo)

            # Формируем данные для CSV
            row = [
                promo.code,
                summarize_effects(effects),
                effects.applies_to,
                effects.discount_percent or "",
                effects.duration_multiplier,
                effects.traffic_multiplier,
                effects.min_subscription_months or "",
                effects.min_traffic_gb or "",
                promo.bonus_days,
                promo.max_activations,
                promo.current_activations,
                status_text,
                i18n.gettext(export_lang, "csv_yes")
                if promo.is_active
                else i18n.gettext(export_lang, "csv_no"),
                promo.valid_until.strftime("%Y-%m-%d %H:%M:%S")
                if promo.valid_until
                else i18n.gettext(export_lang, "admin_promo_valid_indefinitely"),
                promo.created_at.strftime("%Y-%m-%d %H:%M:%S") if promo.created_at else "N/A",
                promo.created_by_admin_id or "N/A",
            ]
            writer.writerow(row)

        output.seek(0)

        # Создаем файл для отправки
        filename = f"promo_codes_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
        file = types.BufferedInputFile(
            output.getvalue().encode("utf-8-sig"),  # BOM для корректного отображения в Excel
            filename=filename,
        )

        caption = i18n.gettext(export_lang, "admin_promo_export_all_caption", count=len(all_promos))
        await callback_message(callback).answer_document(file, caption=caption)

    except Exception as e:
        await callback.answer(f"❌ Export error: {e!s}", show_alert=True)


@router.callback_query(F.data.startswith("promo_delete:"))
async def promo_delete_handler(
    callback: types.CallbackQuery, i18n_data: dict, settings: Settings, session: AsyncSession
) -> None:
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    current_lang = i18n_data.get("current_language")
    if not i18n or not callback.message or not current_lang:
        await callback.answer("Language service error.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    try:
        promo_id = int(callback_data(callback).split(":")[1])
        promo = await promo_code_dal.delete_promo_code(session, promo_id)
        if promo:
            await session.commit()
            await callback.answer(
                _("admin_promo_deleted_success", code=promo.code), show_alert=True
            )
            await promo_management_handler(callback, i18n_data, settings, session, 0)
        else:
            await callback.answer(_("admin_promo_not_found"), show_alert=True)
    except (ValueError, IndexError):
        await callback.answer(_("admin_promo_not_found"), show_alert=True)


# --- Promo Edit Handlers ---
@router.callback_query(F.data.startswith("promo_edit_select:"))
async def promo_edit_select_handler(
    callback: types.CallbackQuery, i18n_data: dict, session: AsyncSession
) -> None:
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    current_lang = i18n_data.get("current_language")
    if not i18n or not callback.message or not current_lang:
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)
    promo_id = int(callback_data(callback).split(":")[1])

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_edit_bonus_days"),
            callback_data=f"promo_edit_field:bonus_days:{promo_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Discount %",
            callback_data=f"promo_edit_field:discount_percent:{promo_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Duration x",
            callback_data=f"promo_edit_field:duration_multiplier:{promo_id}",
        ),
        InlineKeyboardButton(
            text="Traffic x",
            callback_data=f"promo_edit_field:traffic_multiplier:{promo_id}",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="Scope",
            callback_data=f"promo_edit_field:applies_to:{promo_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Min months",
            callback_data=f"promo_edit_field:min_subscription_months:{promo_id}",
        ),
        InlineKeyboardButton(
            text="Min GB",
            callback_data=f"promo_edit_field:min_traffic_gb:{promo_id}",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_edit_max_activations"),
            callback_data=f"promo_edit_field:max_activations:{promo_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_edit_validity"),
            callback_data=f"promo_edit_field:valid_until:{promo_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_back_to_detail_button"), callback_data=f"promo_detail:{promo_id}"
        )
    )

    await callback_message(callback).edit_text(
        _("admin_promo_edit_select_field"), reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("promo_edit_field:"))
async def promo_edit_field_handler(
    callback: types.CallbackQuery, state: FSMContext, i18n_data: dict, session: AsyncSession
) -> None:
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    current_lang = i18n_data.get("current_language")
    if not i18n or not callback.message or not current_lang:
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    _action, field, promo_id_str = callback_data(callback).split(":")
    await state.update_data(promo_id=int(promo_id_str), field_to_edit=field)

    prompts = {
        "bonus_days": "admin_promo_prompt_bonus_days",
        "max_activations": "admin_promo_prompt_max_activations",
        "valid_until": "admin_promo_prompt_validity_days",
    }
    prompt = (
        _(prompts[field])
        if field in prompts
        else f"Send new value for {PROMO_EDIT_FIELD_LABELS.get(field, field)}"
    )
    if field == "applies_to":
        prompt += f"\nAllowed: {', '.join(sorted(ALLOWED_PROMO_SCOPES))}"
    elif field in {"discount_percent", "min_subscription_months", "min_traffic_gb"}:
        prompt += "\nUse 0 or none to clear."
    elif field in {"duration_multiplier", "traffic_multiplier"}:
        prompt += "\nUse 1 or none to reset."
    await state.set_state(AdminStates.waiting_for_promo_edit_details)
    await callback_message(callback).edit_text(prompt)
    await callback.answer()


@router.message(StateFilter(AdminStates.waiting_for_promo_edit_details))
async def process_promo_edit_details(
    message: types.Message, state: FSMContext, session: AsyncSession, i18n_data: dict
) -> None:
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    current_lang = i18n_data.get("current_language")
    if not i18n or not message or not current_lang:
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    data = await state.get_data()
    promo_id_raw = data.get("promo_id")
    field = str(data.get("field_to_edit") or "")
    if promo_id_raw is None:
        await message.answer(_("error_occurred_try_again"))
        await state.clear()
        return
    promo_id = int(promo_id_raw)

    try:
        value = (message.text or "").strip()
        update_data: dict[str, Any] = {}
        promo = await promo_code_dal.get_promo_code_by_id(session, promo_id)
        if not promo:
            await message.answer(_("admin_promo_not_found"))
            await state.clear()
            return

        if field == "bonus_days":
            update_data["bonus_days"] = int(value)
            if update_data["bonus_days"] < 0:
                raise ValueError
        elif field == "discount_percent":
            update_data["discount_percent"] = _optional_float(value)
        elif field == "duration_multiplier":
            update_data["duration_multiplier"] = _optional_float(value)
        elif field == "traffic_multiplier":
            update_data["traffic_multiplier"] = _optional_float(value)
        elif field == "applies_to":
            scope = value.lower()
            if scope not in ALLOWED_PROMO_SCOPES:
                raise ValueError
            update_data["applies_to"] = scope
        elif field == "min_subscription_months":
            update_data["min_subscription_months"] = _optional_int(value)
        elif field == "min_traffic_gb":
            update_data["min_traffic_gb"] = _optional_float(value)
        elif field == "max_activations":
            update_data["max_activations"] = int(value)
            if update_data["max_activations"] < int(promo.current_activations or 0):
                raise ValueError
        elif field == "valid_until":
            if _none_like(value):
                update_data["valid_until"] = None
            else:
                days = int(value)
                if days <= 0:
                    raise ValueError
                update_data["valid_until"] = datetime.now(UTC) + timedelta(days=days)
        else:
            raise ValueError

        _single_effect_update(field, update_data)
        _promo_effects_for_update(promo, update_data)

        if await promo_code_dal.update_promo_code(session, promo_id, update_data):
            await session.commit()
            await message.answer(_("admin_promo_edit_success"))

            # Reset state and show updated details
            await state.clear()
            text, keyboard = await get_promo_detail_text_and_keyboard(
                promo_id, session, i18n, current_lang
            )
            if text:
                await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await message.answer(_("error_occurred_try_again"))
            await state.clear()

    except (ValueError, TypeError):
        await message.answer(_("admin_promo_invalid_input"))
        # Don't clear state, let them try again


async def manage_promo_codes_handler(
    callback: types.CallbackQuery, i18n_data: dict, settings: Settings, session: AsyncSession
) -> None:
    await promo_management_handler(callback, i18n_data, settings, session)
