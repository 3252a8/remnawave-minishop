"""Domain event bus: delivery semantics and core emit-point wiring."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
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
    value = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
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


def test_create_user_emits_user_registered(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from db.dal import user_dal

    received = []

    async def handler(event_name, payload):
        received.append(payload)

    events.subscribe(events.USER_REGISTERED, handler)

    fake_user = SimpleNamespace(user_id=123, referred_by_id=77)

    async def fake_get_user(session, user_id):
        return fake_user

    monkeypatch.setattr(user_dal, "get_user_by_id", fake_get_user)

    insert_result = MagicMock()
    insert_result.first.return_value = (123,)  # row returned => created
    session = MagicMock()
    session.execute = AsyncMock(return_value=insert_result)

    user, created = asyncio.run(
        user_dal.create_user(
            session,
            {
                "user_id": 123,
                "telegram_id": 123,
                "language_code": "ru",
                "referred_by_id": 77,
                "referral_code": "ABCDEF123",
            },
        )
    )

    assert created is True
    assert received == [
        {
            "user_id": 123,
            "language": "ru",
            "referred_by_id": 77,
            "registered_via": "telegram",
            "telegram_id": 123,
            "username": None,
            "first_name": None,
            "email": None,
        }
    ]


def test_create_user_suppresses_event_for_technical_rows(monkeypatch):
    """registered_via=None marks technical row creation (account-linking
    intermediates, bulk imports) that must not look like a registration."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from db.dal import user_dal

    received = []

    async def handler(event_name, payload):
        received.append(payload)

    events.subscribe(events.USER_REGISTERED, handler)

    async def fake_get_user(session, user_id):
        return SimpleNamespace(user_id=123, referred_by_id=None)

    monkeypatch.setattr(user_dal, "get_user_by_id", fake_get_user)

    insert_result = MagicMock()
    insert_result.first.return_value = (123,)
    session = MagicMock()
    session.execute = AsyncMock(return_value=insert_result)

    _, created = asyncio.run(
        user_dal.create_user(
            session,
            {"user_id": 123, "telegram_id": 123, "referral_code": "ABCDEF123"},
            registered_via=None,
        )
    )

    assert created is True
    assert received == []


def test_create_user_uses_explicit_registration_source(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from db.dal import user_dal

    received = []

    async def handler(event_name, payload):
        received.append(payload)

    events.subscribe(events.USER_REGISTERED, handler)

    async def fake_get_user(session, user_id):
        return SimpleNamespace(user_id=321, referred_by_id=None)

    monkeypatch.setattr(user_dal, "get_user_by_id", fake_get_user)

    insert_result = MagicMock()
    insert_result.first.return_value = (321,)
    session = MagicMock()
    session.execute = AsyncMock(return_value=insert_result)

    asyncio.run(
        user_dal.create_user(
            session,
            {"user_id": 321, "telegram_id": 321, "referral_code": "ABCDEF321"},
            registered_via="panel_sync",
        )
    )

    assert [p["registered_via"] for p in received] == ["panel_sync"]


def test_create_user_existing_user_does_not_emit(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from db.dal import user_dal

    received = []

    async def handler(event_name, payload):
        received.append(payload)

    events.subscribe(events.USER_REGISTERED, handler)

    async def fake_get_user(session, user_id):
        return SimpleNamespace(user_id=123, referred_by_id=None)

    monkeypatch.setattr(user_dal, "get_user_by_id", fake_get_user)

    insert_result = MagicMock()
    insert_result.first.return_value = None  # conflict => already exists
    session = MagicMock()
    session.execute = AsyncMock(return_value=insert_result)

    _, created = asyncio.run(
        user_dal.create_user(
            session,
            {"user_id": 123, "telegram_id": 123, "referral_code": "ABCDEF123"},
        )
    )

    assert created is False
    assert received == []


# --- Wiring guard ---------------------------------------------------------------

# Every module that must publish a given event. The test fails when an emit
# call/model construction is removed without updating this map.
EXPECTED_EVENT_WIRING = {
    "backend/bot/payment_providers/shared/success.py": [
        ("PAYMENT_SUCCEEDED", "PaymentSucceededPayload"),
        ("SUBSCRIPTION_CREATED", "SubscriptionCreatedPayload"),
        ("SUBSCRIPTION_EXTENDED", "SubscriptionExtendedPayload"),
        ("REFERRAL_BONUS_GRANTED", "ReferralBonusGrantedPayload"),
    ],
    "backend/bot/payment_providers/yookassa/success.py": [
        ("PAYMENT_SUCCEEDED", "PaymentSucceededPayload"),
        ("SUBSCRIPTION_CREATED", "SubscriptionCreatedPayload"),
        ("SUBSCRIPTION_EXTENDED", "SubscriptionExtendedPayload"),
    ],
    "backend/bot/payment_providers/yookassa/webhook.py": [
        ("PAYMENT_CANCELED", "PaymentCanceledPayload"),
    ],
    "backend/bot/services/subscription_service_impl/trial.py": [
        ("TRIAL_ACTIVATED", "TrialActivatedPayload")
    ],
    # user.registered is emitted in the DAL so every registration path is
    # covered: bot /start, Mini App Telegram login and email signup all go
    # through create_user. account.merged likewise covers all merge paths.
    "backend/db/dal/user_dal.py": [
        ("USER_REGISTERED", "UserRegisteredPayload"),
        ("ACCOUNT_MERGED", "AccountMergedPayload"),
    ],
    "backend/bot/app/web/webapp/account.py": [
        ("ACCOUNT_EMAIL_LINKED", "AccountEmailLinkedPayload"),
        ("ACCOUNT_TELEGRAM_LINKED", "AccountTelegramLinkedPayload"),
    ],
    "backend/bot/services/promo_code_service.py": [
        ("PROMO_CODE_APPLIED", "PromoCodeAppliedPayload")
    ],
    # Payment-triggered accrual payloads are calculated by the service and
    # emitted by the provider success layer. The one-time welcome grant has two
    # entry points (bot /start and the webapp helper used by claim/login flows).
    "backend/bot/handlers/user/start_flow.py": [
        ("REFERRAL_BONUS_GRANTED", "ReferralBonusGrantedPayload")
    ],
    "backend/bot/app/web/webapp/auth_referral.py": [
        ("REFERRAL_BONUS_GRANTED", "ReferralBonusGrantedPayload")
    ],
    "backend/bot/services/support_service.py": [
        ("SUPPORT_TICKET_CREATED", "SupportTicketCreatedPayload")
    ],
    "backend/bot/services/panel_webhook_service.py": [
        ("PANEL_WEBHOOK_RECEIVED", "PanelWebhookReceivedPayload")
    ],
}


def test_emit_points_are_wired():
    for module_path, event_contracts in EXPECTED_EVENT_WIRING.items():
        source = Path(module_path).read_text(encoding="utf-8")
        assert "events.emit(" in source or "events.emit_model(" in source, (
            f"{module_path} lost its event emit call"
        )
        for constant, payload_model in event_contracts:
            assert getattr(events, constant), f"unknown event constant {constant}"
            assert payload_model in source, f"{module_path} no longer builds {payload_model}"
