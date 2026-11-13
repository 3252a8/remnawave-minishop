"""OpenAPI request shapes for JSON message bodies with an optional image."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from bot.app.web.route_contracts import BINARY_RESPONSE_SCHEMA, schema_ref
from bot.services.message_image_service import SUPPORT_MESSAGE_IMAGE_MAX_COUNT


def message_image_request_content(
    model: type[BaseModel], *, multiple: bool = False
) -> dict[str, dict[str, Any]]:
    image_schema = (
        {
            "type": "array",
            "items": BINARY_RESPONSE_SCHEMA,
            "maxItems": SUPPORT_MESSAGE_IMAGE_MAX_COUNT,
        }
        if multiple
        else BINARY_RESPONSE_SCHEMA
    )
    return {
        "application/json": schema_ref(model),
        "multipart/form-data": {
            "allOf": [
                schema_ref(model),
                {
                    "type": "object",
                    "properties": {"image": image_schema},
                },
            ]
        },
    }
