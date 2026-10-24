import contextlib
import logging
from typing import Any

from aiogram import Bot, types
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import (
    get_channel_subscription_keyboard,
)
from bot.middlewares.i18n import JsonI18n
from bot.services.account_roles import is_admin
from bot.services.channel_membership import check_membership
from bot.utils.callback_answer import (
    callback_message,
    message_bot,
    message_from_user,
)
from bot.utils.channel_subscription import (
    normalize_required_channel_id,
    resolve_required_channel_link,
)
from config.settings import Settings
from db.dal import user_dal
from db.models import User

logger = logging.getLogger(__name__)


async def ensure_required_channel_subscription(
    event: types.Message | types.CallbackQuery,
    settings: Settings,
    i18n: JsonI18n | None,
    current_lang: str,
    session: AsyncSession,
    db_user: User | None = None,
    *,
    force: bool = False,
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
        bot_instance: Bot | None = getattr(event, "bot", None)
        if bot_instance is None and event.message:
            bot_instance = message_bot(callback_message(event))
        message_obj: types.Message | None = callback_message(event) if event.message else None
    else:
        user_id = message_from_user(event).id
        bot_instance = event.bot if hasattr(event, "bot") else None
        message_obj = event

    if bot_instance is None:
        logger.error("Channel subscription check: bot instance missing for user %s.", user_id)
        return False

    if db_user is None:
        try:
            db_user = await user_dal.get_user_by_telegram_id(session, user_id)
        except Exception as fetch_error:
            logger.exception(
                "Channel subscription check: failed to fetch user %s: %s", user_id, fetch_error
            )
            return False

    if not db_user:
        logger.warning(
            "Required channel check skipped because user %s is not persisted yet.",
            user_id,
        )
        return True

    if await is_admin(session, int(db_user.user_id)):
        return True

    def translate(key: str, **kwargs: Any) -> str:
        if i18n:
            return str(i18n.gettext(current_lang, key, **kwargs))
        return key

    is_member = await check_membership(session, bot_instance, settings, db_user, force=force)
    if is_member is None:
        error_text = translate("channel_subscription_check_failed")
        if isinstance(event, types.CallbackQuery):
            with contextlib.suppress(Exception):
                await event.answer(error_text, show_alert=True)
            if message_obj:
                with contextlib.suppress(Exception):
                    await message_obj.answer(error_text)
        else:
            await event.answer(error_text)
        return False
    if is_member:
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
                logger.debug(
                    "Failed to edit prompt message for user %s: %s",
                    user_id,
                    edit_error,
                )
        if keyboard is None and message_obj:
            with contextlib.suppress(Exception):
                await message_obj.answer(prompt_text)
        with contextlib.suppress(Exception):
            await event.answer(prompt_text, show_alert=True)
    else:
        await event.answer(prompt_text, reply_markup=keyboard)

    return False
