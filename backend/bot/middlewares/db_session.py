import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)


class DBSessionMiddleware(BaseMiddleware):
    def __init__(self, async_session_factory: sessionmaker):
        super().__init__()
        self.async_session_factory = async_session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if self.async_session_factory is None:
            logger.critical("DBSessionMiddleware: async_session_factory is None!")
            raise RuntimeError("async_session_factory not provided to DBSessionMiddleware")

        async with self.async_session_factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)

                await session.commit()
                return result
            except Exception:
                await session.rollback()
                logger.exception("DBSessionMiddleware: Exception caused rollback.")
                raise
