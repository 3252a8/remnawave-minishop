"""Compatibility facade for the admin Mini App API."""

# ruff: noqa: I001

from bot.app.web.admin_api_impl import (
    _runtime as _runtime,
    ads as _ads,
    auth as _auth,
    backups as _backups,
    broadcast as _broadcast,
    common as _common,
    health as _health,
    logs as _logs,
    panel as _panel,
    payments as _payments,
    promos as _promos,
    routes as _routes,
    settings as _settings,
    stats as _stats,
    support as _support,
    sync as _sync,
    tariffs as _tariffs,
    themes as _themes,
    translations as _translations,
    users as _users,
)

_MODULES = (
    _runtime,
    _auth,
    _common,
    _health,
    _stats,
    _users,
    _payments,
    _promos,
    _logs,
    _support,
    _broadcast,
    _sync,
    _ads,
    _backups,
    _settings,
    _tariffs,
    _themes,
    _translations,
    _panel,
    _routes,
)

_NAMESPACE = {}
for _module in _MODULES:
    _NAMESPACE.update(
        {
            _name: _value
            for _name, _value in vars(_module).items()
            if not _name.startswith("__") and _name != "annotations"
        }
    )

for _module in _MODULES:
    vars(_module).update(_NAMESPACE)

globals().update(_NAMESPACE)

__all__ = sorted(_name for _name in _NAMESPACE if not _name.startswith("__"))
