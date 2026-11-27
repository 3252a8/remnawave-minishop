"""Minishop Plugin API v1 entry point."""

import json
from pathlib import Path

from aiohttp import web

from bot.plugins.extensions import ExtensionContributions
from bot.plugins.spec import WEB_SCOPE_WEBAPP, Plugin, PluginContext, WorkerTaskSpec
from db.migrator import Migration

from .alerts import PLUGIN_ID, alert_contributions, subscribe_to_events
from .api import setup_routes
from .localization import plugin_i18n
from .migrations import migrations
from .settings import SUPPORTS_USERS_TABLE
from .worker import run_refresh_worker

__version__: str = json.loads(Path(__file__).with_name("manifest.json").read_bytes())["version"]


class BlacklistPlugin(Plugin):
    name = PLUGIN_ID
    version = __version__
    plugin_api_min_version = 1
    plugin_api_max_version = 1

    def setup(self, ctx: PluginContext) -> None:
        if ctx.session_factory is not None:
            subscribe_to_events(ctx)

    def extensions(self, ctx: PluginContext) -> ExtensionContributions:
        contributions = alert_contributions()
        if not SUPPORTS_USERS_TABLE:
            return contributions

        from .users_table import add_users_table

        return add_users_table(contributions, plugin_i18n(ctx), ctx.settings.DEFAULT_LANGUAGE)

    def migrations(self) -> list[Migration]:
        return migrations()

    def setup_web(self, ctx: PluginContext, app: web.Application, *, scope: str) -> None:
        if scope == WEB_SCOPE_WEBAPP:
            setup_routes(app)
            if SUPPORTS_USERS_TABLE:
                from .users_table import setup_users_table

                setup_users_table(app, plugin_i18n(ctx), ctx.settings.DEFAULT_LANGUAGE)

    def locales_dir(self) -> Path:
        return Path(__file__).parent / "locales"

    def worker_tasks(self, ctx: PluginContext) -> list[WorkerTaskSpec]:
        return [WorkerTaskSpec(name=f"{self.name}.refresh", factory=run_refresh_worker)]


plugin = BlacklistPlugin()
