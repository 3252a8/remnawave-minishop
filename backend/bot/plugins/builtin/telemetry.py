"""Built-in plugin wiring the anonymous install telemetry beacon.

The beacon implementation lives in :mod:`bot.services.telemetry_worker`;
this plugin only contributes its background task to the worker process.
Opt-out behavior (env toggle, admin toggle, empty endpoint/key) is handled
by the worker itself.
"""

from __future__ import annotations

from typing import List

from bot.plugins.spec import Plugin, PluginContext, WorkerTaskSpec


def _telemetry_task(ctx: PluginContext):
    from bot.services.telemetry_worker import TelemetryWorker

    return TelemetryWorker(ctx.settings, ctx.session_factory).run()


class TelemetryPlugin(Plugin):
    name = "telemetry"
    version = "1.0.0"

    def worker_tasks(self, ctx: PluginContext) -> List[WorkerTaskSpec]:
        return [WorkerTaskSpec(name="TelemetryWorker", factory=_telemetry_task)]
