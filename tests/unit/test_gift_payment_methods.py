import asyncio
import json
from collections.abc import Callable, Coroutine
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web

from bot.app.web.webapp import billing_checkout_quote, billing_payments
from bot.app.web.webapp.payloads import (
    WebAppPaymentCreatePayload,
    WebAppSubscriptionQuotePayload,
)
from bot.payment_providers import iter_provider_specs
from bot.services.subscription_gifts import gift_payment_method_available

GIFT_PAYMENT_METHODS = (
    ("freekassa", True),
    ("platega_sbp", True),
    ("platega_card", True),
    ("platega_crypto", True),
    ("platega_international", True),
    ("platega_all_methods", True),
    ("platega_subscription", False),
    ("rollypay", True),
    ("rollypay_sbp", True),
    ("rollypay_card", True),
    ("rollypay_international", True),
    ("rollypay_crypto", True),
    ("rollypay_subscription", False),
    ("severpay", True),
    ("wata", True),
    ("wata_crypto", True),
    ("yookassa", True),
    ("stars", True),
    ("cryptopay", True),
    ("heleket", True),
    ("paykilla", True),
    ("lava", True),
    ("pally", True),
    ("cloudpayments", True),
    ("overpay", True),
    ("oxapay", True),
    ("stripe", True),
    ("tribute", False),
    ("qa", True),
)
PLATEGA_ONE_OFF_METHODS = (
    "platega",
    "platega_sbp",
    "platega_card",
    "platega_crypto",
    "platega_international",
    "platega_all_methods",
)


class _SessionContext:
    async def __aenter__(self) -> AsyncMock:
        return AsyncMock()

    async def __aexit__(self, *_args: object) -> None:
        return None


def _error_code(response: web.Response) -> str:
    assert response.text is not None
    return str(json.loads(response.text)["error"])


def test_gift_payment_matrix_covers_every_registered_method() -> None:
    assert {method for method, _available in GIFT_PAYMENT_METHODS} == {
        spec.id for spec in iter_provider_specs()
    }


@pytest.mark.parametrize(("method", "available"), GIFT_PAYMENT_METHODS)
def test_gift_payment_availability_is_method_specific(method: str, available: bool) -> None:
    assert gift_payment_method_available(method) is available


@pytest.mark.parametrize("method", PLATEGA_ONE_OFF_METHODS)
def test_gift_quote_accepts_platega_one_off_methods(method: str) -> None:
    payload = WebAppSubscriptionQuotePayload.model_validate(
        {"method": method, "months": 1, "gift": True}
    )
    settings = SimpleNamespace(GIFTS_ENABLED=True)

    with (
        patch.object(billing_checkout_quote, "_require_user_id", return_value=42),
        patch.object(
            billing_checkout_quote,
            "_parse_model_payload",
            AsyncMock(return_value=payload),
        ),
        patch.object(billing_checkout_quote, "get_settings", return_value=settings),
        patch.object(
            billing_checkout_quote,
            "get_subscription_service",
            return_value=SimpleNamespace(),
        ),
        patch.object(
            billing_checkout_quote,
            "get_session_factory",
            return_value=lambda: _SessionContext(),
        ),
        patch.object(
            billing_checkout_quote.user_dal,
            "get_user_by_id",
            AsyncMock(return_value=None),
        ),
    ):
        response = asyncio.run(billing_checkout_quote.subscription_quote_route(SimpleNamespace()))

    assert response.status == 403
    assert _error_code(response) == "access_denied"


@pytest.mark.parametrize("method", PLATEGA_ONE_OFF_METHODS)
def test_gift_payment_accepts_platega_one_off_methods(method: str) -> None:
    payload = WebAppPaymentCreatePayload.model_validate(
        {"method": method, "months": 1, "gift": True}
    )
    settings = SimpleNamespace(
        GIFTS_ENABLED=True,
        DEFAULT_CURRENCY_SYMBOL="RUB",
        tariffs_config=None,
        traffic_sale_mode=False,
    )

    with (
        patch.object(billing_payments, "_require_user_id", return_value=42),
        patch.object(
            billing_payments,
            "_enforce_webapp_rate_limit",
            AsyncMock(return_value=None),
        ),
        patch.object(
            billing_payments,
            "_parse_model_payload",
            AsyncMock(return_value=payload),
        ),
        patch.object(billing_payments, "get_settings", return_value=settings),
        patch.object(
            billing_payments,
            "get_subscription_service",
            return_value=SimpleNamespace(),
        ),
        patch.object(
            billing_payments,
            "_get_cached_webapp_settings",
            return_value={"subscription_options": {}, "stars_subscription_options": {}},
        ),
    ):
        response = asyncio.run(billing_payments.create_payment_route(SimpleNamespace()))

    assert response.status == 400
    assert _error_code(response) == "invalid_plan"


@pytest.mark.parametrize(
    ("route", "payload_type"),
    (
        (billing_checkout_quote.subscription_quote_route, WebAppSubscriptionQuotePayload),
        (billing_payments.create_payment_route, WebAppPaymentCreatePayload),
    ),
)
def test_gift_routes_reject_provider_managed_subscription_method(
    route: Callable[[Any], Coroutine[Any, Any, web.Response]],
    payload_type: type[WebAppPaymentCreatePayload],
) -> None:
    payload = payload_type.model_validate(
        {"method": "platega_subscription", "months": 1, "gift": True}
    )
    settings = SimpleNamespace(
        GIFTS_ENABLED=True,
        DEFAULT_CURRENCY_SYMBOL="RUB",
        tariffs_config=None,
        traffic_sale_mode=False,
    )
    module = (
        billing_checkout_quote
        if route is billing_checkout_quote.subscription_quote_route
        else billing_payments
    )

    patches = [
        patch.object(module, "_require_user_id", return_value=42),
        patch.object(module, "_parse_model_payload", AsyncMock(return_value=payload)),
        patch.object(module, "get_settings", return_value=settings),
    ]
    if module is billing_payments:
        patches.extend(
            (
                patch.object(
                    module,
                    "_enforce_webapp_rate_limit",
                    AsyncMock(return_value=None),
                ),
                patch.object(
                    module,
                    "get_subscription_service",
                    return_value=SimpleNamespace(),
                ),
                patch.object(
                    module,
                    "_get_cached_webapp_settings",
                    return_value={
                        "subscription_options": {},
                        "stars_subscription_options": {},
                    },
                ),
            )
        )
    for current in patches:
        current.start()
    try:
        response: web.Response = asyncio.run(route(SimpleNamespace()))
    finally:
        for current in reversed(patches):
            current.stop()

    assert response.status == 400
    assert _error_code(response) == "gift_purchase_unavailable"
