from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message, User


class AdminFilter(Filter):
    def __init__(self, admin_ids: list[int]):
        self.admin_ids = admin_ids

    async def __call__(self, event: Message | CallbackQuery, event_from_user: User) -> bool:
        if not event_from_user:
            return False
        if not self.admin_ids:
            return False
        return event_from_user.id in self.admin_ids
