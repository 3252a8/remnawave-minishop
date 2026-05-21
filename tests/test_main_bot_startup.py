import asyncio
import logging

from aiogram.exceptions import TelegramNetworkError

from bot.main_bot import _run_telegram_startup_step


def test_telegram_startup_network_error_retries_until_success_without_traceback(caplog):
    calls = []

    async def failing_step():
        calls.append("try")
        if len(calls) >= 3:
            return
        try:
            raise OSError("Temporary failure in name resolution")
        except OSError as exc:
            raise TelegramNetworkError(
                method=object(),
                message="ClientConnectorDNSError: Cannot connect to host api.telegram.org:443",
            ) from exc

    with caplog.at_level(logging.INFO):
        result = asyncio.run(
            _run_telegram_startup_step(
                "registering mini app menu button",
                failing_step,
                "unexpected",
                retry_delay_seconds=0,
            )
        )

    assert result is True
    assert calls == ["try", "try", "try"]
    assert "Telegram network error while registering mini app menu button" in caplog.text
    assert (
        "Telegram step succeeded while registering mini app menu button on attempt 3"
        in caplog.text
    )
    assert "api.telegram.org" in caplog.text
    assert "Temporary failure in name resolution" in caplog.text
    assert "Traceback" not in caplog.text


def test_telegram_startup_step_returns_true_on_success():
    calls = []

    async def successful_step():
        calls.append("ok")

    result = asyncio.run(
        _run_telegram_startup_step(
            "setting bot commands",
            successful_step,
            "unexpected",
        )
    )

    assert result is True
    assert calls == ["ok"]


def test_telegram_startup_step_can_be_limited_for_tests(caplog):
    async def failing_step():
        raise TelegramNetworkError(method=object(), message="temporary dns failure")

    with caplog.at_level(logging.WARNING):
        result = asyncio.run(
            _run_telegram_startup_step(
                "setting bot commands",
                failing_step,
                "unexpected",
                attempts=2,
                retry_delay_seconds=0,
            )
        )

    assert result is False
    assert "after 2 attempts" in caplog.text
