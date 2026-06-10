import ast
import asyncio
import logging
from pathlib import Path

from aiogram.exceptions import TelegramNetworkError

from bot.main_bot import _run_telegram_startup_step


def test_backend_startup_does_not_run_panel_sync_inline():
    source = Path("backend/bot/main_bot.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "bot.handlers.admin.sync_admin"
    ]
    forbidden_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "perform_sync"
    ]

    assert forbidden_imports == []
    assert forbidden_calls == []


def test_worker_starts_backup_task_without_enabled_guard():
    source = Path("backend/main_worker.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    guarded_backup_tasks = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Attribute)
        and node.test.attr == "BACKUP_ENABLED"
    ]

    assert "BackupWorker" in source
    assert guarded_backup_tasks == []


def test_telegram_webhook_configuration_is_deferred_until_site_start():
    main_source = Path("backend/bot/main_bot.py").read_text(encoding="utf-8")
    web_source = Path("backend/bot/app/web/web_server.py").read_text(encoding="utf-8")
    tree = ast.parse(main_source)
    startup_node = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "on_startup_configured"
    )

    startup_set_webhook_calls = [
        node
        for node in ast.walk(startup_node)
        if isinstance(node, ast.Attribute) and node.attr == "set_webhook"
    ]

    assert startup_set_webhook_calls == []
    assert "after_webhooks_started=_after_webhooks_started" in main_source
    assert web_source.index("await site.start()") < web_source.index(
        "await after_webhooks_started()"
    )


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
        "Telegram step succeeded while registering mini app menu button on attempt 3" in caplog.text
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
