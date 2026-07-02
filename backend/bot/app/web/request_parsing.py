"""Shared JSON request body parsing helpers for typed web API endpoints."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import NoReturn, TypeVar

from aiohttp import web
from pydantic import BaseModel, ValidationError

BodyModelT = TypeVar("BodyModelT", bound=BaseModel)
ValidationErrorResponseFactory = Callable[[ValidationError], web.Response]


def _error(status: int, code: str, message: str = "") -> web.Response:
    return web.json_response(
        {"ok": False, "error": code, "message": message or code},
        status=status,
    )


def _raise_response(response: web.Response) -> NoReturn:
    if response.status != 400:
        raise RuntimeError("parse_body_or_400 can only raise HTTP 400 responses")
    raise web.HTTPBadRequest(
        text=response.text or json.dumps({"ok": False, "error": "invalid_payload"}),
        content_type=response.content_type or "application/json",
    )


def _validation_error_summary(exc: ValidationError) -> str:
    messages: list[str] = []
    for error in exc.errors()[:3]:
        location = ".".join(str(part) for part in error.get("loc", ()) if part != "__root__")
        detail = str(error.get("msg") or "Invalid value")
        messages.append(f"{location}: {detail}" if location else detail)
    if len(exc.errors()) > 3:
        messages.append("...")
    return "; ".join(messages) or "Invalid payload"


async def parse_body[BodyModelT: BaseModel](
    request: web.Request,
    model_cls: type[BodyModelT],
) -> tuple[BodyModelT | None, web.Response | None]:
    """Parse and validate a JSON object body for a typed endpoint."""
    try:
        raw_payload = await request.json()
    except Exception:
        return None, _error(400, "invalid_payload", "Invalid JSON payload")

    if not isinstance(raw_payload, dict):
        return None, _error(400, "invalid_payload", "Payload must be a JSON object")

    try:
        return model_cls.model_validate(raw_payload), None
    except ValidationError as exc:
        return None, _error(400, "invalid_payload", _validation_error_summary(exc))


async def parse_body_or_400[BodyModelT: BaseModel](
    request: web.Request,
    model_cls: type[BodyModelT],
    *,
    validation_error_response_factory: ValidationErrorResponseFactory | None = None,
) -> BodyModelT:
    """Parse a typed JSON body or raise the existing JSON 400 envelope."""
    try:
        raw_payload = await request.json()
    except Exception:
        _raise_response(_error(400, "invalid_payload", "Invalid JSON payload"))

    if not isinstance(raw_payload, dict):
        _raise_response(_error(400, "invalid_payload", "Payload must be a JSON object"))

    try:
        return model_cls.model_validate(raw_payload)
    except ValidationError as exc:
        if validation_error_response_factory is not None:
            _raise_response(validation_error_response_factory(exc))
        _raise_response(_error(400, "invalid_payload", _validation_error_summary(exc)))
