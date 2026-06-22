"""Heleket provider facade."""

from . import service as _service

_NAMESPACE = {
    _name: _value
    for _name, _value in vars(_service).items()
    if not _name.startswith("__") and _name != "annotations"
}

globals().update(_NAMESPACE)

__all__ = sorted(_NAMESPACE)
