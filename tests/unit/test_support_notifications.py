import asyncio
from pathlib import Path
from types import SimpleNamespace

from bot.middlewares.i18n import JsonI18n
from bot.services.email_templates import (
    render_support_new_ticket_admin,
    render_support_ticket_closed_user,
)
from bot.services.notification_service import NotificationService
from config.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def _settings(**overrides):
    data = {
        "BOT_TOKEN": "123456:test",
        "POSTGRES_USER": "app_user",
        "POSTGRES_PASSWORD": "app_password",
        # Keep the helper hermetic: an ambient SUBSCRIPTION_MINI_APP_URL (set in CI) must
        # not leak into the fallback tests that expect it unset. Explicit overrides win.
        "SUBSCRIPTION_MINI_APP_URL": "",
    }
    data.update(overrides)
    return Settings(_env_file=None, **data)


def _i18n():
    return JsonI18n(str(REPO_ROOT / "locales"), default="ru")


def _keyboard_buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_support_ticket_closed_email_uses_user_language():
    content = render_support_ticket_closed_user(
        _settings(DEFAULT_LANGUAGE="en"),
        _i18n(),
        "ru",
        ticket_id=7,
        subject="Проблема с подключением",
        ticket_url="https://app.example.com/support/7",
    )

    assert content.subject == "Тикет #7 закрыт"
    assert '<html lang="ru"' in content.html
    assert "Ticket #7 was closed" not in content.text
    assert "Тема: Проблема с подключением" in content.text
    assert "Открыть обращение" in content.html


def test_support_admin_email_localizes_snapshot_rows_for_recipient():
    content = render_support_new_ticket_admin(
        _settings(DEFAULT_LANGUAGE="en"),
        _i18n(),
        "ru",
        ticket_id=11,
        user_display="user@example.com",
        subject="Не работает сайт",
        body_preview="Не открывается личный кабинет",
        snapshot_rows=[
            ("email_support_row_tariff", "Стандарт"),
            ("email_support_row_remaining", "3 д. 2 ч."),
        ],
        ticket_url="https://app.example.com/admin/support/11",
    )

    assert content.subject == "Новый тикет поддержки #11"
    assert "Тариф: Стандарт" in content.text
    assert "Осталось: 3 д. 2 ч." in content.text
    assert "Tariff: Standard" not in content.text


def test_support_ticket_url_uses_subscription_mini_app_url():
    service = NotificationService(
        bot=SimpleNamespace(),
        settings=_settings(SUBSCRIPTION_MINI_APP_URL="https://app.example.com"),
    )

    assert service._support_ticket_url(42, admin=True) == "https://app.example.com/admin/support/42"
    assert service._support_ticket_url(42, admin=False) == "https://app.example.com/support/42"


def test_support_ticket_url_falls_back_to_startapp_deeplink():
    service = NotificationService(
        bot=SimpleNamespace(),
        settings=_settings(),
        bot_username="demo_bot",
    )

    assert service._support_ticket_url(42) == "https://t.me/demo_bot?startapp=ticket_42"


def test_admin_support_keyboard_uses_consistent_admin_links():
    service = NotificationService(
        bot=SimpleNamespace(),
        settings=_settings(SUBSCRIPTION_MINI_APP_URL="https://app.example.com/app"),
    )
    ticket = SimpleNamespace(ticket_id=42)
    user = SimpleNamespace(user_id=100200300)

    keyboard = service._support_keyboard(ticket, user, admin=True)
    ticket_button = keyboard.inline_keyboard[0][0]
    user_card_button = keyboard.inline_keyboard[1][1]

    assert keyboard.inline_keyboard[0][0].text == "Открыть тикет"
    assert ticket_button.url is None
    assert ticket_button.web_app.url == "https://app.example.com/app/admin/support/42"
    assert keyboard.inline_keyboard[1][0].url == "tg://user?id=100200300"
    assert user_card_button.url is None
    assert user_card_button.web_app.url == "https://app.example.com/app/admin/users/100200300"


def test_admin_support_keyboard_can_use_group_safe_urls():
    service = NotificationService(
        bot=SimpleNamespace(),
        settings=_settings(SUBSCRIPTION_MINI_APP_URL="https://app.example.com/app"),
    )
    ticket = SimpleNamespace(ticket_id=42)
    user = SimpleNamespace(user_id=100200300)

    keyboard = service._support_keyboard(ticket, user, admin=True, web_app_buttons=False)
    ticket_button = keyboard.inline_keyboard[0][0]
    user_card_button = keyboard.inline_keyboard[1][1]

    assert ticket_button.web_app is None
    assert ticket_button.url == "https://app.example.com/app/admin/support/42"
    assert keyboard.inline_keyboard[1][0].url == "tg://user?id=100200300"
    assert user_card_button.web_app is None
    assert user_card_button.url == "https://app.example.com/app/admin/users/100200300"


def test_admin_support_keyboard_falls_back_to_startapp_url():
    service = NotificationService(
        bot=SimpleNamespace(),
        settings=_settings(),
        bot_username="demo_bot",
    )
    ticket = SimpleNamespace(ticket_id=42)
    user = SimpleNamespace(user_id=100200300)

    keyboard = service._support_keyboard(ticket, user, admin=True)
    button = keyboard.inline_keyboard[0][0]

    assert button.web_app is None
    assert button.url == "https://t.me/demo_bot?startapp=ticket_42"


def test_user_support_keyboard_uses_web_app_button_when_configured():
    service = NotificationService(
        bot=SimpleNamespace(),
        settings=_settings(SUBSCRIPTION_MINI_APP_URL="https://app.example.com/app"),
    )
    ticket = SimpleNamespace(ticket_id=42)
    user = SimpleNamespace(language_code="ru")

    keyboard = service._support_user_keyboard(ticket, user)
    button = keyboard.inline_keyboard[0][0]

    assert button.text == "Открыть тикет"
    assert button.url is None
    assert button.web_app.url == "https://app.example.com/app/support/42"


def test_user_support_keyboard_falls_back_to_startapp_url():
    service = NotificationService(
        bot=SimpleNamespace(),
        settings=_settings(),
        bot_username="demo_bot",
    )
    ticket = SimpleNamespace(ticket_id=42)
    user = SimpleNamespace(language_code="ru")

    keyboard = service._support_user_keyboard(ticket, user)
    button = keyboard.inline_keyboard[0][0]

    assert button.text == "Открыть тикет"
    assert button.web_app is None
    assert button.url == "https://t.me/demo_bot?startapp=ticket_42"


def test_admin_support_email_notifications_can_be_disabled():
    sent = []

    class EmailService:
        async def send_rendered_email(self, *, email, content):
            sent.append((email, content))

    service = NotificationService(
        bot=SimpleNamespace(),
        settings=_settings(SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED=False),
        email_auth_service=EmailService(),
    )

    async def admin_email_users():
        return [SimpleNamespace(user_id=1, email="admin@example.com", language_code="en")]

    service._admin_email_users = admin_email_users

    async def run():
        await service._send_admin_support_email(
            lambda *_args, **_kwargs: SimpleNamespace(subject="Ticket", html="Body", text="Body"),
            ticket_id=1,
        )

    asyncio.run(run())

    assert sent == []


def test_admin_support_email_notifications_default_to_disabled():
    sent = []

    class EmailService:
        async def send_rendered_email(self, *, email, content):
            sent.append((email, content))

    service = NotificationService(
        bot=SimpleNamespace(),
        settings=_settings(),
        email_auth_service=EmailService(),
    )

    async def admin_email_users():
        return [SimpleNamespace(user_id=1, email="admin@example.com", language_code="en")]

    service._admin_email_users = admin_email_users

    async def run():
        await service._send_admin_support_email(
            lambda *_args, **_kwargs: SimpleNamespace(subject="Ticket", html="Body", text="Body"),
            ticket_id=1,
        )

    asyncio.run(run())

    assert sent == []


def test_persisted_support_email_override_disables_env_enabled(monkeypatch):
    sent = []

    class EmailService:
        async def send_rendered_email(self, *, email, content):
            sent.append((email, content))

    class SessionFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return SimpleNamespace()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def get_override_value(_session, key):
        assert key == "SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED"
        return True, False

    monkeypatch.setattr(
        "bot.services.notification_service.app_settings_dal.get_override_value",
        get_override_value,
    )

    service = NotificationService(
        bot=SimpleNamespace(),
        settings=_settings(SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED=True),
        session_factory=SessionFactory(),
        email_auth_service=EmailService(),
    )

    async def admin_email_users():
        return [SimpleNamespace(user_id=1, email="admin@example.com", language_code="en")]

    service._admin_email_users = admin_email_users

    async def run():
        await service._send_admin_support_email(
            lambda *_args, **_kwargs: SimpleNamespace(subject="Ticket", html="Body", text="Body"),
            ticket_id=1,
        )

    asyncio.run(run())

    assert sent == []


def test_persisted_support_email_override_enables_default_disabled(monkeypatch):
    sent = []

    class EmailService:
        async def send_rendered_email(self, *, email, content):
            sent.append((email, content))

    class SessionFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return SimpleNamespace()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def get_override_value(_session, key):
        assert key == "SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED"
        return True, True

    monkeypatch.setattr(
        "bot.services.notification_service.app_settings_dal.get_override_value",
        get_override_value,
    )

    service = NotificationService(
        bot=SimpleNamespace(),
        settings=_settings(),
        session_factory=SessionFactory(),
        email_auth_service=EmailService(),
    )

    async def admin_email_users():
        return [SimpleNamespace(user_id=1, email="admin@example.com", language_code="en")]

    service._admin_email_users = admin_email_users

    async def run():
        await service._send_admin_support_email(
            lambda *_args, **_kwargs: SimpleNamespace(subject="Ticket", html="Body", text="Body"),
            ticket_id=1,
        )

    asyncio.run(run())

    assert len(sent) == 1


def test_disabled_admin_support_email_keeps_telegram_and_log_notifications():
    emails = []
    channels = []

    class EmailService:
        async def send_rendered_email(self, *, email, content):
            emails.append((email, content))

    service = NotificationService(
        bot=SimpleNamespace(),
        settings=_settings(
            SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED=False,
            SUBSCRIPTION_MINI_APP_URL="https://app.example.com",
        ),
        email_auth_service=EmailService(),
    )

    async def send_to_admins(message, reply_markup=None):
        channels.append(("admins", bool(message), bool(reply_markup)))

    async def send_to_log_channel(message, thread_id=None, reply_markup=None):
        channels.append(("log", bool(message), bool(reply_markup)))

    service._send_to_admins = send_to_admins
    service._send_to_log_channel = send_to_log_channel

    ticket = SimpleNamespace(
        ticket_id=7,
        priority="normal",
        category="technical",
        subject="Connection issue",
    )
    user = SimpleNamespace(
        user_id=100200300,
        username="user",
        first_name="User",
        last_name=None,
        email="user@example.com",
    )

    asyncio.run(
        service.notify_new_support_ticket(
            ticket,
            user,
            "Cannot connect",
            {"tariff": "Standard", "end_date": "2026-06-01"},
        )
    )

    assert [item[0] for item in channels] == ["admins", "log"]
    assert emails == []


def test_support_topic_suppresses_admin_dm_and_uses_url_buttons():
    channels = []

    service = NotificationService(
        bot=SimpleNamespace(),
        settings=_settings(
            LOG_CHAT_ID=-1003918000002,
            LOG_SUPPORT_THREAD_ID=77,
            SUBSCRIPTION_MINI_APP_URL="https://app.example.com",
        ),
    )

    async def send_to_admins(message, reply_markup=None):
        channels.append(("admins", None, bool(message), reply_markup))

    async def send_to_log_channel(message, thread_id=None, reply_markup=None):
        channels.append(("log", thread_id, bool(message), reply_markup))

    service._send_to_admins = send_to_admins
    service._send_to_log_channel = send_to_log_channel

    ticket = SimpleNamespace(
        ticket_id=7,
        priority="normal",
        category="technical",
        subject="Connection issue",
    )
    user = SimpleNamespace(
        user_id=100200300,
        username="user",
        first_name="User",
        last_name=None,
        email="user@example.com",
    )

    asyncio.run(
        service.notify_new_support_ticket(
            ticket,
            user,
            "Cannot connect",
            {"tariff": "Standard", "end_date": "2026-06-01"},
        )
    )

    assert [item[0] for item in channels] == ["log"]
    assert channels[0][1] == 77
    markup = channels[0][3]
    buttons = _keyboard_buttons(markup)
    assert all(button.web_app is None for button in buttons)
    assert buttons[0].url == "https://app.example.com/admin/support/7"
    assert buttons[2].url == "https://app.example.com/admin/users/100200300"


def test_support_user_reply_topic_suppresses_admin_dm_and_uses_url_buttons():
    channels = []

    service = NotificationService(
        bot=SimpleNamespace(),
        settings=_settings(
            LOG_CHAT_ID=-1003918000002,
            LOG_SUPPORT_THREAD_ID=77,
            SUBSCRIPTION_MINI_APP_URL="https://app.example.com",
        ),
    )

    async def send_to_admins(message, reply_markup=None):
        channels.append(("admins", None, bool(message), reply_markup))

    async def send_to_log_channel(message, thread_id=None, reply_markup=None):
        channels.append(("log", thread_id, bool(message), reply_markup))

    service._send_to_admins = send_to_admins
    service._send_to_log_channel = send_to_log_channel

    ticket = SimpleNamespace(
        ticket_id=7,
        priority="normal",
        category="technical",
        subject="Connection issue",
    )
    message = SimpleNamespace(body="Still cannot connect")
    user = SimpleNamespace(
        user_id=100200300,
        username="user",
        first_name="User",
        last_name=None,
        email="user@example.com",
    )

    asyncio.run(
        service.notify_support_user_reply(
            ticket,
            message,
            user,
            {},
            unread_count=3,
            send_telegram=True,
            send_email=False,
        )
    )

    assert [item[0] for item in channels] == ["log"]
    assert channels[0][1] == 77
    buttons = _keyboard_buttons(channels[0][3])
    assert all(button.web_app is None for button in buttons)
    assert buttons[0].url == "https://app.example.com/admin/support/7"


def test_support_user_reply_can_send_email_without_telegram_channels():
    emails = []
    channels = []

    service = NotificationService(
        bot=SimpleNamespace(),
        settings=_settings(SUBSCRIPTION_MINI_APP_URL="https://app.example.com"),
    )

    async def send_to_admins(message, reply_markup=None):
        channels.append(("admins", bool(message), bool(reply_markup)))

    async def send_to_log_channel(message, thread_id=None, reply_markup=None):
        channels.append(("log", bool(message), bool(reply_markup)))

    async def send_admin_support_email(renderer, **kwargs):
        emails.append(kwargs)

    service._send_to_admins = send_to_admins
    service._send_to_log_channel = send_to_log_channel
    service._send_admin_support_email = send_admin_support_email

    ticket = SimpleNamespace(
        ticket_id=7,
        priority="normal",
        category="technical",
        subject="Connection issue",
    )
    message = SimpleNamespace(body="Still cannot connect")
    user = SimpleNamespace(
        user_id=100200300,
        username="user",
        first_name="User",
        last_name=None,
        email="user@example.com",
    )

    asyncio.run(
        service.notify_support_user_reply(
            ticket,
            message,
            user,
            {},
            unread_count=3,
            send_telegram=False,
            send_email=True,
        )
    )

    assert channels == []
    assert emails[0]["ticket_id"] == 7


def test_account_merge_notification_goes_to_log_channel():
    messages = []

    class I18n:
        def gettext(self, _language, key, **kwargs):
            if key == "log_open_profile_link":
                return "Open profile"
            assert key == "log_account_merged"
            return (
                f"merged primary={kwargs['primary_user_id']} "
                f"removed={kwargs['removed_user_id']} "
                f"email={kwargs['email']} end={kwargs['final_end_date']}"
            )

    service = NotificationService(
        bot=SimpleNamespace(),
        settings=_settings(LOG_CHAT_ID=-100123, DEFAULT_LANGUAGE="en"),
        i18n=I18n(),
    )

    async def send_to_log_channel(message, thread_id=None, reply_markup=None):
        messages.append((message, thread_id, reply_markup))

    service._send_to_log_channel = send_to_log_channel

    asyncio.run(
        service.notify_account_merged(
            primary_user_id=42,
            removed_user_id=-100,
            email="paid@example.com",
            telegram_id=100200300,
            username="alice",
            first_name="Alice",
            final_end_date_text="2026-06-21 10:00",
            primary_panel_user_uuid="panel-telegram",
            removed_panel_user_uuid="panel-email",
        )
    )

    assert len(messages) == 1
    message, thread_id, reply_markup = messages[0]
    assert "primary=42" in message
    assert "removed=-100" in message
    assert "paid@example.com" in message
    assert thread_id is None
    assert reply_markup.inline_keyboard[0][0].url == "tg://user?id=100200300"
