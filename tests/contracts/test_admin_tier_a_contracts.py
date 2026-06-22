from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from aiohttp import web

import bot.app.web.admin_api  # noqa: F401 - populates admin_api_impl module namespaces
from bot.app.web.admin_api_impl import ads as ads_module
from bot.app.web.admin_api_impl import common as common_module
from bot.app.web.admin_api_impl.schemas import AdOut, LogOut, PaymentDetailOut, PaymentOut


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


def _json_body(response):
    return json.loads(response.text)


def _run_direct_bad_request(coro):
    try:
        return asyncio.run(coro)
    except web.HTTPBadRequest as exc:
        return exc


def _payment(**overrides):
    values = {
        "payment_id": 10,
        "user_id": 42,
        "provider": "wata",
        "provider_payment_id": "provider-10",
        "yookassa_payment_id": None,
        "idempotence_key": "idem-10",
        "promo_code_used": SimpleNamespace(code="GIFT"),
        "amount": 120.0,
        "currency": "RUB",
        "status": "succeeded",
        "description": "Top-up",
        "subscription_duration_months": None,
        "sale_mode": "premium_topup@standard",
        "tariff_key": "standard",
        "purchased_gb": 12.5,
        "purchased_hwid_devices": 2,
        "created_at": datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 2, 4, 5, tzinfo=timezone.utc),
        "user": SimpleNamespace(
            user_id=42,
            telegram_id=42,
            username="alice",
            first_name="Alice",
            last_name="",
            email="alice@example.test",
        ),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_payment_response_models_match_legacy_serializer():
    payment = _payment()

    assert PaymentOut.from_orm_payment(payment).model_dump(
        mode="json"
    ) == common_module._serialize_payment(payment)
    assert PaymentDetailOut.from_orm_payment_detail(payment).model_dump(mode="json") == {
        **common_module._serialize_payment(payment),
        "yookassa_payment_id": None,
        "idempotence_key": "idem-10",
        "promo_code": "GIFT",
        "updated_at": "2026-01-02T04:05:00+00:00",
    }


def test_ad_response_model_matches_legacy_serializer():
    campaign = SimpleNamespace(
        ad_campaign_id=5,
        source="telegram",
        start_param="summer",
        cost=15,
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    stats = {"starts": 4, "trials": 2, "payers": 1, "revenue": 120.0}

    assert AdOut.from_orm_ad(campaign, stats).model_dump(
        mode="json"
    ) == common_module._serialize_ad(campaign, stats)


class _LazyLogEntry:
    log_id = 9
    user_id = 42
    target_user_id = 43
    telegram_username = "neo"
    telegram_first_name = "Neo"
    event_type = "message"
    content = "hello"
    is_admin_event = True
    timestamp = datetime(2026, 1, 3, 5, 6, tzinfo=timezone.utc)

    @property
    def author_user(self):
        raise AssertionError("author_user relationship was lazy-loaded")

    @property
    def target_user(self):
        raise AssertionError("target_user relationship was lazy-loaded")


def test_log_response_model_avoids_lazy_relationship_loads():
    entry = _LazyLogEntry()

    assert LogOut.from_orm_log(entry).model_dump(mode="json") == {
        "log_id": 9,
        "user_id": 42,
        "user_label": "Neo",
        "telegram_username": "neo",
        "telegram_first_name": "Neo",
        "email": None,
        "event_type": "message",
        "content": "hello",
        "is_admin_event": True,
        "target_user_id": 43,
        "target_user_label": "43",
        "timestamp": "2026-01-03T05:06:00+00:00",
    }


def test_ad_create_rejects_malformed_typed_body():
    async def run():
        request = _FakeRequest({"start_param": "summer"})
        with patch.object(ads_module, "_require_admin_user_id", return_value=100):
            return await ads_module.admin_ad_create_route(request)

    response = _run_direct_bad_request(run())

    assert response.status == 400
    assert _json_body(response)["error"] == "invalid_payload"
