"""Domain event bus: delivery semantics and core emit-point wiring."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bot.infra import events
from bot.plugins import Plugin, PluginContext, register, reset_plugins, run_setup
from bot.services.panel_webhook_service import PanelWebhookService
from config.settings import Settings


@pytest.fixture(autouse=True)
def _clean_event_state():
    events.reset_subscribers()
    yield
    events.reset_subscribers()


def make_settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "BOT_TOKEN": "x",
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
        "ADMIN_IDS": "1",
    }
    values.update(overrides)
    return Settings(**values)


# --- Bus semantics ------------------------------------------------------------


def test_emit_delivers_name_and_payload():
    received = []

    async def handler(event_name, payload):
        received.append((event_name, payload))

    events.subscribe(events.TRIAL_ACTIVATED, handler)
    asyncio.run(events.emit(events.TRIAL_ACTIVATED, {"user_id": 1}))

    assert received == [(events.TRIAL_ACTIVATED, {"user_id": 1})]


def test_emit_without_subscribers_is_noop():
    asyncio.run(events.emit(events.PAYMENT_SUCCEEDED, {"user_id": 1}))


def test_failing_subscriber_does_not_break_emit_or_other_subscribers(caplog):
    received = []

    async def broken(event_name, payload):
        raise RuntimeError("boom")

    async def healthy(event_name, payload):
        received.append(payload)

    events.subscribe(events.USER_REGISTERED, broken)
    events.subscribe(events.USER_REGISTERED, healthy)

    with caplog.at_level("ERROR"):
        asyncio.run(events.emit(events.USER_REGISTERED, {"user_id": 7}))

    assert received == [{"user_id": 7}]
    assert "Event subscriber" in caplog.text


def test_unsubscribe_stops_delivery():
    received = []

    async def handler(event_name, payload):
        received.append(payload)

    events.subscribe(events.PROMO_CODE_APPLIED, handler)
    events.unsubscribe(events.PROMO_CODE_APPLIED, handler)
    asyncio.run(events.emit(events.PROMO_CODE_APPLIED, {"user_id": 1}))

    assert received == []


def test_iso_formats_datetimes():
    value = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert events.iso(value) == "2026-01-02T03:04:05+00:00"
    assert events.iso(None) is None


# --- Plugins subscribe in setup() ---------------------------------------------


def test_plugin_subscribes_to_events_in_setup():
    reset_plugins()
    received = []

    class SubscribingPlugin(Plugin):
        name = "subscribing"

        def setup(self, ctx):
            async def on_event(event_name, payload):
                received.append((event_name, payload))

            events.subscribe(events.PAYMENT_SUCCEEDED, on_event)

    register(SubscribingPlugin())
    try:
        run_setup(PluginContext(settings=make_settings()))
        asyncio.run(events.emit(events.PAYMENT_SUCCEEDED, {"user_id": 5, "amount": 100.0}))
    finally:
        reset_plugins()

    assert received == [(events.PAYMENT_SUCCEEDED, {"user_id": 5, "amount": 100.0})]


# --- Emit-point integration -----------------------------------------------------


def test_panel_webhook_service_emits_received_event():
    received = []

    async def handler(event_name, payload):
        received.append(payload)

    events.subscribe(events.PANEL_WEBHOOK_RECEIVED, handler)

    service = PanelWebhookService(
        MagicMock(),
        make_settings(SUBSCRIPTION_NOTIFICATIONS_ENABLED=False),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    asyncio.run(service.handle_event("user.expired", {"uuid": "abc", "telegramId": 42}))

    assert received == [{"event": "user.expired", "panel_user_uuid": "abc", "telegram_id": 42}]


# --- Wiring guard ---------------------------------------------------------------

# Every module that must publish a given event. The test fails when an emit
# call is removed (or the constant is renamed) without updating this map.
EXPECTED_EVENT_WIRING = {
    "backend/bot/payment_providers/shared/success.py": [
        "PAYMENT_SUCCEEDED",
        "SUBSCRIPTION_CREATED",
        "SUBSCRIPTION_EXTENDED",
    ],
    "backend/bot/payment_providers/yookassa.py": [
        "PAYMENT_SUCCEEDED",
        "PAYMENT_CANCELED",
        "SUBSCRIPTION_CREATED",
        "SUBSCRIPTION_EXTENDED",
    ],
    "backend/bot/services/subscription_service_impl/trial.py": ["TRIAL_ACTIVATED"],
    "backend/bot/handlers/user/start.py": ["USER_REGISTERED"],
    "backend/bot/services/promo_code_service.py": ["PROMO_CODE_APPLIED"],
    "backend/bot/services/referral_service.py": ["REFERRAL_BONUS_GRANTED"],
    "backend/bot/services/support_service.py": ["SUPPORT_TICKET_CREATED"],
    "backend/bot/services/panel_webhook_service.py": ["PANEL_WEBHOOK_RECEIVED"],
}


def test_emit_points_are_wired():
    for module_path, constants in EXPECTED_EVENT_WIRING.items():
        source = Path(module_path).read_text(encoding="utf-8")
        assert "events.emit(" in source, f"{module_path} lost its events.emit call"
        for constant in constants:
            assert getattr(events, constant), f"unknown event constant {constant}"
            assert f"events.{constant}" in source, (
                f"{module_path} no longer references events.{constant}"
            )
