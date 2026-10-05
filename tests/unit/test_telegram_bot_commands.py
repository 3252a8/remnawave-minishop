import asyncio
from types import SimpleNamespace

import pytest

from bot.services.telegram_bot_commands import sync_telegram_bot_commands


def _scope_key(scope, language_code=None):
    return type(scope).__name__, getattr(scope, "chat_id", None), language_code


class FakeBot:
    def __init__(self):
        self.commands = {}
        self.descriptions = {}

    async def delete_my_commands(self, *, scope, language_code=None):
        self.commands.pop(_scope_key(scope, language_code), None)

    async def set_my_commands(self, commands, *, scope, language_code=None):
        key = _scope_key(scope, language_code)
        self.commands[key] = [command.command for command in commands]
        self.descriptions[key] = {command.command: command.description for command in commands}


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
        (scope_name, None, language): ["start"]
        for scope_name in ("BotCommandScopeDefault", "BotCommandScopeAllPrivateChats")
        for language in (None, "ru", "en")
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
        (scope_name, None, language): ["start", "tg"]
        for scope_name in ("BotCommandScopeDefault", "BotCommandScopeAllPrivateChats")
        for language in (None, "ru", "en")
    }


@pytest.mark.parametrize("default_language", ["ru", "en"])
@pytest.mark.parametrize("start_description", [None, "Open shop"])
def test_command_descriptions_follow_telegram_language(default_language, start_description):
    bot = FakeBot()
    settings = SimpleNamespace(
        DEFAULT_LANGUAGE=default_language,
        START_COMMAND_DESCRIPTION=start_description,
        TELEGRAM_BOT_MENU_DISABLED=False,
        ADMIN_IDS=[],
    )

    asyncio.run(sync_telegram_bot_commands(bot, settings))

    descriptions = {
        "ru": {"start": start_description or "Главное меню", "tg": "Интерфейс бота"},
        "en": {"start": start_description or "Main menu", "tg": "Bot interface"},
    }
    for scope_name in ("BotCommandScopeDefault", "BotCommandScopeAllPrivateChats"):
        for language in ("ru", "en"):
            assert bot.descriptions[(scope_name, None, language)] == descriptions[language]
        assert bot.descriptions[(scope_name, None, None)] == descriptions[default_language]
