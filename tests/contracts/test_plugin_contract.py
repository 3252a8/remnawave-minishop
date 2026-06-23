from __future__ import annotations

import asyncio

from bot.infra import events
from bot.plugins import Plugin, PluginContext, register, reset_plugins, run_setup
from config.settings import Settings


def make_settings(**overrides: object) -> Settings:
    values = {
        "_env_file": None,
        "BOT_TOKEN": "x",
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
        "ADMIN_IDS": "1",
    }
    values.update(overrides)
    return Settings(**values)


def test_plugin_base_hooks_are_noops_and_context_services_stays_dict() -> None:
    service_marker = object()
    ctx = PluginContext(settings=make_settings(), services={"sample": service_marker})
    plugin = Plugin()

    plugin.setup(ctx)
    plugin.setup_bot(ctx, user_root=object(), admin_root=object())
    plugin.setup_web(ctx, object(), scope="webapp")

    assert ctx.services == {"sample": service_marker}
    assert plugin.worker_tasks(ctx) == []
    assert plugin.queue_handlers(ctx) == {}
    assert plugin.migrations() == []
    assert plugin.locales_dir() is None
    assert plugin.entitlements_provider() is None


def test_plugin_setup_subscriber_receives_event_name_and_plain_dict_payload() -> None:
    received = []

    async def subscriber(event_name: str, payload: dict[str, object]) -> None:
        received.append((event_name, payload, type(payload)))

    class SubscriberPlugin(Plugin):
        name = "subscriber_contract"
        version = "1.0.0"

        def setup(self, ctx: PluginContext) -> None:
            events.subscribe("contract.sample", subscriber)

    reset_plugins()
    events.reset_subscribers()
    register(SubscriberPlugin())
    try:
        run_setup(PluginContext(settings=make_settings()))
        asyncio.run(events.emit("contract.sample", {"user_id": 42}))
    finally:
        reset_plugins()
        events.reset_subscribers()

    assert received == [("contract.sample", {"user_id": 42}, dict)]
