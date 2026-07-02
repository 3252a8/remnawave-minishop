from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import web

import bot.app.web.admin_api  # noqa: F401 - populates admin_api_impl module namespaces
from bot.app.web.admin_api_impl import common as common_module
from bot.app.web.admin_api_impl import promos as promos_module
from bot.app.web.admin_api_impl.schemas import PromoActivationOut, PromoOut


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
        "valid_until": datetime(2026, 1, 8, tzinfo=UTC),
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "created_by_admin_id": 100,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _settings():
    return SimpleNamespace(
        PROMO_DURATION_MULTIPLIER_MAX=12.0,
        PROMO_TRAFFIC_MULTIPLIER_MAX=12.0,
        SUBSCRIPTION_MINI_APP_URL=None,
    )


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


def test_promo_response_can_include_application_links():
    promo = _promo(code="SAVE20")
    request = _FakeRequest(
        {},
        app={
            "bot_username": "shop_bot",
            "settings": SimpleNamespace(
                SUBSCRIPTION_MINI_APP_URL="https://app.example.com/webapp?lang=ru",
            ),
        },
    )

    payload = promos_module._serialize_promo_for_request(request, promo)

    assert payload["bot_link"] == "https://t.me/shop_bot?start=promo_SAVE20"
    assert payload["webapp_link"] == "https://app.example.com/webapp?lang=ru&startapp=promo_SAVE20"


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
            app={"async_session_factory": lambda: session, "settings": _settings()},
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
        "discount_percent": None,
        "duration_multiplier": None,
        "traffic_multiplier": None,
        "bonus_requires_payment": False,
        "applies_to": "all",
        "min_subscription_months": None,
        "min_traffic_gb": None,
        "origin": "admin",
        "max_activations": 3,
        "valid_until": None,
        "created_by_admin_id": 100,
        "is_active": True,
    }
    session.commit.assert_awaited_once()
    assert _json_body(response)["promo"] == PromoOut.from_orm_promo(promo).model_dump(mode="json")


def test_promo_create_rejects_multiple_effects():
    async def run():
        request = _FakeRequest(
            {
                "code": "gift",
                "bonus_days": 7,
                "discount_percent": 10,
                "max_activations": 3,
            }
        )

        with patch.object(promos_module, "_require_admin_user_id", return_value=100):
            return await promos_module.admin_promo_create_route(request)

    response = _run_direct_bad_request(run())

    assert response.status == 400
    body = _json_body(response)
    assert body["error"] == "invalid_payload"
    assert "multiple_effects" in body["message"]


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
            app={"async_session_factory": lambda: session, "settings": _settings()},
            match_info={"promo_id": "5"},
        )

        with (
            patch.object(promos_module, "_require_admin_user_id", return_value=100),
            patch.object(
                promos_module.promo_code_dal,
                "get_promo_code_by_id",
                AsyncMock(return_value=promo),
            ),
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


def test_promo_update_can_disable_existing_multiple_effects():
    async def run():
        session = _FakeSession()
        promo = _promo(is_active=True, bonus_days=7, discount_percent=10)
        request = _FakeRequest(
            {"is_active": False},
            app={"async_session_factory": lambda: session, "settings": _settings()},
            match_info={"promo_id": "5"},
        )

        with (
            patch.object(promos_module, "_require_admin_user_id", return_value=100),
            patch.object(
                promos_module.promo_code_dal,
                "get_promo_code_by_id",
                AsyncMock(return_value=promo),
            ),
            patch.object(
                promos_module.promo_code_dal,
                "update_promo_code",
                AsyncMock(return_value=promo),
            ) as update_promo,
        ):
            response = await promos_module.admin_promo_update_route(request)
        return response, session, update_promo

    response, session, update_promo = asyncio.run(run())

    assert response.status == 200
    update_promo.assert_awaited_once_with(session, 5, {"is_active": False})
    session.commit.assert_awaited_once()


def test_promo_update_rejects_enabling_existing_multiple_effects():
    async def run():
        session = _FakeSession()
        promo = _promo(is_active=False, bonus_days=7, discount_percent=10)
        request = _FakeRequest(
            {"is_active": True},
            app={"async_session_factory": lambda: session, "settings": _settings()},
            match_info={"promo_id": "5"},
        )

        with (
            patch.object(promos_module, "_require_admin_user_id", return_value=100),
            patch.object(
                promos_module.promo_code_dal,
                "get_promo_code_by_id",
                AsyncMock(return_value=promo),
            ),
            patch.object(
                promos_module.promo_code_dal,
                "update_promo_code",
                AsyncMock(),
            ) as update_promo,
        ):
            response = await promos_module.admin_promo_update_route(request)
        return response, session, update_promo

    response, session, update_promo = asyncio.run(run())

    assert response.status == 400
    assert _json_body(response)["error"] == "multiple_effects"
    update_promo.assert_not_awaited()
    session.commit.assert_not_awaited()


def test_promo_update_returns_no_changes_for_empty_typed_body():
    async def run():
        request = _FakeRequest({}, match_info={"promo_id": "5"})

        with patch.object(promos_module, "_require_admin_user_id", return_value=100):
            return await promos_module.admin_promo_update_route(request)

    response = asyncio.run(run())

    assert response.status == 400
    assert _json_body(response)["error"] == "no_changes"


def test_promo_update_rejects_max_activations_below_current_count():
    async def run():
        session = _FakeSession()
        promo = _promo(current_activations=2, max_activations=5)
        request = _FakeRequest(
            {"max_activations": 1},
            app={"async_session_factory": lambda: session, "settings": _settings()},
            match_info={"promo_id": "5"},
        )

        with (
            patch.object(promos_module, "_require_admin_user_id", return_value=100),
            patch.object(
                promos_module.promo_code_dal,
                "get_promo_code_by_id",
                AsyncMock(return_value=promo),
            ),
            patch.object(
                promos_module.promo_code_dal,
                "update_promo_code",
                AsyncMock(),
            ) as update_promo,
        ):
            response = await promos_module.admin_promo_update_route(request)
        return response, session, update_promo

    response, session, update_promo = asyncio.run(run())

    assert response.status == 400
    assert _json_body(response)["error"] == "max_activations_below_current"
    update_promo.assert_not_awaited()
    session.commit.assert_not_awaited()


def test_promo_update_can_clear_valid_until():
    async def run():
        session = _FakeSession()
        promo = _promo()
        request = _FakeRequest(
            {"clear_valid_until": True},
            app={"async_session_factory": lambda: session, "settings": _settings()},
            match_info={"promo_id": "5"},
        )

        with (
            patch.object(promos_module, "_require_admin_user_id", return_value=100),
            patch.object(
                promos_module.promo_code_dal,
                "get_promo_code_by_id",
                AsyncMock(return_value=promo),
            ),
            patch.object(
                promos_module.promo_code_dal,
                "update_promo_code",
                AsyncMock(return_value=promo),
            ) as update_promo,
        ):
            response = await promos_module.admin_promo_update_route(request)
        return response, session, update_promo

    response, session, update_promo = asyncio.run(run())

    assert response.status == 200
    update_promo.assert_awaited_once_with(session, 5, {"valid_until": None})
    session.commit.assert_awaited_once()


def test_promo_update_accepts_explicit_valid_until():
    expires_at = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)

    async def run():
        session = _FakeSession()
        promo = _promo()
        request = _FakeRequest(
            {"valid_until": expires_at.isoformat()},
            app={"async_session_factory": lambda: session, "settings": _settings()},
            match_info={"promo_id": "5"},
        )

        with (
            patch.object(promos_module, "_require_admin_user_id", return_value=100),
            patch.object(
                promos_module.promo_code_dal,
                "get_promo_code_by_id",
                AsyncMock(return_value=promo),
            ),
            patch.object(
                promos_module.promo_code_dal,
                "update_promo_code",
                AsyncMock(return_value=promo),
            ) as update_promo,
        ):
            response = await promos_module.admin_promo_update_route(request)
        return response, session, update_promo

    response, session, update_promo = asyncio.run(run())

    assert response.status == 200
    update_promo.assert_awaited_once_with(session, 5, {"valid_until": expires_at})
    session.commit.assert_awaited_once()


def test_promo_activations_route_returns_user_and_payment_context():
    async def run():
        session = _FakeSession()
        promo = _promo()
        user = SimpleNamespace(
            user_id=42,
            telegram_id=4242,
            first_name="Ada",
            last_name="Lovelace",
            username="ada",
            email=None,
        )
        payment = SimpleNamespace(
            payment_id=77,
            amount=80.0,
            currency="RUB",
            status="succeeded",
            provider="yookassa",
            sale_mode="subscription@standard",
            description="Subscription",
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
            checkout_base_amount=100.0,
            checkout_discount_amount=20.0,
            checkout_charged_months=3,
            checkout_charged_gb=None,
        )
        activation = SimpleNamespace(
            activation_id=9,
            promo_code_id=5,
            user_id=42,
            activated_at=datetime(2026, 1, 3, tzinfo=UTC),
            payment_id=77,
            user=user,
            payment=payment,
            effect_summary="-20%",
            bonus_days=0,
            discount_percent=20,
            duration_multiplier=None,
            traffic_multiplier=None,
            applies_to="subscription",
            base_amount=None,
            discount_amount=0.0,
            charged_months=None,
            charged_gb=None,
            granted_days=14,
            granted_gb=None,
        )
        request = _FakeRequest(
            {},
            app={"async_session_factory": lambda: session},
            match_info={"promo_id": "5"},
            query={"page": "0", "page_size": "25"},
        )

        with (
            patch.object(promos_module, "_require_admin_user_id", return_value=100),
            patch.object(
                promos_module.promo_code_dal,
                "get_promo_code_by_id",
                AsyncMock(return_value=promo),
            ),
            patch.object(
                promos_module.promo_code_dal,
                "get_promo_activations_by_code_id",
                AsyncMock(return_value=[activation]),
            ) as get_activations,
            patch.object(
                promos_module.promo_code_dal,
                "count_promo_activations_by_code_id",
                AsyncMock(return_value=1),
            ),
        ):
            response = await promos_module.admin_promo_activations_route(request)
        return response, session, activation, get_activations

    response, session, activation, get_activations = asyncio.run(run())

    assert response.status == 200
    get_activations.assert_awaited_once_with(session, 5, limit=25, offset=0)
    body = _json_body(response)
    assert body["total"] == 1
    serialized = PromoActivationOut.from_orm_activation(activation).model_dump(mode="json")
    assert serialized["base_amount"] == 100.0
    assert serialized["discount_amount"] == 0.0
    assert serialized["charged_months"] == 3
    assert serialized["granted_days"] == 14
    assert body["activations"] == [serialized]
