from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiohttp_socks import ProxyConnectionError

from bot.app.factories import telegram_bot as telegram_bot_factory
from config.settings import Settings


def make_settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "BOT_TOKEN": "123456789:AA_test_bot_token",
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
    }
    values.update(overrides)
    return Settings(**values)


def test_factory_keeps_aiogram_default_session_without_proxy(monkeypatch) -> None:
    created_bots = []

    class FakeBot:
        def __init__(self, **kwargs):
            created_bots.append(kwargs)

    def unexpected_session(**_kwargs):
        raise AssertionError("A custom session must not be created in direct mode")

    monkeypatch.setattr(telegram_bot_factory, "Bot", FakeBot)
    monkeypatch.setattr(telegram_bot_factory, "AiohttpSession", unexpected_session)

    bot = telegram_bot_factory.create_telegram_bot(make_settings())

    assert isinstance(bot, FakeBot)
    assert len(created_bots) == 1
    assert "session" not in created_bots[0]
    assert created_bots[0]["default"].parse_mode == ParseMode.HTML


def test_factory_uses_local_bot_api_server(monkeypatch, caplog) -> None:
    created_sessions = []
    created_bots = []

    class FakeSession:
        def __init__(self, **kwargs):
            self.api = kwargs["api"]
            self.middleware = self
            self.middlewares = []
            created_sessions.append(self)

        def register(self, middleware):
            self.middlewares.append(middleware)

    class FakeBot:
        def __init__(self, **kwargs):
            created_bots.append(kwargs)

    monkeypatch.setattr(telegram_bot_factory, "AiohttpSession", FakeSession)
    monkeypatch.setattr(telegram_bot_factory, "Bot", FakeBot)

    with caplog.at_level("INFO"):
        telegram_bot_factory.create_telegram_bot(
            make_settings(TELEGRAM_BOT_API_BASE_URL="http://telegram-bot-api:8081/")
        )

    assert len(created_sessions) == 1
    assert created_sessions[0].api.base == "http://telegram-bot-api:8081/bot{token}/{method}"
    assert created_sessions[0].api.is_local is True
    assert created_sessions[0].middlewares == []
    assert created_bots[0]["session"] is created_sessions[0]
    assert "http://telegram-bot-api:8081" in caplog.text


def test_factory_creates_one_proxy_session_and_redacts_startup_log(monkeypatch, caplog) -> None:
    raw_url = "socks5://proxy-user:proxy-password@proxy.example.com:1080"
    created_sessions = []
    created_bots = []

    class FakeSession:
        def __init__(self, *, proxy):
            self.proxy = proxy
            self.middlewares = []
            self.middleware = self
            created_sessions.append(self)

        def register(self, middleware):
            self.middlewares.append(middleware)

    class FakeBot:
        def __init__(self, **kwargs):
            self.session = kwargs["session"]
            created_bots.append(kwargs)

    monkeypatch.setattr(telegram_bot_factory, "AiohttpSession", FakeSession)
    monkeypatch.setattr(telegram_bot_factory, "Bot", FakeBot)

    with caplog.at_level("INFO"):
        bot = telegram_bot_factory.create_telegram_bot(
            make_settings(TELEGRAM_BOT_PROXY_URL=raw_url)
        )

    assert isinstance(bot, FakeBot)
    assert len(created_sessions) == 1
    assert len(created_bots) == 1
    assert created_sessions[0].proxy == raw_url
    assert len(created_sessions[0].middlewares) == 1
    assert isinstance(
        created_sessions[0].middlewares[0],
        telegram_bot_factory.TelegramProxyErrorMiddleware,
    )
    assert created_bots[0]["session"] is created_sessions[0]
    assert created_bots[0]["default"].parse_mode == ParseMode.HTML
    assert raw_url not in caplog.text
    assert "proxy-password" not in caplog.text
    assert "socks5://***:***@proxy.example.com:1080" in caplog.text


def test_pinned_aiogram_session_selects_socks5_connector_with_remote_dns() -> None:
    session = AiohttpSession(proxy="socks5://user%40example:p%3Aword@proxy.example.com:1080")
    try:
        assert session.proxy == "socks5://user%40example:p%3Aword@proxy.example.com:1080"
        assert session._connector_type.__name__ == "ProxyConnector"
        assert session._connector_init["proxy_type"].name == "SOCKS5"
        assert session._connector_init["host"] == "proxy.example.com"
        assert session._connector_init["port"] == 1080
        assert session._connector_init["username"] == "user@example"
        assert session._connector_init["password"] == "p:word"
        assert session._connector_init["rdns"] is True
    finally:
        asyncio.run(session.close())


def test_proxy_transport_errors_keep_aiogram_network_error_contract(monkeypatch) -> None:
    raw_url = "socks5://proxy-user:proxy-password@proxy.example.com:1080"

    async def fail_with_proxy_error(*_args, **_kwargs):
        raise ProxyConnectionError(f"Cannot connect through {raw_url}")

    monkeypatch.setattr(AiohttpSession, "make_request", fail_with_proxy_error)
    bot = telegram_bot_factory.create_telegram_bot(make_settings(TELEGRAM_BOT_PROXY_URL=raw_url))
    try:
        with pytest.raises(TelegramNetworkError) as error:
            asyncio.run(bot.get_me())
    finally:
        asyncio.run(bot.session.close())

    assert "proxy-password" not in str(error.value)
    assert raw_url not in str(error.value)
    assert "socks5://***:***@proxy.example.com:1080" in str(error.value)


def test_backend_worker_and_diagnostic_sender_use_shared_factory() -> None:
    runtime_source = Path("backend/bot/app/factories/runtime.py").read_text(encoding="utf-8")
    sender_source = Path("scripts/send_premium_traffic_warning_test.py").read_text(encoding="utf-8")
    runtime_tree = ast.parse(runtime_source)
    sender_tree = ast.parse(sender_source)

    assert "create_telegram_bot(settings)" in runtime_source
    assert "create_telegram_bot(settings)" in sender_source
    assert not any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Bot"
        for tree in (runtime_tree, sender_tree)
        for node in ast.walk(tree)
    )

    backend_source = Path("backend/bot/main_bot.py").read_text(encoding="utf-8")
    worker_source = Path("backend/main_worker.py").read_text(encoding="utf-8")
    assert "build_runtime_bootstrap(settings_param)" in backend_source
    assert "build_runtime_bootstrap(settings)" in worker_source
