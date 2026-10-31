"""Telegram transport IDs must never select an unrelated payment account."""

import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, create_autospec

import pytest

from bot.payment_providers.platega import service as platega
from bot.payment_providers.shared import PaymentCallbackParts
from bot.payment_providers.yookassa import callback_common, payment_methods
from bot.services import telegram_account


@pytest.fixture
def linked_account(monkeypatch):
    lookup = AsyncMock(return_value=SimpleNamespace(user_id=456))
    monkeypatch.setattr(telegram_account.user_dal, "get_user_by_telegram_id", lookup)
    return lookup


def _callback(data):
    return SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=123),
        message=AsyncMock(),
        answer=AsyncMock(),
    )


def _i18n_data():
    return {"i18n_instance": SimpleNamespace(gettext=lambda language, key, **kwargs: key)}


@pytest.mark.parametrize("provider", ["cryptopay", "stars", "stripe"])
@pytest.mark.parametrize("account_id", [123, 456])
def test_invoice_callbacks_keep_account_id_separate_from_telegram(
    monkeypatch, linked_account, provider, account_id
):
    linked_account.return_value = SimpleNamespace(user_id=account_id)
    module = importlib.import_module(
        f"bot.payment_providers.{provider}.{'callbacks' if provider == 'stripe' else 'service'}"
    )
    spec_owner = (
        importlib.import_module("bot.payment_providers.stripe") if provider == "stripe" else module
    )
    available = Mock(return_value=True)
    monkeypatch.setattr(spec_owner, "SPEC", SimpleNamespace(is_available_to_user=available))
    parts = PaymentCallbackParts(months=1, price=100, sale_mode="subscription")
    quote = AsyncMock(return_value=(parts, None))
    monkeypatch.setattr(module, "quote_hwid_callback_parts", quote)
    monkeypatch.setattr(module, "freeze_subscription_terms", lambda *args: None)
    for name in ("default_currency_key_for_settings", "default_payment_currency_code_for_settings"):
        if hasattr(module, name):
            monkeypatch.setattr(module, name, lambda settings: "RUB")
    create_record = AsyncMock(return_value=SimpleNamespace(payment_id=77, user_id=account_id))
    monkeypatch.setattr(module.payment_dal, "create_payment_record", create_record)
    monkeypatch.setattr(
        module.payment_dal,
        "find_recent_pending_provider_payment",
        create_autospec(module.payment_dal.find_recent_pending_provider_payment, return_value=None),
    )
    if provider == "stripe":
        monkeypatch.setattr(module, "render_link_or_fail", AsyncMock())
    service = SimpleNamespace(
        configured=True,
        subscription_service=object(),
        create_invoice=AsyncMock(return_value=None),
        create_checkout_session=AsyncMock(
            return_value=(True, {"url": "https://pay.example/1", "id": "checkout-1"})
        ),
    )
    session = AsyncMock()
    callback = _callback(f"pay_{provider}:1:100:subscription")
    handler_name = (
        "pay_crypto_callback_handler"
        if provider == "cryptopay"
        else f"pay_{provider}_callback_handler"
    )
    asyncio.run(
        getattr(module, handler_name)(
            callback=callback,
            settings=SimpleNamespace(DEFAULT_LANGUAGE="en"),
            i18n_data=_i18n_data(),
            session=session,
            **{f"{provider}_service": service},
        )
    )

    linked_account.assert_awaited_once_with(session, 123)
    assert available.call_args.kwargs["user_id"] == account_id
    assert quote.await_args.kwargs["user_id"] == account_id
    if provider == "stripe":
        assert create_record.await_args.args[1]["user_id"] == account_id
        assert service.create_checkout_session.await_args.kwargs["user_id"] == account_id
    else:
        assert service.create_invoice.await_args.kwargs["user_id"] == account_id
        if provider == "stars":
            assert service.create_invoice.await_args.kwargs["chat_id"] == 123


@pytest.mark.parametrize(
    ("module_name", "handler_name", "data"),
    [
        ("callback_payment", "pay_yk_callback_handler", "pay_yk_bank_card:1:100:subscription"),
        ("callback_payment", "pay_yk_new_card_handler", "pay_yk_new:1:100:subscription"),
        ("callback_saved", "pay_yk_saved_list_handler", "pay_yk_saved_list:1:100:0:subscription"),
        ("callback_saved", "pay_yk_use_saved_handler", "pay_yk_use_saved:1:100:7:subscription"),
    ],
)
def test_yookassa_callbacks_check_and_quote_the_linked_account(
    monkeypatch, linked_account, module_name, handler_name, data
):
    module = importlib.import_module(f"bot.payment_providers.yookassa.{module_name}")
    monkeypatch.setattr(module, "callback_message_or_none", lambda callback: callback.message)
    available = Mock(return_value=True)
    monkeypatch.setattr(
        callback_common,
        "_provider_spec",
        lambda *args: SimpleNamespace(is_available_to_user=available),
    )
    quote = AsyncMock(return_value=(None, None))
    monkeypatch.setattr(module, "quote_hwid_callback_parts", quote)
    saved = AsyncMock(return_value=[])
    monkeypatch.setattr(module.user_billing_dal, "list_user_payment_methods", saved)
    for name in ("default_currency_key_for_settings", "default_payment_currency_code_for_settings"):
        monkeypatch.setattr(module, name, lambda settings: "RUB")
    session = AsyncMock()
    asyncio.run(
        getattr(module, handler_name)(
            _callback(data),
            SimpleNamespace(
                DEFAULT_LANGUAGE="en",
                yookassa_autopayments_active=True,
                traffic_sale_mode=False,
                YOOKASSA_AUTOPAYMENTS_REQUIRE_CARD_BINDING=True,
            ),
            _i18n_data(),
            SimpleNamespace(configured=True, subscription_service=object()),
            session,
        )
    )
    linked_account.assert_awaited_once_with(session, 123)
    assert available.call_args.kwargs["user_id"] == 456
    if quote.await_count:
        assert quote.await_args.kwargs["user_id"] == 456
    if saved.await_count:
        assert saved.await_args.args[1] == 456


def test_platega_reuses_payment_for_its_account_instead_of_transport_context():
    reuse = AsyncMock(return_value="https://pay.example/reused")
    payment = SimpleNamespace(payment_id=77, user_id=456)
    url = asyncio.run(
        platega._reuse_payment_with_context(
            SimpleNamespace(try_reuse_pending_transaction=reuse),
            payment,
            {"platega_variant": "sbp", "user_id": 123, "sale_mode": "subscription"},
        )
    )
    assert url == "https://pay.example/reused"
    assert reuse.await_args.kwargs["user_id"] == 456


def test_yookassa_binding_metadata_uses_the_linked_account(monkeypatch, linked_account):
    class RequestCaptured(Exception):
        pass

    create = AsyncMock(side_effect=RequestCaptured)
    monkeypatch.setattr(
        payment_methods, "callback_message_or_none", lambda callback: callback.message
    )
    monkeypatch.setattr(
        payment_methods, "default_payment_currency_code_for_settings", lambda settings: "RUB"
    )
    session = AsyncMock()
    with pytest.raises(RequestCaptured):
        asyncio.run(
            payment_methods.payment_method_bind(
                _callback("pm:bind"),
                SimpleNamespace(DEFAULT_LANGUAGE="en", yookassa_autopayments_active=True),
                _i18n_data(),
                session,
                SimpleNamespace(
                    create_payment=create,
                    config=SimpleNamespace(DEFAULT_RECEIPT_EMAIL="receipt@example.test"),
                ),
            )
        )
    linked_account.assert_awaited_once_with(session, 123)
    assert create.await_args.kwargs["metadata"] == {"user_id": "456", "bind_only": "1"}
