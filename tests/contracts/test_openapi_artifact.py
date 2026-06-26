from __future__ import annotations

import json
from pathlib import Path

from bot.app.web.openapi import (
    DEFAULT_OUTPUT_PATH,
    _build_core_webapp,
    _route_path,
    generate_openapi,
    serialize_openapi,
)
from bot.app.web.route_contracts import get_contracts


def test_openapi_artifact_is_current():
    expected = DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
    actual = serialize_openapi(generate_openapi())

    assert actual == expected, "Regenerate docs/openapi.json with backend/bot/app/web/openapi.py"


def test_openapi_includes_typed_promos_contracts():
    document = json.loads(DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8"))

    create_operation = document["paths"]["/api/admin/promos"]["post"]
    assert (
        create_operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/PromoCreateBody"
    )
    assert (
        create_operation["responses"]["200"]["content"]["application/json"]["schema"]["properties"][
            "promo"
        ]["$ref"]
        == "#/components/schemas/PromoOut"
    )

    export_operation = document["paths"]["/api/admin/payments/export.csv"]["get"]
    assert "text/csv" in export_operation["responses"]["200"]["content"]

    avatar_operation = document["paths"]["/api/admin/users/{user_id}/avatar"]["get"]
    assert "image/jpeg" in avatar_operation["responses"]["200"]["content"]


def test_openapi_marks_user_session_security():
    document = json.loads(DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8"))
    security_schemes = document["components"]["securitySchemes"]
    assert security_schemes["UserSession"]["name"] == "rw_webapp_session"
    assert security_schemes["UserBearer"]["scheme"] == "bearer"

    user_security = [{"UserSession": []}, {"UserBearer": []}]
    assert document["paths"]["/api/me"]["get"]["security"] == user_security
    assert document["paths"]["/api/devices"]["get"]["security"] == user_security
    assert document["paths"]["/api/subscription-guides"]["get"]["security"] == user_security

    assert "security" not in document["paths"]["/api/bootstrap"]["get"]
    assert "security" not in document["paths"]["/api/i18n"]["get"]
    assert (
        "security" not in document["paths"]["/api/subscription-guides/public/{share_token}"]["get"]
    )


def test_openapi_lists_every_live_api_route():
    document = json.loads(DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8"))
    generated = generate_openapi()

    assert set(document["paths"]) == set(generated["paths"])
    assert Path("docs/openapi.json") == DEFAULT_OUTPUT_PATH.relative_to(Path.cwd())


def test_live_api_routes_have_response_contracts():
    app = _build_core_webapp()
    contracts = get_contracts()
    missing = []

    for route in app.router.routes():
        if route.method.upper() == "HEAD":
            continue

        path = _route_path(route)
        if not path.startswith("/api/"):
            continue

        handler_name = getattr(route.handler, "__name__", "")
        contract = contracts.get(handler_name)
        if contract is None or contract.response_schema is None:
            missing.append(f"{route.method} {path} ({handler_name})")

    assert missing == []


def test_live_api_routes_are_registered_in_contracts():
    app = _build_core_webapp()
    contracts = get_contracts()

    api_handlers = {
        getattr(route.handler, "__name__", "")
        for route in app.router.routes()
        if route.method != "HEAD"
        and _route_path(route).startswith("/api/")
    }

    missing_contracts = sorted(
        handler
        for handler in api_handlers
        if handler
        and contracts.get(handler) is None
        and handler not in {"", None}
    )
    assert missing_contracts == []

    undocumented_contracts = sorted(
        handler for handler in contracts if handler not in api_handlers
    )
    assert undocumented_contracts == []
