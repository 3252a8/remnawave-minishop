import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiohttp import web

from bot.app.web.webapp import billing_payments
from bot.app.web.webapp.billing_quotes import _resolve_checkout_pricing_context
from bot.app.web.webapp.payloads import WebAppPaymentCreatePayload
from bot.app.web.webapp.serializers_billing_options import _serialize_trial_payment_plan
from bot.app.web.webapp.serializers_checkout import attach_checkout_pricing_context_to_plans
from bot.payment_providers.shared.success import PaymentSuccessRequest, finalize_successful_payment
from tests.support.settings_stub import settings_stub


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
    async def test_paid_trial_checkout_uses_server_price_and_no_promo_inputs(self) -> None:
        payload = WebAppPaymentCreatePayload.model_validate(
            {
                "method": "yookassa",
                "months": 12,
                "sale_mode": "trial",
                "promo_code": "FREE100",
                "balance_source": "partner",
            }
        )
        settings = settings_stub(
            ADMIN_IDS=[],
            TRIAL_ENABLED=True,
            TRIAL_DURATION_DAYS=5,
            TRIAL_PAYMENT_ENABLED=True,
            TRIAL_PAYMENT_PRICE=149.0,
            TRIAL_PAYMENT_STARS_PRICE=75,
        )
        subscription_service = SimpleNamespace(
            has_trial_blocking_subscription=AsyncMock(return_value=False)
        )
        session = AsyncMock()

        class _SessionContext:
            async def __aenter__(self):
                return session

            async def __aexit__(self, *_args):
                return False

        create_payment = AsyncMock(return_value=web.json_response({"ok": True}))
        with (
            patch.object(billing_payments, "_require_user_id", return_value=42),
            patch.object(
                billing_payments,
                "_enforce_webapp_rate_limit",
                AsyncMock(return_value=None),
            ),
            patch.object(billing_payments, "_parse_model_payload", AsyncMock(return_value=payload)),
            patch.object(billing_payments, "get_settings", return_value=settings),
            patch.object(
                billing_payments,
                "get_subscription_service",
                return_value=subscription_service,
            ),
            patch.object(billing_payments, "_get_cached_webapp_settings", return_value={}),
            patch.object(billing_payments, "get_session_factory", return_value=_SessionContext),
            patch.object(
                billing_payments.user_dal,
                "get_user_by_id",
                AsyncMock(
                    return_value=SimpleNamespace(
                        is_banned=False,
                        language_code="en",
                        telegram_id=42,
                        email=None,
                    )
                ),
            ),
            patch.object(billing_payments, "_create_subscription_payment", create_payment),
        ):
            response = await billing_payments.create_payment_route(SimpleNamespace(app={}))

        self.assertEqual(response.status, 200)
        assert create_payment.await_args is not None
        kwargs = create_payment.await_args.kwargs
        self.assertEqual(kwargs["sale_mode"], "trial")
        self.assertEqual(kwargs["months"], 1)
        self.assertEqual(kwargs["price"], 149.0)
        self.assertEqual(kwargs["stars_price"], 75)
        self.assertNotIn("promo_code", kwargs)
        self.assertNotIn("balance_source", kwargs)

    def test_trial_payment_plan_hides_unpriced_stars(self) -> None:
        settings = settings_stub(
            PAYMENT_METHODS_ORDER="yookassa,stars",
            TRIAL_PAYMENT_ENABLED=True,
            TRIAL_PAYMENT_PRICE=149.0,
            TRIAL_PAYMENT_STARS_PRICE=0,
            TRIAL_DURATION_DAYS=5,
            TRIAL_TRAFFIC_LIMIT_GB=8,
        )
        settings.payment_methods_order = ["yookassa", "stars"]
        fiat_spec = SimpleNamespace(
            price_source="rub",
            is_usable_for_payment_context=lambda *_args: True,
            is_price_managed_externally=lambda *_args: False,
            is_checkout_addon_supported=lambda *_args: True,
        )
        stars_spec = SimpleNamespace(
            price_source="stars",
            is_usable_for_payment_context=lambda *_args: True,
            is_price_managed_externally=lambda *_args: False,
            is_checkout_addon_supported=lambda *_args: True,
        )

        with patch(
            "bot.payment_providers.get_provider_spec",
            side_effect=lambda method: stars_spec if method == "stars" else fiat_spec,
        ):
            plan = _serialize_trial_payment_plan(settings)

        assert plan is not None
        self.assertEqual(plan["duration_days"], 5)
        self.assertEqual(plan["traffic_gb"], 8)
        self.assertEqual(plan["available_payment_method_ids"], ["yookassa"])

    async def test_successful_trial_payment_activates_trial_atomically(self) -> None:
        end_date = datetime(2026, 1, 5, tzinfo=UTC)
        payment = SimpleNamespace(
            payment_id=17,
            user_id=42,
            status="pending",
            amount=149.0,
            currency="RUB",
            sale_mode="trial",
            provider="yookassa",
            subscription_duration_months=1,
            period_semantics=None,
            tariff_key=None,
            is_auto_renew=False,
        )
        session = AsyncMock()
        trial_activation = AsyncMock(
            return_value={
                "activated": True,
                "end_date": end_date,
                "days": 5,
                "traffic_gb": 8,
                "subscription_url": "https://panel.example/sub",
            }
        )
        subscription_service = SimpleNamespace(
            activate_trial_subscription=trial_activation,
            activate_subscription=AsyncMock(),
        )
        settings = SimpleNamespace(
            DEFAULT_LANGUAGE="en",
            SUBSCRIPTION_MINI_APP_URL="",
            TRIAL_DURATION_DAYS=5,
            partner_settings=None,
        )

        with (
            patch(
                "bot.payment_providers.shared.success.payment_dal.get_payment_by_db_id_for_update",
                AsyncMock(return_value=payment),
            ),
            patch(
                "bot.payment_providers.shared.success.user_dal.lock_user_by_id",
                AsyncMock(
                    return_value=SimpleNamespace(
                        user_id=42,
                        language_code="en",
                        referred_by_id=None,
                    )
                ),
            ),
            patch(
                "bot.payment_providers.shared.success._capture_fulfillment_snapshot",
                AsyncMock(return_value=None),
            ),
            patch(
                "bot.payment_providers.shared.success.payment_dal.update_payment_status_by_db_id",
                AsyncMock(),
            ) as update_status,
            patch(
                "bot.payment_providers.shared.success.auto_renew_dal.mark_cycle_succeeded_for_record",
                AsyncMock(),
            ),
            patch("bot.payment_providers.shared.success.events.emit_model", AsyncMock()) as emit,
            patch(
                "bot.payment_providers.shared.success.build_payment_succeeded_payload",
                return_value={},
            ),
            patch("bot.payment_providers.shared.success.PaymentSucceededPayload.model_validate"),
            patch(
                "bot.payment_providers.shared.success.prepare_config_links",
                AsyncMock(return_value=("link", "https://example.test/sub")),
            ),
            patch(
                "bot.payment_providers.shared.success.send_success_message_to_user",
                AsyncMock(),
            ),
        ):
            outcome = await finalize_successful_payment(
                PaymentSuccessRequest(
                    bot=SimpleNamespace(),
                    settings=settings,
                    i18n=SimpleNamespace(gettext=lambda _lang, key, **_kwargs: key),
                    session=session,
                    subscription_service=subscription_service,
                    referral_service=SimpleNamespace(),
                    payment=payment,
                    user_id=42,
                    amount=149,
                    currency="RUB",
                    sale_mode="trial",
                    months=1,
                    traffic_amount=None,
                    provider_subscription="yookassa",
                    provider_notification="yookassa",
                    skip_keyboard=True,
                )
            )

        self.assertIsNotNone(outcome)
        trial_activation.assert_awaited_once_with(
            session,
            42,
            commit=False,
            emit_event=False,
        )
        subscription_service.activate_subscription.assert_not_awaited()
        update_status.assert_awaited_once_with(session, 17, "succeeded")
        session.commit.assert_awaited_once()
        self.assertEqual(emit.await_count, 2)

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

    async def test_trial_can_checkout_any_tariff_with_complimentary_context(self) -> None:
        end_date = datetime(2026, 1, 5, tzinfo=UTC)
        trial_markers = (
            {"provider": "trial", "status_from_panel": "ACTIVE", "tariff_key": None},
            {"provider": "manual", "status_from_panel": "TRIAL", "tariff_key": "legacy"},
            {"provider": "trial", "status_from_panel": "TRIAL", "tariff_key": "standard"},
        )

        for markers in trial_markers:
            for tariff_key in ("standard", "premium"):
                with self.subTest(markers=markers, tariff_key=tariff_key):
                    context, error = await self._resolve(
                        SimpleNamespace(subscription_id=7, end_date=end_date, **markers),
                        f"subscription@{tariff_key}",
                    )

                    self.assertIsNone(error)
                    assert context is not None
                    self.assertEqual(context.active_subscription_id, 7)
                    self.assertEqual(context.active_end_at, end_date)
                    self.assertTrue(context.complimentary_remaining_period)

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

    async def test_trial_plan_payload_allows_all_tariffs_and_addons(self) -> None:
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

        self.assertEqual(plans[0]["checkout_addons"], {"devices": {"enabled": True}})
        self.assertNotIn("tariff_switch_required", plans[0])
        self.assertEqual(plans[1]["checkout_addons"], {"traffic": {"enabled": True}})
        self.assertNotIn("tariff_switch_required", plans[1])
