from types import SimpleNamespace

from bot.services.email_templates_common import EmailContent
from bot.services.user_notification_preferences import (
    UserNotificationPreferences,
    add_user_email_preferences_footer,
    create_email_preferences_token,
    token_matches_user_email,
    verify_email_preferences_token,
)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        WEBAPP_SESSION_SECRET="stable-test-secret",
        SUBSCRIPTION_MINI_APP_URL="https://app.example.test",
        DEFAULT_LANGUAGE="en",
    )


def _user(**overrides: object) -> SimpleNamespace:
    values = {
        "user_id": 42,
        "email": "user@example.test",
        "notification_email": "alerts@example.test",
        "language_code": "en",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_preferences_default_to_enabled_for_legacy_user_objects() -> None:
    assert UserNotificationPreferences.from_user(_user()) == UserNotificationPreferences()


def test_signed_token_is_bound_to_current_notification_email() -> None:
    settings = _settings()
    user = _user()
    token = create_email_preferences_token(settings, user)
    verified = verify_email_preferences_token(settings, token)

    assert verified is not None
    assert verified[0] == 42
    assert token_matches_user_email(user, verified[1])

    user.notification_email = "new@example.test"
    assert not token_matches_user_email(user, verified[1])


def test_invalid_signature_is_rejected() -> None:
    token = create_email_preferences_token(_settings(), _user())

    assert verify_email_preferences_token(_settings(), f"{token}x") is None


def test_footer_contains_public_preferences_link() -> None:
    content = add_user_email_preferences_footer(
        EmailContent(subject="Subject", text="Body", html="<html><body>Body</body></html>"),
        settings=_settings(),
        i18n=None,
        user=_user(),
    )

    assert "Manage email notifications" in content.text
    assert "https://app.example.test/unsubscribe?token=" in content.text
    assert "/unsubscribe?token=" in content.html
