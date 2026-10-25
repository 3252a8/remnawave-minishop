"""Gift bearer links shared by the bot and authenticated gift views."""

import re

from bot.utils.mini_app_url import bot_start_deep_link

GIFT_TOKEN_PATTERN = r"[A-Za-z0-9_-]{43}"


def gift_telegram_url(bot_username: str | None, token: str) -> str | None:
    if not re.fullmatch(GIFT_TOKEN_PATTERN, token):
        return None
    return bot_start_deep_link(bot_username, f"gift_{token}")


def redact_gift_tokens(text: str) -> str:
    return re.sub(r"(gift_|gift:claim:)[A-Za-z0-9_-]{43,}", r"\1[redacted]", text)
