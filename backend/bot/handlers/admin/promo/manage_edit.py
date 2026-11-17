"""Promo code edit-flow FSM handlers.

Split out of ``manage.py`` (which re-exports this surface).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.admin_keyboards import get_admin_back_keyboard
from bot.middlewares.i18n import JsonI18n
from bot.services.promo_effects import ALLOWED_PROMO_SCOPES
from bot.states.admin_states import AdminStates
from bot.utils.callback_answer import callback_data, callback_message
from db.dal import promo_code_dal

from .manage_format import (
    PROMO_EDIT_FIELD_LABELS,
    _none_like,
    _optional_float,
    _optional_int,
    _promo_effects_for_update,
    _single_effect_update,
    get_promo_detail_text_and_keyboard,
    promo_list_page,
)

router = Router(name="promo_manage_edit_router")


@router.callback_query(F.data.startswith("promo_edit_select:"))
async def promo_edit_select_handler(
    callback: types.CallbackQuery, i18n_data: dict, session: AsyncSession, state: FSMContext
) -> None:
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    current_lang = i18n_data.get("current_language")
    if not i18n or not callback.message or not current_lang:
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)
    parts = callback_data(callback).split(":")
    promo_id = int(parts[1])
    list_page = promo_list_page(parts, 2)
    if await state.get_state() == AdminStates.waiting_for_promo_edit_details.state:
        await state.clear()

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_edit_bonus_days"),
            callback_data=f"promo_edit_field:bonus_days:{promo_id}:{list_page}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Discount %",
            callback_data=f"promo_edit_field:discount_percent:{promo_id}:{list_page}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Duration x",
            callback_data=f"promo_edit_field:duration_multiplier:{promo_id}:{list_page}",
        ),
        InlineKeyboardButton(
            text="Traffic x",
            callback_data=f"promo_edit_field:traffic_multiplier:{promo_id}:{list_page}",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="Scope",
            callback_data=f"promo_edit_field:applies_to:{promo_id}:{list_page}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Min months",
            callback_data=f"promo_edit_field:min_subscription_months:{promo_id}:{list_page}",
        ),
        InlineKeyboardButton(
            text="Min GB",
            callback_data=f"promo_edit_field:min_traffic_gb:{promo_id}:{list_page}",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_edit_max_activations"),
            callback_data=f"promo_edit_field:max_activations:{promo_id}:{list_page}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_edit_validity"),
            callback_data=f"promo_edit_field:valid_until:{promo_id}:{list_page}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_back_to_detail_button"),
            callback_data=f"promo_detail:{promo_id}:{list_page}",
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

    parts = callback_data(callback).split(":")
    field, promo_id = parts[1], int(parts[2])
    list_page = promo_list_page(parts, 3)
    await state.update_data(promo_id=promo_id, field_to_edit=field, list_page=list_page)

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
    await callback_message(callback).edit_text(
        prompt,
        reply_markup=get_admin_back_keyboard(
            current_lang, i18n, f"promo_edit_select:{promo_id}:{list_page}", "cancel_button"
        ),
    )
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
                promo_id, session, i18n, current_lang, list_page=data.get("list_page", 0)
            )
            if text:
                await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await message.answer(_("error_occurred_try_again"))
            await state.clear()

    except (ValueError, TypeError):
        await message.answer(_("admin_promo_invalid_input"))
        # Don't clear state, let them try again
