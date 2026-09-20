from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class TelegramTransportSettings(BaseSettings):
    BOT_TOKEN: str
    TELEGRAM_BOT_PROXY_URL: SecretStr | None = Field(
        default=None,
        description="Optional SOCKS5 proxy used only for outgoing Telegram Bot API requests",
    )
    TELEGRAM_BOT_API_BASE_URL: str | None = Field(
        default=None,
        description="Optional base URL of a self-hosted Telegram Bot API server",
    )
