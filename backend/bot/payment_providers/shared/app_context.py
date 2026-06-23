from __future__ import annotations

from typing import TypeVar, cast

from aiohttp import web

T = TypeVar("T")


def app_required(request: web.Request, key: str, _expected_type: type[T]) -> T:
    return cast(T, request.app[key])


def app_optional(request: web.Request, key: str, _expected_type: type[T]) -> T | None:
    return cast(T | None, request.app.get(key))
