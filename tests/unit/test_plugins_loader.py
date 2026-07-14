"""Tests for the plugin discovery loader and its core hook points."""

from __future__ import annotations

import json

import pytest
from aiogram import Router
from aiohttp import web

from bot.middlewares.i18n import JsonI18n
from bot.plugins import (
    PLUGIN_API_VERSION,
    WEB_SCOPE_WEBAPP,
    WEB_SCOPE_WEBHOOKS,
    Plugin,
    PluginApiCompatibilityError,
    PluginContext,
    WorkerTaskSpec,
    apply_plugin_locales,
    collect_queue_handlers,
    collect_worker_tasks,
    get_plugins,
    register,
    reset_plugins,
    run_setup,
    setup_web_plugins,
)
from bot.plugins import loader as plugins_loader
from bot.routers import build_root_router
from config.settings import Settings
from db.migrator import Migration, validate_migration_chains


@pytest.fixture(autouse=True)
def _clean_plugin_state():
    reset_plugins()
    yield
    reset_plugins()


@pytest.fixture
def fresh_core_routers(monkeypatch):
    """Replace module-level router aggregates so build_root_router can run
    more than once per process (aiogram forbids re-attaching a router)."""
    import bot.routers as routers_mod

    monkeypatch.setattr(routers_mod, "user_router_aggregate", Router(name="user_agg_stub"))
    monkeypatch.setattr(routers_mod, "admin_router_aggregate", Router(name="admin_agg_stub"))
    monkeypatch.setattr(routers_mod.inline_mode, "router", Router(name="inline_stub"))


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


class RecordingPlugin(Plugin):
    name = "recording"
    version = "1.0.0"

    def __init__(self):
        self.calls = []
        self.user_router = Router(name="recording_user")
        self.admin_router = Router(name="recording_admin")

    def setup(self, ctx):
        self.calls.append(("setup", ctx))

    def setup_bot(self, ctx, *, user_root, admin_root):
        self.calls.append(("setup_bot", user_root, admin_root))
        user_root.include_router(self.user_router)
        admin_root.include_router(self.admin_router)

    def setup_web(self, ctx, app, *, scope):
        self.calls.append(("setup_web", scope))
        app.router.add_get(f"/recording/{scope}", self._handler)

    async def _handler(self, request):
        return web.json_response({"ok": True})


class FailingPlugin(Plugin):
    name = "failing"

    def setup(self, ctx):
        raise RuntimeError("boom")

    def setup_bot(self, ctx, *, user_root, admin_root):
        raise RuntimeError("boom")

    def setup_web(self, ctx, app, *, scope):
        raise RuntimeError("boom")


def test_builtin_plugins_active_by_default(caplog):
    settings = make_settings()
    with caplog.at_level("INFO"):
        names = [plugin.name for plugin in get_plugins(settings)]
    assert names == ["telemetry", "lknpd"]
    assert "Plugins active: telemetry==" in caplog.text


def test_plugins_disabled_setting_keeps_builtins_only():
    register(RecordingPlugin())
    settings = make_settings(PLUGINS_ENABLED=False)
    names = [plugin.name for plugin in get_plugins(settings)]
    assert "recording" not in names
    assert names == ["telemetry", "lknpd"]


def test_setup_hook_runs_for_registered_plugins():
    plugin = RecordingPlugin()
    register(plugin)
    ctx = PluginContext(settings=make_settings())
    run_setup(ctx)
    assert plugin.calls == [("setup", ctx)]


def test_build_root_router_invokes_setup_bot_and_includes_routers(fresh_core_routers):
    plugin = RecordingPlugin()
    register(plugin)
    settings = make_settings()
    ctx = PluginContext(settings=settings)

    root = build_root_router(settings, ctx)

    assert plugin.calls and plugin.calls[0][0] == "setup_bot"
    _, user_root, admin_root = plugin.calls[0]
    assert user_root is root
    assert admin_root.name == "admin_main_filtered_router"
    assert plugin.user_router in root.sub_routers
    assert plugin.admin_router in admin_root.sub_routers


def test_build_root_router_without_context_skips_plugins(fresh_core_routers):
    plugin = RecordingPlugin()
    register(plugin)

    root = build_root_router(make_settings())

    assert plugin.calls == []
    assert plugin.user_router not in root.sub_routers


def test_setup_web_registers_routes_per_scope():
    plugin = RecordingPlugin()
    register(plugin)
    ctx = PluginContext(settings=make_settings())

    for scope in (WEB_SCOPE_WEBHOOKS, WEB_SCOPE_WEBAPP):
        app = web.Application()
        setup_web_plugins(ctx, app, scope=scope)
        paths = {resource.canonical for resource in app.router.resources()}
        assert f"/recording/{scope}" in paths

    assert [call for call in plugin.calls if call[0] == "setup_web"] == [
        ("setup_web", WEB_SCOPE_WEBHOOKS),
        ("setup_web", WEB_SCOPE_WEBAPP),
    ]


def test_failing_plugin_is_isolated(caplog):
    failing = FailingPlugin()
    recording = RecordingPlugin()
    register(failing)
    register(recording)
    ctx = PluginContext(settings=make_settings())

    with caplog.at_level("ERROR"):
        run_setup(ctx)

    assert recording.calls == [("setup", ctx)]
    assert "Plugin 'failing' failed in setup" in caplog.text


def test_failing_plugin_is_fatal_in_strict_mode():
    register(FailingPlugin())
    ctx = PluginContext(settings=make_settings(PLUGINS_STRICT=True))

    with pytest.raises(RuntimeError, match="boom"):
        run_setup(ctx)


class _FakeEntryPoint:
    name = "fake"

    def __init__(self, target):
        self._target = target

    def load(self):
        return self._target


def test_entry_point_discovery_accepts_class(monkeypatch):
    monkeypatch.setattr(
        plugins_loader.metadata,
        "entry_points",
        lambda group: [_FakeEntryPoint(RecordingPlugin)],
    )
    names = [plugin.name for plugin in get_plugins(make_settings())]
    assert "recording" in names


def test_entry_point_discovery_rejects_non_plugin(monkeypatch, caplog):
    monkeypatch.setattr(
        plugins_loader.metadata,
        "entry_points",
        lambda group: [_FakeEntryPoint(object())],
    )
    with caplog.at_level("ERROR"):
        names = [plugin.name for plugin in get_plugins(make_settings())]
    assert names == ["telemetry", "lknpd"]
    assert "Failed to load plugin from entry point" in caplog.text


def test_entry_point_discovery_rejects_non_plugin_strict(monkeypatch):
    monkeypatch.setattr(
        plugins_loader.metadata,
        "entry_points",
        lambda group: [_FakeEntryPoint(object())],
    )
    with pytest.raises(TypeError):
        get_plugins(make_settings(PLUGINS_STRICT=True))


def test_declared_incompatible_plugin_api_fails_before_hooks_run():
    class IncompatiblePlugin(Plugin):
        name = "incompatible"
        plugin_api_min_version = PLUGIN_API_VERSION + 1
        plugin_api_max_version = PLUGIN_API_VERSION + 1

    register(IncompatiblePlugin())

    with pytest.raises(PluginApiCompatibilityError, match="but core provides"):
        get_plugins(make_settings())


def test_declared_current_plugin_api_is_accepted():
    class CompatiblePlugin(Plugin):
        name = "compatible"
        plugin_api_min_version = PLUGIN_API_VERSION
        plugin_api_max_version = PLUGIN_API_VERSION

    register(CompatiblePlugin())

    assert "compatible" in [plugin.name for plugin in get_plugins(make_settings())]


# --- Worker task and queue handler registries -------------------------------


class WorkerPlugin(Plugin):
    name = "worker_plugin"

    def __init__(self):
        self.specs = [
            WorkerTaskSpec(name="AlwaysOn", factory=lambda ctx: _noop()),
            WorkerTaskSpec(
                name="GatedOff",
                factory=lambda ctx: _noop(),
                enabled=lambda settings: False,
            ),
        ]

    def worker_tasks(self, ctx):
        return self.specs

    def queue_handlers(self, ctx):
        async def _handler(ctx, payload):
            return None

        return {"worker_plugin_events": _handler, "yookassa": _handler}


async def _noop():
    return None


def test_collect_worker_tasks_returns_plugin_specs():
    plugin = WorkerPlugin()
    register(plugin)
    ctx = PluginContext(settings=make_settings())

    specs = collect_worker_tasks(ctx)

    names = [spec.name for spec in specs]
    assert "AlwaysOn" in names and "GatedOff" in names
    # Telemetry built-in contributes its worker task through the same hook.
    assert "TelemetryWorker" in names


def test_collect_queue_handlers_skips_reserved_names(caplog):
    register(WorkerPlugin())
    ctx = PluginContext(settings=make_settings())

    with caplog.at_level("ERROR"):
        handlers = collect_queue_handlers(ctx, reserved={"yookassa", "panel", "panel_sync"})

    assert set(handlers) == {"worker_plugin_events"}
    assert "already taken" in caplog.text


def test_collect_queue_handlers_conflict_is_fatal_in_strict_mode():
    register(WorkerPlugin())
    ctx = PluginContext(settings=make_settings(PLUGINS_STRICT=True))

    with pytest.raises(ValueError, match="already taken"):
        collect_queue_handlers(ctx, reserved={"yookassa"})


# --- Migration chains --------------------------------------------------------


def _dummy_migration(migration_id: str) -> Migration:
    return Migration(id=migration_id, description="test", upgrade=lambda connection: None)


def test_validate_migration_chains_requires_namespace_prefix():
    chains = {"myplugin": [_dummy_migration("0001_initial")]}
    with pytest.raises(ValueError, match=r"must start with 'myplugin\.'"):
        validate_migration_chains(chains)


def test_validate_migration_chains_accepts_prefixed_and_core_ids():
    validate_migration_chains(
        {
            "core": [_dummy_migration("0001_initial")],
            "myplugin": [_dummy_migration("myplugin.0001_initial")],
        }
    )


def test_collect_migrations_groups_by_plugin_name():
    class MigratingPlugin(Plugin):
        name = "migrating"

        def migrations(self):
            return [_dummy_migration("migrating.0001_initial")]

    register(MigratingPlugin())
    chains = plugins_loader.collect_migrations(make_settings())
    assert list(chains) == ["migrating"]
    assert chains["migrating"][0].id == "migrating.0001_initial"


# --- Plugin locales -----------------------------------------------------------


def test_apply_plugin_locales_merges_without_overriding_core(tmp_path):
    locales_dir = tmp_path / "locales"
    locales_dir.mkdir()
    (locales_dir / "en.json").write_text(
        json.dumps({"plugin_only_key": "Plugin value", "yes_button": "Hijacked"}),
        encoding="utf-8",
    )

    class LocalizedPlugin(Plugin):
        name = "localized"

        def locales_dir(self):
            return locales_dir

    register(LocalizedPlugin())
    i18n = JsonI18n(path="locales", default="en")
    core_value = i18n.gettext("en", "yes_button")

    apply_plugin_locales(make_settings(), i18n)

    assert i18n.gettext("en", "plugin_only_key") == "Plugin value"
    assert i18n.gettext("en", "yes_button") == core_value


# --- Built-in plugins ---------------------------------------------------------


def test_builtin_lknpd_plugin_provides_service():
    ctx = PluginContext(settings=make_settings())
    run_setup(ctx)
    service = ctx.services.get("lknpd_service")
    assert service is not None
    assert service.configured is False


def test_builtin_lknpd_plugin_respects_existing_service():
    sentinel = object()
    ctx = PluginContext(settings=make_settings(), services={"lknpd_service": sentinel})
    run_setup(ctx)
    assert ctx.services["lknpd_service"] is sentinel
