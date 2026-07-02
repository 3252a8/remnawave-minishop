import logging
from datetime import UTC, datetime

from aiogram import Bot, F, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.utils.markdown import hcode
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.admin_keyboards import get_back_to_admin_panel_keyboard
from bot.middlewares.i18n import JsonI18n
from bot.services.panel_api_service import PanelApiService
from bot.services.referral_service import ReferralService
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.states.admin_states import AdminStates
from bot.utils import get_message_content, send_direct_message
from bot.utils.callback_answer import (
    callback_data,
    callback_message,
    message_bot,
    message_from_user,
)
from config.settings import Settings
from db.dal import message_log_dal, subscription_dal, user_dal

from .user_management_cards import (
    _send_with_profile_link_fallback,
    format_user_card,
    get_user_card_keyboard,
)
from .user_management_common import (
    _find_user_by_admin_input,
    _resolve_admin_period_tariff_key,
    _resolve_bot_username,
    router,
)
from .user_management_overrides import _admin_hwid_limit_state_text


@router.message(AdminStates.waiting_for_subscription_days_to_add, F.text)
async def process_subscription_days_handler(
    message: types.Message,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    subscription_service: SubscriptionService,
    session: AsyncSession,
) -> None:
    """Process subscription days input"""
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        await message.reply("Language service error.")
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    tariff_key = data.get("subscription_tariff_key")
    if not target_user_id:
        await message.answer("Error: target user not found in state")
        await state.clear()
        return
    tariff_key, tariff_error = _resolve_admin_period_tariff_key(settings, tariff_key)
    if tariff_error:
        await message.answer(_(tariff_error))
        return

    try:
        days_to_add = int((message.text or "").strip())
        if days_to_add <= 0 or days_to_add > 3650:  # Max 10 years
            raise ValueError("Invalid days count")
    except ValueError:
        await message.answer(_("admin_user_invalid_days"))
        return

    try:
        # Extend subscription
        result = await subscription_service.extend_active_subscription_days(
            session,
            target_user_id,
            days_to_add,
            "admin_manual_extension",
            tariff_key=tariff_key,
        )

        if result:
            await session.commit()
            await message.answer(
                _(
                    "admin_user_subscription_added_success",
                    days=days_to_add,
                    user_id=target_user_id,
                )
            )

            # Show updated user card
            user = await user_dal.get_user_by_id(session, target_user_id)
            if user:
                referral_service = ReferralService(
                    settings, subscription_service, message_bot(message), i18n
                )
                bot_username = await _resolve_bot_username(message_bot(message))
                user_card_text = await format_user_card(
                    user,
                    session,
                    subscription_service,
                    i18n,
                    current_lang,
                    referral_service,
                    settings=settings,
                    bot_username=bot_username,
                )
                keyboard = get_user_card_keyboard(
                    user.user_id, i18n, current_lang, user.referred_by_id
                )

                await _send_with_profile_link_fallback(
                    message.answer,
                    text=user_card_text,
                    markup=keyboard.as_markup(),
                    user_id=user.user_id,
                    parse_mode="HTML",
                )
        else:
            await session.rollback()
            await message.answer(_("admin_user_subscription_added_error"))

    except Exception as e:
        logging.error(f"Error adding subscription days for user {target_user_id}: {e}")
        await session.rollback()
        await message.answer(_("admin_user_subscription_added_error"))

    await state.clear()


@router.message(AdminStates.waiting_for_direct_message_to_user)
async def process_direct_message_handler(
    message: types.Message,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    bot: Bot,
    session: AsyncSession,
) -> None:
    """Process direct message to user"""
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        await message.reply("Language service error.")
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    if not target_user_id:
        await message.answer("Error: target user not found in state")
        await state.clear()
        return

    # Determine content similar to broadcast
    text = (message.text or message.caption or "").strip()
    if len(text) > 4000:
        await message.answer(_("admin_user_message_too_long"))
        return

    try:
        # Get target user
        target_user = await user_dal.get_user_by_id(session, target_user_id)
        if not target_user:
            await message.answer("Target user not found")
            await state.clear()
            return

        # Prepare admin signature and get content
        admin_signature = _("admin_direct_message_signature")

        content = get_message_content(message)

        if not content.text and not content.file_id:
            await message.answer(_("admin_direct_empty_message"))
            return

        (content.text + admin_signature) if content.text else None

        # Send to target user using our fancy match/case function
        try:
            await send_direct_message(
                bot,
                target_user_id,
                content,
                extra_text=admin_signature,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except TelegramBadRequest as e:
            await message.answer(
                _(
                    "admin_broadcast_invalid_html",
                    error=str(e),
                )
            )
            return

        # Confirm to admin
        await message.answer(_("admin_user_message_sent_success", user_id=target_user_id))

        # Show user card again
        from bot.services.panel_api_service import PanelApiService

        async with PanelApiService(settings) as panel_service:
            subscription_service = SubscriptionService(settings, panel_service)
            referral_service = ReferralService(settings, subscription_service, bot, i18n)
            bot_username = await _resolve_bot_username(bot)
            user_card_text = await format_user_card(
                target_user,
                session,
                subscription_service,
                i18n,
                current_lang,
                referral_service,
                settings=settings,
                bot_username=bot_username,
            )
            keyboard = get_user_card_keyboard(
                target_user.user_id, i18n, current_lang, target_user.referred_by_id
            )

            await _send_with_profile_link_fallback(
                message.answer,
                text=user_card_text,
                markup=keyboard.as_markup(),
                user_id=target_user.user_id,
                parse_mode="HTML",
            )

    except Exception as e:
        logging.error(f"Error sending direct message to user {target_user_id}: {e}")
        await message.answer(_("admin_user_message_sent_error"))

    await state.clear()


async def ban_user_prompt_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
) -> None:
    """Prompt admin to enter user ID or username to ban"""
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await callback.answer("Error preparing ban prompt.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    prompt_text = _("admin_ban_user_prompt")

    try:
        await callback_message(callback).edit_text(
            prompt_text, reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n)
        )
    except Exception as e:
        logging.warning(f"Could not edit message for ban prompt: {e}. Sending new.")
        await callback_message(callback).answer(
            prompt_text, reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n)
        )

    await callback.answer()
    await state.set_state(AdminStates.waiting_for_user_id_to_ban)


async def unban_user_prompt_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
) -> None:
    """Prompt admin to enter user ID or username to unban"""
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await callback.answer("Error preparing unban prompt.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    prompt_text = _("admin_unban_user_prompt")

    try:
        await callback_message(callback).edit_text(
            prompt_text, reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n)
        )
    except Exception as e:
        logging.warning(f"Could not edit message for unban prompt: {e}. Sending new.")
        await callback_message(callback).answer(
            prompt_text, reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n)
        )

    await callback.answer()
    await state.set_state(AdminStates.waiting_for_user_id_to_unban)


async def view_banned_users_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
) -> None:
    """Display list of banned users"""
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await callback.answer("Error preparing banned users list.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    try:
        # Get banned users
        banned_users = await user_dal.get_banned_users(session)

        if not banned_users:
            message_text = _("admin_banned_users_empty")
        else:
            user_list = []
            for user in banned_users:
                display_name = user.first_name or "Unknown"
                if user.username:
                    display_name = f"@{user.username}"
                user_list.append(f"• {display_name} (ID: {user.user_id})")

            message_text = _(
                "admin_banned_users_list", count=len(banned_users), users="\n".join(user_list)
            )

        await callback_message(callback).edit_text(
            message_text, reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n)
        )

    except Exception as e:
        logging.error(f"Error displaying banned users: {e}")
        await callback.answer("Error loading banned users", show_alert=True)


@router.message(AdminStates.waiting_for_user_id_to_ban, F.text)
async def process_ban_user_handler(
    message: types.Message,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    panel_service: PanelApiService,
    session: AsyncSession,
) -> None:
    """Process user ban input"""
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        await message.reply("Language service error.")
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    input_text = (message.text or "").strip() if message.text else ""
    user_model = await _find_user_by_admin_input(session, input_text)

    if not user_model:
        await message.answer(_("admin_user_not_found", input=hcode(input_text)))
        return

    try:
        # Check if user is already banned
        if user_model.is_banned:
            await message.answer(_("admin_user_already_banned"))
            await state.clear()
            return

        # Ban the user
        await user_dal.update_user(session, user_model.user_id, {"is_banned": True})

        # Update on panel if user has panel UUID
        if user_model.panel_user_uuid:
            await panel_service.update_user_status_on_panel(user_model.panel_user_uuid, False)

        await session.commit()

        await message.answer(_("admin_user_ban_success", input=hcode(input_text)))

    except Exception as e:
        logging.error(f"Error banning user {user_model.user_id}: {e}")
        await session.rollback()
        await message.answer(_("admin_user_ban_error"))

    await state.clear()


@router.message(AdminStates.waiting_for_user_id_to_unban, F.text)
async def process_unban_user_handler(
    message: types.Message,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    panel_service: PanelApiService,
    session: AsyncSession,
) -> None:
    """Process user unban input"""
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        await message.reply("Language service error.")
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    input_text = (message.text or "").strip() if message.text else ""
    user_model = await _find_user_by_admin_input(session, input_text)

    if not user_model:
        await message.answer(_("admin_user_not_found", input=hcode(input_text)))
        return

    try:
        # Check if user is not banned
        if not user_model.is_banned:
            await message.answer(_("admin_user_not_banned"))
            await state.clear()
            return

        # Unban the user
        await user_dal.update_user(session, user_model.user_id, {"is_banned": False})

        # Update on panel if user has panel UUID
        if user_model.panel_user_uuid:
            await panel_service.update_user_status_on_panel(user_model.panel_user_uuid, True)

        await session.commit()

        await message.answer(_("admin_user_unban_success", input=hcode(input_text)))

    except Exception as e:
        logging.error(f"Error unbanning user {user_model.user_id}: {e}")
        await session.rollback()
        await message.answer(_("admin_user_unban_error"))

    await state.clear()


@router.message(AdminStates.waiting_for_premium_override_bonus_gb, F.text)
async def process_premium_override_bonus_handler(
    message: types.Message,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    subscription_service: SubscriptionService,
    session: AsyncSession,
) -> None:
    """Read bonus GB and apply premium override (non-unlimited path)."""
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        await message.reply("Language service error.")
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    if not target_user_id:
        await message.answer(_("admin_premium_override_state_missing"))
        await state.clear()
        return

    raw = (message.text or "").strip().replace(",", ".")
    try:
        gb = float(raw)
        if gb < 0 or gb > 1_000_000:
            raise ValueError("out_of_range")
    except (TypeError, ValueError):
        await message.answer(_("admin_premium_override_invalid_gb"))
        return

    bonus_bytes = round(gb * (1024**3))
    target_user = await user_dal.get_user_by_id(session, target_user_id)
    if not target_user:
        await message.answer(_("admin_user_not_found_action"))
        await state.clear()
        return

    try:
        active_sub = await subscription_dal.get_active_subscription_by_user_id(
            session, target_user_id
        )
        if not active_sub:
            await message.answer(_("admin_premium_override_no_subscription"))
            await state.clear()
            return

        active_sub.premium_unlimited_override = False
        active_sub.premium_bonus_bytes = max(0, bonus_bytes)

        await message_log_dal.create_message_log_no_commit(
            session,
            {
                "user_id": message_from_user(message).id if message.from_user else target_user_id,
                "event_type": "admin:premium_override",
                "content": f"unlimited=False bonus_bytes={int(bonus_bytes)}",
                "is_admin_event": True,
                "target_user_id": target_user_id,
                "timestamp": datetime.now(UTC),
            },
        )
        await session.commit()

        await subscription_service.sync_premium_squad_access_to_panel(session, target_user_id)
        await session.commit()

        await message.answer(
            _("admin_premium_override_bonus_set", gb=f"{gb:.2f}", user_id=target_user_id)
        )

        referral_service = ReferralService(
            settings, subscription_service, message_bot(message), i18n
        )
        bot_username = await _resolve_bot_username(message_bot(message))
        user_card_text = await format_user_card(
            target_user,
            session,
            subscription_service,
            i18n,
            current_lang,
            referral_service,
            settings=settings,
            bot_username=bot_username,
        )
        keyboard = get_user_card_keyboard(
            target_user.user_id, i18n, current_lang, target_user.referred_by_id
        )
        await _send_with_profile_link_fallback(
            message.answer,
            text=user_card_text,
            markup=keyboard.as_markup(),
            user_id=target_user.user_id,
            parse_mode="HTML",
        )
    except Exception as exc:
        logging.error(
            "Error setting premium override bonus for user %s: %s",
            target_user_id,
            exc,
            exc_info=True,
        )
        await session.rollback()
        await message.answer(_("admin_premium_override_save_error"))
    finally:
        await state.clear()


@router.message(AdminStates.waiting_for_hwid_device_limit, F.text)
async def process_hwid_device_limit_handler(
    message: types.Message,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    subscription_service: SubscriptionService,
    session: AsyncSession,
) -> None:
    """Read explicit HWID device limit and apply it."""
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        await message.reply("Language service error.")
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    if not target_user_id:
        await message.answer(_("admin_hwid_limit_state_missing"))
        await state.clear()
        return

    raw = (message.text or "").strip()
    try:
        hwid_device_limit = int(raw)
        if hwid_device_limit < 0 or hwid_device_limit > 1_000_000:
            raise ValueError("out_of_range")
    except (TypeError, ValueError):
        await message.answer(_("admin_hwid_limit_invalid"))
        return

    target_user = await user_dal.get_user_by_id(session, target_user_id)
    if not target_user:
        await message.answer(_("admin_user_not_found_action"))
        await state.clear()
        return

    try:
        active_sub = await subscription_dal.get_active_subscription_by_user_id(
            session, target_user_id
        )
        if not active_sub:
            await message.answer(_("admin_hwid_limit_no_subscription"))
            await state.clear()
            return

        active_sub.hwid_device_limit = hwid_device_limit
        effective_limit = await subscription_service.sync_hwid_device_limit_to_panel(
            session, target_user_id
        )
        await message_log_dal.create_message_log_no_commit(
            session,
            {
                "user_id": message_from_user(message).id if message.from_user else target_user_id,
                "event_type": "admin:hwid_device_limit",
                "content": (
                    f"hwid_device_limit={hwid_device_limit!r} "
                    f"effective_hwid_device_limit={effective_limit!r}"
                ),
                "is_admin_event": True,
                "target_user_id": target_user_id,
                "timestamp": datetime.now(UTC),
            },
        )
        await session.commit()

        current_text = _admin_hwid_limit_state_text(_, hwid_device_limit)
        await message.answer(
            _("admin_hwid_limit_set", current=current_text, user_id=target_user_id)
        )

        referral_service = ReferralService(
            settings, subscription_service, message_bot(message), i18n
        )
        bot_username = await _resolve_bot_username(message_bot(message))
        user_card_text = await format_user_card(
            target_user,
            session,
            subscription_service,
            i18n,
            current_lang,
            referral_service,
            settings=settings,
            bot_username=bot_username,
        )
        keyboard = get_user_card_keyboard(
            target_user.user_id, i18n, current_lang, target_user.referred_by_id
        )
        await _send_with_profile_link_fallback(
            message.answer,
            text=user_card_text,
            markup=keyboard.as_markup(),
            user_id=target_user.user_id,
            parse_mode="HTML",
        )
    except Exception as exc:
        logging.error(
            "Error setting HWID device limit for user %s: %s",
            target_user_id,
            exc,
            exc_info=True,
        )
        await session.rollback()
        await message.answer(_("admin_hwid_limit_save_error"))
    finally:
        await state.clear()


@router.message(AdminStates.waiting_for_traffic_grant_gb, F.text)
async def process_traffic_grant_gb_handler(
    message: types.Message,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    subscription_service: SubscriptionService,
    session: AsyncSession,
) -> None:
    """Read GB amount and apply admin grant of regular or premium traffic."""
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        await message.reply("Language service error.")
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    kind = (data.get("traffic_grant_kind") or "regular").lower()
    if not target_user_id:
        await message.answer(_("admin_traffic_grant_no_user"))
        await state.clear()
        return

    raw = (message.text or "").strip().replace(",", ".")
    try:
        gb_value = float(raw)
        if gb_value <= 0 or gb_value > 1_000_000:
            raise ValueError("out_of_range")
    except (TypeError, ValueError):
        await message.answer(_("admin_traffic_grant_invalid_gb"))
        return

    target_user = await user_dal.get_user_by_id(session, target_user_id)
    if not target_user:
        await message.answer(_("admin_user_not_found_action"))
        await state.clear()
        return

    try:
        if kind == "premium":
            result = await subscription_service.admin_grant_premium_topup(
                session, target_user_id, gb_value
            )
        else:
            result = await subscription_service.admin_grant_topup(session, target_user_id, gb_value)
        if not result:
            await session.rollback()
            await message.answer(_("admin_traffic_grant_failed"))
            await state.clear()
            return
        await message_log_dal.create_message_log_no_commit(
            session,
            {
                "user_id": message_from_user(message).id if message.from_user else target_user_id,
                "event_type": "admin:traffic_grant",
                "content": f"kind={kind} gb={gb_value:g}",
                "is_admin_event": True,
                "target_user_id": target_user_id,
                "timestamp": datetime.now(UTC),
            },
        )
        await session.commit()

        gb_text = f"{gb_value:g}"
        success_key = (
            "admin_traffic_grant_premium_done"
            if kind == "premium"
            else "admin_traffic_grant_regular_done"
        )
        await message.answer(_(success_key, gb=gb_text, user_id=target_user_id))

        referral_service = ReferralService(
            settings, subscription_service, message_bot(message), i18n
        )
        bot_username = await _resolve_bot_username(message_bot(message))
        user_card_text = await format_user_card(
            target_user,
            session,
            subscription_service,
            i18n,
            current_lang,
            referral_service,
            settings=settings,
            bot_username=bot_username,
        )
        keyboard = get_user_card_keyboard(
            target_user.user_id, i18n, current_lang, target_user.referred_by_id
        )
        await _send_with_profile_link_fallback(
            message.answer,
            text=user_card_text,
            markup=keyboard.as_markup(),
            user_id=target_user.user_id,
            parse_mode="HTML",
        )
    except Exception as exc:
        logging.error(
            "Error granting traffic for user %s (kind=%s, gb=%s): %s",
            target_user_id,
            kind,
            gb_value,
            exc,
            exc_info=True,
        )
        await session.rollback()
        await message.answer(_("admin_traffic_grant_failed"))
    finally:
        await state.clear()


@router.callback_query(F.data.startswith("admin_user_card_from_list:"))
async def user_card_from_list_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    i18n_data: dict,
    settings: Settings,
    bot: Bot,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
    session: AsyncSession,
) -> None:
    """Display user card when clicked from user list"""
    try:
        parts = callback_data(callback).split(":")
        user_id = int(parts[1])
        page = int(parts[2])
    except (IndexError, ValueError):
        await callback.answer("Invalid user data", show_alert=True)
        return

    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        await callback.answer("Language service error", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    # Get user from database
    user = await user_dal.get_user_by_id(session, user_id)
    if not user:
        await callback.answer("User not found", show_alert=True)
        return

    # Create keyboard with back to list button
    keyboard = get_user_card_keyboard(user_id, i18n, current_lang, user.referred_by_id)
    keyboard.button(
        text=_("admin_user_back_to_list_button"), callback_data=f"admin_action:users_list:{page}"
    )
    quick_links_width = 2 if user.referred_by_id else 1
    keyboard.adjust(2, 2, 2, 1, 2, quick_links_width, 1, 2, 1)

    # Format user card
    try:
        from bot.services.referral_service import ReferralService

        referral_service = ReferralService(settings, subscription_service, bot, i18n)
        bot_username = await _resolve_bot_username(bot)
        user_card_text = await format_user_card(
            user,
            session,
            subscription_service,
            i18n,
            current_lang,
            referral_service,
            settings=settings,
            bot_username=bot_username,
        )
        markup = keyboard.as_markup()

        await _send_with_profile_link_fallback(
            callback_message(callback).edit_text,
            text=user_card_text,
            markup=markup,
            user_id=user.user_id,
            parse_mode="HTML",
        )
        await callback.answer()

    except Exception as e:
        logging.error(f"Error displaying user card: {e}")
        await callback.answer("Error displaying user card", show_alert=True)
