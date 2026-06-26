"""OpenAPI generation from the live aiohttp router.

The generator intentionally walks the same router objects the application uses,
then enriches routes with typed request/response schemas. Routes without typed
models still appear with method, path, parameters, and a generic JSON response
envelope.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from aiohttp import web
from pydantic import BaseModel

from bot.app.web.route_contracts import (
    ADMIN_SECURITY,
    RouteContract,
    get_contracts,
    ok_envelope,
    schema_ref,
)
from bot.app.web.webapp.routes import setup_subscription_webapp_routes
from bot.plugins import WEB_SCOPE_WEBAPP, PluginContext, setup_web_plugins

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT_PATH = REPO_ROOT / "docs" / "openapi.json"

_PATH_PARAM_RE = re.compile(r"{(?P<name>[^}:]+)(?::(?P<pattern>[^}]+))?}")
_GENERIC_JSON_RESPONSE = ok_envelope({}, [])


def _build_core_webapp() -> web.Application:
    app = web.Application()
    setup_subscription_webapp_routes(app)

    settings = SimpleNamespace(PLUGINS_ENABLED=False, PLUGINS_STRICT=False)
    ctx = PluginContext(settings=settings)
    setup_web_plugins(ctx, app, scope=WEB_SCOPE_WEBAPP)
    return app


def _route_path(route: web.AbstractRoute) -> str:
    resource = route.resource
    if resource is None:
        return ""
    info = resource.get_info()
    return str(info.get("formatter") or getattr(resource, "canonical", ""))


def _group_pattern(route: web.AbstractRoute, name: str) -> str | None:
    if route.resource is None:
        return None
    pattern = route.resource.get_info().get("pattern")
    if pattern is None:
        return None
    match = re.search(rf"\?P<{re.escape(name)}>([^)]+)", pattern.pattern)
    return match.group(1) if match else None


def _param_schema(raw_pattern: str | None) -> dict[str, Any]:
    if not raw_pattern:
        return {"type": "string"}
    if raw_pattern in {r"\d+", r"-?\d+", r"[0-9]+", r"-?[0-9]+"}:
        return {"type": "integer"}
    if "|" in raw_pattern and not re.search(r"[\\[\]()+*?{}]", raw_pattern):
        return {"type": "string", "enum": raw_pattern.split("|")}
    schema: dict[str, Any] = {"type": "string"}
    if raw_pattern:
        schema["pattern"] = raw_pattern
    return schema


def _path_parameters(path: str, route: web.AbstractRoute) -> list[dict[str, Any]]:
    parameters: list[dict[str, Any]] = []
    for match in _PATH_PARAM_RE.finditer(path):
        name = match.group("name")
        raw_pattern = match.group("pattern") or _group_pattern(route, name)
        parameters.append(
            {
                "name": name,
                "in": "path",
                "required": True,
                "schema": _param_schema(raw_pattern),
            }
        )
    return parameters


def _tag_for_path(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "api" and parts[1] == "admin":
        return "admin"
    if len(parts) >= 2 and parts[0] == "api":
        return parts[1]
    return "api"


def _operation_summary(handler_name: str) -> str:
    summary = handler_name
    if summary.endswith("_route"):
        summary = summary[: -len("_route")]
    return summary.replace("_", " ").title()


def _operation_id(method: str, handler_name: str) -> str:
    return f"{method.lower()}_{handler_name}"


def _json_response(contract: RouteContract | None) -> dict[str, Any]:
    if contract is not None and contract.response_content_type != "application/json":
        return {
            "description": "Response",
            "content": {
                contract.response_content_type: {
                    "schema": contract.response_schema or {"type": "string"}
                }
            },
        }
    schema = (
        contract.response_schema
        if contract and contract.response_schema
        else _GENERIC_JSON_RESPONSE
    )
    return {
        "description": "JSON response",
        "content": {"application/json": {"schema": schema}},
    }


def _operation_for_route(
    route: web.AbstractRoute,
    path: str,
    contracts: dict[str, RouteContract],
) -> dict[str, Any]:
    method = route.method.upper()
    handler_name = getattr(route.handler, "__name__", route.handler.__class__.__name__)
    contract = contracts.get(handler_name)
    operation: dict[str, Any] = {
        "operationId": _operation_id(method, handler_name),
        "summary": _operation_summary(handler_name),
        "tags": [_tag_for_path(path)],
        "responses": {"200": _json_response(contract)},
    }
    parameters = _path_parameters(path, route)
    if parameters:
        operation["parameters"] = parameters
    if contract is not None and contract.security is not None:
        operation["security"] = contract.security
    elif path.startswith("/api/admin/"):
        operation["security"] = ADMIN_SECURITY
    request_content: dict[str, dict[str, Any]] | None = None
    request_schema: dict[str, Any] | None = None
    request_content_type = "application/json"
    if contract is not None:
        if contract.request_content is not None:
            request_content = contract.request_content
        else:
            request_schema = (
                schema_ref(contract.request_model)
                if contract.request_model is not None
                else contract.request_schema
            )
            request_content_type = contract.request_content_type
    if request_content is not None:
        operation["requestBody"] = {
            "required": True,
            "content": {
                content_type: {"schema": schema}
                for content_type, schema in sorted(request_content.items())
            },
        }
    elif request_schema is not None:
        operation["requestBody"] = {
            "required": True,
            "content": {
                request_content_type: {
                    "schema": request_schema,
                }
            },
        }
    return operation


def _pop_json_schema_defs(schema: Any) -> dict[str, Any]:
    if isinstance(schema, list):
        defs: dict[str, Any] = {}
        for item in schema:
            defs.update(_pop_json_schema_defs(item))
        return defs
    if not isinstance(schema, dict):
        return {}

    defs = {
        str(name): nested_schema
        for name, nested_schema in (schema.pop("$defs", {}) or {}).items()
        if isinstance(nested_schema, dict)
    }
    for nested_schema in list(defs.values()):
        defs.update(_pop_json_schema_defs(nested_schema))
    for value in list(schema.values()):
        defs.update(_pop_json_schema_defs(value))
    return defs


def _components(contracts: dict[str, RouteContract]) -> dict[str, Any]:
    models: set[type[BaseModel]] = set()
    for contract in contracts.values():
        if contract.request_model is not None:
            models.add(contract.request_model)
        models.update(contract.models)
    schemas: dict[str, Any] = {}
    for model in sorted(models, key=lambda item: item.__name__):
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        schemas.update(_pop_json_schema_defs(schema))
        schemas[model.__name__] = schema
    return {
        "schemas": {name: schemas[name] for name in sorted(schemas)},
        "securitySchemes": {
            "AdminSession": {
                "type": "apiKey",
                "in": "cookie",
                "name": "rw_webapp_session",
                "description": "Authenticated admin webapp session cookie.",
            },
            "AdminBearer": {
                "type": "http",
                "scheme": "bearer",
                "description": "Authenticated admin bearer token.",
            },
            "UserSession": {
                "type": "apiKey",
                "in": "cookie",
                "name": "rw_webapp_session",
                "description": "Authenticated Mini App user session cookie.",
            },
            "UserBearer": {
                "type": "http",
                "scheme": "bearer",
                "description": "Authenticated Mini App user bearer token.",
            },
        },
    }


def generate_openapi() -> dict[str, Any]:
    app = _build_core_webapp()
    contracts = get_contracts()
    paths: dict[str, dict[str, Any]] = {}
    for route in app.router.routes():
        method = route.method.upper()
        if method == "HEAD":
            continue
        path = _route_path(route)
        if not path.startswith("/api/"):
            continue
        paths.setdefault(path, {})[method.lower()] = _operation_for_route(route, path, contracts)

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Remnawave Minishop HTTP API",
            "version": "0.1.0",
            "description": (
                "Core and built-in Mini App HTTP API generated from the live aiohttp router."
            ),
        },
        "x-generated-from": {
            "router": "bot.app.web.webapp.routes.setup_subscription_webapp_routes",
            "plugins": "core+builtin only",
        },
        "paths": {path: paths[path] for path in sorted(paths)},
        "components": _components(contracts),
    }


def serialize_openapi(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_openapi(path: Path = DEFAULT_OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_openapi(generate_openapi()), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the OpenAPI artifact.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    write_openapi(args.output)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
