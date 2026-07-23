"""Regression tests for provider-agnostic auto-renew wiring."""

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

from bot.handlers.user.subscription import core as subscription_core
from bot.payment_providers.shared import RecurringChargeResult
from bot.services.subscription_service_impl.renewal import RenewalMixin


class _FakeRecurringService:
    def __init__(
        self,
        *,
        configured: bool = True,
        recurring_active: bool = True,
        result: RecurringChargeResult | None = None,
    ) -> None:
        self.configured = configured
        self.recurring_active = recurring_active
        self.calls: list[object] = []
        self._result = result or RecurringChargeResult.ok(
            provider_payment_id="auto-pay-1",
            status="pending",
        )

    async def charge_saved_payment_method(self, context):
        self.calls.append(context)
        return self._result


class _FakePaymentMethod:
    def __init__(self, pm_id: str = "pm-42") -> None:
        self.provider_payment_method_id = pm_id


class _FakeSub(SimpleNamespace):
    pass


def _make_mixin(
    *,
    service: _FakeRecurringService | None,
    provider: str = "yookassa",
    price_for_months: float | None = 100.0,
):
    mixin = RenewalMixin()
    mixin.settings = SimpleNamespace(
        traffic_sale_mode=False,
        yookassa_autopayments_active=True,
        subscription_options={1: price_for_months} if price_for_months else {},
        DEFAULT_CURRENCY_SYMBOL="RUB",
        DEFAULT_LANGUAGE="en",
    )
    if service is not None:
        mixin.recurring_provider_services = {provider: service}  # type: ignore[attr-defined]
    return mixin


async def _stub_default_pm(session, user_id, provider="yookassa"):
    return _FakePaymentMethod(f"{provider}-pm-42")


async def _no_default_pm(session, user_id, provider="yookassa"):
    return None


class ChargeRenewalShortCircuitTests(unittest.IsolatedAsyncioTestCase):
    async def test_skips_when_traffic_sale_mode_enabled(self):
        mixin = _make_mixin(service=None)
        mixin.settings.traffic_sale_mode = True
        ok = await mixin.charge_subscription_renewal(session=None, sub=_FakeSub())
        self.assertTrue(ok)

    async def test_skips_when_auto_renew_disabled(self):
        mixin = _make_mixin(service=None)
        ok = await mixin.charge_subscription_renewal(
            session=None,
            sub=_FakeSub(auto_renew_enabled=False),
        )
        self.assertTrue(ok)

    async def test_skips_when_provider_recurring_is_disabled(self):
        service = _FakeRecurringService(configured=True, recurring_active=False)
        mixin = _make_mixin(service=service)
        ok = await mixin.charge_subscription_renewal(
            session=None,
            sub=_FakeSub(auto_renew_enabled=True, provider="yookassa"),
        )
        self.assertTrue(ok)
        self.assertEqual(service.calls, [])

    async def test_skips_for_non_recurring_provider(self):
        mixin = _make_mixin(service=None)
        emit_failure = AsyncMock()
        with patch(
            "bot.services.subscription_service_impl.renewal._emit_auto_renew_failure",
            emit_failure,
        ):
            ok = await mixin.charge_subscription_renewal(
                session=None,
                sub=_FakeSub(auto_renew_enabled=True, provider="freekassa"),
            )
        self.assertTrue(ok)
        # Unsupported providers are intentionally skipped. They must not turn
        # into a failure event that could target a broad recovery broadcast.
        emit_failure.assert_not_awaited()


class ChargeRenewalFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_false_when_no_saved_payment_method(self):
        service = _FakeRecurringService()
        mixin = _make_mixin(service=service)
        with patch(
            "db.dal.user_billing_dal.get_user_default_payment_method",
            _no_default_pm,
        ):
            ok = await mixin.charge_subscription_renewal(
                session=None,
                sub=_FakeSub(
                    auto_renew_enabled=True,
                    provider="yookassa",
                    user_id=1,
                    subscription_id=10,
                    duration_months=1,
                ),
            )
        self.assertFalse(ok)
        self.assertEqual(service.calls, [])

    async def test_returns_false_when_recurring_service_missing(self):
        mixin = _make_mixin(service=None)
        with patch(
            "db.dal.user_billing_dal.get_user_default_payment_method",
            _stub_default_pm,
        ):
            ok = await mixin.charge_subscription_renewal(
                session=None,
                sub=_FakeSub(
                    auto_renew_enabled=True,
                    provider="yookassa",
                    user_id=1,
                    subscription_id=10,
                    duration_months=1,
                ),
            )
        self.assertFalse(ok)

    async def test_returns_false_when_service_not_configured(self):
        mixin = _make_mixin(service=_FakeRecurringService(configured=False))
        with patch(
            "db.dal.user_billing_dal.get_user_default_payment_method",
            _stub_default_pm,
        ):
            ok = await mixin.charge_subscription_renewal(
                session=None,
                sub=_FakeSub(
                    auto_renew_enabled=True,
                    provider="yookassa",
                    user_id=1,
                    subscription_id=10,
                    duration_months=1,
                ),
            )
        self.assertFalse(ok)

    async def test_returns_false_when_legacy_price_for_months_missing(self):
        mixin = _make_mixin(service=_FakeRecurringService(), price_for_months=None)
        with patch(
            "db.dal.user_billing_dal.get_user_default_payment_method",
            _stub_default_pm,
        ):
            ok = await mixin.charge_subscription_renewal(
                session=None,
                sub=_FakeSub(
                    auto_renew_enabled=True,
                    provider="yookassa",
                    user_id=1,
                    subscription_id=10,
                    duration_months=1,
                ),
            )
        self.assertFalse(ok)

    async def test_returns_false_when_provider_charge_fails(self):
        service = _FakeRecurringService(result=RecurringChargeResult.failed("declined"))
        mixin = _make_mixin(service=service)
        emit_failure = AsyncMock()
        with (
            patch(
                "db.dal.user_billing_dal.get_user_default_payment_method",
                _stub_default_pm,
            ),
            patch(
                "bot.services.subscription_service_impl.renewal._emit_auto_renew_failure",
                emit_failure,
            ),
        ):
            ok = await mixin.charge_subscription_renewal(
                session=None,
                sub=_FakeSub(
                    auto_renew_enabled=True,
                    provider="yookassa",
                    user_id=1,
                    subscription_id=10,
                    duration_months=1,
                ),
            )
        self.assertFalse(ok)
        emit_failure.assert_awaited_once_with(
            sub=ANY,
            provider="yookassa",
            reason_code="provider_rejected",
            renewal_cycle_end=None,
            retryable=True,
            payment_db_id=None,
            provider_payment_id=None,
        )


class ChargeRenewalHappyPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_initiates_payment_with_saved_method(self):
        service = _FakeRecurringService(
            result=RecurringChargeResult.ok(provider_payment_id="auto-pay-7", status="pending")
        )
        mixin = _make_mixin(service=service, price_for_months=399.0)

        with patch(
            "db.dal.user_billing_dal.get_user_default_payment_method",
            _stub_default_pm,
        ):
            ok = await mixin.charge_subscription_renewal(
                session=None,
                sub=_FakeSub(
                    auto_renew_enabled=True,
                    provider="yookassa",
                    user_id=77,
                    subscription_id=555,
                    duration_months=1,
                ),
            )

        self.assertTrue(ok)
        self.assertEqual(len(service.calls), 1)
        context = service.calls[0]
        self.assertEqual(context.amount, 399.0)
        self.assertEqual(context.currency, "RUB")
        self.assertEqual(context.saved_method.provider_payment_method_id, "yookassa-pm-42")
        self.assertEqual(context.user_id, 77)
        self.assertEqual(context.subscription_id, 555)
        self.assertEqual(context.months, 1)
        self.assertEqual(context.description, "Subscription payment for 1 mo.")
        self.assertEqual(context.metadata["user_id"], "77")
        self.assertEqual(context.metadata["auto_renew_for_subscription_id"], "555")
        self.assertEqual(context.metadata["subscription_months"], "1")
        self.assertTrue(context.idempotence_key.startswith("yk-auto-"))
        self.assertLessEqual(len(context.idempotence_key), 64)

    async def test_panel_cycle_anchor_keeps_duplicate_renewal_key_stable(self):
        service = _FakeRecurringService()
        mixin = _make_mixin(service=service, price_for_months=399.0)
        old_cycle_end = datetime(2099, 2, 1, 12, 0, tzinfo=UTC)
        sub = _FakeSub(
            auto_renew_enabled=True,
            provider="yookassa",
            user_id=77,
            subscription_id=555,
            duration_months=1,
            end_date=old_cycle_end,
        )

        with patch(
            "db.dal.user_billing_dal.get_user_default_payment_method",
            _stub_default_pm,
        ):
            first = await mixin.charge_subscription_renewal(
                session=None,
                sub=sub,
                renewal_cycle_end=old_cycle_end,
            )
            # The payment webhook renews this same subscription row.  A late
            # copy of the old panel event must retain its original key even
            # when the panel omits the timestamp portion of expireAt.
            sub.end_date = datetime(2099, 3, 1, 12, 0, tzinfo=UTC)
            late_duplicate = await mixin.charge_subscription_renewal(
                session=None,
                sub=sub,
                renewal_cycle_end=datetime(2099, 2, 1, tzinfo=UTC),
            )
            next_cycle = await mixin.charge_subscription_renewal(
                session=None,
                sub=sub,
                renewal_cycle_end=sub.end_date,
            )

        self.assertTrue(first)
        self.assertTrue(late_duplicate)
        self.assertTrue(next_cycle)
        self.assertEqual(service.calls[0].idempotence_key, service.calls[1].idempotence_key)
        self.assertNotEqual(service.calls[1].idempotence_key, service.calls[2].idempotence_key)

    async def test_uses_subscription_provider_for_saved_method_lookup(self):
        service = _FakeRecurringService()
        mixin = _make_mixin(service=service, provider="cloudpayments", price_for_months=399.0)
        seen = {}

        async def _provider_pm(session, user_id, provider="yookassa"):
            seen["provider"] = provider
            return _FakePaymentMethod("cp-token")

        with patch(
            "db.dal.user_billing_dal.get_user_default_payment_method",
            _provider_pm,
        ):
            ok = await mixin.charge_subscription_renewal(
                session=None,
                sub=_FakeSub(
                    auto_renew_enabled=True,
                    provider="cloudpayments",
                    user_id=77,
                    subscription_id=555,
                    duration_months=1,
                ),
            )

        self.assertTrue(ok)
        self.assertEqual(seen["provider"], "cloudpayments")
        self.assertEqual(service.calls[0].saved_method.provider_payment_method_id, "cp-token")

    async def test_defaults_to_one_month_when_duration_missing(self):
        service = _FakeRecurringService()
        mixin = _make_mixin(service=service, price_for_months=99.0)

        with patch(
            "db.dal.user_billing_dal.get_user_default_payment_method",
            _stub_default_pm,
        ):
            ok = await mixin.charge_subscription_renewal(
                session=None,
                sub=_FakeSub(
                    auto_renew_enabled=True,
                    provider="yookassa",
                    user_id=1,
                    subscription_id=2,
                    duration_months=None,
                ),
            )

        self.assertTrue(ok)
        self.assertEqual(service.calls[0].metadata["subscription_months"], "1")
        self.assertEqual(service.calls[0].amount, 99.0)

    async def test_includes_hwid_device_renewal_in_saved_method_charge(self):
        service = _FakeRecurringService()
        mixin = _make_mixin(service=service, price_for_months=399.0)
        valid_from = datetime(2099, 2, 1, tzinfo=UTC)
        valid_until = datetime(2099, 3, 1, tzinfo=UTC)
        mixin.quote_hwid_device_renewal_for_subscription = AsyncMock(
            return_value={
                "device_count": 2,
                "price": 50.0,
                "full_price": 50.0,
                "valid_from": valid_from,
                "valid_until": valid_until,
                "pricing_period_months": 1,
                "proration_ratio": 1.0,
            }
        )

        with patch(
            "db.dal.user_billing_dal.get_user_default_payment_method",
            _stub_default_pm,
        ):
            ok = await mixin.charge_subscription_renewal(
                session=None,
                sub=_FakeSub(
                    auto_renew_enabled=True,
                    provider="yookassa",
                    user_id=77,
                    subscription_id=555,
                    tariff_key="standard",
                    duration_months=1,
                ),
            )

        self.assertTrue(ok)
        self.assertEqual(len(service.calls), 1)
        context = service.calls[0]
        self.assertEqual(context.amount, 449.0)
        self.assertEqual(context.sale_mode, "subscription@standard")
        self.assertEqual(context.hwid_quote["device_count"], 2)
        meta = context.metadata
        self.assertEqual(meta["sale_mode"], "subscription@standard")
        self.assertEqual(meta["hwid_devices"], "2")
        self.assertEqual(meta["hwid_valid_from"], valid_from.isoformat())
        self.assertEqual(meta["hwid_valid_until"], valid_until.isoformat())
        self.assertEqual(meta["hwid_pricing_period_months"], "1")
        self.assertEqual(meta["hwid_proration_ratio"], "1.0")
        self.assertEqual(meta["hwid_full_price"], "50.0")
        mixin.quote_hwid_device_renewal_for_subscription.assert_awaited_once_with(
            None,
            user_id=77,
            target_tariff_key="standard",
            months=1,
            currency="rub",
        )


class AutoRenewControlVisibilityTests(unittest.TestCase):
    def test_visible_for_enabled_yookassa_subscription_even_when_service_inactive(self):
        service = _FakeRecurringService(configured=True, recurring_active=False)
        subscription_service = SimpleNamespace(recurring_provider_services={"yookassa": service})
        sub = SimpleNamespace(provider="yookassa", auto_renew_enabled=True)

        self.assertTrue(subscription_core._auto_renew_control_visible(subscription_service, sub))

    def test_visible_for_yookassa_when_shared_recurring_service_is_active(self):
        service = _FakeRecurringService(configured=True, recurring_active=True)
        subscription_service = SimpleNamespace(recurring_provider_services={"yookassa": service})
        sub = SimpleNamespace(provider="yookassa", auto_renew_enabled=False)

        self.assertTrue(subscription_core._auto_renew_control_visible(subscription_service, sub))

    def test_hidden_for_non_recurring_provider(self):
        subscription_service = SimpleNamespace(recurring_provider_services={})
        sub = SimpleNamespace(provider="freekassa", auto_renew_enabled=True)

        self.assertFalse(subscription_core._auto_renew_control_visible(subscription_service, sub))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
