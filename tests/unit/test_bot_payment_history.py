import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.handlers.user import payment_history


def test_payment_history_is_account_scoped_and_only_resumes_active_checkout(monkeypatch):
    future = datetime.now(UTC) + timedelta(hours=1)
    entries = [
        SimpleNamespace(
            payment_id=number,
            amount=190,
            currency="RUB",
            provider="<demo>",
            status=status,
            created_at=None,
            provider_payment_url=f"https://pay.example/{number}",
            checkout_expires_at=expires,
            fulfilled_at=None,
            reversed_at=None,
        )
        for number, status, expires in (
            (11, "pending", future),
            (12, "pending", future - timedelta(days=1)),
            (13, "succeeded", future),
        )
    ]
    account = AsyncMock(return_value=91)
    payments = AsyncMock(side_effect=[([], 6), (entries, 6)])
    monkeypatch.setattr(payment_history, "require_telegram_account_id", account)
    monkeypatch.setattr(payment_history, "list_user_payments", payments)
    monkeypatch.setattr(payment_history, "provider_label_map", lambda *args: {})
    event = SimpleNamespace(from_user=SimpleNamespace(id=17), answer=AsyncMock())
    settings = SimpleNamespace(DEFAULT_LANGUAGE="en")

    def gettext(lang, key, **values):
        return values["provider"] if key == "bot_payment_history_item" else key

    i18n = SimpleNamespace(gettext=gettext)
    session = object()

    asyncio.run(
        payment_history.send_payment_history(event, settings, {"i18n_instance": i18n}, session, 3)
    )

    account.assert_awaited_once_with(session, 17)
    assert [call.args for call in payments.await_args_list] == [(session, 91), (session, 91)]
    assert [call.kwargs["offset"] for call in payments.await_args_list] == [15, 5]
    assert "&lt;demo&gt;" in event.answer.await_args.args[0]
    markup = event.answer.await_args.kwargs["reply_markup"]
    assert [button.url for row in markup.inline_keyboard for button in row if button.url] == [
        "https://pay.example/11"
    ]
    assert [row[0].callback_data for row in markup.inline_keyboard[1:]] == [
        "main_action:bot_payment_history:0",
        "main_action:bot_interface",
    ]
