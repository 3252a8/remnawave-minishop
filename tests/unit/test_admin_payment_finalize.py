from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import pytest

from bot.app.web.admin_api_impl import payments
from bot.app.web.admin_api_impl.payment_schemas import AdminPaymentFinalizeBody


@pytest.mark.parametrize("confirmed", [False, True])
def test_manual_finalization_requires_and_forwards_context_confirmation(
    confirmed: bool,
) -> None:
    payment = SimpleNamespace(
        payment_id=77,
        user_id=42,
        amount=100,
        currency="RUB",
        sale_mode="subscription@basic",
        subscription_duration_months=1,
        provider="yookassa",
    )
    session = AsyncMock()
    factory = Mock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    state = {
        "can_manual_finalize": True,
        "manual_finalize_requires_promo_confirmation": False,
        "manual_finalize_requires_context_confirmation": True,
        "manual_finalize_warnings": ["active_subscription_end_changed"],
    }
    finalize = AsyncMock(return_value=SimpleNamespace())
    settings = SimpleNamespace(balance_settings=SimpleNamespace(enabled=True))
    with (
        patch.multiple(
            payments,
            _require_admin_user_id=Mock(return_value=9),
            parse_body_or_400=AsyncMock(
                return_value=AdminPaymentFinalizeBody(
                    reason="Verified unapplied purchase",
                    confirm_subscription_end_change=confirmed,
                )
            ),
            get_optional_subscription_service=Mock(return_value=SimpleNamespace()),
            get_referral_service=Mock(return_value=SimpleNamespace()),
            get_i18n=Mock(return_value=SimpleNamespace()),
            get_session_factory=Mock(return_value=factory),
            get_settings=Mock(return_value=settings),
            get_bot=Mock(return_value=None),
            payment_action_state=AsyncMock(return_value=state),
            finalize_successful_payment=finalize,
            _payment_detail_payload=AsyncMock(return_value={"payment_id": 77}),
        ),
        patch.object(
            payments.payment_dal, "get_payment_by_db_id_for_update", AsyncMock(return_value=payment)
        ),
        patch.object(payments.payment_dal, "get_payment_by_db_id", AsyncMock(return_value=payment)),
    ):
        response = asyncio.run(
            payments.admin_payment_finalize_route(
                cast(Any, SimpleNamespace(match_info={"payment_id": "77"}))
            )
        )
    if not confirmed:
        assert response.status == 409
        assert (
            json.loads(response.body)["error"] == "payment_subscription_end_confirmation_required"
        )
        finalize.assert_not_awaited()
        session.flush.assert_not_awaited()
    else:
        assert response.status == 200
        assert finalize.await_args is not None
        request = finalize.await_args.args[0]
        assert request.allow_subscription_end_change is True
        assert payment.fulfilled_by_admin_id == 9
        assert payment.fulfillment_note == "Verified unapplied purchase"
        session.flush.assert_awaited_once()
