import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import main_worker
import pytest
from aiogram.exceptions import TelegramNetworkError

from bot.app.factories import runtime as runtime_factory
from bot.app.factories.runtime import RuntimeBootstrap, build_core_runtime
from bot.plugins import (
    Plugin,
    WorkerTaskSpec,
    collect_migrations,
    collect_queue_handlers,
    collect_worker_tasks,
    register,
    reset_plugins,
)
from config.settings import Settings
from db.migrator import Migration, validate_migration_chains


def make_settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "BOT_TOKEN": "x",
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
        "ADMIN_IDS": "1",
    }
    values.update(overrides)
    return Settings(**values)


async def _noop() -> None:
    return None


def test_worker_keeps_outbound_settings_current_without_restart(monkeypatch) -> None:
    settings = make_settings()
    session_factory = object()
    ctx = SimpleNamespace(settings=settings, require_session_factory=lambda: session_factory)
    keys = {"SMTP_HOST", "PAYKILLA_BASE_URL"}
    refresh = AsyncMock()
    sleep = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(main_worker, "outbound_runtime_setting_keys", lambda: keys)
    monkeypatch.setattr(main_worker, "refresh_overrides_from_db", refresh)
    monkeypatch.setattr(main_worker.asyncio, "sleep", sleep)
    assert "OutboundSettingsRefresh" in {spec.name for spec in main_worker._core_worker_tasks()}
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main_worker._outbound_settings_refresh_task(ctx))
    refresh.assert_awaited_once_with(settings, session_factory, keys=keys)
    sleep.assert_awaited_once_with(5)


def teardown_function() -> None:
    reset_plugins()


def test_worker_startup_redacts_proxy_credentials_from_telegram_errors(monkeypatch, caplog) -> None:
    password = "worker-proxy-password"
    proxy_url = f"socks5://proxy-user:{password}@proxy.example.com:1080"
    plugin_context = object()

    class FailingBot:
        async def get_me(self):
            try:
                raise OSError(f"Cannot connect through {proxy_url}")
            except OSError as cause:
                raise TelegramNetworkError(
                    method=object(),
                    message=f"Proxy connection failed: {proxy_url}",
                ) from cause

    runtime = SimpleNamespace(bot=FailingBot())

    async def fake_build_runtime_bootstrap(_settings):
        return runtime

    monkeypatch.setattr(main_worker, "build_runtime_bootstrap", fake_build_runtime_bootstrap)
    monkeypatch.setattr(main_worker, "configure_message_log_notifier", lambda *_args: None)
    monkeypatch.setattr(main_worker, "init_queue_manager", lambda *_args: None)
    monkeypatch.setattr(
        main_worker,
        "build_core_runtime",
        lambda *_args, **_kwargs: SimpleNamespace(plugin_context=plugin_context),
    )
    monkeypatch.setattr(main_worker, "run_setup", lambda *_args: None)
    monkeypatch.setattr(main_worker, "register_core_reactions", lambda *_args: None)

    with caplog.at_level(logging.WARNING):
        result = asyncio.run(main_worker._build_worker_context(make_settings()))

    assert result is plugin_context
    assert password not in caplog.text
    assert proxy_url not in caplog.text
    assert "socks5://***:***@proxy.example.com:1080" in caplog.text
    assert "Traceback" not in caplog.text


def test_build_core_runtime_uses_shared_bootstrap_for_plugin_context(monkeypatch) -> None:
    settings = object()
    session_factory = object()
    bot = object()
    i18n = object()
    service = object()
    calls = []

    class FakeCoreServices:
        def as_dict(self) -> dict[str, object]:
            return {"panel_service": service}

    def fake_build_core_services(
        settings_arg,
        bot_arg,
        session_factory_arg,
        i18n_arg,
        bot_username_arg,
    ):
        calls.append(
            (
                settings_arg,
                bot_arg,
                session_factory_arg,
                i18n_arg,
                bot_username_arg,
            )
        )
        return FakeCoreServices()

    monkeypatch.setattr(runtime_factory, "build_core_services", fake_build_core_services)

    bootstrap = RuntimeBootstrap(
        settings=settings,
        session_factory=session_factory,
        bot=bot,
        i18n=i18n,
    )
    core_runtime = build_core_runtime(bootstrap, bot_username="runtimebot")

    assert calls == [(settings, bot, session_factory, i18n, "runtimebot")]
    assert core_runtime.bootstrap is bootstrap
    assert core_runtime.plugin_context.settings is settings
    assert core_runtime.plugin_context.session_factory is session_factory
    assert core_runtime.plugin_context.bot is bot
    assert core_runtime.plugin_context.i18n is i18n
    assert core_runtime.services == {"panel_service": service}


def test_worker_plugin_hooks_use_shared_runtime_context(monkeypatch) -> None:
    settings = make_settings()
    session_factory = object()
    bot = object()
    i18n = object()
    panel_service = object()

    class FakeCoreServices:
        def as_dict(self) -> dict[str, object]:
            return {"panel_service": panel_service}

    monkeypatch.setattr(
        runtime_factory,
        "build_core_services",
        lambda *_args, **_kwargs: FakeCoreServices(),
    )

    class WorkerCompositionPlugin(Plugin):
        name = "worker_composition"

        def worker_tasks(self, ctx):
            assert ctx.require_session_factory() is session_factory
            assert ctx.require_panel_service() is panel_service
            return [WorkerTaskSpec(name="PluginWorker", factory=lambda _ctx: _noop())]

        def queue_handlers(self, ctx):
            assert ctx.require_bot() is bot

            async def _handler(_ctx, _payload):
                return None

            return {"worker_composition": _handler}

        def migrations(self):
            return [
                Migration(
                    id="worker_composition.0001_initial",
                    description="test",
                    upgrade=lambda _connection: None,
                )
            ]

    register(WorkerCompositionPlugin())
    runtime = RuntimeBootstrap(
        settings=settings,
        session_factory=session_factory,
        bot=bot,
        i18n=i18n,
    )
    ctx = build_core_runtime(runtime, bot_username="workerbot").plugin_context

    handlers = main_worker._core_queue_handlers()
    handlers.update(collect_queue_handlers(ctx, reserved=set(handlers)))
    task_specs = [*main_worker._core_worker_tasks(), *collect_worker_tasks(ctx)]
    migration_chains = collect_migrations(settings)
    validate_migration_chains(migration_chains)

    assert "worker_composition" in handlers
    assert "PluginWorker" in {spec.name for spec in task_specs}
    assert migration_chains["worker_composition"][0].id == "worker_composition.0001_initial"


@pytest.mark.parametrize("saved_enabled", [True, False])
@pytest.mark.parametrize(
    ("event_name", "meta"),
    [
        ("user.expires_in_72_hours", None),
        ("user.expires_in_48_hours", None),
        ("user.expires_in_24_hours", None),
        ("user.expired", None),
        ("user.expired_24_hours_ago", None),
        ("user.expiration", {"expiration": -72}),
        ("user.expiration", {"expiration": -48}),
        ("user.expiration", {"expiration": -24}),
        ("user.expiration", {"expiration": -12}),
        ("user.expiration", {"expiration": 12}),
        ("user.expiration", {"expiration": 24}),
    ],
)
def test_panel_queue_handler_refreshes_subscription_settings_before_dispatch(
    event_name, meta, saved_enabled
) -> None:
    settings = SimpleNamespace(
        SUBSCRIPTION_NOTIFICATIONS_ENABLED=not saved_enabled,
        SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED=not saved_enabled,
        SUBSCRIPTION_NOTIFY_ON_EXPIRE=False,
        SUBSCRIPTION_NOTIFY_AFTER_EXPIRE=False,
        SUBSCRIPTION_NOTIFY_DAYS_BEFORE=0,
    )
    saved_settings = {
        "SUBSCRIPTION_NOTIFICATIONS_ENABLED": saved_enabled,
        "SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED": saved_enabled,
        "SUBSCRIPTION_NOTIFY_ON_EXPIRE": True,
        "SUBSCRIPTION_NOTIFY_AFTER_EXPIRE": True,
        "SUBSCRIPTION_NOTIFY_DAYS_BEFORE": 3,
    }
    observed_settings = []
    session_factory = object()

    async def refresh_settings(runtime_settings, runtime_session_factory, *, keys):
        assert runtime_settings is settings
        assert runtime_session_factory is session_factory
        for key, value in saved_settings.items():
            if key in keys:
                setattr(runtime_settings, key, value)

    async def handle_event(event, user, *, meta):
        observed_settings.append({key: getattr(settings, key) for key in saved_settings})

    panel_webhook_service = SimpleNamespace(handle_event=AsyncMock(side_effect=handle_event))
    ctx = SimpleNamespace(
        settings=settings,
        require_panel_webhook_service=lambda: panel_webhook_service,
        require_session_factory=lambda: session_factory,
    )
    payload = {
        "event": event_name,
        "user": {"uuid": "panel-user-1", "telegramId": 99},
        "meta": meta,
    }

    with patch.object(main_worker, "refresh_overrides_from_db", refresh_settings):
        asyncio.run(main_worker._handle_panel_event(ctx, payload))

    assert observed_settings == [saved_settings]
    panel_webhook_service.handle_event.assert_awaited_once_with(
        event_name,
        payload["user"],
        meta=meta,
    )


def test_panel_queue_handler_forwards_torrent_notification_context() -> None:
    panel_webhook_service = SimpleNamespace(handle_event=AsyncMock())
    settings = SimpleNamespace(TORRENT_BLOCKER_NOTIFICATIONS_ENABLED=False)
    session_factory = object()

    async def refresh_settings(runtime_settings, runtime_session_factory, *, keys):
        assert runtime_settings is settings
        assert runtime_session_factory is session_factory
        assert keys == main_worker.TORRENT_BLOCKER_RUNTIME_SETTING_KEYS
        runtime_settings.TORRENT_BLOCKER_NOTIFICATIONS_ENABLED = True

    ctx = SimpleNamespace(
        settings=settings,
        require_panel_webhook_service=lambda: panel_webhook_service,
        require_session_factory=lambda: session_factory,
    )
    payload = {
        "event": "torrent_blocker.report",
        "user": {"uuid": "panel-user-1", "telegramId": 99},
        "context": {
            "blocked": True,
            "ip": "203.0.113.8",
            "block_duration": 3600,
            "will_unblock_at": "2026-07-17T11:00:00Z",
            "processed_at": "2026-07-17T10:00:00Z",
            "event_timestamp": "2026-07-17T10:00:01Z",
        },
    }

    with patch.object(main_worker, "refresh_overrides_from_db", refresh_settings):
        asyncio.run(main_worker._handle_panel_event(ctx, payload))

    assert settings.TORRENT_BLOCKER_NOTIFICATIONS_ENABLED is True
    panel_webhook_service.handle_event.assert_awaited_once_with(
        "torrent_blocker.report",
        payload["user"],
        meta=None,
        context=payload["context"],
    )


def test_panel_queue_handler_refreshes_hwid_notification_settings() -> None:
    panel_webhook_service = SimpleNamespace(handle_event=AsyncMock())
    settings = SimpleNamespace(USER_NOTIFICATION_DEVICE_LIMIT_EMAIL_ENABLED=False)
    session_factory = object()

    async def refresh_settings(runtime_settings, runtime_session_factory, *, keys):
        assert runtime_settings is settings
        assert runtime_session_factory is session_factory
        assert keys == main_worker.HWID_DEVICE_NOTIFICATION_RUNTIME_SETTING_KEYS
        runtime_settings.USER_NOTIFICATION_DEVICE_LIMIT_EMAIL_ENABLED = True

    ctx = SimpleNamespace(
        settings=settings,
        require_panel_webhook_service=lambda: panel_webhook_service,
        require_session_factory=lambda: session_factory,
    )
    payload = {
        "event": "user_hwid_devices.added",
        "user": {"uuid": "panel-user-1"},
        "context": {"fingerprint": "a" * 24, "platform": "Android"},
    }

    with patch.object(main_worker, "refresh_overrides_from_db", refresh_settings):
        asyncio.run(main_worker._handle_panel_event(ctx, payload))

    assert settings.USER_NOTIFICATION_DEVICE_LIMIT_EMAIL_ENABLED is True
    panel_webhook_service.handle_event.assert_awaited_once_with(
        "user_hwid_devices.added",
        payload["user"],
        meta=None,
        context=payload["context"],
    )
