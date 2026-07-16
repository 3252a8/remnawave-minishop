import csv
import io
import logging
import random
import string
from datetime import UTC, datetime, timedelta

from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.admin_keyboards import (
    get_admin_panel_keyboard,
    get_back_to_admin_panel_keyboard,
)
from bot.middlewares.i18n import JsonI18n
from bot.services.promo_code_service import PromoCodeService
from bot.services.promo_effects import PROMO_APPLIES_TO_SUBSCRIPTION, PromoEffects
from bot.states.admin_states import AdminStates
from bot.utils.callback_answer import callback_message, message_bot
from config.settings import Settings
from db.dal import promo_code_dal

logger = logging.getLogger(__name__)

router = Router(name="promo_bulk_router")


async def create_bulk_promo_prompt_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await callback.answer("Error preparing bulk promo creation.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    # Step 1: Ask for quantity
    prompt_text = _("admin_bulk_promo_step1_quantity")

    try:
        await callback_message(callback).edit_text(
            prompt_text,
            reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning("Could not edit message for bulk promo prompt: %s. Sending new.", e)
        await callback_message(callback).answer(
            prompt_text,
            reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
            parse_mode="HTML",
        )
    await callback.answer()
    await state.set_state(AdminStates.waiting_for_bulk_promo_quantity)


def generate_unique_promo_code(length: int = 8) -> str:
    """Generate a unique random promo code"""
    characters = string.ascii_uppercase + string.digits
    return "".join(random.choice(characters) for _ in range(length))


# Step 1: Process quantity
@router.message(AdminStates.waiting_for_bulk_promo_quantity, F.text)
async def process_bulk_promo_quantity_handler(
    message: types.Message, state: FSMContext, i18n_data: dict, settings: Settings
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        await message.reply("Language service error.")
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    try:
        quantity = int((message.text or "").strip())
        if not (1 <= quantity <= 100):
            await message.answer(_("admin_bulk_promo_invalid_quantity"))
            return

        await state.update_data(quantity=quantity)

        # Step 2: Ask for bonus days
        prompt_text = _("admin_bulk_promo_step2_bonus_days", quantity=quantity)

        await message.answer(
            prompt_text,
            reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
            parse_mode="HTML",
        )
        await state.set_state(AdminStates.waiting_for_bulk_promo_bonus_days)

    except ValueError:
        await message.answer(_("admin_promo_invalid_number"))
    except Exception as e:
        logger.error("Error processing bulk promo quantity: %s", e)
        await message.answer(_("error_occurred_try_again"))


# Step 2: Process bonus days
@router.message(AdminStates.waiting_for_bulk_promo_bonus_days, F.text)
async def process_bulk_promo_bonus_days_handler(
    message: types.Message, state: FSMContext, i18n_data: dict, settings: Settings
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        await message.reply("Language service error.")
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    try:
        bonus_days = int((message.text or "").strip())
        if not (1 <= bonus_days <= 365):
            await message.answer(_("admin_promo_invalid_bonus_days"))
            return

        await state.update_data(bonus_days=bonus_days)

        # Step 3: Ask for max activations
        data = await state.get_data()
        prompt_text = _(
            "admin_bulk_promo_step3_max_activations",
            quantity=data.get("quantity"),
            bonus_days=bonus_days,
        )

        await message.answer(
            prompt_text,
            reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
            parse_mode="HTML",
        )
        await state.set_state(AdminStates.waiting_for_bulk_promo_max_activations)

    except ValueError:
        await message.answer(_("admin_promo_invalid_number"))
    except Exception as e:
        logger.error("Error processing bulk promo bonus days: %s", e)
        await message.answer(_("error_occurred_try_again"))


# Step 3: Process max activations
@router.message(AdminStates.waiting_for_bulk_promo_max_activations, F.text)
async def process_bulk_promo_max_activations_handler(
    message: types.Message, state: FSMContext, i18n_data: dict, settings: Settings
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        await message.reply("Language service error.")
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    try:
        max_activations = int((message.text or "").strip())
        if not (1 <= max_activations <= 10000):
            await message.answer(_("admin_promo_invalid_max_activations"))
            return

        await state.update_data(max_activations=max_activations)

        # Step 4: Ask for validity
        data = await state.get_data()
        prompt_text = _(
            "admin_bulk_promo_step4_validity",
            quantity=data.get("quantity"),
            bonus_days=data.get("bonus_days"),
            max_activations=max_activations,
        )

        # Create keyboard for validity options
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text=_("admin_promo_unlimited_validity"),
                callback_data="bulk_promo_unlimited_validity",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=_("admin_promo_set_validity_days"), callback_data="bulk_promo_set_validity"
            )
        )
        builder.row(
            InlineKeyboardButton(text=_("admin_back_to_panel"), callback_data="admin_action:main")
        )

        await message.answer(prompt_text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await state.set_state(AdminStates.waiting_for_bulk_promo_validity_days)

    except ValueError:
        await message.answer(_("admin_promo_invalid_number"))
    except Exception as e:
        logger.error("Error processing bulk promo max activations: %s", e)
        await message.answer(_("error_occurred_try_again"))


# Step 4: Handle unlimited validity
@router.callback_query(
    F.data == "bulk_promo_unlimited_validity",
    StateFilter(AdminStates.waiting_for_bulk_promo_validity_days),
)
async def process_bulk_promo_unlimited_validity(
    callback: types.CallbackQuery,
    state: FSMContext,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
) -> None:
    await state.update_data(validity_days=None)
    await create_bulk_promo_codes_final(callback, state, i18n_data, settings, session)


# Step 4: Handle set validity
@router.callback_query(
    F.data == "bulk_promo_set_validity",
    StateFilter(AdminStates.waiting_for_bulk_promo_validity_days),
)
async def process_bulk_promo_set_validity(
    callback: types.CallbackQuery, state: FSMContext, i18n_data: dict, settings: Settings
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await callback.answer("Error processing validity.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    data = await state.get_data()
    prompt_text = _(
        "admin_bulk_promo_enter_validity_days",
        quantity=data.get("quantity"),
        bonus_days=data.get("bonus_days"),
        max_activations=data.get("max_activations"),
    )

    try:
        await callback_message(callback).edit_text(
            prompt_text,
            reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
            parse_mode="HTML",
        )
    except Exception:
        await callback_message(callback).answer(
            prompt_text,
            reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
            parse_mode="HTML",
        )
    await callback.answer()


# Step 4: Process validity days
@router.message(AdminStates.waiting_for_bulk_promo_validity_days, F.text)
async def process_bulk_promo_validity_days_handler(
    message: types.Message,
    state: FSMContext,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        await message.reply("Language service error.")
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    try:
        validity_days = int((message.text or "").strip())
        if not (1 <= validity_days <= 365):
            await message.answer(_("admin_promo_invalid_validity_days"))
            return

        await state.update_data(validity_days=validity_days)
        await create_bulk_promo_codes_final(message, state, i18n_data, settings, session)

    except ValueError:
        await message.answer(_("admin_promo_invalid_number"))
    except Exception as e:
        logger.error("Error processing bulk promo validity days: %s", e)
        await message.answer(_("error_occurred_try_again"))


async def create_bulk_promo_codes_final(
    callback_or_message: types.Message | types.CallbackQuery,
    state: FSMContext,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
) -> None:
    """Final step - create multiple promo codes in database"""
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    try:
        data = await state.get_data()
        quantity = data["quantity"]

        # Show progress message
        progress_text = _("admin_bulk_promo_creating", quantity=quantity)

        if isinstance(callback_or_message, types.CallbackQuery):
            message = callback_message(callback_or_message)
            try:
                await message.edit_text(progress_text, parse_mode="HTML")
            except Exception:
                await message.answer(progress_text, parse_mode="HTML")
            await callback_or_message.answer()
        else:  # Message
            await callback_or_message.answer(progress_text, parse_mode="HTML")

        # Generate and create promo codes
        created_codes = []
        failed_codes = []
        actor = getattr(callback_or_message, "from_user", None)
        created_by_admin_id = int(getattr(actor, "id", 0) or 0)

        for i in range(quantity):
            try:
                # Generate unique code
                attempts = 0
                while attempts < 10:  # Max 10 attempts to generate unique code
                    promo_code = generate_unique_promo_code()
                    existing_promo = await promo_code_dal.get_promo_code_by_code(
                        session, promo_code
                    )
                    if existing_promo and getattr(existing_promo, "archived_at", None) is not None:
                        await promo_code_dal.release_archived_promo_code(session, existing_promo)
                        existing_promo = None
                    if not existing_promo:
                        break
                    attempts += 1

                if attempts >= 10:
                    failed_codes.append(_("admin_bulk_promo_unique_error", number=i + 1))
                    continue

                # Set validity
                if data.get("validity_days"):
                    expires_at = datetime.now(UTC) + timedelta(days=data["validity_days"])
                else:
                    expires_at = None

                # Create promo code
                created_promo = await PromoCodeService.issue_code(
                    session,
                    effects=PromoEffects(
                        bonus_days=int(data["bonus_days"]),
                        applies_to=PROMO_APPLIES_TO_SUBSCRIPTION,
                    ),
                    code=promo_code,
                    max_activations=int(data["max_activations"]),
                    valid_until=expires_at,
                    origin="admin",
                    created_by_admin_id=created_by_admin_id,
                    max_duration_multiplier=float(settings.PROMO_DURATION_MULTIPLIER_MAX),
                    max_traffic_multiplier=float(settings.PROMO_TRAFFIC_MULTIPLIER_MAX),
                )
                created_codes.append(created_promo.code)

            except Exception as e:
                logger.error("Error creating bulk promo code #%s: %s", i + 1, e)
                failed_codes.append(
                    _("admin_bulk_promo_code_error", number=i + 1, error=str(e)[:50])
                )

        await session.commit()

        # Success message
        success_lines = [
            _("admin_bulk_promo_created_title"),
            _("admin_bulk_promo_created_stats", created=len(created_codes), total=quantity),
        ]

        if data.get("validity_days"):
            validity_text = _("admin_promo_days_value", days=data["validity_days"])
        else:
            validity_text = _("admin_promo_unlimited")

        success_lines.append(
            _(
                "admin_bulk_promo_settings",
                bonus_days=data["bonus_days"],
                max_activations=data["max_activations"],
                validity=validity_text,
            )
        )

        # Create CSV file with promo codes if any were created
        csv_file = None
        if created_codes:
            success_lines.append(_("admin_bulk_promo_created_count", count=len(created_codes)))
            success_lines.append(_("admin_bulk_promo_csv_sent"))

            # Create CSV file
            output = io.StringIO()
            writer = csv.writer(output)

            # CSV headers
            writer.writerow(
                [
                    _("admin_promo_csv_code"),
                    _("admin_promo_csv_bonus_days"),
                    _("admin_promo_csv_max_activations"),
                    _("admin_promo_csv_valid_until"),
                    _("admin_bulk_promo_csv_start_command"),
                    _("admin_bulk_promo_csv_activation_link"),
                ]
            )

            # Get real bot username
            bot_username = "your_bot"  # fallback
            try:
                if isinstance(callback_or_message, types.CallbackQuery):
                    bot = message_bot(callback_message(callback_or_message))
                else:
                    bot = message_bot(callback_or_message)
                bot_info = await bot.get_me()
                bot_username = bot_info.username or "your_bot"
            except Exception as e:
                logger.error("Failed to get bot username for CSV links: %s", e)
                bot_username = "your_bot"

            for code in created_codes:
                # Determine validity info
                if data.get("validity_days"):
                    valid_until = (
                        datetime.now(UTC) + timedelta(days=data["validity_days"])
                    ).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    valid_until = _("admin_bulk_promo_csv_unlimited")

                start_command = f"/start promo_{code}"
                telegram_link = f"https://t.me/{bot_username}?start=promo_{code}"

                writer.writerow(
                    [
                        code,
                        data["bonus_days"],
                        data["max_activations"],
                        valid_until,
                        start_command,
                        telegram_link,
                    ]
                )

            output.seek(0)

            # Create file for sending
            filename = f"bulk_promo_codes_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
            csv_file = types.BufferedInputFile(
                output.getvalue().encode("utf-8-sig"),  # BOM for correct Excel display
                filename=filename,
            )

        if failed_codes:
            success_lines.append(_("admin_bulk_promo_errors_title", count=len(failed_codes)))
            success_lines.extend(failed_codes[:5])  # Show first 5 errors
            if len(failed_codes) > 5:
                success_lines.append(_("admin_bulk_promo_more_errors", count=len(failed_codes) - 5))

        success_text = "\n".join(success_lines)

        if isinstance(callback_or_message, types.CallbackQuery):
            message = callback_message(callback_or_message)
            try:
                await message.edit_text(
                    success_text,
                    reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
                    parse_mode="HTML",
                )
                message_obj = message
            except Exception:
                message_obj = await message.answer(
                    success_text,
                    reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
                    parse_mode="HTML",
                )
            await callback_or_message.answer()
        else:  # Message
            message_obj = await callback_or_message.answer(
                success_text,
                reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
                parse_mode="HTML",
            )

        # Send CSV file if created
        if csv_file:
            csv_caption = _(
                "admin_bulk_promo_csv_caption",
                count=len(created_codes),
                days=data["bonus_days"],
            )
            await message_obj.answer_document(csv_file, caption=csv_caption)

        await state.clear()

    except Exception as e:
        logger.error("Error creating bulk promo codes: %s", e)
        error_text = _("error_occurred_try_again")

        if isinstance(callback_or_message, types.CallbackQuery):
            await callback_message(callback_or_message).answer(error_text)
        else:  # Message
            await callback_or_message.answer(error_text)

        await state.clear()


# Cancel bulk promo creation
@router.callback_query(
    F.data == "admin_action:main",
    StateFilter(
        AdminStates.waiting_for_bulk_promo_quantity,
        AdminStates.waiting_for_bulk_promo_bonus_days,
        AdminStates.waiting_for_bulk_promo_max_activations,
        AdminStates.waiting_for_bulk_promo_validity_days,
    ),
)
async def cancel_bulk_promo_creation_state_to_menu(
    callback: types.CallbackQuery,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await callback.answer("Error cancelling.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    try:
        await callback_message(callback).edit_text(
            _(key="admin_panel_title"),
            reply_markup=get_admin_panel_keyboard(i18n, current_lang, settings),
        )
    except Exception:
        await callback_message(callback).answer(
            _(key="admin_panel_title"),
            reply_markup=get_admin_panel_keyboard(i18n, current_lang, settings),
        )

    await callback.answer(_("admin_bulk_promo_creation_cancelled"))
    await state.clear()
