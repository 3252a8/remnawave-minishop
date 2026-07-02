import contextlib
import logging

from aiogram import Bot, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.text_decorations import html_decoration as hd
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import (
    get_information_links_keyboard,
    get_language_selection_keyboard,
    telegram_bot_menu_enabled_for_user,
)
from bot.middlewares.i18n import JsonI18n, normalize_locale_language_code
from bot.services.panel_api_service import PanelApiService
from bot.services.promo_code_service import PromoCodeService
from bot.services.referral_service import ReferralService
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.utils.callback_answer import (
    callback_data,
    callback_message,
    message_from_user,
    safe_answer_callback,
)
from config.settings import Settings
from db.dal import user_dal

from .start_channel import ensure_required_channel_subscription
from .start_common import (
    router,
)
from .start_menus import send_bot_interface_menu, send_main_menu


@router.message(Command("tg"))
async def tg_interface_command_handler(
    message: types.Message,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    subscription_service: SubscriptionService,
    session: AsyncSession,
) -> None:
    await state.clear()

    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    db_user = await user_dal.get_user_by_id(session, message_from_user(message).id)
    if not await ensure_required_channel_subscription(
        message, settings, i18n, current_lang, session, db_user
    ):
        return

    if not telegram_bot_menu_enabled_for_user(settings, user_id=message_from_user(message).id):
        await send_main_menu(
            message, settings, i18n_data, subscription_service, session, is_edit=False
        )
        return

    await send_bot_interface_menu(
        message, settings, i18n_data, subscription_service, session, is_edit=False
    )


@router.callback_query(F.data == "channel_subscription:verify")
async def verify_channel_subscription_callback(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    subscription_service: SubscriptionService,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")

    db_user = await user_dal.get_user_by_id(session, callback.from_user.id)

    verified = await ensure_required_channel_subscription(
        callback, settings, i18n, current_lang, session, db_user
    )
    if not verified:
        return

    if db_user and db_user.language_code:
        current_lang = db_user.language_code
        i18n_data["current_language"] = current_lang

    if i18n:
        _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)
    else:
        _ = lambda key, **kwargs: key

    if not settings.DISABLE_WELCOME_MESSAGE:
        welcome_text = _(key="welcome", user_name=hd.quote(callback.from_user.full_name))
        if callback.message:
            await callback_message(callback).answer(welcome_text)
        else:
            fallback_bot: Bot | None = getattr(callback, "bot", None)
            if fallback_bot:
                await fallback_bot.send_message(callback.from_user.id, welcome_text)

    with contextlib.suppress(Exception):
        await safe_answer_callback(
            callback,
            _(key="channel_subscription_verified_success"),
            show_alert=True,
        )

    await send_main_menu(
        callback, settings, i18n_data, subscription_service, session, is_edit=bool(callback.message)
    )


@router.message(Command("language"))
@router.callback_query(F.data == "main_action:language")
async def language_command_handler(
    event: types.Message | types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    back_callback: str = "main_action:back_to_main",
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    text_to_send = _(key="choose_language")
    reply_markup = get_language_selection_keyboard(
        i18n,
        current_lang,
        back_callback=back_callback,
    )

    target_message_obj = event.message if isinstance(event, types.CallbackQuery) else event
    if not target_message_obj:
        if isinstance(event, types.CallbackQuery):
            await safe_answer_callback(
                event,
                _("error_occurred_try_again"),
                show_alert=True,
            )
        return

    if isinstance(event, types.CallbackQuery):
        if event.message:
            try:
                await callback_message(event).edit_text(text_to_send, reply_markup=reply_markup)
            except Exception:
                await target_message_obj.answer(text_to_send, reply_markup=reply_markup)
        await safe_answer_callback(event)
    else:
        await target_message_obj.answer(text_to_send, reply_markup=reply_markup)


@router.callback_query(F.data.startswith("set_lang_"))
async def select_language_callback_handler(
    callback: types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    subscription_service: SubscriptionService,
    session: AsyncSession,
) -> None:
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await safe_answer_callback(
            callback,
            "Service error or message context lost.",
            show_alert=True,
        )
        return

    try:
        lang_payload = callback_data(callback).split("_", 2)[2]
        raw_lang_code, _, return_target = lang_payload.partition(":")
        lang_code = normalize_locale_language_code(
            raw_lang_code,
            set(i18n.locales_data.keys()),
            prefer_known_base=True,
        )
    except IndexError:
        await safe_answer_callback(
            callback,
            "Error processing language selection.",
            show_alert=True,
        )
        return
    if lang_code not in i18n.locales_data:
        await safe_answer_callback(
            callback,
            "Unsupported language.",
            show_alert=True,
        )
        return

    user_id = callback.from_user.id
    try:
        updated = await user_dal.update_user_language(session, user_id, lang_code)
        if updated:
            i18n_data["current_language"] = lang_code
            _ = lambda key, **kwargs: i18n.gettext(lang_code, key, **kwargs)
            await safe_answer_callback(callback, _(key="language_set_alert"))
            logging.info(f"User {user_id} language updated to {lang_code} in session.")
        else:
            await safe_answer_callback(
                callback,
                "Could not set language.",
                show_alert=True,
            )
            return
    except Exception as e_lang_update:
        logging.error(f"Error updating lang for user {user_id}: {e_lang_update}", exc_info=True)
        await safe_answer_callback(callback, "Error setting language.", show_alert=True)
        return
    if return_target == "bot" and telegram_bot_menu_enabled_for_user(
        settings, user_id=callback.from_user.id
    ):
        await send_bot_interface_menu(
            callback, settings, i18n_data, subscription_service, session, is_edit=True
        )
    else:
        await send_main_menu(
            callback, settings, i18n_data, subscription_service, session, is_edit=True
        )


@router.callback_query(F.data.startswith("main_action:"))
async def main_action_callback_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    bot: Bot,
    subscription_service: SubscriptionService,
    referral_service: ReferralService,
    panel_service: PanelApiService,
    promo_code_service: PromoCodeService,
    session: AsyncSession,
) -> None:
    action = callback_data(callback).split(":")[1]

    if action in {"back_to_main", "back_to_main_keep", "bot_interface"}:
        await state.clear()

    from . import promo_user as user_promo_handlers
    from . import referral as user_referral_handlers
    from . import subscription as user_subscription_handlers
    from . import trial_handler as user_trial_handlers

    if not callback.message:
        await safe_answer_callback(
            callback,
            "Error: message context lost.",
            show_alert=True,
        )
        return

    bot_interface_actions = {
        "bot_interface",
        "bot_subscribe",
        "bot_my_subscription",
        "bot_referral",
        "bot_apply_promo",
        "bot_language",
        "bot_info",
    }
    if action in bot_interface_actions and not telegram_bot_menu_enabled_for_user(
        settings, user_id=callback.from_user.id
    ):
        await send_main_menu(
            callback, settings, i18n_data, subscription_service, session, is_edit=True
        )
        return

    if action == "subscribe":
        await user_subscription_handlers.display_subscription_options(
            callback, i18n_data, settings, session
        )
    elif action == "bot_subscribe":
        await user_subscription_handlers.display_subscription_options(
            callback,
            i18n_data,
            settings,
            session,
            back_callback="main_action:bot_interface",
        )
    elif action == "my_subscription":
        await user_subscription_handlers.my_subscription_command_handler(
            callback, i18n_data, settings, panel_service, subscription_service, session, bot
        )
    elif action == "bot_my_subscription":
        await user_subscription_handlers.my_subscription_command_handler(
            callback,
            i18n_data,
            settings,
            panel_service,
            subscription_service,
            session,
            bot,
            back_callback="main_action:bot_interface",
        )
    elif action == "my_devices":
        await user_subscription_handlers.my_devices_command_handler(
            callback, i18n_data, settings, panel_service, subscription_service, session, bot
        )
    elif action == "referral":
        await user_referral_handlers.referral_command_handler(
            callback, settings, i18n_data, referral_service, bot, session
        )
    elif action == "bot_referral":
        await user_referral_handlers.referral_command_handler(
            callback,
            settings,
            i18n_data,
            referral_service,
            bot,
            session,
            back_callback="main_action:bot_interface",
        )
    elif action == "apply_promo":
        await user_promo_handlers.prompt_promo_code_input(
            callback, state, i18n_data, settings, session
        )
    elif action == "bot_apply_promo":
        await user_promo_handlers.prompt_promo_code_input(
            callback,
            state,
            i18n_data,
            settings,
            session,
            back_callback="main_action:bot_interface",
        )
    elif action == "request_trial":
        await user_trial_handlers.request_trial_confirmation_handler(
            callback, settings, i18n_data, subscription_service, session
        )
    elif action == "language":
        await language_command_handler(callback, i18n_data, settings)
    elif action == "bot_language":
        await language_command_handler(
            callback,
            i18n_data,
            settings,
            back_callback="main_action:bot_interface",
        )
    elif action == "bot_interface":
        await send_bot_interface_menu(
            callback, settings, i18n_data, subscription_service, session, is_edit=True
        )
    elif action in {"info", "bot_info"}:
        i18n: JsonI18n | None = i18n_data.get("i18n_instance")
        current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
        if not i18n:
            await safe_answer_callback(
                callback,
                "Language service error.",
                show_alert=True,
            )
            return
        _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

        privacy_url = settings.PRIVACY_POLICY_URL
        user_agreement_url = settings.USER_AGREEMENT_URL

        if not privacy_url and not user_agreement_url:
            await safe_answer_callback(
                callback,
                _("error_occurred_try_again"),
                show_alert=True,
            )
            return

        reply_markup = get_information_links_keyboard(
            current_lang,
            i18n,
            privacy_url,
            user_agreement_url,
            back_callback=(
                "main_action:bot_interface"
                if callback.data == "main_action:bot_info"
                else "main_action:back_to_main"
            ),
        )
        try:
            await callback_message(callback).edit_text(
                _(key="info_links_message"), reply_markup=reply_markup
            )
        except Exception:
            await callback_message(callback).answer(
                _(key="info_links_message"), reply_markup=reply_markup
            )
        await safe_answer_callback(callback)
    elif action == "back_to_main":
        await send_main_menu(
            callback, settings, i18n_data, subscription_service, session, is_edit=True
        )
    elif action == "back_to_main_keep":
        await send_main_menu(
            callback, settings, i18n_data, subscription_service, session, is_edit=False
        )
    else:
        fallback_i18n: JsonI18n | None = i18n_data.get("i18n_instance")
        _ = lambda key, **kwargs: (
            fallback_i18n.gettext(i18n_data.get("current_language"), key, **kwargs)
            if fallback_i18n
            else key
        )
        await safe_answer_callback(
            callback,
            _("main_menu_unknown_action"),
            show_alert=True,
        )
