import logging
from datetime import datetime, timezone
from typing import Any, Optional, Union

from aiogram import Bot, types
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import (
    get_channel_subscription_keyboard,
)
from bot.middlewares.i18n import JsonI18n
from bot.utils.callback_answer import (
    callback_message,
    message_bot,
    message_from_user,
)
from bot.utils.channel_subscription import (
    is_required_channel_access_error,
    normalize_required_channel_id,
    resolve_required_channel_link,
)
from config.settings import Settings
from db.dal import user_dal
from db.models import User


async def ensure_required_channel_subscription(
    event: Union[types.Message, types.CallbackQuery],
    settings: Settings,
    i18n: Optional[JsonI18n],
    current_lang: str,
    session: AsyncSession,
    db_user: Optional[User] = None,
) -> bool:
    """
    Verify that the user is a member of the required channel (if configured).
    Returns True when access can proceed, False when user must subscribe first.
    """
    required_channel_id = normalize_required_channel_id(settings.REQUIRED_CHANNEL_ID)
    if not required_channel_id:
        return True

    if isinstance(event, types.CallbackQuery):
        user_id = event.from_user.id
        bot_instance: Optional[Bot] = getattr(event, "bot", None)
        if bot_instance is None and event.message:
            bot_instance = message_bot(callback_message(event))
        message_obj: Optional[types.Message] = callback_message(event) if event.message else None
    else:
        user_id = message_from_user(event).id
        bot_instance = event.bot if hasattr(event, "bot") else None
        message_obj = event

    if bot_instance is None:
        logging.error("Channel subscription check: bot instance missing for user %s.", user_id)
        return False

    if user_id in settings.ADMIN_IDS:
        return True

    if db_user is None:
        try:
            db_user = await user_dal.get_user_by_id(session, user_id)
        except Exception as fetch_error:
            logging.error(
                "Channel subscription check: failed to fetch user %s: %s",
                user_id,
                fetch_error,
                exc_info=True,
            )
            return False

    if not db_user:
        logging.warning(
            "Required channel check skipped because user %s is not persisted yet.",
            user_id,
        )
        return True

    if (
        db_user.channel_subscription_verified
        and db_user.channel_subscription_verified_for == required_channel_id
    ):
        return True

    def translate(key: str, **kwargs: Any) -> str:
        if i18n:
            return str(i18n.gettext(current_lang, key, **kwargs))
        return key

    now = datetime.now(timezone.utc)
    is_member = False
    status_value = None

    try:
        member = await bot_instance.get_chat_member(required_channel_id, user_id)
        status = getattr(member, "status", None)
        status_value = getattr(status, "value", status)
        allowed_statuses = {"creator", "administrator", "member", "restricted"}
        if status_value in allowed_statuses:
            is_member = True
    except TelegramBadRequest as bad_request:
        if is_required_channel_access_error(bad_request):
            logging.error(
                "Required channel check failed due to channel access/configuration error "
                "(configured=%s, normalized=%s): %s",
                settings.REQUIRED_CHANNEL_ID,
                required_channel_id,
                bad_request,
            )
            error_text = translate("channel_subscription_check_failed")
            if isinstance(event, types.CallbackQuery):
                try:
                    await event.answer(error_text, show_alert=True)
                except Exception:
                    pass
                if message_obj:
                    try:
                        await message_obj.answer(error_text)
                    except Exception:
                        pass
            else:
                await event.answer(error_text)
            return False

        logging.info(
            "Required channel check: user %s not subscribed (details: %s)",
            user_id,
            bad_request,
        )
    except TelegramForbiddenError as forbidden_error:
        logging.error(
            "Required channel check failed due to insufficient permissions: %s",
            forbidden_error,
        )
        error_text = translate("channel_subscription_check_failed")
        if isinstance(event, types.CallbackQuery):
            try:
                await event.answer(error_text, show_alert=True)
            except Exception:
                pass
            if message_obj:
                try:
                    await message_obj.answer(error_text)
                except Exception:
                    pass
        else:
            await event.answer(error_text)
        return False
    except TelegramAPIError as api_error:
        logging.error(
            "Required channel check failed for user %s: %s",
            user_id,
            api_error,
            exc_info=True,
        )
        error_text = translate("channel_subscription_check_failed")
        if isinstance(event, types.CallbackQuery):
            try:
                await event.answer(error_text, show_alert=True)
            except Exception:
                pass
            if message_obj:
                try:
                    await message_obj.answer(error_text)
                except Exception:
                    pass
        else:
            await event.answer(error_text)
        return False

    update_payload = {
        "channel_subscription_checked_at": now,
        "channel_subscription_verified_for": required_channel_id,
        "channel_subscription_verified": is_member,
    }
    try:
        await user_dal.update_user(session, user_id, update_payload)
    except Exception as update_error:
        logging.error(
            "Failed to persist channel verification result for user %s: %s",
            user_id,
            update_error,
            exc_info=True,
        )

    if is_member:
        logging.info(
            "User %s confirmed as member of required channel %s (status=%s).",
            user_id,
            required_channel_id,
            status_value,
        )
        return True

    channel_link = await resolve_required_channel_link(
        bot_instance,
        required_channel_id,
        settings.REQUIRED_CHANNEL_LINK,
    )
    keyboard = get_channel_subscription_keyboard(current_lang, i18n, channel_link) if i18n else None

    prompt_text = translate("channel_subscription_required")

    if isinstance(event, types.CallbackQuery):
        if keyboard and event.message:
            try:
                await callback_message(event).edit_text(prompt_text, reply_markup=keyboard)
            except Exception as edit_error:
                logging.debug(
                    "Failed to edit prompt message for user %s: %s",
                    user_id,
                    edit_error,
                )
        if keyboard is None and message_obj:
            try:
                await message_obj.answer(prompt_text)
            except Exception:
                pass
        try:
            await event.answer(prompt_text, show_alert=True)
        except Exception:
            pass
    else:
        await event.answer(prompt_text, reply_markup=keyboard)

    return False
