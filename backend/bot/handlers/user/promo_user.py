import logging
import re
from datetime import datetime

from aiogram import Bot, F, Router, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import (
    get_back_to_main_menu_markup,
    get_connect_and_main_keyboard,
)
from bot.middlewares.i18n import JsonI18n
from bot.services.promo_code_service import PromoCheckoutRequired, PromoCodeService
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.states.user_states import UserPromoStates
from bot.utils.callback_answer import callback_message, message_from_user, safe_answer_callback
from bot.utils.install_links import (
    append_install_share_link_text,
    ensure_user_install_guide_links,
)
from bot.utils.mini_app_url import subscription_mini_app_checkout_code_url
from config.settings import Settings
from db.dal import user_dal

from .start import send_main_menu

logger = logging.getLogger(__name__)

router = Router(name="user_promo_router")

SUSPICIOUS_SQL_KEYWORDS_REGEX = re.compile(
    r"\b(DROP\s*TABLE|DELETE\s*FROM|ALTER\s*TABLE|TRUNCATE\s*TABLE|UNION\s*SELECT|"
    r";\s*SELECT|;\s*INSERT|;\s*UPDATE|;\s*DELETE|xp_cmdshell|sysdatabases|sysobjects|INFORMATION_SCHEMA)\b",
    re.IGNORECASE,
)
SUSPICIOUS_CHARS_REGEX = re.compile(r"(--|#\s|;|\*\/|\/\*)")
MAX_PROMO_CODE_INPUT_LENGTH = 100


async def prompt_promo_code_input(
    callback: types.CallbackQuery,
    state: FSMContext,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
    back_callback: str = "main_action:back_to_main",
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        await safe_answer_callback(callback, "Language service error.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    if not callback.message:
        logger.error("CallbackQuery has no message in prompt_promo_code_input")
        await safe_answer_callback(
            callback,
            _("error_occurred_processing_request"),
            show_alert=True,
        )
        return

    try:
        await callback_message(callback).edit_text(
            text=_(key="promo_code_prompt"),
            reply_markup=get_back_to_main_menu_markup(
                current_lang,
                i18n,
                callback_data=back_callback,
            ),
        )
    except Exception as e_edit:
        logger.warning("Failed to edit message for promo prompt: %s. Sending new one.", e_edit)
        await callback_message(callback).answer(
            text=_(key="promo_code_prompt"),
            reply_markup=get_back_to_main_menu_markup(
                current_lang,
                i18n,
                callback_data=back_callback,
            ),
        )

    await safe_answer_callback(callback)
    await state.set_state(UserPromoStates.waiting_for_promo_code)
    logger.info(
        "User %s entered state UserPromoStates.waiting_for_promo_code. FSM state: %s",
        callback.from_user.id,
        await state.get_state(),
    )


@router.message(UserPromoStates.waiting_for_promo_code, F.text)
async def process_promo_code_input(
    message: types.Message,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    promo_code_service: PromoCodeService,
    subscription_service: SubscriptionService,
    bot: Bot,
    session: AsyncSession,
) -> None:
    logger.info(
        "Processing promo code input from user %s in state %s: '%s'",
        message_from_user(message).id,
        await state.get_state(),
        message.text,
    )

    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")

    if not i18n or not promo_code_service:
        logger.error("Dependencies (i18n or PromoCodeService) missing in process_promo_code_input")
        await message.reply("Service error. Please try again later.")
        await state.clear()
        return

    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)
    code_input = (message.text or "").strip() if message.text else ""
    user = message_from_user(message)

    is_suspicious = False
    if not code_input:
        is_suspicious = True
        logger.warning("Empty promo code input by user %s.", user.id)
    elif (
        len(code_input) > MAX_PROMO_CODE_INPUT_LENGTH
        or SUSPICIOUS_SQL_KEYWORDS_REGEX.search(code_input)
        or SUSPICIOUS_CHARS_REGEX.search(code_input)
    ):
        is_suspicious = True
        logger.warning(
            "Suspicious input for promo code by user %s (len: %s): '%s'",
            user.id,
            len(code_input),
            code_input,
        )

    response_to_user_text = ""
    if is_suspicious and settings.LOG_SUSPICIOUS_ACTIVITY:
        # Send notification through NotificationService if enabled
        try:
            from bot.services.notification_service import NotificationService

            notification_service = NotificationService(bot, settings, i18n)
            db_user = await user_dal.get_user_by_id(session, user.id)
            await notification_service.notify_suspicious_promo_attempt(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                email=getattr(db_user, "email", None) if db_user else None,
                suspicious_input=code_input,
            )
        except Exception as e:
            logger.error("Failed to send suspicious promo notification: %s", e)

    success, result = await promo_code_service.apply_promo_code(
        session, user.id, code_input, current_lang
    )
    if success and isinstance(result, PromoCheckoutRequired):
        await session.commit()
        logger.info(
            "Code '%s' requires checkout for user %s; sending Mini App handoff.",
            code_input,
            user.id,
        )
        checkout_url = subscription_mini_app_checkout_code_url(settings, result.code or code_input)
        reply_markup = None
        if checkout_url:
            reply_markup = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text=_("open_mini_app"),
                            web_app=types.WebAppInfo(url=checkout_url),
                        )
                    ]
                ]
            )

        await message.answer(
            _("promo_code_requires_checkout", effect=result.effect_summary),
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        await state.clear()
        logger.info(
            "Promo code input '%s' processing finished for user %s. State cleared.",
            code_input,
            user.id,
        )
        return

    if success:
        await session.commit()
        logger.info("Promo code '%s' successfully applied for user %s.", code_input, user.id)

        new_end_date = result if isinstance(result, datetime) else None
        active = await subscription_service.get_active_subscription_details(session, user.id)
        config_link_display = active.get("config_link") if active else None
        connect_button_url = active.get("connect_button_url") if active else None
        config_link_text = config_link_display or _("config_link_not_available")

        response_to_user_text = _(
            "promo_code_applied_success_full",
            end_date=(new_end_date.strftime("%d.%m.%Y %H:%M:%S") if new_end_date else "N/A"),
            config_link=config_link_text,
        )
        install_links = await ensure_user_install_guide_links(session, settings, user.id)
        install_share_url = install_links.public_share_url
        if install_share_url:
            try:
                await session.commit()
                response_to_user_text = append_install_share_link_text(
                    response_to_user_text,
                    _,
                    install_share_url,
                )
            except Exception:
                await session.rollback()
                logger.exception(
                    "Failed to persist install guide share token for promo user %s.",
                    user.id,
                )
                install_share_url = None
        reply_markup = get_connect_and_main_keyboard(
            current_lang,
            i18n,
            settings,
            config_link_display,
            connect_button_url=connect_button_url,
            install_share_url=install_share_url,
        )
    else:
        await session.commit()
        logger.info(
            "Promo code '%s' application failed for user %s. Reason: %s",
            code_input,
            user.id,
            result,
        )
        response_to_user_text = result
        reply_markup = get_back_to_main_menu_markup(current_lang, i18n)

    await message.answer(
        response_to_user_text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )
    await state.clear()
    logger.info(
        "Promo code input '%s' processing finished for user %s. State cleared.",
        code_input,
        message_from_user(message).id,
    )


@router.callback_query(F.data == "main_action:back_to_main", UserPromoStates.waiting_for_promo_code)
async def cancel_promo_input_via_button(
    callback: types.CallbackQuery,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    subscription_service: SubscriptionService,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        logger.error("i18n missing in cancel_promo_input_via_button")
        await safe_answer_callback(callback, "Language error", show_alert=True)
        return

    logger.info(
        "User %s cancelled promo code input via button from state %s. Clearing state.",
        callback.from_user.id,
        await state.get_state(),
    )
    await state.clear()

    if callback.message:
        await send_main_menu(
            callback, settings, i18n_data, subscription_service, session, is_edit=True
        )
    else:
        _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)
        await safe_answer_callback(
            callback,
            _("promo_input_cancelled_short"),
            show_alert=False,
        )
