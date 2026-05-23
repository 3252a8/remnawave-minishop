"""Compatibility facade for the subscription Mini App backend."""

# ruff: noqa: I001

from bot.app.web.webapp import (
    _runtime as _runtime,
    account as _account,
    application as _application,
    assets as _assets,
    auth as _auth,
    billing as _billing,
    common as _common,
    devices as _devices,
    guides as _guides,
    payloads as _payloads,
    routes as _routes,
    serializers as _serializers,
    support as _support,
)

_MODULES = (
    _runtime,
    _payloads,
    _common,
    _assets,
    _auth,
    _account,
    _serializers,
    _billing,
    _devices,
    _guides,
    _support,
    _routes,
    _application,
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
