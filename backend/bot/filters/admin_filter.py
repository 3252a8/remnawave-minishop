from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message, User
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.account_roles import is_admin
from db.dal.user_reads_dal import get_user_by_telegram_id


class AdminFilter(Filter):
    async def __call__(
        self,
        event: Message | CallbackQuery,
        event_from_user: User,
        session: AsyncSession,
    ) -> bool:
        if not event_from_user:
            return False
        account = await get_user_by_telegram_id(session, event_from_user.id)
        return bool(account and await is_admin(session, int(account.user_id)))
