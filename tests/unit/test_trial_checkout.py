import json
from types import SimpleNamespace
from typing import Any
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.app.web.webapp.billing_quotes import _resolve_checkout_pricing_context
from bot.app.web.webapp.payloads import WebAppPaymentCreatePayload
from bot.app.web.webapp.serializers_checkout import attach_checkout_pricing_context_to_plans


def _payload() -> WebAppPaymentCreatePayload:
    return WebAppPaymentCreatePayload.model_validate(
        {
            "method": "yookassa",
            "months": 1,
            "tariff_key": "standard",
            "sale_mode": "subscription",
        }
    )


def _settings() -> SimpleNamespace:
    tariffs = {
        "standard": SimpleNamespace(key="standard"),
        "premium": SimpleNamespace(key="premium"),
    }
    return SimpleNamespace(
        tariffs_config=SimpleNamespace(
            default_tariff="standard",
            get=tariffs.get,
        )
    )


class TrialCheckoutTests(IsolatedAsyncioTestCase):
    async def _resolve(self, subscription: SimpleNamespace, sale_mode: str):
        with patch(
            "bot.app.web.webapp.billing_quotes.subscription_dal.get_active_subscription_by_user_id",
            AsyncMock(return_value=subscription),
        ):
            return await _resolve_checkout_pricing_context(
                session=AsyncMock(),
                user_id=42,
                db_user=SimpleNamespace(panel_user_uuid="panel-user"),
                payment_payload=_payload(),
                settings=_settings(),
                sale_mode=sale_mode,
            )

    async def test_trial_can_checkout_default_tariff_without_paid_renewal_context(self) -> None:
        trial_markers = (
            {"provider": "trial", "status_from_panel": "ACTIVE", "tariff_key": None},
            {"provider": "manual", "status_from_panel": "TRIAL", "tariff_key": "legacy"},
            {"provider": "trial", "status_from_panel": "TRIAL", "tariff_key": "standard"},
        )

        for markers in trial_markers:
            with self.subTest(markers=markers):
                context, error = await self._resolve(
                    SimpleNamespace(subscription_id=7, **markers),
                    "subscription@standard",
                )

                self.assertIsNone(context)
                self.assertIsNone(error)

    async def test_trial_cannot_renew_a_non_default_tariff(self) -> None:
        context, error = await self._resolve(
            SimpleNamespace(
                subscription_id=7,
                provider="trial",
                status_from_panel="TRIAL",
                tariff_key=None,
            ),
            "subscription@premium",
        )

        self.assertIsNone(context)
        assert error is not None
        self.assertEqual(error.status, 409)
        self.assertEqual(json.loads(error.text)["error"], "tariff_switch_required")

    async def test_paid_subscription_keeps_cross_tariff_renewal_guard(self) -> None:
        context, error = await self._resolve(
            SimpleNamespace(
                subscription_id=7,
                provider="yookassa",
                status_from_panel="ACTIVE",
                tariff_key="premium",
            ),
            "subscription@standard",
        )

        self.assertIsNone(context)
        assert error is not None
        self.assertEqual(error.status, 409)
        self.assertEqual(json.loads(error.text)["error"], "tariff_switch_required")

    async def test_trial_plan_payload_allows_only_default_without_addons(self) -> None:
        plans: list[dict[str, Any]] = [
            {
                "sale_mode": "subscription",
                "tariff_key": "standard",
                "checkout_addons": {"devices": {"enabled": True}},
                "tariff_switch_required": True,
            },
            {
                "sale_mode": "subscription",
                "tariff_key": "premium",
                "checkout_addons": {"traffic": {"enabled": True}},
            },
        ]

        await attach_checkout_pricing_context_to_plans(
            AsyncMock(),
            _settings(),
            local_sub=SimpleNamespace(
                provider="trial",
                status_from_panel="TRIAL",
            ),
            plans=plans,
        )

        self.assertEqual(plans[0]["checkout_addons"], {})
        self.assertNotIn("tariff_switch_required", plans[0])
        self.assertEqual(plans[1]["checkout_addons"], {})
        self.assertTrue(plans[1]["tariff_switch_required"])
