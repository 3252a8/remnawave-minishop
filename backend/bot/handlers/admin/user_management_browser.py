import logging

from aiogram import Bot, F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.markdown import hcode
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.admin_keyboards import get_back_to_admin_panel_keyboard
from bot.middlewares.i18n import JsonI18n
from bot.services.panel_api_service import PanelApiService
from bot.services.referral_service import ReferralService
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.states.admin_states import AdminStates
from bot.utils.callback_answer import (
    callback_data,
    callback_message,
    message_bot,
)
from config.settings import Settings
from db.dal import user_dal

from .user_management_cards import (
    _send_with_profile_link_fallback,
    format_user_card,
    get_user_card_keyboard,
)
from .user_management_common import (
    _find_user_by_admin_input,
    _resolve_bot_username,
    router,
)
from .user_management_info import (
    handle_delete_user_prompt,
    handle_refresh_user_card,
    handle_view_user_invitees,
    handle_view_user_logs,
)
from .user_management_overrides import (
    handle_hwid_limit_apply,
    handle_hwid_limit_menu,
    handle_hwid_limit_prompt,
    handle_premium_override_apply,
    handle_premium_override_bonus_prompt,
    handle_premium_override_menu,
)
from .user_management_subscription import (
    handle_add_subscription_days_prompt,
    handle_add_subscription_prompt,
    handle_change_tariff_apply,
    handle_change_tariff_menu,
    handle_reset_trial,
    handle_send_message_prompt,
    handle_toggle_ban,
    handle_traffic_grant_menu,
    handle_traffic_grant_prompt,
)

logger = logging.getLogger(__name__)


async def users_list_handler(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
    page: int = 0,
) -> None:
    """Display paginated list of all users"""
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await callback.answer("Error preparing user list.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    try:
        # Get paginated users
        from bot.keyboards.inline.admin_keyboards import get_users_list_keyboard
        from db.dal import user_dal

        users = await user_dal.get_all_users_paginated(session, page=page, page_size=15)
        total_users = await user_dal.count_all_users(session)
        total_pages = max(1, (total_users + 14) // 15)

        # Format message
        header_text = _(
            "admin_users_list_header", current=page + 1, total=total_pages, total_users=total_users
        )

        keyboard = get_users_list_keyboard(
            users, page, total_users, i18n, current_lang, page_size=15
        )

        await callback_message(callback).edit_text(
            header_text, reply_markup=keyboard, parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error("Error displaying user list: %s", e)
        await callback.answer(_("admin_users_display_error"), show_alert=True)


async def user_search_prompt_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
) -> None:
    """Display search prompt for user management"""
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await callback.answer("Error preparing search.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    prompt_text = _("admin_user_management_prompt")

    try:
        await callback_message(callback).edit_text(
            prompt_text, reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n)
        )
    except Exception as e:
        logger.warning("Could not edit message for user management: %s. Sending new.", e)
        await callback_message(callback).answer(
            prompt_text, reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n)
        )

    await callback.answer()
    await state.set_state(AdminStates.waiting_for_user_search)


@router.message(AdminStates.waiting_for_user_search, F.text)
async def process_user_search_handler(
    message: types.Message,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    subscription_service: SubscriptionService,
    session: AsyncSession,
) -> None:
    """Process user search input and display user card"""
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

    # Store user ID in state for further operations
    await state.update_data(target_user_id=user_model.user_id)
    await state.clear()

    # Format and send user card
    try:
        referral_service = ReferralService(
            settings, subscription_service, message_bot(message), i18n
        )
        bot_username = await _resolve_bot_username(message_bot(message))
        user_card_text = await format_user_card(
            user_model,
            session,
            subscription_service,
            i18n,
            current_lang,
            referral_service,
            settings=settings,
            bot_username=bot_username,
        )
        keyboard = get_user_card_keyboard(
            user_model.user_id, i18n, current_lang, user_model.referred_by_id
        )

        await _send_with_profile_link_fallback(
            message.answer,
            text=user_card_text,
            markup=keyboard.as_markup(),
            user_id=user_model.user_id,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error("Error displaying user card for %s: %s", user_model.user_id, e)
        await message.answer(_("admin_user_card_error"))


@router.callback_query(F.data.startswith("user_action:"))
async def user_action_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    bot: Bot,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
    session: AsyncSession,
) -> None:
    """Handle user management actions"""
    try:
        parts = callback_data(callback).split(":")
        action = parts[1]
        user_id = int(parts[2])
    except (IndexError, ValueError):
        await callback.answer("Invalid action format.", show_alert=True)
        return

    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        await callback.answer("Language service error.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    # Get user from database
    user = await user_dal.get_user_by_id(session, user_id)
    if not user:
        await callback.answer(_("admin_user_not_found_action"), show_alert=True)
        return

    if action == "reset_trial":
        await handle_reset_trial(
            callback, user, subscription_service, session, settings, i18n, current_lang
        )
    elif action == "add_subscription":
        await handle_add_subscription_prompt(callback, state, user, settings, i18n, current_lang)
    elif action == "add_subscription_tariff":
        tariff_key = parts[3] if len(parts) > 3 else ""
        await handle_add_subscription_days_prompt(
            callback,
            state,
            user,
            settings,
            i18n,
            current_lang,
            tariff_key=tariff_key,
        )
    elif action == "change_tariff":
        await handle_change_tariff_menu(
            callback,
            user,
            settings,
            subscription_service,
            session,
            i18n,
            current_lang,
        )
    elif action == "set_tariff":
        tariff_key = parts[3] if len(parts) > 3 else ""
        await handle_change_tariff_apply(
            callback,
            user,
            settings,
            subscription_service,
            session,
            i18n,
            current_lang,
            tariff_key=tariff_key,
        )
    elif action == "toggle_ban":
        await handle_toggle_ban(
            callback,
            user,
            panel_service,
            subscription_service,
            session,
            settings,
            i18n,
            current_lang,
        )
    elif action == "send_message":
        await handle_send_message_prompt(callback, state, user, i18n, current_lang)
    elif action == "view_logs":
        await handle_view_user_logs(callback, user, session, settings, i18n, current_lang)
    elif action == "invitees":
        try:
            page = max(0, int(parts[3])) if len(parts) > 3 else 0
        except (TypeError, ValueError):
            page = 0
        await handle_view_user_invitees(callback, user, session, i18n, current_lang, page=page)
    elif action == "refresh":
        await handle_refresh_user_card(
            callback, user, subscription_service, session, settings, i18n, current_lang
        )
    elif action == "delete_user":
        await handle_delete_user_prompt(
            callback, state, user, settings, i18n, current_lang, session
        )
    elif action == "premium_override":
        await handle_premium_override_menu(
            callback, state, user, subscription_service, session, i18n, current_lang
        )
    elif action == "premium_override_set_unlimited":
        await handle_premium_override_apply(
            callback,
            user,
            subscription_service,
            session,
            settings,
            i18n,
            current_lang,
            unlimited=True,
            bonus_bytes=0,
        )
    elif action == "premium_override_clear":
        await handle_premium_override_apply(
            callback,
            user,
            subscription_service,
            session,
            settings,
            i18n,
            current_lang,
            unlimited=False,
            bonus_bytes=0,
        )
    elif action == "premium_override_set_bonus":
        await handle_premium_override_bonus_prompt(callback, state, user, i18n, current_lang)
    elif action == "traffic_grant":
        await handle_traffic_grant_menu(callback, user, i18n, current_lang)
    elif action == "traffic_grant_regular":
        await handle_traffic_grant_prompt(callback, state, user, "regular", i18n, current_lang)
    elif action == "traffic_grant_premium":
        await handle_traffic_grant_prompt(callback, state, user, "premium", i18n, current_lang)
    elif action == "hwid_limit":
        await handle_hwid_limit_menu(callback, state, user, session, i18n, current_lang)
    elif action == "hwid_limit_set_unlimited":
        await handle_hwid_limit_apply(
            callback,
            user,
            subscription_service,
            session,
            settings,
            i18n,
            current_lang,
            hwid_device_limit=0,
        )
    elif action == "hwid_limit_reset":
        await handle_hwid_limit_apply(
            callback,
            user,
            subscription_service,
            session,
            settings,
            i18n,
            current_lang,
            hwid_device_limit=None,
        )
    elif action == "hwid_limit_set_number":
        await handle_hwid_limit_prompt(callback, state, user, i18n, current_lang)
    else:
        await callback.answer(_("admin_unknown_action"), show_alert=True)
