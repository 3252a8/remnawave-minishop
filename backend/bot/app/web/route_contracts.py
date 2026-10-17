"""Decentralized OpenAPI route contracts for the web API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

ADMIN_SECURITY: list[dict[str, list[Any]]] = [{"AdminSession": []}, {"AdminBearer": []}]
USER_SECURITY: list[dict[str, list[Any]]] = [{"UserSession": []}, {"UserBearer": []}]
STRING_SCHEMA: dict[str, str] = {"type": "string"}
INTEGER_SCHEMA: dict[str, str] = {"type": "integer"}
NUMBER_SCHEMA: dict[str, str] = {"type": "number"}
BOOLEAN_SCHEMA: dict[str, str] = {"type": "boolean"}
NULLABLE_STRING_SCHEMA: dict[str, list[str]] = {"type": ["string", "null"]}
NULLABLE_INTEGER_SCHEMA: dict[str, list[str]] = {"type": ["integer", "null"]}
NULLABLE_NUMBER_SCHEMA: dict[str, list[str]] = {"type": ["number", "null"]}
JSON_OBJECT_SCHEMA: dict[str, Any] = {"type": "object", "additionalProperties": True}
JSON_ARRAY_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": JSON_OBJECT_SCHEMA,
}
BINARY_RESPONSE_SCHEMA: dict[str, str] = {"type": "string", "format": "binary"}
GENERIC_OK_RESPONSE: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ok"],
    "properties": {
        "ok": {"type": "boolean", "const": True},
    },
}


@dataclass(frozen=True)
class RouteContract:
    request_model: type[BaseModel] | None = None
    request_schema: dict[str, Any] | None = None
    request_content_type: str = "application/json"
    request_content: dict[str, dict[str, Any]] | None = None
    response_schema: dict[str, Any] | None = None
    response_content_type: str = "application/json"
    models: tuple[type[BaseModel], ...] = field(default_factory=tuple)
    security: list[dict[str, list[Any]]] | None = None
    query_parameters: tuple[dict[str, Any], ...] = field(default_factory=tuple)


_CONTRACTS: dict[str, RouteContract] = {}


def register_contract(handler_name: str, contract: RouteContract) -> None:
    """Register or replace a contract for an aiohttp handler function name."""

    _CONTRACTS[handler_name] = contract


def get_contracts() -> dict[str, RouteContract]:
    return dict(_CONTRACTS)


def reset_contracts() -> None:
    _CONTRACTS.clear()


def schema_ref(model: type[BaseModel]) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{model.__name__}"}


def ok_envelope(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["ok", *required],
        "properties": {
            "ok": {"type": "boolean", "const": True},
            **properties,
        },
    }


def loose_object_schema(description: str | None = None) -> dict[str, Any]:
    schema = dict(JSON_OBJECT_SCHEMA)
    if description:
        schema["description"] = description
    return schema


def loose_array_schema(description: str | None = None) -> dict[str, Any]:
    schema = dict(JSON_ARRAY_SCHEMA)
    if description:
        schema["description"] = description
    return schema


def ok_envelope_with(
    properties: dict[str, Any] | None = None,
    *,
    required: list[str] | None = None,
) -> dict[str, Any]:
    properties = properties or {}
    return ok_envelope(properties, required if required is not None else list(properties))


def ok_envelope_for(
    response_model: type[BaseModel] | None = None,
    *,
    key: str | None = None,
    many: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if response_model is not None and key is None:
        return {"allOf": [ok_envelope({}, []), schema_ref(response_model)]}

    properties: dict[str, Any] = {}
    required: list[str] = []
    if response_model is not None and key is not None:
        model_schema: dict[str, Any] = schema_ref(response_model)
        properties[key] = {"type": "array", "items": model_schema} if many else model_schema
        required.append(key)
    if extra:
        properties.update(extra)
        required.extend(extra)
    return ok_envelope(properties, required)
