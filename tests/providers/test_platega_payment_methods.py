"""Platega one-off payment-method variants and hosted chooser contract."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.payment_providers.platega import service as platega_service


def _service(**config_overrides: object) -> platega_service.PlategaService:
    service = object.__new__(platega_service.PlategaService)
    service.config = platega_service.PlategaConfig(
        ENABLED=True,
        MERCHANT_ID="merchant",
        SECRET="secret",
        **config_overrides,
    )
    service.settings = SimpleNamespace(
        DEFAULT_CURRENCY_SYMBOL="RUB",
        PAYMENT_REQUEST_TIMEOUT_SECONDS=20,
    )
    service._default_return_url = "shopbot"
    return service


def _capture_create_request(monkeypatch, service: platega_service.PlategaService) -> dict:
    captured: dict = {}

    async def _fake_post(session, url, *, body, headers, log_prefix, **kwargs):
        captured.update(url=url, body=body, headers=headers, log_prefix=log_prefix)
        return True, {
            "transactionId": "tx-1",
            "url": "https://pay.platega.io/?id=tx-1",
        }

    monkeypatch.setattr(platega_service, "post_json_request", _fake_post)
    monkeypatch.setattr(
        platega_service.PlategaService,
        "_get_session",
        AsyncMock(return_value=SimpleNamespace()),
    )
    return captured


def test_new_payment_buttons_are_opt_in_with_documented_international_method() -> None:
    config = platega_service.PlategaConfig(
        ENABLED=True,
        MERCHANT_ID="merchant",
        SECRET="secret",
    )

    assert config.INTERNATIONAL_ENABLED is False
    assert config.ALL_METHODS_ENABLED is False
    assert config.CARD_ENABLED is False
    assert config.CARD_METHOD == 11
    assert config.INTERNATIONAL_METHOD == 12
    assert platega_service.CARD_SPEC.enabled(config) is False
    assert platega_service.INTERNATIONAL_SPEC.enabled(config) is False
    assert platega_service.ALL_METHODS_SPEC.enabled(config) is False


def test_international_payment_uses_method_12_on_legacy_endpoint(monkeypatch) -> None:
    service = _service(INTERNATIONAL_ENABLED=True)
    captured = _capture_create_request(monkeypatch, service)

    success, _data = asyncio.run(
        service.create_transaction(
            amount=150.0,
            currency="RUB",
            description="International card",
            payment_method=service.international_method,
        )
    )

    assert success is True
    assert captured["url"].endswith("/transaction/process")
    assert captured["body"]["paymentMethod"] == 12


def test_card_payment_uses_method_11_on_legacy_endpoint(monkeypatch) -> None:
    service = _service(CARD_ENABLED=True)
    captured = _capture_create_request(monkeypatch, service)

    success, _data = asyncio.run(
        service.create_transaction(
            amount=150.0,
            currency="RUB",
            description="Card payment",
            payment_method=service.card_method,
        )
    )

    assert success is True
    assert captured["url"].endswith("/transaction/process")
    assert captured["body"]["paymentMethod"] == 11


def test_hosted_chooser_uses_v2_endpoint_without_payment_method(monkeypatch) -> None:
    service = _service(ALL_METHODS_ENABLED=True)
    captured = _capture_create_request(monkeypatch, service)

    success, data = asyncio.run(
        service.create_transaction(
            amount=150.0,
            currency="RUB",
            description="Choose payment method",
            payload=json.dumps({"payment_db_id": 17}),
            metadata={"userId": "42", "userName": "42"},
            allow_method_selection=True,
        )
    )

    assert success is True
    assert data["transactionId"] == "tx-1"
    assert captured["url"].endswith("/v2/transaction/process")
    assert "paymentMethod" not in captured["body"]
    assert captured["body"]["paymentDetails"] == {"amount": 150.0, "currency": "RUB"}
    assert captured["body"]["metadata"] == {"userId": "42", "userName": "42"}


def test_create_payment_includes_antifraud_payer_metadata(monkeypatch) -> None:
    service = _service(SBP_ENABLED=True)
    create_transaction = AsyncMock(
        return_value=(True, {"transactionId": "tx-1", "redirect": "https://pay.platega.io/t/1"})
    )
    monkeypatch.setattr(service, "create_transaction", create_transaction)
    request = SimpleNamespace(
        payment=SimpleNamespace(payment_id=17),
        user_id=42,
        amount=150.0,
        currency="RUB",
        description="Subscription",
        months=1,
        sale_mode="subscription",
        provider_context={"platega_variant": "sbp"},
    )

    asyncio.run(platega_service._create_payment(service, request))

    create_call = create_transaction.await_args
    assert create_call is not None
    assert create_call.kwargs["metadata"] == {
        "userId": "42",
        "userName": "42",
    }


def test_variant_routing_keeps_callbacks_and_webapp_reuse_isolated() -> None:
    card = platega_service._platega_descriptor_for_callback_prefix("pay_platega_card")
    international = platega_service._platega_descriptor_for_callback_prefix(
        "pay_platega_international"
    )
    all_methods = platega_service._platega_descriptor_for_callback_prefix("pay_platega_all_methods")

    assert card.spec is platega_service.CARD_SPEC
    assert international.spec is platega_service.INTERNATIONAL_SPEC
    assert all_methods.spec is platega_service.ALL_METHODS_SPEC
    assert platega_service._DESCRIPTORS_BY_METHOD["platega_card"] is card
    assert platega_service._DESCRIPTORS_BY_METHOD["platega_international"] is international
    assert platega_service._DESCRIPTORS_BY_METHOD["platega_all_methods"] is all_methods


def test_pending_v2_transaction_accepts_transaction_id_response_shape(monkeypatch) -> None:
    service = _service(ALL_METHODS_ENABLED=True)
    monkeypatch.setattr(
        service,
        "get_transaction",
        AsyncMock(
            return_value=(
                True,
                {
                    "transactionId": "tx-1",
                    "status": "PENDING",
                    "payload": json.dumps(
                        {
                            "payment_db_id": 17,
                            "user_id": 42,
                            "sale_mode": "subscription",
                            "platega_variant": "all_methods",
                        }
                    ),
                },
            )
        ),
    )
    payment = SimpleNamespace(
        payment_id=17,
        provider_payment_id="tx-1",
        provider_payment_url="https://pay.platega.io/?id=tx-1",
    )

    payment_url = asyncio.run(
        service.try_reuse_pending_transaction(
            payment,
            user_id=42,
            sale_mode="subscription",
            variant="all_methods",
        )
    )

    assert payment_url == "https://pay.platega.io/?id=tx-1"
