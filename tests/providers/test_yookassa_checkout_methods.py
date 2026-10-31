import asyncio
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from bot.payment_providers import registry
from bot.payment_providers.base import ProviderConfigBundle, WebAppPaymentContext
from bot.payment_providers.yookassa import CARD_SPEC, SBP_SPEC, SPEC, callback_payment, payments
from bot.payment_providers.yookassa.config import YooKassaConfig, order_checkout_methods
from bot.payment_providers.yookassa.service import YooKassaService
from bot.services import telegram_account


def _service():
    service = object.__new__(YooKassaService)
    service.settings = SimpleNamespace()
    service.config = YooKassaConfig(
        _env_file=None,
        SHOP_ID="shop",
        SECRET_KEY="secret",
        RETURN_URL="https://shop.example/return",
        DEFAULT_RECEIPT_EMAIL="receipt@example.test",
        PAYMENT_METHODS="sbp,bank_card,other",
    )
    service._sdk_configured_for = ("shop", "secret")
    service._configured_return_url_override = None
    service._bot_username_for_default_return = None
    service._run_sdk_call = AsyncMock(
        return_value=SimpleNamespace(
            id="payment-1",
            status="pending",
            paid=False,
            refundable=False,
            confirmation=SimpleNamespace(confirmation_url="https://pay.example/1"),
            metadata={},
            created_at="now",
            description="Order",
            test=True,
            amount=SimpleNamespace(value="10.13", currency="RUB"),
            payment_method=None,
        )
    )
    return service


@pytest.mark.parametrize("method", [None, "sbp", "bank_card"])
@pytest.mark.parametrize("saved", [False, True])
def test_sdk_request_keeps_saved_cards_receipts_and_idempotency(method, saved) -> None:
    service = _service()
    result = asyncio.run(
        service.create_payment(
            amount=10.125,
            currency="RUB",
            description="Order",
            metadata={"payment_db_id": "42"},
            payment_method_type=method,
            payment_method_id="saved-card" if saved else None,
            save_payment_method=not saved,
            idempotence_key="same-order",
        )
    )
    assert result and result["id"] == "payment-1"
    call = service._run_sdk_call.await_args
    assert call is not None
    request = call.args[2]
    assert call.args[3] == "same-order"
    assert request.amount.value == Decimal("10.13")
    assert request.receipt.items[0].amount.value == Decimal("10.13")
    assert request.receipt.customer.email == "receipt@example.test"
    assert request.metadata == {"payment_db_id": "42"}
    if saved:
        assert request.payment_method_id == "saved-card"
        assert request.payment_method_data is None
        assert request.confirmation is None
        assert not request.save_payment_method
    else:
        assert request.payment_method_id is None
        assert (request.payment_method_data.type if request.payment_method_data else None) == method
        assert request.confirmation.return_url == "https://shop.example/return"
        assert request.save_payment_method is (method != "sbp")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"payment_method_type": "invalid"},
        {"payment_method_type": "sbp", "bind_only": True},
        {"payment_method_type": "sbp", "capture": False},
    ],
)
def test_unsupported_method_operation_never_calls_provider(kwargs) -> None:
    service = _service()
    asyncio.run(service.create_payment(10, "RUB", "Order", {}, **kwargs))
    service._run_sdk_call.assert_not_awaited()


@pytest.mark.parametrize(
    "value,expected",
    [
        ("", ["other"]),
        (" SBP,bank_card,sbp,other ", ["sbp", "bank_card", "other"]),
        ("bank_card,sbp", ["bank_card", "sbp"]),
    ],
)
def test_checkout_configuration_order_and_legacy_default(value, expected) -> None:
    config = YooKassaConfig(_env_file=None, PAYMENT_METHODS=value)
    assert config.checkout_methods == expected
    with patch.object(
        registry,
        "_provider_configs",
        {
            "yookassa_service": ProviderConfigBundle(config=config, presentation=None),
        },
    ):
        assert SPEC.is_enabled(None)
        assert SBP_SPEC.is_enabled(None) == ("sbp" in expected)
        assert CARD_SPEC.is_enabled(None) == ("bank_card" in expected)
        order = order_checkout_methods(
            ["stars", "yookassa", "stripe", "yookassa_sbp", "yookassa_bank_card"]
        )
        if value:
            assert order == [
                "stars",
                *["yookassa" if method == "other" else f"yookassa_{method}" for method in expected],
                "stripe",
            ]


def test_invalid_checkout_configuration_is_rejected() -> None:
    with pytest.raises(ValidationError):
        YooKassaConfig(_env_file=None, PAYMENT_METHODS="sbp,unknown")


def test_live_override_normalization_and_admin_only_do_not_enable_unselected_methods() -> None:
    config = YooKassaConfig(_env_file=None, ENABLED=False, ADMIN_ONLY_ENABLED=True)
    config.PAYMENT_METHODS = " SBP,unknown,sbp "
    with patch.object(
        registry,
        "_provider_configs",
        {
            "yookassa_service": ProviderConfigBundle(config=config),
        },
    ):
        assert config.checkout_methods == ["sbp"]
        assert SBP_SPEC.is_effectively_enabled(None)
        assert not CARD_SPEC.is_effectively_enabled(None)
        assert order_checkout_methods(["yookassa", "stars"]) == ["yookassa_sbp", "stars"]


@pytest.mark.parametrize("method", ["sbp", "bank_card"])
def test_telegram_selection_keeps_sbp_out_of_saved_card_flow(method) -> None:
    callback = SimpleNamespace(
        data=f"pay_yk_{method}:1:10:subscription",
        from_user=SimpleNamespace(id=42),
        answer=AsyncMock(),
    )
    settings = SimpleNamespace(
        DEFAULT_LANGUAGE="en",
        yookassa_autopayments_active=True,
        traffic_sale_mode=False,
        YOOKASSA_AUTOPAYMENTS_REQUIRE_CARD_BINDING=True,
    )
    quote = SimpleNamespace(months=1, price=10, entitlement_context_snapshot=None)
    initiate = AsyncMock(return_value=True)
    saved = AsyncMock(return_value=[])
    with (
        patch.object(
            telegram_account.user_dal,
            "get_user_by_telegram_id",
            AsyncMock(return_value=SimpleNamespace(user_id=456)),
        ),
        patch.object(callback_payment, "callback_message_or_none", return_value=AsyncMock()),
        patch.object(
            callback_payment, "_yookassa_available_to_callback_user", AsyncMock(return_value=True)
        ) as available,
        patch.object(
            callback_payment, "_parse_offer_payload", return_value=(1, 10, "subscription")
        ),
        patch.object(
            callback_payment, "quote_hwid_callback_parts", AsyncMock(return_value=(quote, None))
        ),
        patch.object(
            callback_payment, "default_payment_currency_code_for_settings", return_value="RUB"
        ),
        patch.object(callback_payment, "default_currency_key_for_settings", return_value="RUB"),
        patch.object(callback_payment, "_initiate_yk_payment", initiate),
        patch.object(callback_payment.user_billing_dal, "list_user_payment_methods", saved),
    ):
        asyncio.run(
            callback_payment.pay_yk_callback_handler(
                callback,
                settings,
                {"i18n_instance": SimpleNamespace(gettext=lambda *args, **kwargs: args[1])},
                SimpleNamespace(configured=True, subscription_service=None),
                AsyncMock(),
            )
        )
    assert available.await_args is not None
    assert initiate.await_args is not None
    assert available.await_args.args[3] == method
    assert available.await_args.kwargs["user_id"] == 456
    assert initiate.await_args.kwargs["user_id"] == 456
    assert initiate.await_args.kwargs["payment_method_type"] == method
    assert initiate.await_args.kwargs["save_payment_method"] is (method == "bank_card")
    assert saved.await_count == (1 if method == "bank_card" else 0)


@pytest.mark.parametrize("method", ["yookassa", "yookassa_sbp", "yookassa_bank_card"])
@pytest.mark.parametrize(
    "sale_mode", ["subscription", "balance_topup", "topup", "extension|" + "a" * 32]
)
def test_webapp_passes_selected_method_without_changing_payment_provider(method, sale_mode) -> None:
    service = _service()
    service.create_payment = AsyncMock(
        return_value={"id": "p1", "confirmation_url": "https://pay.example/1"}
    )
    session = AsyncMock()
    ctx = WebAppPaymentContext(
        request=SimpleNamespace(app={"yookassa_service": service}),
        session=session,
        user_id=42,
        method=method,
        months=1,
        price=10,
        stars_price=None,
        description="Order",
        sale_mode=sale_mode,
    )
    create_record = AsyncMock(return_value=SimpleNamespace(payment_id=7))
    with (
        patch.object(payments, "create_webapp_payment_record", create_record),
        patch.object(payments.payment_dal, "update_payment_status_by_db_id", AsyncMock()),
    ):
        response = asyncio.run(payments.create_webapp_payment(ctx))
    assert response.status == 200
    assert create_record.await_args is not None
    assert create_record.await_args.kwargs["provider"] == "yookassa"
    args = service.create_payment.await_args.kwargs
    assert args["metadata"]["sale_mode"] == sale_mode
    assert args["metadata"]["payment_db_id"] == "7"
    assert args.get("payment_method_type") == {
        "yookassa_sbp": "sbp",
        "yookassa_bank_card": "bank_card",
    }.get(method)
    assert args["save_payment_method"] is False
    session.commit.assert_awaited_once()


def test_webapp_does_not_reuse_invoice_for_another_method() -> None:
    service = _service()
    service.get_payment_info = AsyncMock(
        return_value={
            "status": "pending",
            "paid": False,
            "confirmation_url": "https://pay.example/sbp",
            "metadata": {
                "user_id": "42",
                "payment_db_id": "7",
                "sale_mode": "subscription",
                "checkout_method": "sbp",
            },
        }
    )
    ctx = WebAppPaymentContext(
        request=SimpleNamespace(app={"yookassa_service": service}),
        session=AsyncMock(),
        user_id=42,
        method="yookassa_bank_card",
        months=1,
        price=10,
        stars_price=None,
        description="Order",
        sale_mode="subscription",
    )
    payment = SimpleNamespace(payment_id=7, yookassa_payment_id="p1")
    assert asyncio.run(payments.reuse_webapp_payment(ctx, payment)) is None
    ctx = replace(ctx, method="yookassa_sbp")
    assert asyncio.run(payments.reuse_webapp_payment(ctx, payment)) == "https://pay.example/sbp"
