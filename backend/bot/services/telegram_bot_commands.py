import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    BotCommandScopeUnion,
)

from config.settings import Settings

logger = logging.getLogger(__name__)

BOT_MENU_SETTING_KEY = "TELEGRAM_BOT_MENU_DISABLED"


def _telegram_command_language_codes(settings: Settings) -> list[str | None]:
    language_codes: list[str | None] = [None]
    for code in (settings.DEFAULT_LANGUAGE, "ru", "en"):
        normalized = str(code or "").strip().lower()
        if normalized and normalized not in language_codes:
            language_codes.append(normalized)
    return language_codes


async def sync_telegram_bot_commands(bot: Bot, settings: Settings) -> None:
    start_description = settings.START_COMMAND_DESCRIPTION or "Main menu"
    bot_commands = [
        BotCommand(command="start", description=start_description),
        BotCommand(command="tg", description="Bot interface"),
    ]
    bot_menu_disabled = bool(settings.TELEGRAM_BOT_MENU_DISABLED)
    public_bot_commands = [bot_commands[0]] if bot_menu_disabled else bot_commands
    language_codes = _telegram_command_language_codes(settings)
    command_scopes_to_clear: list[BotCommandScopeUnion] = [
        BotCommandScopeDefault(),
        BotCommandScopeAllPrivateChats(),
        BotCommandScopeAllGroupChats(),
        BotCommandScopeAllChatAdministrators(),
    ]
    for scope in command_scopes_to_clear:
        for language_code in language_codes:
            await bot.delete_my_commands(scope=scope, language_code=language_code)
    if bot_menu_disabled:
        for admin_id in settings.ADMIN_IDS or []:
            for language_code in language_codes:
                try:
                    await bot.delete_my_commands(
                        scope=BotCommandScopeChat(chat_id=admin_id),
                        language_code=language_code,
                    )
                except TelegramBadRequest as exc:
                    logger.warning(
                        "Could not clear chat-specific bot commands for chat %s: %s",
                        admin_id,
                        exc,
                    )
    await bot.set_my_commands(public_bot_commands, scope=BotCommandScopeDefault())
    await bot.set_my_commands(public_bot_commands, scope=BotCommandScopeAllPrivateChats())


__all__ = ["BOT_MENU_SETTING_KEY", "sync_telegram_bot_commands"]
