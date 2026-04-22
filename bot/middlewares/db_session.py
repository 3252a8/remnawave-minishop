import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Update
from sqlalchemy.orm import sessionmaker

from bot.utils.callback_answer import is_expired_callback_answer_error


class DBSessionMiddleware(BaseMiddleware):

    def __init__(self, async_session_factory: sessionmaker):
        super().__init__()
        self.async_session_factory = async_session_factory

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        if self.async_session_factory is None:
            logging.critical("DBSessionMiddleware: async_session_factory is None!")
            raise RuntimeError(
                "async_session_factory not provided to DBSessionMiddleware"
            )

        async with self.async_session_factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)

                await session.commit()
                return result
            except TelegramBadRequest as error:
                await session.rollback()
                if is_expired_callback_answer_error(error):
                    logging.info(
                        "DBSessionMiddleware: expired callback answer ignored; "
                        "session rolled back for the interrupted update."
                    )
                    return None
                logging.error(
                    "DBSessionMiddleware: Exception caused rollback.", exc_info=True
                )
                raise
            except Exception:
                await session.rollback()
                logging.error(
                    "DBSessionMiddleware: Exception caused rollback.", exc_info=True
                )
                raise

