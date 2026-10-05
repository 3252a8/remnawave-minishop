"""Signed legacy and Remnawave 2.x/3.x webhooks reach subscription recipients."""

import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import main_worker
import pytest
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter, TelegramServerError
from aiogram.methods import SendMessage

from bot.services import panel_webhook_service as panel
from bot.services import subscription_lifecycle_notifications as lifecycle
from tests.support.settings_stub import settings_stub


class SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


EXPIRATION_CASES = [
    ("user.expires_in_72_hours", None, "before_3d"),
    ("user.expires_in_48_hours", None, "before_2d"),
    ("user.expires_in_24_hours", None, "before_1d"),
    ("user.expired", None, "expired"),
    ("user.expired_24_hours_ago", None, "expired_24h_after"),
    ("user.expiration", {"expiration": -72}, "before_3d"),
    ("user.expiration", {"expiration": -48}, "before_2d"),
    ("user.expiration", {"expiration": -24}, "before_1d"),
    ("user.expiration", {"expiration": -12}, "before_12h"),
    ("user.expiration", {"expiration": -3}, "before_3h"),
    ("user.expiration", {"expiration": 12}, "expired_12h_after"),
    ("user.expiration", {"expiration": 24}, "expired_24h_after"),
]
PAYLOAD_CASES = [
    ("name_payload", {"uuid": "panel-user-1"}, 555),
    ("event_data", {"uuid": "panel-user-1"}, "555"),
    ("event_data", {"id": 42}, 555),
    ("event_data", {"id": "42"}, None),
    ("nested_user", {"id": 42}, None),
    ("nested_meta", {"uuid": "panel-user-1"}, 555),
]


def assert_signed_webhook_delivery(
    monkeypatch,
    event_name,
    meta,
    stage_key,
    envelope,
    identity,
    telegram_id,
    runtime_email_only,
    *,
    telegram_error=None,
):
    secret = "panel-test-secret"
    settings = settings_stub(
        PANEL_WEBHOOK_SECRET=secret,
        SUBSCRIPTION_NOTIFICATIONS_ENABLED=False,
        SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED=runtime_email_only,
        SUBSCRIPTION_NOTIFY_ON_EXPIRE=runtime_email_only,
        SUBSCRIPTION_NOTIFY_AFTER_EXPIRE=runtime_email_only,
        SUBSCRIPTION_NOTIFY_DAYS_BEFORE=3 if runtime_email_only else 0,
        SUBSCRIPTION_MINI_APP_URL="https://app.example.test/",
        DEFAULT_LANGUAGE="ru",
        email_auth_configured=True,
        smtp_delivery_configured=True,
    )
    session = SimpleNamespace(commit=AsyncMock())
    session_factory = lambda: SessionContext(session)
    bot = SimpleNamespace(send_message=AsyncMock())
    if telegram_error is not None:
        bot.send_message.side_effect = [telegram_error, None]
    i18n = SimpleNamespace(gettext=lambda lang, key, **kwargs: key)
    service = panel.PanelWebhookService(bot, settings, i18n, session_factory, object())
    email_service = SimpleNamespace(send_rendered_email=AsyncMock())
    service.lifecycle_notifications.email_service = email_service
    user = SimpleNamespace(
        user_id=123,
        telegram_id=555,
        email="user@example.test",
        language_code="ru",
        first_name="Ada",
        telegram_notifications_status="enabled",
    )
    subscription = SimpleNamespace(
        subscription_id=456,
        user_id=123,
        user=user,
        end_date=datetime(2026, 6, 1, tzinfo=UTC),
        tariff_key="standard",
        provider="remnawave",
        auto_renew_enabled=False,
    )
    expected_reference = str(identity.get("uuid") or identity["id"])
    telegram_lookup = AsyncMock(return_value=user)
    panel_lookup = AsyncMock(return_value=user)
    monkeypatch.setattr(panel.user_dal, "get_user_by_telegram_id", telegram_lookup)
    monkeypatch.setattr(panel.user_dal, "get_user_by_panel_uuid", panel_lookup)
    monkeypatch.setattr(service, "_subscription_for_payload", AsyncMock(return_value=subscription))
    monkeypatch.setattr(service, "_superseded_by_newer_subscription", AsyncMock(return_value=False))
    monkeypatch.setattr(service, "_hwid_renewal_note", AsyncMock(return_value=""))
    monkeypatch.setattr(panel, "record_subscription_panel_activity", AsyncMock(return_value=None))
    monkeypatch.setattr(
        panel.subscription_dal,
        "get_active_subscription_by_user_id",
        AsyncMock(return_value=subscription),
    )
    monkeypatch.setattr(lifecycle, "log_user_message_delivery", AsyncMock())
    recorded = set()

    async def has_notification(db_session, subscription_id, key):
        return key in recorded

    async def record_notification(db_session, subscription_id, key, *, sent_at=None):
        recorded.add(key)

    monkeypatch.setattr(
        lifecycle.subscription_dal, "has_subscription_notification", has_notification
    )
    monkeypatch.setattr(
        lifecycle.subscription_dal, "record_subscription_notification", record_notification
    )
    saved_settings = {
        "SUBSCRIPTION_NOTIFICATIONS_ENABLED": True,
        "SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED": True,
        "SUBSCRIPTION_NOTIFY_ON_EXPIRE": True,
        "SUBSCRIPTION_NOTIFY_AFTER_EXPIRE": True,
        "SUBSCRIPTION_NOTIFY_DAYS_BEFORE": 3,
    }

    async def refresh_settings(runtime_settings, runtime_session_factory, *, keys):
        for key, value in saved_settings.items():
            if key in keys:
                setattr(runtime_settings, key, value)

    monkeypatch.setattr(main_worker, "refresh_overrides_from_db", refresh_settings)
    queued = []

    async def enqueue(runtime_settings, provider, payload, *, event_id=None):
        assert provider == "panel"
        queued.append(payload)
        return True

    monkeypatch.setattr(panel, "enqueue_webhook_event", enqueue)
    user_payload = {**identity, "telegramId": telegram_id, "expireAt": "2026-06-01T00:00:00Z"}
    if envelope == "name_payload":
        payload = {"name": event_name, "payload": user_payload, "meta": meta}
    elif envelope == "nested_user":
        payload = {"event": event_name, "data": {"user": user_payload}, "meta": meta}
    elif envelope == "nested_meta":
        payload = {"event": event_name, "data": {**user_payload, "_meta": meta}}
    else:
        payload = {"scope": "user", "event": event_name, "data": user_payload, "meta": meta}
    body = json.dumps(payload).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    ctx = SimpleNamespace(
        settings=settings,
        require_panel_webhook_service=lambda: service,
        require_session_factory=lambda: session_factory,
    )

    async def run():
        response = await service.handle_webhook(body, signature)
        assert response.status == 200
        assert len(queued) == 1
        assert queued[0]["user"]["uuid"] == expected_reference
        if telegram_error is None:
            await main_worker._handle_panel_event(ctx, queued[0])
        else:
            with pytest.raises(lifecycle.SubscriptionNotificationRetryError) as failure:
                await main_worker._handle_panel_event(ctx, queued[0])
            assert failure.value.channels == ("telegram",)
            assert recorded == {f"{stage_key}:email"}
            session.commit.assert_awaited()
            await main_worker._handle_panel_event(ctx, queued[0])
        await main_worker._handle_panel_event(ctx, queued[0])

    asyncio.run(run())

    assert bot.send_message.await_count == (2 if telegram_error is not None else 1)
    assert bot.send_message.await_args.args[0] == 555
    email_service.send_rendered_email.assert_awaited_once()
    assert email_service.send_rendered_email.await_args.kwargs["email"] == "user@example.test"
    assert recorded == {f"{stage_key}:telegram", f"{stage_key}:email"}
    if telegram_id is None:
        panel_lookup.assert_awaited_with(session, expected_reference)
        telegram_lookup.assert_not_awaited()
    else:
        telegram_lookup.assert_awaited_with(session, 555)


@pytest.mark.parametrize(("event_name", "meta", "stage_key"), EXPIRATION_CASES)
@pytest.mark.parametrize(("envelope", "identity", "telegram_id"), PAYLOAD_CASES)
@pytest.mark.parametrize("runtime_email_only", [False, True])
def test_signed_subscription_webhook_delivers_each_channel_once(
    monkeypatch, event_name, meta, stage_key, envelope, identity, telegram_id, runtime_email_only
):
    assert_signed_webhook_delivery(
        monkeypatch,
        event_name,
        meta,
        stage_key,
        envelope,
        identity,
        telegram_id,
        runtime_email_only,
    )


@pytest.mark.parametrize(("event_name", "meta", "stage_key"), EXPIRATION_CASES)
@pytest.mark.parametrize("error_kind", ["network", "server", "rate_limit"])
def test_telegram_failure_retries_without_resending_delivered_email(
    monkeypatch, event_name, meta, stage_key, error_kind
):
    method = SendMessage(chat_id=555, text="Subscription notice")
    error: Exception
    if error_kind == "rate_limit":
        error = TelegramRetryAfter(method=method, message="Too many requests", retry_after=1)
    elif error_kind == "server":
        error = TelegramServerError(method=method, message="Server unavailable")
    else:
        error = TelegramNetworkError(method=method, message="Connection timeout")
    assert_signed_webhook_delivery(
        monkeypatch,
        event_name,
        meta,
        stage_key,
        "event_data",
        {"id": 42},
        555,
        True,
        telegram_error=error,
    )
