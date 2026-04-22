import logging
from typing import Any

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery


_EXPIRED_CALLBACK_MARKERS = (
    "query is too old",
    "response timeout expired",
    "query id is invalid",
)


def is_expired_callback_answer_error(error: BaseException) -> bool:
    if not isinstance(error, TelegramBadRequest):
        return False
    message = str(error).lower()
    return any(marker in message for marker in _EXPIRED_CALLBACK_MARKERS)


async def safe_answer_callback(
    callback: CallbackQuery,
    *args: Any,
    **kwargs: Any,
) -> bool:
    try:
        await callback.answer(*args, **kwargs)
        return True
    except TelegramBadRequest as error:
        user_id = getattr(getattr(callback, "from_user", None), "id", "unknown")
        if is_expired_callback_answer_error(error):
            logging.info(
                "Ignored expired callback answer for user %s: %s",
                user_id,
                error,
            )
            return False
        logging.warning(
            "Failed to answer callback query for user %s: %s",
            user_id,
            error,
        )
        return False
    except TelegramAPIError as error:
        user_id = getattr(getattr(callback, "from_user", None), "id", "unknown")
        logging.warning(
            "Telegram API error while answering callback query for user %s: %s",
            user_id,
            error,
        )
        return False
