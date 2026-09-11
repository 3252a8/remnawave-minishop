"""Lazy registry for legacy-source adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceAdapter:
    source_type: str
    description: str
    sections: tuple[str, ...]
    env_reader: Callable[[str | None], dict[str, str]]
    importer_factory: Callable[..., Any]


def _read_plain_env(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    values: dict[str, str] = {}
    for raw_line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _remnashop_factory(**kwargs: Any) -> Any:
    from .remnashop import RemnashopImporter

    return RemnashopImporter(**kwargs)


def _bedolaga_factory(**kwargs: Any) -> Any:
    from .bedolaga import BedolagaImporter

    return BedolagaImporter(**kwargs)


def _remnashop_env_reader(path: str | None) -> dict[str, str]:
    from .remnashop_env import read_remnashop_env_file

    return read_remnashop_env_file(path)


ADAPTERS = {
    "remnashop": SourceAdapter(
        source_type="remnashop",
        description="Remnashop",
        sections=("users", "referrals", "subscriptions", "payments", "promocodes", "settings"),
        env_reader=_remnashop_env_reader,
        importer_factory=_remnashop_factory,
    ),
    "bedolaga": SourceAdapter(
        source_type="bedolaga",
        description="Bedolaga VPN",
        sections=(
            "users",
            "referrals",
            "tariffs",
            "subscriptions",
            "payments",
            "gifts",
            "promocodes",
            "support",
            "advertising",
            "partners",
            "settings",
        ),
        env_reader=_read_plain_env,
        importer_factory=_bedolaga_factory,
    ),
}


def get_adapter(source_type: str) -> SourceAdapter:
    try:
        return ADAPTERS[source_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported legacy source: {source_type}") from exc


SOURCE_TYPES = tuple(ADAPTERS)
