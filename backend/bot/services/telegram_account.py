"""Resolve a Telegram transport identity to its linked Minishop account."""

from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import user_dal


class TelegramAccountRequiredError(LookupError):
    """A Telegram update arrived before its sender registered an account."""


async def require_telegram_account_id(session: AsyncSession, telegram_id: int) -> int:
    user = await user_dal.get_user_by_telegram_id(session, int(telegram_id))
    if user is None:
        raise TelegramAccountRequiredError("Start the bot before using account features")
    return int(user.user_id)
