"""Built-in plugin providing the LKNPD (lknpd.nalog.ru) receipt service.

The service implementation lives in :mod:`bot.services.lknpd_service`; this
plugin contributes a configured instance under the ``lknpd_service`` key so
payment flows can send self-employed income receipts. Consumers read the
service with ``.get(...)`` and check ``configured``, so the integration
degrades gracefully when credentials are absent.
"""

from __future__ import annotations

from bot.plugins.spec import Plugin, PluginContext

SERVICE_KEY = "lknpd_service"


class LknpdPlugin(Plugin):
    name = "lknpd"
    version = "1.0.0"

    def setup(self, ctx: PluginContext) -> None:
        if SERVICE_KEY in ctx.services:
            return
        from bot.services.lknpd_service import LknpdService

        ctx.services[SERVICE_KEY] = LknpdService(
            ctx.settings.LKNPD_INN,
            ctx.settings.LKNPD_PASSWORD,
            api_url=ctx.settings.LKNPD_API_URL,
        )
