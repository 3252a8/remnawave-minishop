from aiogram import Bot
from aiogram.types import MenuButtonCommands, MenuButtonWebApp, WebAppInfo

from config.settings_telegram import TelegramTransportSettings, telegram_chat_menu_errors


async def sync_telegram_chat_menu(bot: Bot, settings: TelegramTransportSettings) -> None:
    mode = settings.TELEGRAM_CHAT_MENU_MODE
    if mode == "keep":
        return
    if mode == "commands":
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        return

    text = settings.TELEGRAM_CHAT_MENU_TEXT.strip()
    url = settings.TELEGRAM_CHAT_MENU_URL.strip()
    if errors := telegram_chat_menu_errors(mode, text, url):
        raise ValueError(" ".join(errors.values()))
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text=text, web_app=WebAppInfo(url=url))
    )
