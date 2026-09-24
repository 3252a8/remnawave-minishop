from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.session.base import TelegramType
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import Response, TelegramMethod
from aiohttp_socks import ProxyConnectionError, ProxyError, ProxyTimeoutError

from config.settings import Settings
from config.telegram_proxy import (
    safe_telegram_network_error_detail,
    safe_telegram_proxy_endpoint,
)

logger = logging.getLogger(__name__)


class TelegramProxyErrorMiddleware(BaseRequestMiddleware):
    """Preserve aiogram's network-error contract for aiohttp-socks failures."""

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Response[TelegramType]:
        try:
            return await make_request(bot, method)
        except (ProxyConnectionError, ProxyTimeoutError, ProxyError) as exc:
            detail = safe_telegram_network_error_detail(exc)
            raise TelegramNetworkError(
                method=method,
                message=f"{type(exc).__name__}: {detail}",
            ) from exc


def create_telegram_bot(settings: Settings, *, token: str | None = None) -> Bot:
    """Create the shared Telegram Bot API client for backend and worker runtimes."""
    default = DefaultBotProperties(parse_mode=ParseMode.HTML)
    bot_token = settings.BOT_TOKEN if token is None else token
    if not bot_token:
        raise ValueError("BOT_TOKEN is required for the Telegram adapter")
    proxy_url = settings.TELEGRAM_BOT_PROXY_URL
    api_base_url = settings.TELEGRAM_BOT_API_BASE_URL
    if proxy_url is None and api_base_url is None:
        return Bot(token=bot_token, default=default)

    api_server: TelegramAPIServer | None = None
    if api_base_url is not None:
        logger.info("Local Telegram Bot API server enabled: %s", api_base_url)
        api_server = TelegramAPIServer.from_base(api_base_url, is_local=True)
    if proxy_url is None:
        assert api_server is not None
        session = AiohttpSession(api=api_server)
        return Bot(token=bot_token, default=default, session=session)

    raw_proxy_url = proxy_url.get_secret_value()
    logger.info(
        "Telegram Bot API SOCKS5 proxy enabled: %s",
        safe_telegram_proxy_endpoint(proxy_url),
    )
    session = (
        AiohttpSession(proxy=raw_proxy_url, api=api_server)
        if api_server is not None
        else AiohttpSession(proxy=raw_proxy_url)
    )
    session.middleware.register(TelegramProxyErrorMiddleware())
    return Bot(token=bot_token, default=default, session=session)
