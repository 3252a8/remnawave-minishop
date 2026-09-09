import asyncio
from types import SimpleNamespace

from bot.services.telegram_bot_commands import sync_telegram_bot_commands


def _scope_key(scope, language_code=None):
    return type(scope).__name__, getattr(scope, "chat_id", None), language_code


class FakeBot:
    def __init__(self):
        self.commands = {}

    async def delete_my_commands(self, *, scope, language_code=None):
        self.commands.pop(_scope_key(scope, language_code), None)

    async def set_my_commands(self, commands, *, scope):
        self.commands[_scope_key(scope)] = [command.command for command in commands]


def test_disabling_bot_menu_removes_previously_published_tg_commands():
    bot = FakeBot()
    settings = SimpleNamespace(
        DEFAULT_LANGUAGE="ru",
        START_COMMAND_DESCRIPTION=None,
        TELEGRAM_BOT_MENU_DISABLED=False,
        ADMIN_IDS=[42],
    )

    asyncio.run(sync_telegram_bot_commands(bot, settings))
    bot.commands[("BotCommandScopeDefault", None, "ru")] = ["start", "tg"]
    bot.commands[("BotCommandScopeAllGroupChats", None, None)] = ["start", "tg"]
    bot.commands[("BotCommandScopeChat", 42, None)] = ["start", "tg"]

    settings.TELEGRAM_BOT_MENU_DISABLED = True
    asyncio.run(sync_telegram_bot_commands(bot, settings))

    assert bot.commands == {
        ("BotCommandScopeDefault", None, None): ["start"],
        ("BotCommandScopeAllPrivateChats", None, None): ["start"],
    }


def test_enabling_bot_menu_publishes_tg_command_again():
    bot = FakeBot()
    settings = SimpleNamespace(
        DEFAULT_LANGUAGE="en",
        START_COMMAND_DESCRIPTION="Open shop",
        TELEGRAM_BOT_MENU_DISABLED=True,
        ADMIN_IDS=[],
    )

    asyncio.run(sync_telegram_bot_commands(bot, settings))
    settings.TELEGRAM_BOT_MENU_DISABLED = False
    asyncio.run(sync_telegram_bot_commands(bot, settings))

    assert bot.commands == {
        ("BotCommandScopeDefault", None, None): ["start", "tg"],
        ("BotCommandScopeAllPrivateChats", None, None): ["start", "tg"],
    }
