"""Shared JSON request body parsing helpers for typed web API endpoints."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import NoReturn, TypeVar

from aiohttp import web
from aiohttp.multipart import BodyPartReader
from pydantic import BaseModel, ValidationError

from bot.services.message_image_service import (
    MESSAGE_IMAGE_INPUT_MAX_BYTES,
    UploadedMessageImage,
)

BodyModelT = TypeVar("BodyModelT", bound=BaseModel)
ValidationErrorResponseFactory = Callable[[ValidationError], web.Response]
_MULTIPART_FIELD_MAX_BYTES = 64 * 1024
_MULTIPART_TOTAL_FIELDS_MAX_BYTES = 256 * 1024
_MULTIPART_MAX_FIELDS = 32


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


async def _read_multipart_part(part: BodyPartReader, *, limit: int) -> bytes:
    body = bytearray()
    while True:
        chunk = await part.read_chunk(size=64 * 1024)
        if not chunk:
            return bytes(body)
        body.extend(chunk)
        if len(body) > limit:
            _raise_response(_error(400, "payload_too_large", "Multipart field is too large"))


def _multipart_value(body: bytes) -> object:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        _raise_response(_error(400, "invalid_payload", "Multipart text must be UTF-8"))
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def parse_body_with_optional_image_or_400[BodyModelT: BaseModel](
    request: web.Request,
    model_cls: type[BodyModelT],
    *,
    validation_error_response_factory: ValidationErrorResponseFactory | None = None,
) -> tuple[BodyModelT, UploadedMessageImage | None]:
    """Parse JSON or the same fields plus one streamed multipart image."""

    headers = getattr(request, "headers", {})
    content_type = (headers.get("Content-Type") or "").lower()
    if not content_type.startswith("multipart/form-data"):
        return (
            await parse_body_or_400(
                request,
                model_cls,
                validation_error_response_factory=validation_error_response_factory,
            ),
            None,
        )

    payload: dict[str, object] = {}
    image: UploadedMessageImage | None = None
    total_field_bytes = 0
    field_count = 0
    try:
        reader = await request.multipart()
        async for raw_part in reader:
            if not isinstance(raw_part, BodyPartReader):
                continue
            part = raw_part
            name = str(part.name or "").strip()
            if not name:
                _raise_response(_error(400, "invalid_payload", "Multipart field name is required"))
            if name == "image":
                if image is not None:
                    _raise_response(
                        _error(400, "too_many_images", "Only one image may be attached")
                    )
                body = await _read_multipart_part(part, limit=MESSAGE_IMAGE_INPUT_MAX_BYTES)
                image = UploadedMessageImage(
                    data=body,
                    filename=part.filename or "",
                    content_type=part.headers.get("Content-Type", ""),
                )
                continue
            if part.filename:
                _raise_response(
                    _error(400, "invalid_file_field", "Only the image file field is allowed")
                )
            if name in payload:
                _raise_response(
                    _error(400, "duplicate_field", f"Multipart field {name} was repeated")
                )
            field_count += 1
            if field_count > _MULTIPART_MAX_FIELDS:
                _raise_response(_error(400, "invalid_payload", "Too many multipart fields"))
            body = await _read_multipart_part(part, limit=_MULTIPART_FIELD_MAX_BYTES)
            total_field_bytes += len(body)
            if total_field_bytes > _MULTIPART_TOTAL_FIELDS_MAX_BYTES:
                _raise_response(_error(400, "payload_too_large", "Multipart fields are too large"))
            payload[name] = _multipart_value(body)
    except web.HTTPBadRequest:
        raise
    except Exception:
        _raise_response(_error(400, "invalid_payload", "Invalid multipart payload"))

    try:
        return model_cls.model_validate(payload), image
    except ValidationError as exc:
        if validation_error_response_factory is not None:
            _raise_response(validation_error_response_factory(exc))
        _raise_response(_error(400, "invalid_payload", _validation_error_summary(exc)))
