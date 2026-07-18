import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import main_worker

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


def teardown_function() -> None:
    reset_plugins()


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
