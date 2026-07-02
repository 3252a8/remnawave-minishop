import logging

from aiogram import types
from aiogram.utils.text_decorations import html_decoration as hd
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import (
    get_bot_interface_inline_keyboard,
    get_main_menu_inline_keyboard,
)
from bot.middlewares.i18n import JsonI18n
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.utils.callback_answer import (
    callback_message,
    message_from_user,
    safe_answer_callback,
)
from config.settings import Settings


async def should_show_trial_button(
    settings: Settings,
    subscription_service: SubscriptionService,
    session: AsyncSession,
    user_id: int,
) -> bool:
    if not settings.TRIAL_ENABLED:
        return False

    if hasattr(subscription_service, "has_trial_blocking_subscription") and callable(
        subscription_service.has_trial_blocking_subscription
    ):
        return not await subscription_service.has_trial_blocking_subscription(session, user_id)

    logging.error("Method has_trial_blocking_subscription is missing in SubscriptionService!")
    return False


async def send_main_menu(
    target_event: types.Message | types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    subscription_service: SubscriptionService,
    session: AsyncSession,
    is_edit: bool = False,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")

    event_user = (
        target_event.from_user
        if isinstance(target_event, types.CallbackQuery)
        else message_from_user(target_event)
    )
    user_id = event_user.id
    user_full_name = hd.quote(event_user.full_name)

    if not i18n:
        logging.error(f"i18n_instance missing in send_main_menu for user {user_id}")
        err_msg_fallback = "Error: Language service unavailable. Please try again later."
        if isinstance(target_event, types.CallbackQuery):
            try:
                await target_event.answer(err_msg_fallback, show_alert=True)
            except Exception:
                pass
        elif isinstance(target_event, types.Message):
            try:
                await target_event.answer(err_msg_fallback)
            except Exception:
                pass
        return

    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    show_trial_button_in_menu = await should_show_trial_button(
        settings, subscription_service, session, user_id
    )

    text = _(key="main_menu_greeting", user_name=user_full_name)
    reply_markup = get_main_menu_inline_keyboard(
        current_lang,
        i18n,
        settings,
        show_trial_button_in_menu,
        user_id=user_id,
    )

    target_message_obj: types.Message | None = None
    if isinstance(target_event, types.Message):
        target_message_obj = target_event
    elif isinstance(target_event, types.CallbackQuery) and target_event.message:
        target_message_obj = callback_message(target_event)

    if not target_message_obj:
        logging.error(f"send_main_menu: target_message_obj is None for event from user {user_id}.")
        if isinstance(target_event, types.CallbackQuery):
            await safe_answer_callback(
                target_event,
                _("error_displaying_menu"),
                show_alert=True,
            )
        return

    try:
        if is_edit:
            await target_message_obj.edit_text(text, reply_markup=reply_markup)
        else:
            await target_message_obj.answer(text, reply_markup=reply_markup)

        if isinstance(target_event, types.CallbackQuery):
            await safe_answer_callback(target_event)
    except Exception as e_send_edit:
        logging.warning(
            f"Failed to send/edit main menu (user: {user_id}, is_edit: {is_edit}): {type(e_send_edit).__name__} - {e_send_edit}."  # noqa: E501
        )
        if is_edit and target_message_obj:
            try:
                await target_message_obj.answer(text, reply_markup=reply_markup)
            except Exception as e_send_new:
                logging.error(
                    f"Also failed to send new main menu message for user {user_id}: {e_send_new}"
                )
        if isinstance(target_event, types.CallbackQuery):
            await safe_answer_callback(
                target_event,
                _("error_occurred_try_again") if is_edit else None,
            )


async def send_bot_interface_menu(
    target_event: types.Message | types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    subscription_service: SubscriptionService,
    session: AsyncSession,
    is_edit: bool = False,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")

    if not i18n:
        logging.error("i18n_instance missing in send_bot_interface_menu.")
        return

    event_user = (
        target_event.from_user
        if isinstance(target_event, types.CallbackQuery)
        else message_from_user(target_event)
    )
    user_id = event_user.id
    show_trial_button_in_menu = await should_show_trial_button(
        settings, subscription_service, session, user_id
    )

    text = i18n.gettext(current_lang, "bot_interface_menu_title")
    if settings.SUBSCRIPTION_MINI_APP_URL:
        text = f"{text}\n\n{i18n.gettext(current_lang, 'bot_interface_menu_webapp_hint')}"
    reply_markup = get_bot_interface_inline_keyboard(
        current_lang, i18n, settings, show_trial_button_in_menu
    )

    target_message_obj: types.Message | None = None
    if isinstance(target_event, types.Message):
        target_message_obj = target_event
    elif isinstance(target_event, types.CallbackQuery) and target_event.message:
        target_message_obj = callback_message(target_event)

    if not target_message_obj:
        logging.error(
            "send_bot_interface_menu: target_message_obj is None for user %s.",
            user_id,
        )
        return

    try:
        if is_edit:
            await target_message_obj.edit_text(text, reply_markup=reply_markup)
        else:
            await target_message_obj.answer(text, reply_markup=reply_markup)

        if isinstance(target_event, types.CallbackQuery):
            await safe_answer_callback(target_event)
    except Exception as e_send_edit:
        logging.warning(
            "Failed to send/edit bot interface menu (user: %s, is_edit: %s): %s - %s.",
            user_id,
            is_edit,
            type(e_send_edit).__name__,
            e_send_edit,
        )
        if is_edit:
            try:
                await target_message_obj.answer(text, reply_markup=reply_markup)
            except Exception as e_send_new:
                logging.error(
                    "Also failed to send new bot interface menu for user %s: %s",
                    user_id,
                    e_send_new,
                )
