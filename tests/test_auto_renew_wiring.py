"""Regression tests for the auto-renew code path in ``RenewalMixin``.

Prior to the fix, ``charge_subscription_renewal`` did::

    try:
        from .yookassa_service import YooKassaService  # local import to avoid cycles
        yk: YooKassaService = self.yookassa_service
    except Exception:
        yk = None

There is no ``yookassa_service`` module inside ``subscription_service_impl``
(the real implementation lives in ``bot.payment_providers.yookassa``), so the import
always raised ``ModuleNotFoundError``, ``yk`` became ``None``, and every
auto-renew silently logged ``YooKassa unavailable for auto-renew`` and
returned False — even though ``build_core_services`` had wired a real
``yookassa_service`` onto the subscription service via ``setattr``.

These tests pin the working contract end-to-end so the regression cannot
return.
"""

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, patch

from bot.services.subscription_service_impl.renewal import RenewalMixin


class _FakeYooKassaService:
    """Stand-in for the real ``YooKassaService``."""

    def __init__(self, configured: bool = True, response: Optional[Dict[str, Any]] = None) -> None:
        self.configured = configured
        self.calls: List[Dict[str, Any]] = []
        self._response = response if response is not None else {"id": "pay-1", "status": "pending"}

    async def create_payment(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakePaymentMethod:
    def __init__(self, pm_id: str = "pm-42") -> None:
        self.provider_payment_method_id = pm_id


class _FakeSub(SimpleNamespace):
    pass


def _make_mixin(*, yk: Optional[_FakeYooKassaService], price_for_months: Optional[float] = 100.0):
    mixin = RenewalMixin()
    mixin.settings = SimpleNamespace(
        traffic_sale_mode=False,
        yookassa_autopayments_active=True,
        subscription_options={1: price_for_months} if price_for_months else {},
    )
    if yk is not None:
        mixin.yookassa_service = yk  # type: ignore[attr-defined]
    return mixin


async def _stub_default_pm(session, user_id):
    return _FakePaymentMethod()


async def _no_default_pm(session, user_id):
    return None


class ChargeRenewalShortCircuitTests(unittest.IsolatedAsyncioTestCase):
    """Negative paths that should return *without* hitting YooKassa."""

    async def test_skips_when_traffic_sale_mode_enabled(self):
        mixin = _make_mixin(yk=None)
        mixin.settings.traffic_sale_mode = True
        ok = await mixin.charge_subscription_renewal(session=None, sub=_FakeSub())
        self.assertTrue(ok)

    async def test_skips_when_auto_renew_disabled(self):
        mixin = _make_mixin(yk=None)
        ok = await mixin.charge_subscription_renewal(
            session=None,
            sub=_FakeSub(auto_renew_enabled=False),
        )
        self.assertTrue(ok)

    async def test_skips_when_autopayments_globally_disabled(self):
        mixin = _make_mixin(yk=None)
        mixin.settings.yookassa_autopayments_active = False
        ok = await mixin.charge_subscription_renewal(
            session=None,
            sub=_FakeSub(auto_renew_enabled=True, provider="yookassa"),
        )
        self.assertTrue(ok)

    async def test_skips_for_non_yookassa_provider(self):
        mixin = _make_mixin(yk=None)
        ok = await mixin.charge_subscription_renewal(
            session=None,
            sub=_FakeSub(auto_renew_enabled=True, provider="freekassa"),
        )
        self.assertTrue(ok)


class ChargeRenewalFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_false_when_no_saved_payment_method(self):
        mixin = _make_mixin(yk=_FakeYooKassaService())
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

    async def test_returns_false_when_yookassa_service_missing(self):
        # Reproduces the historic bug: build_core_services did not attach
        # ``yookassa_service`` for some reason → auto-renew must report False.
        mixin = _make_mixin(yk=None)
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

    async def test_returns_false_when_yookassa_not_configured(self):
        mixin = _make_mixin(yk=_FakeYooKassaService(configured=False))
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
        mixin = _make_mixin(yk=_FakeYooKassaService(), price_for_months=None)
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

    async def test_returns_false_when_yookassa_response_unrecognized_status(self):
        yk = _FakeYooKassaService(response={"id": "p", "status": "failed"})
        mixin = _make_mixin(yk=yk)
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


class ChargeRenewalHappyPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_initiates_payment_with_saved_method(self):
        yk = _FakeYooKassaService(response={"id": "auto-pay-7", "status": "pending"})
        mixin = _make_mixin(yk=yk, price_for_months=399.0)

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
        self.assertEqual(len(yk.calls), 1)
        call = yk.calls[0]
        self.assertEqual(call["amount"], 399.0)
        self.assertEqual(call["currency"], "RUB")
        self.assertEqual(call["payment_method_id"], "pm-42")
        self.assertEqual(call["save_payment_method"], False)
        self.assertEqual(call["capture"], True)
        meta = call["metadata"]
        self.assertEqual(meta["user_id"], "77")
        self.assertEqual(meta["auto_renew_for_subscription_id"], "555")
        self.assertEqual(meta["subscription_months"], "1")

    async def test_accepts_waiting_for_capture_status(self):
        yk = _FakeYooKassaService(response={"id": "p", "status": "waiting_for_capture"})
        mixin = _make_mixin(yk=yk)

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
                    duration_months=1,
                ),
            )

        self.assertTrue(ok)

    async def test_defaults_to_one_month_when_duration_missing(self):
        yk = _FakeYooKassaService()
        mixin = _make_mixin(yk=yk, price_for_months=99.0)

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
        self.assertEqual(yk.calls[0]["metadata"]["subscription_months"], "1")
        self.assertEqual(yk.calls[0]["amount"], 99.0)

    async def test_includes_hwid_device_renewal_in_saved_method_charge(self):
        yk = _FakeYooKassaService(response={"id": "auto-pay-8", "status": "pending"})
        mixin = _make_mixin(yk=yk, price_for_months=399.0)
        valid_from = datetime(2099, 2, 1, tzinfo=timezone.utc)
        valid_until = datetime(2099, 3, 1, tzinfo=timezone.utc)
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
        self.assertEqual(len(yk.calls), 1)
        call = yk.calls[0]
        self.assertEqual(call["amount"], 449.0)
        meta = call["metadata"]
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
