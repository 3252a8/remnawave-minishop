from __future__ import annotations

import logging

from aiohttp import web

from bot.infra import events
from bot.plugins.spec import WEB_SCOPE_WEBAPP, Plugin, PluginContext

logger = logging.getLogger(__name__)


async def _on_user_registered(event_name: str, payload: dict[str, object]) -> None:
    logger.info(
        "AuditLoggerPlugin observed %s with payload keys: %s",
        event_name,
        sorted(payload),
    )


async def _health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "plugin": "audit_logger"})


class AuditLoggerPlugin(Plugin):
    name = "audit_logger"
    version = "0.1.0"
    plugin_api_min_version = 1
    plugin_api_max_version = 1

    def setup(self, ctx: PluginContext) -> None:
        ctx.services["audit_logger.enabled"] = True
        events.subscribe(events.USER_REGISTERED, _on_user_registered)

    def setup_web(self, ctx: PluginContext, app: web.Application, *, scope: str) -> None:
        if scope != WEB_SCOPE_WEBAPP:
            return
        app.router.add_get("/plugins/audit-logger/health", _health)


plugin = AuditLoggerPlugin()
