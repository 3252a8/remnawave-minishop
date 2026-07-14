"""Promo code list/detail, toggle, activations and CSV export handlers.

Shared formatting lives in ``manage_format``; the edit-flow FSM in
``manage_edit``. Both are re-exported here for compatibility.
"""

import csv
import io
from datetime import UTC, datetime

from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.admin_keyboards import get_back_to_admin_panel_keyboard
from bot.middlewares.i18n import JsonI18n
from bot.services.promo_effects import (
    PromoEffects,
    summarize_effects,
)
from bot.utils.callback_answer import callback_data, callback_message
from config.settings import Settings
from db.dal import promo_code_dal

from .manage_edit import (  # noqa: F401
    process_promo_edit_details,
    promo_edit_field_handler,
    promo_edit_select_handler,
)
from .manage_edit import (
    router as _edit_router,
)
from .manage_format import (  # noqa: F401
    PROMO_EDIT_FIELD_LABELS,
    PROMO_EFFECT_FIELDS,
    _activation_effect_text,
    _activation_grant_text,
    _activation_line,
    _active_promo_list_line,
    _money_text,
    _none_like,
    _number_text,
    _optional_float,
    _optional_int,
    _promo_effects_for_update,
    _single_effect_update,
    _threshold_text,
    get_promo_detail_text_and_keyboard,
    get_promo_status_emoji_and_text,
)

router = Router(name="promo_manage_router")
router.include_router(_edit_router)


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

    page_size = 10  # Number of promo codes per page
    offset = page * page_size

    # Get the total number of promo codes
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

    # Add pagination buttons when there is more than one page
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

    # Add export and back buttons
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

    # Build the header with pagination information
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

        # Get all promo codes
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
            # Determine the status
            _status_emoji, status_text = get_promo_status_emoji_and_text(promo, i18n, export_lang)
            effects = PromoEffects.from_model(promo)

            # Build CSV data
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

        # Create the file to send
        filename = f"promo_codes_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
        file = types.BufferedInputFile(
            output.getvalue().encode("utf-8-sig"),  # BOM for correct display in Excel
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


async def manage_promo_codes_handler(
    callback: types.CallbackQuery, i18n_data: dict, settings: Settings, session: AsyncSession
) -> None:
    await promo_management_handler(callback, i18n_data, settings, session)
