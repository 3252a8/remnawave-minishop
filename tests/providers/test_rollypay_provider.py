from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.payment_providers.rollypay import SPECS, RollyPayConfig, RollyPayService
from bot.payment_providers.rollypay.subscriptions import (
    interval_for_months,
    subscription_context_supported,
)
from bot.payment_providers.shared import CreatePaymentRequest


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
