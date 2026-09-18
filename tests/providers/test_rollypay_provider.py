from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram import types

from bot.payment_providers.base import WebAppPaymentContext
from bot.payment_providers.rollypay import SPECS, RollyPayConfig, RollyPayService
from bot.payment_providers.rollypay import service as rollypay_service
from bot.payment_providers.rollypay.subscriptions import (
    interval_for_months,
    subscription_context_supported,
)
from bot.payment_providers.shared import CreatePaymentRequest
from config.subscription_periods import with_period_days


@pytest.mark.parametrize("spec", SPECS, ids=lambda spec: spec.id)
@pytest.mark.parametrize("promo", ["", "|p12"])
def test_imported_tariff_checkout_callbacks_fit_telegram_limit(spec, promo: str) -> None:
    sale_mode = with_period_days("subscription@imported_tariff_12345", 90) + "|bot" + promo
    data = spec.callback_data(value="3", rub_price=1500.0, stars_price=None, sale_mode=sale_mode)

    assert data is not None
    assert data.startswith("pay_")  # Preserve the shared payment cooldown classification.
    assert len(data.encode("utf-8")) <= 64
    assert data.split(":", 3)[1:] == ["3", "1500.0", sale_mode]


@pytest.mark.parametrize(
    ("index", "legacy_prefix"),
    list(
        enumerate(
            (
                "pay_rollypay_all",
                "pay_rollypay_sbp",
                "pay_rollypay_card",
                "pay_rollypay_intl",
                "pay_rollypay_crypto",
                "pay_rollypay_sub",
            )
        )
    ),
)
def test_compact_and_existing_buttons_route_to_same_method(index, legacy_prefix) -> None:
    async def scenario() -> None:
        spec = SPECS[index]
        for prefix in (legacy_prefix, spec.callback_prefix):
            callback = types.CallbackQuery(
                id="test",
                from_user=types.User(id=42, is_bot=False, first_name="Test"),
                chat_instance="test",
                data=f"{prefix}:3:1500.0:subscription@basic|d90|bot",
            )
            handled, _ = await rollypay_service.router.callback_query.handlers[0].check(callback)
            assert handled
            run = AsyncMock()
            with patch.object(rollypay_service, "run_callback_payment", run):
                await rollypay_service.pay_rollypay_callback_handler(
                    callback, AsyncMock(), {}, _service(), AsyncMock()
                )
            run.assert_awaited_once()
            assert run.await_args is not None
            assert run.await_args.args[0].spec is spec
            assert run.await_args.args[1] is callback

    asyncio.run(scenario())


def _service(**config_overrides: object) -> RollyPayService:
    config = RollyPayConfig(
        ENABLED=True,
        API_KEY="api-key",
        SIGNING_SECRET="signing-secret",
        TERMINAL_ID="terminal-id",
        **config_overrides,
    )
    return RollyPayService(
        bot=SimpleNamespace(),
        settings=SimpleNamespace(
            PAYMENT_REQUEST_TIMEOUT_SECONDS=10,
            ADMIN_IDS=[42],
            DEFAULT_LANGUAGE="en",
        ),
        config=config,
        i18n=SimpleNamespace(),
        async_session_factory=SimpleNamespace(),
        subscription_service=SimpleNamespace(),
        referral_service=SimpleNamespace(),
        default_return_url="https://t.me/example_bot",
    )


def test_specs_cover_all_documented_checkout_methods_and_provider_managed_recurring() -> None:
    assert [spec.id for spec in SPECS] == [
        "rollypay",
        "rollypay_sbp",
        "rollypay_card",
        "rollypay_international",
        "rollypay_crypto",
        "rollypay_subscription",
    ]
    assert SPECS[-1].manages_recurring is True
    assert SPECS[-1].supports_recurring is False
    assert SPECS[-1].supported_currencies == ("RUB",)
    assert SPECS[-1].enabled(RollyPayConfig(ENABLED=True, SUBSCRIPTION_ENABLED=True)) is False
    assert (
        SPECS[-1].enabled(
            RollyPayConfig(
                ENABLED=True,
                SUBSCRIPTION_ENABLED=True,
                TERMINAL_ID="terminal-id",
            )
        )
        is True
    )
    assert _service(SUBSCRIPTION_ENABLED=False).manages_recurrence is True


def test_subscription_periods_match_rollypay_plans_and_exclude_sandbox() -> None:
    assert interval_for_months(1) == "month"
    assert interval_for_months(3) == "quarter"
    assert interval_for_months(12) == "year"
    assert interval_for_months(6) is None
    assert subscription_context_supported(RollyPayConfig(), 1, "subscription") is True
    assert (
        subscription_context_supported(RollyPayConfig(TEST_MODE=True), 1, "subscription") is False
    )
    assert subscription_context_supported(RollyPayConfig(), 1, "traffic") is False


@pytest.mark.parametrize(
    "variant",
    ["all_methods", "sbp", "card", "international", "crypto", "subscription"],
)
def test_webapp_context_variants_allow_missing_traffic(variant: str) -> None:
    ctx = WebAppPaymentContext(
        request=SimpleNamespace(),
        session=SimpleNamespace(),
        user_id=42,
        method="rollypay",
        months=1,
        price=100.0,
        stars_price=None,
        description="One month",
        sale_mode="subscription",
    )

    context = rollypay_service._webapp_context_for_variant(variant)(ctx)

    assert context == {
        "rollypay_variant": variant,
        "source": "webapp",
        "traffic_gb": None,
        "hwid_device_count": None,
    }


def test_webhook_signature_binds_timestamp_and_raw_body(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service()
    now = 1_800_000_000
    monkeypatch.setattr(time, "time", lambda: now)
    raw = b'{"event":"payment.paid","data":{"payment_id":"pay-1"}}'
    timestamp = str(now)
    signature = hmac.new(
        b"signing-secret",
        timestamp.encode("ascii") + b"." + raw,
        hashlib.sha256,
    ).hexdigest()

    assert service.verify_webhook(raw, timestamp, signature) is True
    assert service.verify_webhook(raw + b" ", timestamp, signature) is False
    assert service.verify_webhook(raw, str(now - 301), signature) is False


@pytest.mark.parametrize(
    ("variant", "currency", "expected_method"),
    [
        ("all_methods", "RUB", None),
        ("sbp", "RUB", "sbp"),
        ("card", "RUB", "card"),
        ("international", "EUR", "intl_card"),
        ("crypto", "RUB", "crypto"),
    ],
)
def test_one_off_variants_use_expected_remote_method(
    variant: str,
    currency: str,
    expected_method: str | None,
) -> None:
    async def scenario() -> None:
        service = _service(TEST_MODE=True)
        api_request = AsyncMock(return_value=(True, {"payment_id": "pay-1"}))
        request = CreatePaymentRequest(
            payment=SimpleNamespace(payment_id=17, tariff_key="basic"),
            user_id=42,
            amount=12.5,
            currency=currency,
            description="One month",
            months=1,
            sale_mode="subscription",
            provider_context={"rollypay_variant": variant},
        )

        with patch.object(service, "api_request", api_request):
            success, _data = await service.create_payment(request, variant=variant)

        assert success is True
        assert api_request.await_args is not None
        payload = api_request.await_args.kwargs["json_body"]
        assert payload["metadata"]["rollypay_variant"] == variant
        if expected_method is None:
            assert "payment_method" not in payload
        else:
            assert payload["payment_method"] == expected_method

    asyncio.run(scenario())


def test_subscription_variant_uses_recurring_payment_flow() -> None:
    async def scenario() -> None:
        service = _service(SUBSCRIPTION_ENABLED=True)
        request = CreatePaymentRequest(
            payment=SimpleNamespace(payment_id=17, tariff_key="basic"),
            user_id=42,
            amount=12.5,
            currency="RUB",
            description="One month",
            months=1,
            sale_mode="subscription",
            provider_context={"rollypay_variant": "subscription"},
        )

        with patch.object(
            service,
            "create_rollypay_subscription",
            AsyncMock(return_value=(True, {"subscription_id": "sub-1"})),
        ) as create_subscription:
            success, data = await service.create_payment(request, variant="subscription")

        assert success is True
        assert data == {"subscription_id": "sub-1"}
        create_subscription.assert_awaited_once_with(request)

    asyncio.run(scenario())


def test_international_payment_uses_documented_method_and_correlation() -> None:
    async def scenario() -> None:
        service = _service(TEST_MODE=True)
        api_request = AsyncMock(return_value=(True, {"payment_id": "pay-1"}))
        payment = SimpleNamespace(payment_id=17, tariff_key="basic")
        request = CreatePaymentRequest(
            payment=payment,
            user_id=42,
            amount=12.5,
            currency="EUR",
            description="Three months",
            months=3,
            sale_mode="subscription",
            provider_context={"rollypay_variant": "international"},
        )

        with patch.object(service, "api_request", api_request):
            success, _data = await service.create_payment(request, variant="international")

        assert success is True
        assert api_request.await_args is not None
        kwargs = api_request.await_args.kwargs
        assert kwargs["json_body"] == {
            "amount": "12.50",
            "payment_currency": "EUR",
            "order_id": "minishop-17",
            "description": "Three months",
            "customer_id": "42",
            "metadata": {
                "payment_db_id": 17,
                "user_id": 42,
                "sale_mode": "subscription",
                "rollypay_variant": "international",
            },
            "test": True,
            "payment_method": "intl_card",
            "terminal_id": "terminal-id",
            "success_redirect_url": "https://t.me/example_bot",
            "redirect_url": "https://t.me/example_bot",
            "fail_redirect_url": "https://t.me/example_bot",
        }

    asyncio.run(scenario())


def test_plan_selection_enforces_interval_cap_and_latest_version() -> None:
    async def scenario() -> None:
        service = _service(SUBSCRIPTION_ENABLED=True)
        api_request = AsyncMock(
            return_value=(
                True,
                {
                    "data": [
                        {
                            "id": "old",
                            "interval": "quarter",
                            "version": 1,
                            "cap_amount_rub": "9000",
                        },
                        {
                            "id": "current",
                            "interval": "quarter",
                            "version": 2,
                            "cap_amount_rub": "9000",
                        },
                        {
                            "id": "month",
                            "interval": "month",
                            "version": 99,
                            "cap_amount_rub": "4000",
                        },
                    ]
                },
            )
        )

        with patch.object(service, "api_request", api_request):
            selected = await service.choose_subscription_plan(months=3, amount=8999)
            cached = await service.choose_subscription_plan(months=3, amount=8999)

        assert selected and selected["id"] == "current"
        assert cached and cached["id"] == "current"
        api_request.assert_awaited_once()

    asyncio.run(scenario())
