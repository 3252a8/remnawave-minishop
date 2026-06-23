from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bot.services.support_service import (
    SupportService,
    TicketForbidden,
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
    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
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

    decision = _support_admin_notification_decision(ticket, settings, now=now)

    assert decision.send_telegram is True
    assert decision.send_email is True


def test_support_admin_notification_decision_defaults_email_disabled():
    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
    ticket = SimpleNamespace(
        unread_admin_count=1,
        admin_last_notified_at=None,
        admin_last_emailed_at=None,
    )
    settings = settings_stub(
        SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS=300,
        SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS=1800,
    )

    decision = _support_admin_notification_decision(ticket, settings, now=now)

    assert decision.send_telegram is True
    assert decision.send_email is False


def test_support_admin_notification_decision_suppresses_fast_followups():
    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
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

    decision = _support_admin_notification_decision(ticket, settings, now=now)

    assert decision.send_telegram is False
    assert decision.send_email is False


def test_support_admin_notification_decision_uses_separate_email_cooldown():
    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
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

    decision = _support_admin_notification_decision(ticket, settings, now=now)

    assert decision.send_telegram is True
    assert decision.send_email is False
