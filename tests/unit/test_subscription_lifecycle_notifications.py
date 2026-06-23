import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage

from bot.services import subscription_lifecycle_notifications as lifecycle
from bot.services.subscription_lifecycle_notifications import (
    SubscriptionLifecycleNotificationService,
    SubscriptionNotificationStage,
)
from tests.support.settings_stub import settings_stub


class FakeI18n:
    def gettext(self, lang_code, key, **kwargs):
        messages = {
            "subscription_72h_notification": "Hi {user_name}, expires on {end_date}",
            "email_subscription_lifecycle_subject_before_days": "{days} days left",
            "email_subscription_lifecycle_subject_before_hours": "{hours} hours left",
            "email_subscription_lifecycle_subject_expired": "Expired",
            "email_subscription_lifecycle_subject_expired_after": "Expired yesterday",
            "email_subscription_lifecycle_subject_autorenew": "Auto-renewal tomorrow",
            "email_subscription_lifecycle_intro": "Subscription notice",
            "email_subscription_lifecycle_intro_direct": "Direct email notice",
            "email_subscription_lifecycle_intro_mirrored": "Mirrored Telegram notice",
            "email_subscription_lifecycle_row_end_date": "Active until",
            "email_subscription_lifecycle_cta": "Open dashboard",
            "email_subscription_lifecycle_text_renew": "Dashboard: {url}",
            "email_footer_auto": "Sent by {brand}",
        }
        return messages.get(key, key).format(**kwargs)


class FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "reply_markup": reply_markup,
            }
        )


class ChatNotFoundBot:
    def __init__(self):
        self.calls = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.calls.append((chat_id, text, reply_markup))
        raise TelegramBadRequest(
            method=SendMessage(chat_id=chat_id, text=text),
            message="Bad Request: chat not found",
        )


class FakeEmailService:
    def __init__(self):
        self.messages = []

    async def send_rendered_email(self, *, email, content):
        self.messages.append({"email": email, "content": content})


def _settings(**overrides):
    return settings_stub(
        DEFAULT_LANGUAGE="ru",
        SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED=True,
        SUBSCRIPTION_MINI_APP_URL="https://app.example.test/",
        WEBAPP_PRIMARY_COLOR="#00fe7a",
        WEBAPP_TITLE="Minishop",
        WEBAPP_LOGO_URL="",
        email_auth_configured=True,
        **overrides,
    )


def _subscription(**overrides):
    data = {
        "subscription_id": 42,
        "user_id": 123,
        "end_date": datetime(2026, 6, 1, tzinfo=timezone.utc),
        "tariff_key": "standard",
        "provider": "yookassa",
        "status_from_panel": "ACTIVE",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _user(**overrides):
    data = {
        "user_id": 123,
        "telegram_id": 555,
        "email": "user@example.test",
        "language_code": "ru",
        "first_name": "Ada",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_send_stage_records_telegram_and_email_channel_keys(monkeypatch):
    recorded = []
    status_changes = []

    async def fake_has(session, subscription_id, notification_key):
        return notification_key in recorded

    async def fake_record(session, subscription_id, notification_key, *, sent_at=None):
        recorded.append(notification_key)

    async def fake_mark_status(session, user_id, status, *, telegram_id=None, checked_at=None):
        status_changes.append(
            {
                "user_id": user_id,
                "status": status,
                "telegram_id": telegram_id,
                "checked_at": checked_at,
            }
        )

    monkeypatch.setattr(lifecycle.subscription_dal, "has_subscription_notification", fake_has)
    monkeypatch.setattr(lifecycle.subscription_dal, "record_subscription_notification", fake_record)
    monkeypatch.setattr(lifecycle, "mark_telegram_notifications_status", fake_mark_status)

    bot = FakeBot()
    email_service = FakeEmailService()
    service = SubscriptionLifecycleNotificationService(
        _settings(),
        bot,
        FakeI18n(),
        email_service=email_service,
    )

    async def run():
        return await service.send_stage(
            object(),
            _subscription(),
            SubscriptionNotificationStage(
                key="before_3d",
                message_key="subscription_72h_notification",
                days_left=3,
            ),
            user=_user(),
            telegram_markup="markup",
        )

    delivery = asyncio.run(run())

    assert delivery.telegram_sent is True
    assert delivery.email_sent is True
    assert bot.messages == [
        {
            "chat_id": 555,
            "text": "Hi Ada, expires on 2026-06-01",
            "reply_markup": "markup",
        }
    ]
    assert email_service.messages[0]["email"] == "user@example.test"
    assert "Mirrored Telegram notice" in email_service.messages[0]["content"].html
    assert recorded == ["before_3d:telegram", "before_3d:email"]
    assert status_changes == [
        {
            "user_id": 123,
            "status": lifecycle.TELEGRAM_NOTIFICATIONS_ENABLED,
            "telegram_id": 555,
            "checked_at": status_changes[0]["checked_at"],
        }
    ]
    assert status_changes[0]["checked_at"] is not None


def test_legacy_stage_key_suppresses_only_telegram(monkeypatch):
    recorded = ["before_3d"]

    async def fake_has(session, subscription_id, notification_key):
        return notification_key in recorded

    async def fake_record(session, subscription_id, notification_key, *, sent_at=None):
        recorded.append(notification_key)

    async def fake_log(*_args, **_kwargs):
        return None

    monkeypatch.setattr(lifecycle.subscription_dal, "has_subscription_notification", fake_has)
    monkeypatch.setattr(lifecycle.subscription_dal, "record_subscription_notification", fake_record)
    monkeypatch.setattr(lifecycle, "log_user_message_delivery", fake_log)

    bot = FakeBot()
    email_service = FakeEmailService()
    service = SubscriptionLifecycleNotificationService(
        _settings(),
        bot,
        FakeI18n(),
        email_service=email_service,
    )

    async def run():
        return await service.send_stage(
            object(),
            _subscription(),
            SubscriptionNotificationStage(
                key="before_3d",
                message_key="subscription_72h_notification",
                days_left=3,
            ),
            user=_user(),
            telegram_markup="markup",
        )

    delivery = asyncio.run(run())

    assert delivery.telegram_sent is False
    assert delivery.email_sent is True
    assert bot.messages == []
    assert email_service.messages[0]["email"] == "user@example.test"
    assert recorded == ["before_3d", "before_3d:email"]


def test_default_telegram_markup_uses_mini_app_renewal_when_bot_menu_disabled(monkeypatch):
    recorded = []

    async def fake_has(session, subscription_id, notification_key):
        return notification_key in recorded

    async def fake_record(session, subscription_id, notification_key, *, sent_at=None):
        recorded.append(notification_key)

    monkeypatch.setattr(lifecycle.subscription_dal, "has_subscription_notification", fake_has)
    monkeypatch.setattr(lifecycle.subscription_dal, "record_subscription_notification", fake_record)

    bot = FakeBot()
    settings = _settings(TELEGRAM_BOT_MENU_DISABLED=True)
    service = SubscriptionLifecycleNotificationService(
        settings,
        bot,
        FakeI18n(),
    )

    async def run():
        return await service.send_stage(
            object(),
            _subscription(tariff_key="premium"),
            SubscriptionNotificationStage(
                key="before_3d",
                message_key="subscription_72h_notification",
                days_left=3,
            ),
            user=_user(
                email="",
                telegram_notifications_status=lifecycle.TELEGRAM_NOTIFICATIONS_ENABLED,
            ),
        )

    delivery = asyncio.run(run())

    button = bot.messages[0]["reply_markup"].inline_keyboard[0][0]
    assert delivery.telegram_sent is True
    assert button.callback_data is None
    assert button.web_app.url == "https://app.example.test/?renew=1&renew_tariff=premium"


def test_unstarted_telegram_failure_marks_status_without_recording_delivery(monkeypatch):
    recorded = []
    status_changes = []

    async def fake_has(session, subscription_id, notification_key):
        return notification_key in recorded

    async def fake_record(session, subscription_id, notification_key, *, sent_at=None):
        recorded.append(notification_key)

    async def fake_mark_status(session, user_id, status, *, telegram_id=None, checked_at=None):
        status_changes.append(
            {
                "user_id": user_id,
                "status": status,
                "telegram_id": telegram_id,
                "checked_at": checked_at,
            }
        )

    monkeypatch.setattr(lifecycle.subscription_dal, "has_subscription_notification", fake_has)
    monkeypatch.setattr(lifecycle.subscription_dal, "record_subscription_notification", fake_record)
    monkeypatch.setattr(lifecycle, "mark_telegram_notifications_status", fake_mark_status)

    bot = ChatNotFoundBot()
    settings = _settings()
    settings.email_auth_configured = False
    service = SubscriptionLifecycleNotificationService(
        settings,
        bot,
        FakeI18n(),
    )
    user = _user()
    user.telegram_id = 777
    user.email = ""

    async def run():
        return await service.send_stage(
            object(),
            _subscription(),
            SubscriptionNotificationStage(
                key="before_3d",
                message_key="subscription_72h_notification",
                days_left=3,
            ),
            user=user,
            telegram_markup="markup",
        )

    delivery = asyncio.run(run())

    assert delivery.telegram_sent is False
    assert delivery.email_sent is False
    assert bot.calls[0][0] == 777
    assert recorded == []
    assert status_changes == [
        {
            "user_id": 123,
            "status": lifecycle.TELEGRAM_NOTIFICATIONS_NEEDS_START,
            "telegram_id": None,
            "checked_at": None,
        }
    ]


def test_email_only_user_gets_email_name_direct_copy_and_renewal_login_link(monkeypatch):
    recorded = []

    async def fake_has(session, subscription_id, notification_key):
        return notification_key in recorded

    async def fake_record(session, subscription_id, notification_key, *, sent_at=None):
        recorded.append(notification_key)

    monkeypatch.setattr(lifecycle.subscription_dal, "has_subscription_notification", fake_has)
    monkeypatch.setattr(lifecycle.subscription_dal, "record_subscription_notification", fake_record)

    bot = FakeBot()
    email_service = FakeEmailService()
    service = SubscriptionLifecycleNotificationService(
        _settings(),
        bot,
        FakeI18n(),
        email_service=email_service,
    )
    user = _user(user_id=-8758169927032035, telegram_id=None, first_name=None)

    async def run():
        return await service.send_stage(
            object(),
            _subscription(user_id=user.user_id),
            SubscriptionNotificationStage(
                key="expired",
                message_key="subscription_72h_notification",
                days_left=0,
            ),
            user=user,
            telegram_markup="markup",
        )

    delivery = asyncio.run(run())

    assert delivery.telegram_sent is False
    assert delivery.email_sent is True
    assert bot.messages == []
    content = email_service.messages[0]["content"]
    assert "Hi user@example.test, expires on 2026-06-01" in content.text
    assert "User -8758169927032035" not in content.text
    assert "Direct email notice" in content.html
    assert "Mirrored Telegram notice" not in content.html

    dashboard_line = next(
        line for line in content.text.splitlines() if line.startswith("Dashboard: ")
    )
    url = dashboard_line.removeprefix("Dashboard: ")
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "app.example.test"
    assert query["login"] == ["email_code"]
    assert query["login_email"] == ["user@example.test"]
    assert query["after_login"] == ["renew"]
    assert query["renew"] == ["1"]
    assert query["renew_tariff"] == ["standard"]
    assert recorded == ["expired:email"]


def test_trial_subscription_renewal_link_omits_tariff_for_default_fallback(monkeypatch):
    recorded = []

    async def fake_has(session, subscription_id, notification_key):
        return notification_key in recorded

    async def fake_record(session, subscription_id, notification_key, *, sent_at=None):
        recorded.append(notification_key)

    monkeypatch.setattr(lifecycle.subscription_dal, "has_subscription_notification", fake_has)
    monkeypatch.setattr(lifecycle.subscription_dal, "record_subscription_notification", fake_record)

    email_service = FakeEmailService()
    service = SubscriptionLifecycleNotificationService(
        _settings(),
        FakeBot(),
        FakeI18n(),
        email_service=email_service,
    )
    user = _user(user_id=-1001, telegram_id=None, first_name=None)

    async def run():
        return await service.send_stage(
            object(),
            _subscription(
                user_id=user.user_id,
                tariff_key="trial-tariff",
                provider="trial",
                status_from_panel="TRIAL",
            ),
            SubscriptionNotificationStage(
                key="expired",
                message_key="subscription_72h_notification",
                days_left=0,
            ),
            user=user,
        )

    asyncio.run(run())

    content = email_service.messages[0]["content"]
    dashboard_line = next(
        line for line in content.text.splitlines() if line.startswith("Dashboard: ")
    )
    query = parse_qs(urlsplit(dashboard_line.removeprefix("Dashboard: ")).query)
    assert "renew_tariff" not in query
