from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services import hwid_device_notifications as device_notifications
from bot.services.hwid_device_notifications import HwidDeviceNotificationService
from bot.services.panel_api_service import PanelApiService
from config.settings import Settings
from config.tariffs_config import TariffsConfig
from db.models import Subscription, User
from tests.support.settings_stub import settings_stub


class _I18n:
    def gettext(self, language: str, key: str, **kwargs: Any) -> str:
        del language
        suffix = " ".join(f"{name}={value}" for name, value in sorted(kwargs.items()))
        return f"{key} {suffix}".strip()


class _Bot:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> None:
        self.messages.append({"chat_id": chat_id, "text": text, **kwargs})


def _catalog() -> TariffsConfig:
    return TariffsConfig.model_validate(
        {
            "default_tariff": "standard",
            "default_currency": "rub",
            "tariffs": [
                {
                    "key": "standard",
                    "names": {"en": "Standard"},
                    "billing_model": "period",
                    "squad_uuids": ["main"],
                    "monthly_gb": 100,
                    "enabled_periods": [1],
                    "prices": {"rub": {"1": 100}},
                    "hwid_device_limit": 2,
                    "hwid_device_packages": {
                        "rub": [{"count": 1, "price": 50}],
                    },
                }
            ],
        }
    )


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "DEFAULT_LANGUAGE": "en",
        "MY_DEVICES_SECTION_ENABLED": True,
        "SUBSCRIPTION_MINI_APP_URL": "https://t.me/example_bot/app",
        "USER_HWID_DEVICE_LIMIT": None,
        "USER_NOTIFICATION_DEVICE_ACTIVITY_TELEGRAM_ENABLED": True,
        "USER_NOTIFICATION_DEVICE_ACTIVITY_EMAIL_ENABLED": True,
        "USER_NOTIFICATION_DEVICE_LIMIT_TELEGRAM_ENABLED": True,
        "USER_NOTIFICATION_DEVICE_LIMIT_EMAIL_ENABLED": True,
        "USER_NOTIFICATION_SINGLE_CHANNEL_FALLBACK_ENABLED": True,
        "email_auth_configured": True,
        "tariffs_config": _catalog(),
    }
    values.update(overrides)
    return cast(Settings, settings_stub(**values))


def _user(**overrides: Any) -> User:
    values: dict[str, Any] = {
        "user_id": 42,
        "telegram_id": 4242,
        "email": "user@example.test",
        "language_code": "en",
        "telegram_notifications_status": "enabled",
    }
    values.update(overrides)
    return cast(User, SimpleNamespace(**values))


def _subscription(**overrides: Any) -> Subscription:
    values: dict[str, Any] = {
        "subscription_id": 7,
        "user_id": 42,
        "panel_user_uuid": "panel-user",
        "hwid_device_limit": 2,
        "extra_hwid_devices": 0,
        "is_active": True,
        "end_date": datetime(2099, 1, 1, tzinfo=UTC),
        "provider": "yookassa",
        "status_from_panel": "ACTIVE",
        "tariff_key": "standard",
    }
    values.update(overrides)
    return cast(Subscription, SimpleNamespace(**values))


def _service(
    settings: Settings,
    bot: _Bot,
    panel: SimpleNamespace,
) -> HwidDeviceNotificationService:
    return HwidDeviceNotificationService(
        settings,
        cast(Bot, bot),
        cast(JsonI18n, _I18n()),
        cast(PanelApiService, panel),
    )


_SESSION = cast(AsyncSession, object())


@pytest.fixture
def notification_state(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    recorded: set[str] = set()
    emitted: list[Any] = []
    emails: list[dict[str, Any]] = []

    async def has_notification(session, subscription_id, notification_key):
        del session, subscription_id
        return notification_key in recorded

    async def record_notification(
        session,
        subscription_id,
        notification_key,
        *,
        sent_at=None,
    ):
        del session, subscription_id, sent_at
        recorded.add(notification_key)

    async def emit_model(payload):
        emitted.append(payload)

    async def send_email(**kwargs):
        emails.append(kwargs)
        return True

    async def no_audit(*args, **kwargs):
        del args, kwargs

    monkeypatch.setattr(
        device_notifications.subscription_dal,
        "has_subscription_notification",
        has_notification,
    )
    monkeypatch.setattr(
        device_notifications.subscription_dal,
        "record_subscription_notification",
        record_notification,
    )
    monkeypatch.setattr(device_notifications.events, "emit_model", emit_model)
    monkeypatch.setattr(device_notifications, "send_user_notification_email", send_email)
    monkeypatch.setattr(device_notifications, "log_user_message_delivery", no_audit)
    return {"recorded": recorded, "emitted": emitted, "emails": emails}


def test_added_device_combines_limit_message_and_offers_topup(
    notification_state: dict[str, Any],
) -> None:
    bot = _Bot()
    panel = SimpleNamespace(
        get_user_devices=AsyncMock(return_value=[{"hwid": "one"}, {"hwid": "two"}])
    )
    service = _service(_settings(), bot, panel)

    result = asyncio.run(
        service.handle_added(
            _SESSION,
            user=_user(),
            subscription=_subscription(),
            user_payload={"uuid": "panel-user", "hwidDeviceLimit": 2},
            context={
                "fingerprint": "a" * 24,
                "device_model": "Pixel 9",
                "platform": "Android",
                "os_version": "15",
                "created_at": "2026-08-22T10:00:00Z",
            },
        )
    )

    assert result.needs_retry is False
    panel.get_user_devices.assert_awaited_once_with("panel-user", force_refresh=True)
    assert len(bot.messages) == 1
    assert "device_connected_notification" in bot.messages[0]["text"]
    assert "device_limit_reached_notification_topup" in bot.messages[0]["text"]
    assert bot.messages[0]["reply_markup"] is not None
    assert len(notification_state["emails"]) == 1
    assert notification_state["emails"][0]["subject_key"] == ("email_device_limit_reached_subject")
    assert notification_state["emails"][0]["cta_label_key"] == (
        "device_limit_notification_cta_topup"
    )
    assert {payload.EVENT_NAME for payload in notification_state["emitted"]} == {
        "device.connected",
        "device.limit_reached",
    }
    assert {
        f"device_connected:{'a' * 24}:telegram",
        f"device_connected:{'a' * 24}:email",
        f"device_limit:{'a' * 24}:telegram",
        f"device_limit:{'a' * 24}:email",
    }.issubset(notification_state["recorded"])


def test_added_device_below_limit_sends_only_activity(
    notification_state: dict[str, Any],
) -> None:
    bot = _Bot()
    panel = SimpleNamespace(get_user_devices=AsyncMock(return_value=[{"hwid": "one"}]))
    service = _service(
        _settings(USER_NOTIFICATION_DEVICE_ACTIVITY_EMAIL_ENABLED=False),
        bot,
        panel,
    )

    asyncio.run(
        service.handle_added(
            _SESSION,
            user=_user(),
            subscription=_subscription(),
            user_payload={"uuid": "panel-user", "hwidDeviceLimit": 2},
            context={"fingerprint": "b" * 24, "platform": "iOS"},
        )
    )

    assert len(bot.messages) == 1
    assert "device_connected_notification" in bot.messages[0]["text"]
    assert "device_limit_reached" not in bot.messages[0]["text"]
    assert notification_state["emails"] == []
    assert [payload.EVENT_NAME for payload in notification_state["emitted"]] == ["device.connected"]


def test_panel_device_lookup_failure_never_claims_limit_reached(
    notification_state: dict[str, Any],
) -> None:
    bot = _Bot()
    panel = SimpleNamespace(get_user_devices=AsyncMock(side_effect=RuntimeError("offline")))
    service = _service(_settings(), bot, panel)

    asyncio.run(
        service.handle_added(
            _SESSION,
            user=_user(),
            subscription=_subscription(),
            user_payload={"uuid": "panel-user", "hwidDeviceLimit": 1},
            context={"fingerprint": "c" * 24},
        )
    )

    assert len(bot.messages) == 1
    assert "device_limit_reached" not in bot.messages[0]["text"]
    assert len(notification_state["emails"]) == 1
    assert [payload.EVENT_NAME for payload in notification_state["emitted"]] == ["device.connected"]


def test_email_only_user_uses_single_channel_fallback(
    notification_state: dict[str, Any],
) -> None:
    bot = _Bot()
    panel = SimpleNamespace(get_user_devices=AsyncMock(return_value=[{"hwid": "one"}]))
    service = _service(
        _settings(
            USER_NOTIFICATION_DEVICE_ACTIVITY_TELEGRAM_ENABLED=True,
            USER_NOTIFICATION_DEVICE_ACTIVITY_EMAIL_ENABLED=False,
        ),
        bot,
        panel,
    )

    asyncio.run(
        service.handle_added(
            _SESSION,
            user=_user(telegram_id=None, telegram_notifications_status="needs_start"),
            subscription=_subscription(),
            user_payload={"uuid": "panel-user", "hwidDeviceLimit": 3},
            context={"fingerprint": "d" * 24},
        )
    )

    assert bot.messages == []
    assert len(notification_state["emails"]) == 1


def test_both_device_categories_disabled_emit_events_without_delivery(
    notification_state: dict[str, Any],
) -> None:
    bot = _Bot()
    panel = SimpleNamespace(
        get_user_devices=AsyncMock(return_value=[{"hwid": "one"}, {"hwid": "two"}])
    )
    service = _service(
        _settings(
            USER_NOTIFICATION_DEVICE_ACTIVITY_TELEGRAM_ENABLED=False,
            USER_NOTIFICATION_DEVICE_ACTIVITY_EMAIL_ENABLED=False,
            USER_NOTIFICATION_DEVICE_LIMIT_TELEGRAM_ENABLED=False,
            USER_NOTIFICATION_DEVICE_LIMIT_EMAIL_ENABLED=False,
        ),
        bot,
        panel,
    )

    asyncio.run(
        service.handle_added(
            _SESSION,
            user=_user(),
            subscription=_subscription(),
            user_payload={"uuid": "panel-user", "hwidDeviceLimit": 2},
            context={"fingerprint": "e" * 24},
        )
    )

    assert bot.messages == []
    assert notification_state["emails"] == []
    assert {payload.EVENT_NAME for payload in notification_state["emitted"]} == {
        "device.connected",
        "device.limit_reached",
    }


def test_retry_skips_channel_already_recorded(
    notification_state: dict[str, Any],
) -> None:
    fingerprint = "f" * 24
    notification_state["recorded"].add(f"device_connected:{fingerprint}:telegram")
    bot = _Bot()
    panel = SimpleNamespace(get_user_devices=AsyncMock(return_value=[{"hwid": "one"}]))
    service = _service(_settings(), bot, panel)

    asyncio.run(
        service.handle_added(
            _SESSION,
            user=_user(),
            subscription=_subscription(),
            user_payload={"uuid": "panel-user", "hwidDeviceLimit": 3},
            context={"fingerprint": fingerprint},
        )
    )

    assert bot.messages == []
    assert len(notification_state["emails"]) == 1
