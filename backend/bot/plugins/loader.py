"""Discovery and invocation of application plugins.

Plugins are discovered once per process through the ``minishop.plugins``
entry point group and cached. Tests (or embedding code) can also register
plugin instances programmatically with :func:`register`.

A failing plugin never breaks the core: errors are logged and the plugin is
skipped, unless ``PLUGINS_STRICT`` is enabled, in which case the error is
re-raised so a deployment that requires the plugin fails fast.
"""

from __future__ import annotations

import json
import logging
from importlib import metadata
from typing import TYPE_CHECKING, Dict, List, Optional, Set

from .spec import ENTRY_POINT_GROUP, Plugin, PluginContext, QueueHandler, WorkerTaskSpec

if TYPE_CHECKING:
    from aiogram import Router
    from aiohttp import web

    from bot.middlewares.i18n import JsonI18n
    from config.settings import Settings
    from db.migrator import Migration

logger = logging.getLogger(__name__)

_builtin_plugins: Optional[List[Plugin]] = None
_discovered_plugins: Optional[List[Plugin]] = None
_registered_plugins: List[Plugin] = []


def register(plugin: Plugin) -> None:
    """Register a plugin instance programmatically (primarily for tests)."""
    _registered_plugins.append(plugin)


def reset_plugins() -> None:
    """Drop the discovery cache and programmatic registrations (for tests)."""
    global _builtin_plugins, _discovered_plugins
    _builtin_plugins = None
    _discovered_plugins = None
    _registered_plugins.clear()


def _coerce_plugin(loaded: object, entry_point_name: str) -> Plugin:
    if isinstance(loaded, type):
        loaded = loaded()
    if not isinstance(loaded, Plugin):
        raise TypeError(
            f"Entry point {entry_point_name!r} in group {ENTRY_POINT_GROUP!r} must provide "
            f"a Plugin subclass or instance, got {type(loaded).__name__}"
        )
    return loaded


def _discover(settings: "Settings") -> List[Plugin]:
    plugins: List[Plugin] = []
    try:
        entry_points = metadata.entry_points(group=ENTRY_POINT_GROUP)
    except Exception:
        logger.exception("Failed to enumerate %s entry points", ENTRY_POINT_GROUP)
        if settings.PLUGINS_STRICT:
            raise
        return plugins
    for entry_point in entry_points:
        try:
            plugins.append(_coerce_plugin(entry_point.load(), entry_point.name))
        except Exception:
            logger.exception("Failed to load plugin from entry point %r", entry_point.name)
            if settings.PLUGINS_STRICT:
                raise
    return plugins


def _get_builtin_plugins() -> List[Plugin]:
    """Built-in plugins ship with the application and are always active;
    PLUGINS_ENABLED only gates externally installed plugins."""
    global _builtin_plugins
    if _builtin_plugins is None:
        from .builtin import BUILTIN_PLUGINS

        _builtin_plugins = [plugin_cls() for plugin_cls in BUILTIN_PLUGINS]
    return _builtin_plugins


def get_plugins(settings: "Settings") -> List[Plugin]:
    """Return active plugins: built-ins, then entry-point and registered ones."""
    global _discovered_plugins
    builtin = _get_builtin_plugins()
    if not settings.PLUGINS_ENABLED:
        return list(builtin)
    if _discovered_plugins is None:
        _discovered_plugins = _discover(settings)
        logger.info(
            "Plugins active: %s",
            ", ".join(
                f"{plugin.name}=={plugin.version}"
                for plugin in (*builtin, *_discovered_plugins, *_registered_plugins)
            )
            or "none",
        )
    return [*builtin, *_discovered_plugins, *_registered_plugins]


def _run_hook(settings: "Settings", plugin: Plugin, hook_name: str, *args, **kwargs) -> None:
    try:
        getattr(plugin, hook_name)(*args, **kwargs)
    except Exception:
        logger.exception("Plugin %r failed in %s; skipping it", plugin.name, hook_name)
        if settings.PLUGINS_STRICT:
            raise


def run_setup(ctx: PluginContext) -> None:
    """Invoke the general ``setup`` hook of every plugin."""
    for plugin in get_plugins(ctx.settings):
        _run_hook(ctx.settings, plugin, "setup", ctx)


def setup_bot_plugins(ctx: PluginContext, *, user_root: "Router", admin_root: "Router") -> None:
    """Let every plugin register its aiogram routers."""
    for plugin in get_plugins(ctx.settings):
        _run_hook(
            ctx.settings,
            plugin,
            "setup_bot",
            ctx,
            user_root=user_root,
            admin_root=admin_root,
        )


def setup_web_plugins(ctx: PluginContext, app: "web.Application", *, scope: str) -> None:
    """Let every plugin register its aiohttp routes on ``app``."""
    for plugin in get_plugins(ctx.settings):
        _run_hook(ctx.settings, plugin, "setup_web", ctx, app, scope=scope)


def collect_worker_tasks(ctx: PluginContext) -> List[WorkerTaskSpec]:
    """Gather background task specs from every plugin."""
    specs: List[WorkerTaskSpec] = []
    for plugin in get_plugins(ctx.settings):
        try:
            specs.extend(plugin.worker_tasks(ctx) or [])
        except Exception:
            logger.exception("Plugin %r failed in worker_tasks; skipping it", plugin.name)
            if ctx.settings.PLUGINS_STRICT:
                raise
    return specs


def collect_queue_handlers(
    ctx: PluginContext,
    *,
    reserved: Set[str],
) -> Dict[str, QueueHandler]:
    """Gather webhook-queue handlers from plugins.

    ``reserved`` holds provider names already taken by the core; a plugin
    handler that clashes with a reserved or previously collected name is
    rejected (fatal in strict mode).
    """
    handlers: Dict[str, QueueHandler] = {}
    for plugin in get_plugins(ctx.settings):
        try:
            contributed = plugin.queue_handlers(ctx) or {}
        except Exception:
            logger.exception("Plugin %r failed in queue_handlers; skipping it", plugin.name)
            if ctx.settings.PLUGINS_STRICT:
                raise
            continue
        for provider, handler in contributed.items():
            if provider in reserved or provider in handlers:
                message = (
                    f"Plugin {plugin.name!r} tried to register queue handler for "
                    f"provider {provider!r}, which is already taken"
                )
                logger.error(message)
                if ctx.settings.PLUGINS_STRICT:
                    raise ValueError(message)
                continue
            handlers[provider] = handler
    return handlers


def collect_migrations(settings: "Settings") -> Dict[str, List["Migration"]]:
    """Gather migration chains from plugins keyed by plugin name."""
    chains: Dict[str, List["Migration"]] = {}
    for plugin in get_plugins(settings):
        try:
            migrations = list(plugin.migrations() or [])
        except Exception:
            logger.exception("Plugin %r failed in migrations; skipping it", plugin.name)
            if settings.PLUGINS_STRICT:
                raise
            continue
        if not migrations:
            continue
        if plugin.name in chains:
            message = f"Duplicate plugin name {plugin.name!r} in migration chains"
            logger.error(message)
            if settings.PLUGINS_STRICT:
                raise ValueError(message)
            continue
        chains[plugin.name] = migrations
    return chains


def _read_locales_dir(path) -> Dict[str, Dict[str, str]]:
    locales: Dict[str, Dict[str, str]] = {}
    for file in sorted(path.glob("*.json")):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to read plugin locale file %s", file)
            continue
        if isinstance(data, dict):
            locales[file.stem] = {
                str(key): str(value) for key, value in data.items() if isinstance(value, str)
            }
    return locales


def apply_plugin_locales(settings: "Settings", i18n: "JsonI18n") -> None:
    """Merge plugin locale files into the i18n catalog.

    Plugin keys never override core keys; runtime overrides (DB/file) are
    layered on top by the existing override mechanism regardless of order.
    """
    for plugin in get_plugins(settings):
        try:
            locales_dir = plugin.locales_dir()
            if locales_dir is None:
                continue
            additions = _read_locales_dir(locales_dir)
            if additions:
                i18n.merge_base_locales(additions, source=plugin.name)
        except Exception:
            logger.exception("Plugin %r failed in locales_dir; skipping it", plugin.name)
            if settings.PLUGINS_STRICT:
                raise
