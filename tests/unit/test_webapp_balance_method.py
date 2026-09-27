import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.app.web.webapp import billing_payments
from bot.services.user_balance_service import UserBalanceAllocation


@pytest.mark.parametrize("source", ["user", "partner"])
@pytest.mark.parametrize("applied_minor", [70000, 20000])
def test_balance_only_checkout_requires_full_server_quote(source, applied_minor):
    asyncio.run(_balance_only_checkout(source, applied_minor))


async def _balance_only_checkout(source, applied_minor):
    settings = SimpleNamespace(
        DEFAULT_CURRENCY_SYMBOL="RUB", MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED=False
    )
    allocation = UserBalanceAllocation(
        user_id=42,
        currency="RUB",
        currency_scale=2,
        checkout_total_minor=70000,
        applied_minor=applied_minor,
    )
    completed = billing_payments.web.json_response({"ok": True, "action": "completed"})
    with (
        patch.object(billing_payments, "get_settings", return_value=settings),
        patch.object(billing_payments, "get_i18n", return_value=None),
        patch.object(
            billing_payments.subscription_dal,
            "get_active_subscription_by_user_id",
            AsyncMock(return_value=None),
        ),
        patch.object(
            billing_payments, "allocate_checkout_balance", AsyncMock(return_value=allocation)
        ) as allocate,
        patch.object(
            billing_payments,
            "create_fully_balance_funded_payment",
            AsyncMock(return_value=completed),
        ) as finalize,
        patch("bot.payment_providers.get_provider_spec") as external_provider,
    ):
        response = await billing_payments._create_subscription_payment(
            request=SimpleNamespace(app={}),
            session=AsyncMock(),
            user_id=42,
            method="balance",
            months=3,
            price=700,
            stars_price=None,
            lang="en",
            currency="RUB",
            sale_mode="subscription@standard",
            balance_source=source,
            entitlement_context_snapshot="snapshot",
        )
    external_provider.assert_not_called()
    assert allocate.await_args.kwargs["balance_source"] == source
    if applied_minor == 70000:
        assert response is completed
        assert finalize.await_args.kwargs["payment_context"].price == 0
    else:
        assert response.status == 409
        assert json.loads(response.text)["error"] == "balance_insufficient"
        finalize.assert_not_awaited()
