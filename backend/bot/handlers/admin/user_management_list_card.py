import logging

from aiogram import Bot, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.utils.callback_answer import callback_data, callback_message
from config.settings import Settings
from db.dal import user_dal

from .user_management_cards import (
    _send_with_profile_link_fallback,
    format_user_card,
    get_user_card_keyboard,
)
from .user_management_common import _resolve_bot_username, router

logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("admin_user_card_from_list:"))
@router.callback_query(F.data.startswith("admin_user_card:"))
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
    """Show the user card and keep the return path to its originating list."""
    try:
        source, user_id_value, page_value = callback_data(callback).split(":", 2)
        user_id = int(user_id_value)
        page = int(page_value)
    except ValueError:
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
    keyboard = get_user_card_keyboard(
        user_id, i18n, current_lang, user.referred_by_id, telegram_id=user.telegram_id
    )
    from_banned_list = source == "admin_user_card"
    back_label = (
        "user_card_back_to_banned_list_button"
        if from_banned_list
        else "admin_user_back_to_list_button"
    )
    back_action = "view_banned" if from_banned_list else "users_list"
    keyboard.button(text=_(back_label), callback_data=f"admin_action:{back_action}:{page}")
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
        logger.error("Error displaying user card: %s", e)
        await callback.answer("Error displaying user card", show_alert=True)
