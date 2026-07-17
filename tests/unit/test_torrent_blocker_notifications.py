from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, ClassVar, cast
from unittest.mock import AsyncMock

from bot.services import torrent_blocker_notifications as module
from tests.support.settings_stub import settings_stub


class _I18n:
    _MESSAGES: ClassVar[dict[str, str]] = {
        "torrent_blocker_notification": "Blocked until {unblock_at}",
        "torrent_blocker_notification_without_time": "Blocked temporarily",
        "torrent_blocker_notification_ip": "IP: {ip}",
    }

    def gettext(self, language: str, key: str, **kwargs: object) -> str:
        return self._MESSAGES.get(key, key).format(**kwargs)


class _Session:
    def __init__(self) -> None:
        self.commit = AsyncMock()


class _SessionContext:
    def __init__(self, session: _Session) -> None:
        self.session = session

    async def __aenter__(self) -> _Session:
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _SessionFactory:
    def __init__(self) -> None:
        self.session = _Session()
        self.calls = 0

    def __call__(self) -> _SessionContext:
        self.calls += 1
        return _SessionContext(self.session)


def _context(**overrides: object) -> dict[str, Any]:
    result: dict[str, Any] = {
        "blocked": True,
        "ip": "203.0.113.8",
        "block_duration": 3600,
        "will_unblock_at": "2026-07-17T11:00:00Z",
        "processed_at": "2026-07-17T10:00:00Z",
    }
    result.update(overrides)
    return result


def _user(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "user_id": 42,
        "telegram_id": 99,
        "email": "user@example.com",
        "language_code": "en",
        "telegram_notifications_status": "enabled",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _service(**setting_overrides: object):
    setting_values: dict[str, object] = {
        "TORRENT_BLOCKER_NOTIFICATIONS_ENABLED": True,
        "TORRENT_BLOCKER_TELEGRAM_NOTIFICATIONS_ENABLED": True,
        "TORRENT_BLOCKER_EMAIL_NOTIFICATIONS_ENABLED": False,
    }
    setting_values.update(setting_overrides)
    settings = settings_stub(**setting_values)
    bot = SimpleNamespace(send_message=AsyncMock())
    factory = _SessionFactory()
    service = module.TorrentBlockerNotificationService(
        cast(Any, settings),
        cast(Any, bot),
        cast(Any, _I18n()),
        cast(Any, factory),
    )
    return service, bot, factory


def test_report_normalizes_ip_and_derives_missing_unblock_time():
    report = module.TorrentBlockerReport.from_context(
        _context(
            ip="2001:0db8::1",
            will_unblock_at=None,
            processed_at="2026-07-17T10:00:00Z",
            block_duration=120,
        )
    )

    assert report.blocked is True
    assert report.ip == "2001:db8::1"
    assert report.will_unblock_at is not None
    assert report.will_unblock_at.isoformat() == "2026-07-17T10:02:00+00:00"


def test_message_hides_ip_by_default_and_includes_it_only_when_enabled():
    service, _bot, _factory = _service()
    report = module.TorrentBlockerReport.from_context(_context())

    assert service._message_text("en", report) == "Blocked until 2026-07-17 11:00 UTC"

    service.settings.TORRENT_BLOCKER_NOTIFICATION_INCLUDE_IP = True
    assert service._message_text("en", report).endswith("IP: 203.0.113.8")


def test_message_never_includes_an_invalid_ip():
    service, _bot, _factory = _service(TORRENT_BLOCKER_NOTIFICATION_INCLUDE_IP=True)
    report = module.TorrentBlockerReport.from_context(_context(ip="<b>not-an-ip</b>"))

    assert report.ip == ""
    assert "not-an-ip" not in service._message_text("en", report)


def test_non_blocking_report_is_ignored_without_opening_database_session():
    service, bot, factory = _service()

    delivery = asyncio.run(
        service.handle(
            {"uuid": "panel-user-1", "telegramId": 99},
            _context(blocked=False),
        )
    )

    assert delivery == module.TorrentBlockerNotificationDelivery()
    assert factory.calls == 0
    bot.send_message.assert_not_awaited()


def test_sends_telegram_notification_and_audits_only_a_fingerprint(monkeypatch):
    service, bot, factory = _service()
    user = _user()
    audit = AsyncMock()
    mark_status = AsyncMock()

    monkeypatch.setattr(service, "_resolve_user", AsyncMock(return_value=user))
    monkeypatch.setattr(module.user_dal, "lock_user_by_id", AsyncMock(return_value=user))
    monkeypatch.setattr(
        module.message_log_dal,
        "has_target_event_content",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        module.message_log_dal,
        "has_recent_target_event",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(module, "log_user_message_delivery", audit)
    monkeypatch.setattr(module, "mark_telegram_notifications_status", mark_status)

    delivery = asyncio.run(
        service.handle(
            {"uuid": "panel-user-1", "telegramId": 99},
            _context(),
        )
    )

    assert delivery.telegram_sent is True
    assert delivery.email_sent is False
    bot.send_message.assert_awaited_once_with(99, "Blocked until 2026-07-17 11:00 UTC")
    audit.assert_awaited_once()
    audit_kwargs = audit.await_args.kwargs
    assert "fingerprint=" in audit_kwargs["content"]
    assert "203.0.113.8" not in audit_kwargs["content"]
    factory.session.commit.assert_awaited_once()
    mark_status.assert_not_awaited()


def test_channel_cooldown_suppresses_repeated_telegram_message(monkeypatch):
    service, bot, _factory = _service()
    user = _user()

    monkeypatch.setattr(service, "_resolve_user", AsyncMock(return_value=user))
    monkeypatch.setattr(module.user_dal, "lock_user_by_id", AsyncMock(return_value=user))
    monkeypatch.setattr(
        module.message_log_dal,
        "has_target_event_content",
        AsyncMock(return_value=False),
    )
    recent = AsyncMock(return_value=True)
    monkeypatch.setattr(module.message_log_dal, "has_recent_target_event", recent)

    delivery = asyncio.run(
        service.handle(
            {"uuid": "panel-user-1", "telegramId": 99},
            _context(),
        )
    )

    assert delivery.telegram_sent is False
    bot.send_message.assert_not_awaited()
    assert recent.await_args.kwargs["event_type"] == (module.TELEGRAM_TORRENT_NOTIFICATION_EVENT)


def test_exact_duplicate_is_suppressed_even_when_cooldown_is_disabled(monkeypatch):
    service, bot, _factory = _service(TORRENT_BLOCKER_NOTIFICATION_COOLDOWN_SECONDS=0)
    user = _user()

    monkeypatch.setattr(service, "_resolve_user", AsyncMock(return_value=user))
    monkeypatch.setattr(module.user_dal, "lock_user_by_id", AsyncMock(return_value=user))
    exact = AsyncMock(return_value=True)
    recent = AsyncMock(return_value=False)
    monkeypatch.setattr(module.message_log_dal, "has_target_event_content", exact)
    monkeypatch.setattr(module.message_log_dal, "has_recent_target_event", recent)

    delivery = asyncio.run(
        service.handle(
            {"uuid": "panel-user-1", "telegramId": 99},
            _context(),
        )
    )

    assert delivery.telegram_sent is False
    bot.send_message.assert_not_awaited()
    exact.assert_awaited_once()
    recent.assert_not_awaited()


def test_email_channel_uses_dedicated_localized_copy(monkeypatch):
    service, bot, _factory = _service(
        TORRENT_BLOCKER_TELEGRAM_NOTIFICATIONS_ENABLED=False,
        TORRENT_BLOCKER_EMAIL_NOTIFICATIONS_ENABLED=True,
        email_auth_configured=True,
    )
    user = _user()
    send_email = AsyncMock(return_value=True)

    monkeypatch.setattr(service, "_resolve_user", AsyncMock(return_value=user))
    monkeypatch.setattr(module.user_dal, "lock_user_by_id", AsyncMock(return_value=user))
    monkeypatch.setattr(
        module.message_log_dal,
        "has_target_event_content",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        module.message_log_dal,
        "has_recent_target_event",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(module, "send_user_notification_email", send_email)

    delivery = asyncio.run(
        service.handle(
            {"uuid": "panel-user-1", "telegramId": 99},
            _context(),
        )
    )

    assert delivery.telegram_sent is False
    assert delivery.email_sent is True
    bot.send_message.assert_not_awaited()
    email_kwargs = send_email.await_args.kwargs
    assert email_kwargs["subject_key"] == "torrent_blocker_email_subject"
    assert email_kwargs["heading_key"] == "torrent_blocker_email_heading"
    assert email_kwargs["intro_key"] == "torrent_blocker_email_intro"
    assert email_kwargs["audit_event_type"] == module.EMAIL_TORRENT_NOTIFICATION_EVENT
