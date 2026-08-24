import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from bot.services import support_service as support_service_module
from bot.services.support_service import (
    SupportService,
    TicketForbidden,
    TicketRateLimited,
    _support_admin_notification_decision,
)
from tests.support.settings_stub import settings_stub


def test_support_traffic_snapshot_calculates_percent_and_left_bytes():
    snapshot = SupportService._traffic_snapshot(25, 100)

    assert snapshot["percent"] == 25
    assert snapshot["left_bytes"] == 75


def test_ticket_forbidden_error_code_is_stable():
    exc = TicketForbidden("ticket_forbidden")

    assert str(exc) == "ticket_forbidden"


def test_regular_limit_treats_unlimited_override_as_zero_limit():
    sub = SimpleNamespace(regular_unlimited_override=True, traffic_limit_bytes=100)

    assert SupportService._regular_limit(sub) == 0


def test_support_admin_notification_decision_sends_first_unread():
    now = datetime(2026, 5, 20, tzinfo=UTC)
    ticket = SimpleNamespace(
        unread_admin_count=1,
        admin_last_notified_at=now,
        admin_last_emailed_at=now,
    )
    settings = settings_stub(
        SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS=300,
        SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS=1800,
        SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED=True,
    )

    decision = _support_admin_notification_decision(ticket, settings.support_settings, now=now)

    assert decision.send_telegram is True
    assert decision.send_email is True


def test_support_admin_notification_decision_defaults_email_disabled():
    now = datetime(2026, 5, 20, tzinfo=UTC)
    ticket = SimpleNamespace(
        unread_admin_count=1,
        admin_last_notified_at=None,
        admin_last_emailed_at=None,
    )
    settings = settings_stub(
        SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS=300,
        SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS=1800,
    )

    decision = _support_admin_notification_decision(ticket, settings.support_settings, now=now)

    assert decision.send_telegram is True
    assert decision.send_email is False


def test_support_admin_notification_decision_suppresses_fast_followups():
    now = datetime(2026, 5, 20, tzinfo=UTC)
    ticket = SimpleNamespace(
        unread_admin_count=4,
        admin_last_notified_at=now - timedelta(seconds=60),
        admin_last_emailed_at=now - timedelta(seconds=60),
    )
    settings = settings_stub(
        SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS=300,
        SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS=1800,
        SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED=True,
    )

    decision = _support_admin_notification_decision(ticket, settings.support_settings, now=now)

    assert decision.send_telegram is False
    assert decision.send_email is False


def test_support_admin_notification_decision_uses_separate_email_cooldown():
    now = datetime(2026, 5, 20, tzinfo=UTC)
    ticket = SimpleNamespace(
        unread_admin_count=4,
        admin_last_notified_at=now - timedelta(seconds=301),
        admin_last_emailed_at=now - timedelta(seconds=301),
    )
    settings = settings_stub(
        SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS=300,
        SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS=1800,
        SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED=True,
    )

    decision = _support_admin_notification_decision(ticket, settings.support_settings, now=now)

    assert decision.send_telegram is True
    assert decision.send_email is False


def test_user_message_rate_limit_is_persistent_database_count(monkeypatch):
    settings = settings_stub(SUPPORT_MESSAGE_RATE_LIMIT_PER_MINUTE=2)
    service = object.__new__(SupportService)
    service.settings = settings

    async def count_messages(_session, _user_id, _window, *, images_only=False):
        return 0 if images_only else 2

    monkeypatch.setattr(
        support_service_module.support_dal,
        "count_recent_messages_for_user",
        count_messages,
    )

    with pytest.raises(TicketRateLimited, match="support_message_rate_limited"):
        asyncio.run(service._enforce_user_message_limits(object(), 42, has_image=False))


def test_user_daily_image_limit_does_not_apply_to_text(monkeypatch):
    settings = settings_stub(
        SUPPORT_MESSAGE_RATE_LIMIT_PER_MINUTE=0,
        SUPPORT_IMAGE_RATE_LIMIT_PER_DAY=1,
    )
    service = object.__new__(SupportService)
    service.settings = settings

    async def count_messages(_session, _user_id, _window, *, images_only=False):
        return 1 if images_only else 0

    monkeypatch.setattr(
        support_service_module.support_dal,
        "count_recent_messages_for_user",
        count_messages,
    )

    asyncio.run(service._enforce_user_message_limits(object(), 42, has_image=False))
    with pytest.raises(TicketRateLimited, match="support_image_rate_limited"):
        asyncio.run(service._enforce_user_message_limits(object(), 42, has_image=True))


def test_user_reply_refreshes_ticket_after_notification_update(monkeypatch):
    events: list[str] = []

    class Ticket(SimpleNamespace):
        expired = False

        @property
        def updated_at(self):
            if self.expired:
                raise RuntimeError("ticket snapshot is expired")
            return datetime(2026, 8, 24, tzinfo=UTC)

    ticket = Ticket(
        ticket_id=24,
        user_id=42,
        unread_admin_count=1,
        admin_last_notified_at=None,
        admin_last_emailed_at=None,
    )
    message = SimpleNamespace(message_id=25)
    user = SimpleNamespace(user_id=42)

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args: Any):
            return None

        async def refresh(self, row):
            events.append("refresh")
            if row is ticket:
                ticket.expired = False

        async def commit(self):
            events.append("commit")

    async def ensure_user_allowed(_session, _user_id):
        return user

    async def enforce_limits(_session, _user_id, *, has_image):
        del has_image

    async def get_ticket(_session, _ticket_id):
        return ticket, []

    async def add_message(*_args, **_kwargs):
        return message

    async def record_notification(*_args, **_kwargs):
        events.append("record")
        ticket.expired = True

    def discard_notification(coro: Coroutine[Any, Any, None], *_args: Any):
        coro.close()

    service = object.__new__(SupportService)
    service.settings = settings_stub(
        SUPPORT_MESSAGE_RATE_LIMIT_PER_MINUTE=0,
        SUPPORT_IMAGE_RATE_LIMIT_PER_DAY=0,
        SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED=False,
    )
    service.session_factory = lambda: Session()
    service.notification_service = SimpleNamespace(
        support_admin_email_notifications_enabled=AsyncMock(return_value=False),
        notify_support_user_reply=AsyncMock(),
    )
    service.build_user_snapshot = AsyncMock(return_value={})
    service._schedule_notification = discard_notification
    monkeypatch.setattr(service, "_ensure_user_allowed", ensure_user_allowed)
    monkeypatch.setattr(service, "_enforce_user_message_limits", enforce_limits)
    monkeypatch.setattr(
        support_service_module, "persist_message_image", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(support_service_module.support_dal, "get_ticket", get_ticket)
    monkeypatch.setattr(support_service_module.support_dal, "add_message", add_message)
    monkeypatch.setattr(
        support_service_module.support_dal,
        "record_admin_notification",
        record_notification,
    )

    returned_ticket, returned_message = asyncio.run(
        service.reply_as_user(42, 24, "Screenshot", image=SimpleNamespace())
    )

    assert events == ["refresh", "record", "refresh", "commit"]
    assert returned_ticket.updated_at == datetime(2026, 8, 24, tzinfo=UTC)
    assert returned_message is message
