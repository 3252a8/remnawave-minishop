"""Shared JSON response helpers for HTTP handlers."""

from __future__ import annotations

from typing import Any, cast

from aiohttp import web


def json_response(data: Any = None, **kwargs: Any) -> web.Response:
    return cast(web.Response, web.json_response(data, **kwargs))
