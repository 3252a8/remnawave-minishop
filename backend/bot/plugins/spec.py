"""Public contract for application plugins.

Plugins are separate Python packages that extend the application without
forking it. A package advertises itself through the ``minishop.plugins``
entry point group; the entry point must resolve to a :class:`Plugin`
subclass or instance.

Every hook is optional: the base class provides no-op defaults, so a plugin
only overrides what it needs. Hooks must not assume a particular call order
beyond the guarantees documented on each method.

The plugin API is experimental and may change between minor versions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Coroutine, Dict, List, Optional

if TYPE_CHECKING:
    from aiogram import Bot, Dispatcher, Router
    from aiohttp import web
    from sqlalchemy.orm import sessionmaker

    from bot.middlewares.i18n import JsonI18n
    from config.settings import Settings
    from db.migrator import Migration

ENTRY_POINT_GROUP = "minishop.plugins"

# Scopes passed to Plugin.setup_web: the webhooks app serves health checks
# and payment/panel webhooks, the webapp app serves the Mini App and admin API.
WEB_SCOPE_WEBHOOKS = "webhooks"
WEB_SCOPE_WEBAPP = "webapp"


@dataclass(frozen=True)
class WorkerTaskSpec:
    """A long-running background task contributed to the worker process.

    ``factory`` is called once at worker startup and must return the coroutine
    to run (typically ``SomeWorker(...).run()``). ``enabled`` is an optional
    settings predicate checked before the task is started.
    """

    name: str
    factory: Callable[["PluginContext"], Coroutine[Any, Any, None]]
    enabled: Optional[Callable[["Settings"], bool]] = None


#: Handler for one webhook-queue event; receives the context and the raw
#: event payload dict popped from the queue.
QueueHandler = Callable[["PluginContext", Dict[str, Any]], Awaitable[None]]


@dataclass
class PluginContext:
    """Shared core objects handed to every plugin hook.

    Availability depends on the entrypoint: the bot/web process fills all
    fields, while auxiliary entrypoints may leave ``bot`` or ``dispatcher``
    unset. Hooks must tolerate ``None`` for optional fields.
    """

    settings: "Settings"
    session_factory: Optional["sessionmaker"] = None
    bot: Optional["Bot"] = None
    i18n: Optional["JsonI18n"] = None
    dispatcher: Optional["Dispatcher"] = None
    services: Dict[str, Any] = field(default_factory=dict)


class Plugin:
    """Base class for application plugins; override any subset of hooks."""

    #: Unique plugin identifier (used in logs and diagnostics).
    name: str = "unnamed"
    #: Plugin version string (informational).
    version: str = "0.0.0"

    def setup(self, ctx: PluginContext) -> None:
        """General initialization; called first, once per process."""

    def setup_bot(
        self,
        ctx: PluginContext,
        *,
        user_root: "Router",
        admin_root: "Router",
    ) -> None:
        """Register aiogram routers.

        ``user_root`` is the root router (private chats only); routers included
        here run after the core user handlers. ``admin_root`` is already guarded
        by the admin filter, so routers included there only see admin updates.
        """

    def setup_web(self, ctx: PluginContext, app: "web.Application", *, scope: str) -> None:
        """Register aiohttp routes.

        Called once per web application after the core routes are registered.
        ``scope`` is :data:`WEB_SCOPE_WEBHOOKS` or :data:`WEB_SCOPE_WEBAPP`.
        """

    def worker_tasks(self, ctx: PluginContext) -> List[WorkerTaskSpec]:
        """Return background tasks to run in the worker process."""
        return []

    def queue_handlers(self, ctx: PluginContext) -> Dict[str, QueueHandler]:
        """Return webhook-queue handlers keyed by event provider name.

        Provider names already handled by the core (or another plugin) are
        rejected; pick names unique to the plugin.
        """
        return {}

    def migrations(self) -> List["Migration"]:
        """Return the plugin's database migration chain.

        Every migration id must be prefixed with ``"<plugin name>."`` (e.g.
        ``"myplugin.0001_initial"``); all chains share the core
        ``schema_migrations`` table. By convention plugin tables are named
        with an ``ext_<plugin>_`` prefix to avoid clashes with core tables.
        """
        return []

    def locales_dir(self) -> Optional[Path]:
        """Return a directory with extra locale JSON files (same layout as
        the core ``locales/`` directory). Plugin keys never override keys
        already defined by the core locales."""
        return None
