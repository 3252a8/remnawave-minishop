from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .loader import (
        apply_plugin_locales,
        collect_migrations,
        collect_queue_handlers,
        collect_worker_tasks,
        configure_entitlements,
        get_plugins,
        register,
        reset_plugins,
        run_setup,
        setup_bot_plugins,
        setup_web_plugins,
    )
    from .spec import (
        ENTRY_POINT_GROUP,
        PLUGIN_API_VERSION,
        WEB_SCOPE_WEBAPP,
        WEB_SCOPE_WEBHOOKS,
        Plugin,
        PluginApiCompatibilityError,
        PluginContext,
        PluginLocaleGroup,
        QueueHandler,
        WorkerTaskSpec,
        validate_plugin_api_compatibility,
    )

__all__ = [
    "ENTRY_POINT_GROUP",
    "PLUGIN_API_VERSION",
    "WEB_SCOPE_WEBAPP",
    "WEB_SCOPE_WEBHOOKS",
    "Plugin",
    "PluginApiCompatibilityError",
    "PluginContext",
    "PluginLocaleGroup",
    "QueueHandler",
    "WorkerTaskSpec",
    "apply_plugin_locales",
    "collect_migrations",
    "collect_queue_handlers",
    "collect_worker_tasks",
    "configure_entitlements",
    "get_plugins",
    "register",
    "reset_plugins",
    "run_setup",
    "setup_bot_plugins",
    "setup_web_plugins",
    "validate_plugin_api_compatibility",
]

_LOADER_EXPORTS = {
    "apply_plugin_locales",
    "collect_migrations",
    "collect_queue_handlers",
    "collect_worker_tasks",
    "configure_entitlements",
    "get_plugins",
    "register",
    "reset_plugins",
    "run_setup",
    "setup_bot_plugins",
    "setup_web_plugins",
}

_SPEC_EXPORTS = {
    "ENTRY_POINT_GROUP",
    "PLUGIN_API_VERSION",
    "WEB_SCOPE_WEBAPP",
    "WEB_SCOPE_WEBHOOKS",
    "Plugin",
    "PluginApiCompatibilityError",
    "PluginContext",
    "PluginLocaleGroup",
    "QueueHandler",
    "WorkerTaskSpec",
    "validate_plugin_api_compatibility",
}


def __getattr__(name: str) -> Any:
    if name in _LOADER_EXPORTS:
        module = importlib.import_module(".loader", __package__)
        value = getattr(module, name)
        globals()[name] = value
        return value
    if name in _SPEC_EXPORTS:
        module = importlib.import_module(".spec", __package__)
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return list(__all__)
