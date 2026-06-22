from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import web

import bot.app.web.admin_api  # noqa: F401 - populates admin_api_impl module namespaces
from bot.app.web.admin_api_impl import common as common_module
from bot.app.web.admin_api_impl import promos as promos_module
from bot.app.web.admin_api_impl.schemas import PromoOut


class _FakeRequest:
    def __init__(self, payload, *, app=None, match_info=None, query=None):
        self._payload = payload
        self.app = app or {}
        self.match_info = match_info or {}
        self.query = query or {}

    async def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeSession:
    def __init__(self):
        self.commit = AsyncMock()
        self.refresh = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


def _promo(**overrides):
    values = {
        "promo_code_id": 5,
        "code": "GIFT",
        "bonus_days": 7,
        "max_activations": 3,
        "current_activations": 1,
        "is_active": True,
        "valid_until": datetime(2026, 1, 8, tzinfo=timezone.utc),
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "created_by_admin_id": 100,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _json_body(response):
    return json.loads(response.text)


def _run_direct_bad_request(coro):
    try:
        return asyncio.run(coro)
    except web.HTTPBadRequest as exc:
        return exc


def test_promo_response_model_matches_legacy_serializer():
    promo = _promo(created_by_admin_id=None)

    assert PromoOut.from_orm_promo(promo).model_dump(mode="json") == common_module._serialize_promo(
        promo
    )


def test_promo_create_rejects_malformed_json():
    async def run():
        request = _FakeRequest(ValueError("bad json"))

        with patch.object(promos_module, "_require_admin_user_id", return_value=100):
            return await promos_module.admin_promo_create_route(request)

    response = _run_direct_bad_request(run())

    assert response.status == 400
    assert _json_body(response)["error"] == "invalid_payload"


def test_promo_create_uses_typed_body_and_response_model():
    async def run():
        session = _FakeSession()
        promo = _promo(valid_until=None)
        request = _FakeRequest(
            {
                "code": " gift ",
                "bonus_days": "7",
                "max_activations": "3",
                "valid_days": "",
                "ignored": "compatible",
            },
            app={"async_session_factory": lambda: session},
        )

        with (
            patch.object(promos_module, "_require_admin_user_id", return_value=100),
            patch.object(
                promos_module.promo_code_dal,
                "get_promo_code_by_code",
                AsyncMock(return_value=None),
            ) as get_existing,
            patch.object(
                promos_module.promo_code_dal,
                "create_promo_code",
                AsyncMock(return_value=promo),
            ) as create_promo,
        ):
            response = await promos_module.admin_promo_create_route(request)
        return response, session, promo, get_existing, create_promo

    response, session, promo, get_existing, create_promo = asyncio.run(run())

    assert response.status == 200
    get_existing.assert_awaited_once_with(session, "GIFT")
    created_payload = create_promo.await_args.args[1]
    assert created_payload == {
        "code": "GIFT",
        "bonus_days": 7,
        "max_activations": 3,
        "valid_until": None,
        "created_by_admin_id": 100,
        "is_active": True,
    }
    session.commit.assert_awaited_once()
    assert _json_body(response)["promo"] == PromoOut.from_orm_promo(promo).model_dump(mode="json")


def test_promo_create_keeps_invalid_valid_days_error_code():
    async def run():
        request = _FakeRequest(
            {"code": "gift", "bonus_days": 7, "max_activations": 3, "valid_days": "abc"}
        )

        with patch.object(promos_module, "_require_admin_user_id", return_value=100):
            return await promos_module.admin_promo_create_route(request)

    response = asyncio.run(run())

    assert response.status == 400
    assert _json_body(response)["error"] == "invalid_valid_days"


def test_promo_update_uses_typed_body_and_preserves_bool_coercion():
    async def run():
        session = _FakeSession()
        promo = _promo(is_active=True, bonus_days=9)
        request = _FakeRequest(
            {"is_active": "false", "bonus_days": "9"},
            app={"async_session_factory": lambda: session},
            match_info={"promo_id": "5"},
        )

        with (
            patch.object(promos_module, "_require_admin_user_id", return_value=100),
            patch.object(
                promos_module.promo_code_dal,
                "update_promo_code",
                AsyncMock(return_value=promo),
            ) as update_promo,
        ):
            response = await promos_module.admin_promo_update_route(request)
        return response, session, promo, update_promo

    response, session, promo, update_promo = asyncio.run(run())

    assert response.status == 200
    update_promo.assert_awaited_once_with(
        session,
        5,
        {"is_active": True, "bonus_days": 9},
    )
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(promo)
    assert _json_body(response)["promo"] == PromoOut.from_orm_promo(promo).model_dump(mode="json")


def test_promo_update_returns_no_changes_for_empty_typed_body():
    async def run():
        request = _FakeRequest({}, match_info={"promo_id": "5"})

        with patch.object(promos_module, "_require_admin_user_id", return_value=100):
            return await promos_module.admin_promo_update_route(request)

    response = asyncio.run(run())

    assert response.status == 400
    assert _json_body(response)["error"] == "no_changes"
