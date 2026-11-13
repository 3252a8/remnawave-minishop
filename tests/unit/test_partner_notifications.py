from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.services import notification_partner
from bot.services.notification_service import NotificationService


class _LocaleI18n:
    def __init__(self) -> None:
        self.messages = {
            language: json.loads(Path(f"locales/{language}.json").read_text(encoding="utf-8"))
            for language in ("en", "ru")
        }

    def gettext(self, language: str, key: str, **kwargs: object) -> str:
        return str(self.messages.get(language, {}).get(key, key)).format(**kwargs)


def _service() -> NotificationService:
    service = NotificationService(
        bot=SimpleNamespace(send_message=AsyncMock()),
        settings=SimpleNamespace(
            DEFAULT_LANGUAGE="ru",
            LOG_CHAT_ID=-100123,
            LOG_THREAD_ID=77,
            LOG_PARTNER_THREAD_ID=None,
            ADMIN_IDS=[],
        ),
        i18n=_LocaleI18n(),
    )
    service._send_to_log_channel = AsyncMock()
    return service


def _user(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "user_id": -42,
        "telegram_id": 777,
        "username": "alice",
        "first_name": "Alice",
        "email": "alice@example.test",
        "language_code": "ru",
        "telegram_notifications_status": "enabled",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_partner_application_and_withdrawal_requests_go_to_log_chat() -> None:
    service = _service()
    user = _user()
    timestamp = datetime(2026, 8, 9, 10, 0, tzinfo=UTC)

    asyncio.run(
        service.notify_partner_application_submitted(
            application_id=17,
            user=user,
            submitted_at=timestamp,
        )
    )
    asyncio.run(
        service.notify_partner_withdrawal_requested(
            withdrawal_id=23,
            user=user,
            amount_minor=125_050,
            currency="RUB",
            currency_scale=2,
            requested_at=timestamp,
        )
    )

    first = service._send_to_log_channel.await_args_list[0]
    second = service._send_to_log_channel.await_args_list[1]
    assert "Новая заявка на подключение" in first.args[0]
    assert "#17" in first.args[0]
    assert first.kwargs["reply_markup"].inline_keyboard[0][0].url == "tg://user?id=777"
    assert "Новая заявка на вывод" in second.args[0]
    assert "1250.50 RUB" in second.args[0]
    assert "#23" in second.args[0]


def test_partner_application_decision_notifies_user_and_logs_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    user = _user()
    monkeypatch.setattr(notification_partner, "get_queue_manager", lambda: None)

    asyncio.run(
        service.notify_partner_application_decided(
            application_id=17,
            user=user,
            status="approved",
            decided_at=datetime(2026, 8, 9, 10, 5, tzinfo=UTC),
        )
    )

    log_message = service._send_to_log_channel.await_args.args[0]
    assert "Партнёрская программа активирована" in log_message
    service.bot.send_message.assert_awaited_once()
    kwargs = service.bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 777
    assert "заявка в партнёрскую программу одобрена" in kwargs["text"]


def test_partner_application_rejection_notifies_user_without_activation_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    user = _user()
    monkeypatch.setattr(notification_partner, "get_queue_manager", lambda: None)

    asyncio.run(
        service.notify_partner_application_decided(
            application_id=17,
            user=user,
            status="rejected",
            decided_at=datetime(2026, 8, 9, 10, 5, tzinfo=UTC),
        )
    )

    service._send_to_log_channel.assert_not_awaited()
    kwargs = service.bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 777
    assert "заявка в партнёрскую программу отклонена" in kwargs["text"]


@pytest.mark.parametrize(
    ("old_status", "status", "expected"),
    [
        ("none", "active", "партнёрский профиль активирован"),
        ("paused", "active", "снова активен"),
        ("active", "paused", "партнёрский профиль приостановлен"),
        ("active", "closed", "партнёрский профиль закрыт"),
    ],
)
def test_partner_profile_statuses_notify_user(
    monkeypatch: pytest.MonkeyPatch,
    old_status: str,
    status: str,
    expected: str,
) -> None:
    service = _service()
    user = _user()
    monkeypatch.setattr(notification_partner, "get_queue_manager", lambda: None)

    asyncio.run(
        service.notify_partner_profile_status_changed(
            partner_id=8,
            user=user,
            old_status=old_status,
            status=status,
            changed_at=datetime(2026, 8, 9, 10, 5, tzinfo=UTC),
        )
    )

    kwargs = service.bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 777
    assert expected in kwargs["text"].lower()
    if old_status == "none":
        assert (
            "Партнёрский профиль активирован" in (service._send_to_log_channel.await_args.args[0])
        )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("processing", "одобрена и передана в обработку"),
        ("paid", "Выплата по заявке №23 произведена"),
        ("rejected", "возвращены на партнёрский баланс"),
        ("failed", "остаётся зарезервированной"),
        ("canceled", "Заявка на вывод №23 отменена"),
    ],
)
def test_partner_withdrawal_statuses_notify_user(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    expected: str,
) -> None:
    service = _service()
    user = _user()
    monkeypatch.setattr(notification_partner, "get_queue_manager", lambda: None)

    asyncio.run(
        service.notify_partner_withdrawal_status_changed(
            withdrawal_id=23,
            user=user,
            status=status,
            amount_minor=125_050,
            currency="RUB",
            currency_scale=2,
        )
    )

    kwargs = service.bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 777
    assert expected in kwargs["text"]
    assert "1250.50 RUB" in kwargs["text"]


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        (
            "https://tonviewer.com/transaction/abc123",
            'href="https://tonviewer.com/transaction/abc123"',
        ),
        ("abc123", "Хеш транзакции: <code>abc123</code>"),
    ],
)
def test_paid_crypto_withdrawal_notification_includes_settlement_and_transaction(
    monkeypatch: pytest.MonkeyPatch,
    reference: str,
    expected: str,
) -> None:
    service = _service()
    user = _user()
    monkeypatch.setattr(notification_partner, "get_queue_manager", lambda: None)

    asyncio.run(
        service.notify_partner_withdrawal_status_changed(
            withdrawal_id=23,
            user=user,
            status="paid",
            amount_minor=125_050,
            currency="RUB",
            currency_scale=2,
            settlement_amount="16.75 TON",
            external_reference=reference,
        )
    )

    message = service.bot.send_message.await_args.kwargs["text"]
    assert "Итоговая сумма в криптовалюте: <b>16.75 TON</b>" in message
    assert expected in message


def test_partner_notification_skips_known_unreachable_telegram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    user = _user(telegram_notifications_status="blocked")
    monkeypatch.setattr(notification_partner, "get_queue_manager", lambda: None)

    asyncio.run(
        service.notify_partner_application_decided(
            application_id=17,
            user=user,
            status="rejected",
            decided_at=datetime(2026, 8, 9, 10, 5, tzinfo=UTC),
        )
    )

    service.bot.send_message.assert_not_awaited()
