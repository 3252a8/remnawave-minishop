"""Normalize isolated test stands without hiding required dependencies."""

from typing import Any


def prune_optional_dependencies(services: dict[str, Any]) -> None:
    """Remove absent profile dependencies without hiding a broken required edge."""
    for name, service in services.items():
        dependencies = service.get("depends_on", {})
        for dependency, options in list(dependencies.items()):
            if dependency in services:
                continue
            if options.get("required", True):
                raise RuntimeError(f"{name} requires missing service {dependency}")
            del dependencies[dependency]
