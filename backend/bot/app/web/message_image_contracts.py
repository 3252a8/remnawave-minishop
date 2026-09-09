"""OpenAPI request shapes for JSON message bodies with an optional image."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from bot.app.web.route_contracts import BINARY_RESPONSE_SCHEMA, schema_ref


def message_image_request_content(model: type[BaseModel]) -> dict[str, dict[str, Any]]:
    return {
        "application/json": schema_ref(model),
        "multipart/form-data": {
            "allOf": [
                schema_ref(model),
                {
                    "type": "object",
                    "properties": {"image": BINARY_RESPONSE_SCHEMA},
                },
            ]
        },
    }
