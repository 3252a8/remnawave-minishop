from typing import Literal

from pydantic import Field, HttpUrl, SecretStr, ValidationError
from pydantic_settings import BaseSettings

TelegramChatMenuMode = Literal["keep", "web_app", "commands"]
TELEGRAM_CHAT_MENU_KEYS = frozenset(
    {"TELEGRAM_CHAT_MENU_MODE", "TELEGRAM_CHAT_MENU_TEXT", "TELEGRAM_CHAT_MENU_URL"}
)


class TelegramTransportSettings(BaseSettings):
    TELEGRAM_ENABLED: bool = True
    BOT_TOKEN: str | None = None
    TELEGRAM_BOT_PROXY_URL: SecretStr | None = Field(
        default=None,
        description="Optional SOCKS5 proxy used only for outgoing Telegram Bot API requests",
    )
    TELEGRAM_BOT_API_BASE_URL: str | None = Field(
        default=None,
        description="Optional base URL of a self-hosted Telegram Bot API server",
    )
    TELEGRAM_CHAT_MENU_MODE: TelegramChatMenuMode = "keep"
    TELEGRAM_CHAT_MENU_TEXT: str = ""
    TELEGRAM_CHAT_MENU_URL: str = ""


def telegram_chat_menu_errors(mode: str, text: str, url: str) -> dict[str, str]:
    errors: dict[str, str] = {}
    if mode == "web_app" and not text.strip():
        errors["TELEGRAM_CHAT_MENU_TEXT"] = "telegram_chat_menu_text_required"
    url = url.strip()
    try:
        valid_url = (
            url.lower().startswith("https://")
            and not any(char.isspace() for char in url)
            and "\\" not in url
            and bool(HttpUrl(url).host)
        )
    except ValidationError:
        valid_url = False
    if not valid_url and (mode == "web_app" or url):
        errors["TELEGRAM_CHAT_MENU_URL"] = "telegram_chat_menu_url_invalid"
    return errors
