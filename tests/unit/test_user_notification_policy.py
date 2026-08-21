from types import SimpleNamespace

import pytest

from bot.services.user_notification_policy import (
    UserNotificationCategory,
    user_notification_delivery_plan,
)


def _settings(**overrides):
    values = {
        "email_auth_configured": True,
        "USER_NOTIFICATION_PAYMENTS_TELEGRAM_ENABLED": True,
        "USER_NOTIFICATION_PAYMENTS_EMAIL_ENABLED": True,
        "USER_NOTIFICATION_SINGLE_CHANNEL_FALLBACK_ENABLED": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _user(*, telegram_id=42, email="user@example.com", status="enabled"):
    return SimpleNamespace(
        telegram_id=telegram_id,
        email=email,
        telegram_notifications_status=status,
    )


@pytest.mark.parametrize(
    ("telegram_selected", "email_selected", "telegram_id", "email", "expected"),
    [
        (True, True, 42, "user@example.com", (True, True)),
        (True, False, 42, "user@example.com", (True, False)),
        (False, True, 42, "user@example.com", (False, True)),
        (False, False, 42, "user@example.com", (False, False)),
        (True, False, None, "user@example.com", (False, True)),
        (False, True, 42, "", (True, False)),
        (True, False, None, "", (False, False)),
    ],
)
def test_delivery_matrix_and_single_channel_fallback(
    telegram_selected,
    email_selected,
    telegram_id,
    email,
    expected,
):
    settings = _settings(
        USER_NOTIFICATION_PAYMENTS_TELEGRAM_ENABLED=telegram_selected,
        USER_NOTIFICATION_PAYMENTS_EMAIL_ENABLED=email_selected,
    )

    plan = user_notification_delivery_plan(
        settings,
        UserNotificationCategory.PAYMENTS,
        _user(telegram_id=telegram_id, email=email),
    )

    assert (plan.telegram, plan.email) == expected


def test_fallback_can_be_disabled():
    plan = user_notification_delivery_plan(
        _settings(
            USER_NOTIFICATION_PAYMENTS_TELEGRAM_ENABLED=True,
            USER_NOTIFICATION_PAYMENTS_EMAIL_ENABLED=False,
            USER_NOTIFICATION_SINGLE_CHANNEL_FALLBACK_ENABLED=False,
        ),
        UserNotificationCategory.PAYMENTS,
        _user(telegram_id=None),
    )

    assert not plan.any_enabled


@pytest.mark.parametrize("status", ["needs_start", "blocked"])
def test_unreachable_telegram_is_unavailable_for_fallback(status):
    plan = user_notification_delivery_plan(
        _settings(
            USER_NOTIFICATION_PAYMENTS_TELEGRAM_ENABLED=False,
            USER_NOTIFICATION_PAYMENTS_EMAIL_ENABLED=True,
        ),
        UserNotificationCategory.PAYMENTS,
        _user(email="", status=status),
    )

    assert not plan.any_enabled


def test_email_requires_configured_delivery():
    plan = user_notification_delivery_plan(
        _settings(email_auth_configured=False),
        UserNotificationCategory.PAYMENTS,
        _user(telegram_id=None),
    )

    assert not plan.any_enabled
