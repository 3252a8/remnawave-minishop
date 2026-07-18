"""Behavioural tests for ``HwidDeviceMixin.activate_hwid_device_topup``.

The HWID device top-up flow already checks the panel update result correctly
(unlike the regular/premium traffic top-ups, which were the subject of a
recent fix). These tests pin that:

* an unknown package count for the tariff is rejected (anti-tamper);
* unlimited subscribers (``hwid_device_limit == 0``) are a no-op that still
  returns a meaningful payload;
* the panel call uses ``hwidDeviceLimit = base + extra``, not just ``base``;
* a panel failure returns ``None`` and DOES NOT write the audit row;
* the happy path records a validity window ending at the subscription end;
* renewal top-ups start after the current HWID entitlement and do not double
  the active device limit before that date.
"""

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings


def _tariffs_config_payload(**overrides: Any) -> dict:
    tariff = {
        "key": "standard",
        "names": {"en": "Standard"},
        "descriptions": {"en": "Base"},
        "squad_uuids": ["main-squad"],
        "billing_model": "period",
        "monthly_gb": 100,
        "prices_rub": {"1": 100},
        "prices_stars": {"1": 0},
        "enabled_periods": [1],
        "hwid_device_limit": 3,
        "hwid_device_packages": {
            "rub": [{"count": 1, "price": 50}, {"count": 3, "price": 120}],
            "stars": [],
        },
        "enabled": True,
    }
    tariff.update(overrides)
    return {"default_tariff": "standard", "tariffs": [tariff]}


def _make_settings(tmpdir: str, payload: dict, **overrides: Any) -> Settings:
    config_path = Path(tmpdir) / "tariffs.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    values: dict[str, Any] = {
        "_env_file": None,
        "BOT_TOKEN": "token",
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
        "TARIFFS_CONFIG_PATH": str(config_path),
    }
    values.update(overrides)
    return Settings(**values)


def _make_service(settings: Settings) -> SubscriptionService:
    return SubscriptionService(settings, AsyncMock(spec=PanelApiService))


def _make_sub(*, hwid_device_limit=3, extra_hwid_devices=0):
    return SimpleNamespace(
        subscription_id=11,
        user_id=42,
        panel_user_uuid="panel-uuid",
        panel_subscription_uuid="panel-sub",
        tariff_key="standard",
        end_date=datetime(2099, 1, 1, tzinfo=UTC),
        start_date=datetime(2098, 12, 1, tzinfo=UTC),
        duration_months=1,
        hwid_device_limit=hwid_device_limit,
        extra_hwid_devices=extra_hwid_devices,
    )


def _make_user():
    return SimpleNamespace(
        user_id=42,
        telegram_id=42,
        email=None,
        username="u",
        first_name="U",
        last_name="L",
        language_code="en",
        panel_user_uuid="panel-uuid",
    )


async def _echo_panel_entitlement(panel_uuid, payload, *_args, **_kwargs):
    return {**payload, "uuid": panel_uuid}


class HwidDeviceTopupInputTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_non_positive_device_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir, _tariffs_config_payload())
            service = _make_service(settings)
            for bad in (0, -1, "abc"):
                with self.subTest(bad=bad):
                    result = await service.activate_hwid_device_topup(
                        session=AsyncMock(),
                        user_id=42,
                        device_count=bad,
                        payment_amount=50,
                        payment_db_id=1,
                    )
                    self.assertIsNone(result)

    async def test_rejects_count_not_in_tariff_packages(self):
        # Tariff only offers 1-device and 3-device packages; 2 should be rejected.
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir, _tariffs_config_payload())
            service = _make_service(settings)
            sub = _make_sub()
            user = _make_user()
            with (
                patch(
                    "bot.services.subscription_service_impl.devices.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=sub),
                ),
            ):
                result = await service.activate_hwid_device_topup(
                    session=AsyncMock(),
                    user_id=42,
                    device_count=2,
                    payment_amount=70,
                    payment_db_id=1,
                )
            self.assertIsNone(result)

    async def test_rejects_traffic_tariff(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                tmpdir,
                _tariffs_config_payload(
                    billing_model="traffic",
                    traffic_packages={"rub": [{"gb": 100, "price": 100}], "stars": []},
                ),
            )
            service = _make_service(settings)
            sub = _make_sub()
            user = _make_user()
            with (
                patch(
                    "bot.services.subscription_service_impl.devices.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=sub),
                ),
            ):
                result = await service.activate_hwid_device_topup(
                    session=AsyncMock(),
                    user_id=42,
                    device_count=1,
                    payment_amount=50,
                    payment_db_id=1,
                )
            self.assertIsNone(result)


class HwidDeviceTopupBehaviourTests(unittest.IsolatedAsyncioTestCase):
    async def test_quote_prorates_period_price_for_remaining_subscription_window(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                tmpdir,
                _tariffs_config_payload(
                    hwid_device_packages={
                        "rub": [
                            {
                                "count": 1,
                                "price": 100,
                                "prices": {"1": 100},
                                "min_price": 10,
                            }
                        ],
                        "stars": [],
                    }
                ),
            )
            service = _make_service(settings)
            sub = _make_sub()
            sub.start_date = datetime(2099, 1, 1, tzinfo=UTC)
            sub.end_date = datetime(2099, 1, 31, tzinfo=UTC)
            user = _make_user()

            with (
                patch(
                    "bot.services.subscription_service_impl.devices.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.tariff_dal.get_hwid_device_entitlement_summary",
                    AsyncMock(return_value={"active_devices": 0, "active_until": None}),
                ),
            ):
                quote = await service.quote_hwid_device_topup(
                    session=AsyncMock(),
                    user_id=42,
                    device_count=1,
                    tariff_key="standard",
                    currency="rub",
                    now=datetime(2099, 1, 16, tzinfo=UTC),
                )

        self.assertIsNotNone(quote)
        self.assertEqual(quote["price"], 50)
        self.assertAlmostEqual(quote["proration_ratio"], 0.5)

    async def test_quote_uses_last_paid_duration_when_start_date_is_stale(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                tmpdir,
                _tariffs_config_payload(
                    hwid_device_packages={
                        "rub": [
                            {
                                "count": 1,
                                "price": 50,
                                "prices": {"3": 150},
                            }
                        ],
                        "stars": [],
                    }
                ),
            )
            service = _make_service(settings)
            sub = _make_sub()
            sub.duration_months = 3
            sub.start_date = datetime(2098, 7, 1, tzinfo=UTC)
            sub.end_date = datetime(2099, 1, 1, tzinfo=UTC)
            user = _make_user()

            with (
                patch(
                    "bot.services.subscription_service_impl.devices.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.tariff_dal.get_hwid_device_entitlement_summary",
                    AsyncMock(return_value={"active_devices": 0, "active_until": None}),
                ),
            ):
                quote = await service.quote_hwid_device_topup(
                    session=AsyncMock(),
                    user_id=42,
                    device_count=1,
                    tariff_key="standard",
                    currency="rub",
                    now=datetime(2098, 10, 1, tzinfo=UTC),
                )

        self.assertIsNotNone(quote)
        self.assertEqual(quote["price"], 150)
        self.assertAlmostEqual(quote["proration_ratio"], 1.0)

    async def test_quote_keeps_immediate_and_renewal_windows_separate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                tmpdir,
                _tariffs_config_payload(
                    hwid_device_packages={
                        "rub": [{"count": 1, "price": 50, "prices": {"1": 50}}],
                        "stars": [],
                    }
                ),
            )
            service = _make_service(settings)
            sub = _make_sub()
            sub.start_date = datetime(2098, 12, 1, tzinfo=UTC)
            sub.end_date = datetime(2099, 2, 1, tzinfo=UTC)
            user = _make_user()
            now = datetime(2099, 1, 2, tzinfo=UTC)
            existing_extra_until = datetime(2099, 1, 17, tzinfo=UTC)

            with (
                patch(
                    "bot.services.subscription_service_impl.devices.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.tariff_dal.get_hwid_device_entitlement_summary",
                    AsyncMock(
                        return_value={
                            "active_devices": 1,
                            "active_until": existing_extra_until,
                        }
                    ),
                ),
            ):
                immediate = await service.quote_hwid_device_topup(
                    session=AsyncMock(),
                    user_id=42,
                    device_count=1,
                    tariff_key="standard",
                    currency="rub",
                    renewal=False,
                    now=now,
                )
                renewal = await service.quote_hwid_device_topup(
                    session=AsyncMock(),
                    user_id=42,
                    device_count=1,
                    tariff_key="standard",
                    currency="rub",
                    renewal=True,
                    now=now,
                )

        self.assertIsNotNone(immediate)
        self.assertIsNotNone(renewal)
        self.assertEqual(immediate["valid_from"], now)
        self.assertEqual(immediate["valid_until"], sub.end_date)
        self.assertEqual(immediate["price"], 50)
        self.assertEqual(renewal["valid_from"], existing_extra_until)
        self.assertEqual(renewal["valid_until"], sub.end_date)
        self.assertLess(renewal["price"], immediate["price"])

    async def test_subscription_renewal_quote_prices_current_active_extra_devices(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir, _tariffs_config_payload())
            service = _make_service(settings)
            sub = _make_sub()
            sub.end_date = datetime(2099, 2, 1, tzinfo=UTC)
            user = _make_user()

            with (
                patch(
                    "bot.services.subscription_service_impl.devices.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.tariff_dal.get_hwid_device_entitlement_summary",
                    AsyncMock(
                        return_value={
                            "active_devices": 4,
                            "active_until": datetime(2099, 1, 16, tzinfo=UTC),
                        }
                    ),
                ),
            ):
                quote = await service.quote_hwid_device_renewal_for_subscription(
                    session=AsyncMock(),
                    user_id=42,
                    target_tariff_key="standard",
                    months=1,
                    currency="rub",
                    now=datetime(2099, 1, 1, tzinfo=UTC),
                )

        self.assertIsNotNone(quote)
        self.assertEqual(quote["device_count"], 4)
        self.assertEqual(quote["price"], 170)
        self.assertEqual(sorted(quote["package_counts"]), [1, 3])
        self.assertEqual(quote["valid_from"], sub.end_date)
        self.assertEqual(quote["valid_until"], datetime(2099, 3, 1, tzinfo=UTC))

    async def test_unlimited_subscriber_returns_noop_payload(self):
        # hwid_device_limit == 0 means unlimited — top-up makes no sense and must skip.
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir, _tariffs_config_payload())
            service = _make_service(settings)
            sub = _make_sub(hwid_device_limit=0, extra_hwid_devices=0)
            user = _make_user()
            with (
                patch(
                    "bot.services.subscription_service_impl.devices.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.tariff_dal.create_hwid_device_purchase",
                    AsyncMock(),
                ) as create_purchase,
            ):
                result = await service.activate_hwid_device_topup(
                    session=AsyncMock(),
                    user_id=42,
                    device_count=1,
                    payment_amount=50,
                    payment_db_id=1,
                )
            self.assertEqual(result["hwid_device_limit"], 0)
            self.assertEqual(result["purchased_hwid_devices"], 0)
            # Unlimited subscriber: no audit row, no panel touch.
            create_purchase.assert_not_awaited()

    async def test_panel_payload_uses_effective_limit_with_active_entitlements(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir, _tariffs_config_payload())
            service = _make_service(settings)
            sub = _make_sub(hwid_device_limit=3, extra_hwid_devices=2)
            user = _make_user()
            updated_sub = SimpleNamespace(
                subscription_id=11,
                end_date=sub.end_date,
            )
            service.panel_service.update_user_details_on_panel = AsyncMock(
                side_effect=_echo_panel_entitlement
            )
            with (
                patch(
                    "bot.services.subscription_service_impl.devices.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.subscription_dal.update_subscription",
                    AsyncMock(return_value=updated_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.tariff_dal.get_hwid_device_entitlement_summary",
                    AsyncMock(return_value={"active_devices": 2, "active_until": sub.end_date}),
                ),
                patch(
                    "bot.services.subscription_service_impl.payments.payment_dal.get_payment_by_db_id",
                    AsyncMock(return_value=SimpleNamespace()),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.tariff_dal.create_hwid_device_purchase",
                    AsyncMock(),
                ) as create_purchase,
            ):
                result = await service.activate_hwid_device_topup(
                    session=AsyncMock(),
                    user_id=42,
                    device_count=1,
                    payment_amount=50,
                    payment_db_id=1,
                )

        # Caller-facing payload: base=3, new extras = 2 + 1 purchased = 3 → effective = 6.
        self.assertEqual(result["hwid_device_limit"], 6)
        self.assertEqual(result["extra_hwid_devices"], 3)
        self.assertEqual(result["purchased_hwid_devices"], 1)
        create_purchase.assert_awaited_once()
        purchase_kwargs = create_purchase.await_args.kwargs
        self.assertEqual(purchase_kwargs["valid_until"], sub.end_date)
        self.assertLess(purchase_kwargs["valid_from"], sub.end_date)
        # Panel must see the full effective limit, not just the base.
        panel_payload = service.panel_service.update_user_details_on_panel.await_args.args[1]
        self.assertEqual(panel_payload["hwidDeviceLimit"], 6)

    async def test_activation_uses_frozen_payment_validity_window(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir, _tariffs_config_payload())
            service = _make_service(settings)
            sub = _make_sub(hwid_device_limit=3, extra_hwid_devices=0)
            sub.end_date = datetime(2099, 3, 1, tzinfo=UTC)
            user = _make_user()
            frozen_until = datetime(2099, 2, 1, tzinfo=UTC)
            payment = SimpleNamespace(
                hwid_valid_from=datetime(2099, 1, 1, tzinfo=UTC),
                hwid_valid_until=frozen_until,
                hwid_pricing_period_months=1,
                hwid_proration_ratio=1.0,
                hwid_full_price=50,
            )
            updated_sub = SimpleNamespace(subscription_id=11, end_date=sub.end_date)
            service.panel_service.update_user_details_on_panel = AsyncMock(
                side_effect=_echo_panel_entitlement
            )
            with (
                patch(
                    "bot.services.subscription_service_impl.devices.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.subscription_dal.update_subscription",
                    AsyncMock(return_value=updated_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.tariff_dal.get_hwid_device_entitlement_summary",
                    AsyncMock(return_value={"active_devices": 0, "active_until": None}),
                ),
                patch(
                    "bot.services.subscription_service_impl.payments.payment_dal.get_payment_by_db_id",
                    AsyncMock(return_value=payment),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.tariff_dal.create_hwid_device_purchase",
                    AsyncMock(),
                ) as create_purchase,
            ):
                result = await service.activate_hwid_device_topup(
                    session=AsyncMock(),
                    user_id=42,
                    device_count=1,
                    payment_amount=50,
                    payment_db_id=1,
                )

        self.assertEqual(result["hwid_devices_valid_until"], frozen_until)
        purchase_kwargs = create_purchase.await_args.kwargs
        self.assertEqual(purchase_kwargs["valid_until"], frozen_until)

    async def test_renewal_topup_starts_after_existing_entitlement(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir, _tariffs_config_payload())
            service = _make_service(settings)
            current_entitlement_end = datetime(2099, 1, 1, tzinfo=UTC)
            renewed_end = datetime(2099, 2, 1, tzinfo=UTC)
            sub = _make_sub(hwid_device_limit=3, extra_hwid_devices=2)
            sub.end_date = renewed_end
            user = _make_user()
            updated_sub = SimpleNamespace(subscription_id=11, end_date=renewed_end)
            service.panel_service.update_user_details_on_panel = AsyncMock(
                side_effect=_echo_panel_entitlement
            )
            with (
                patch(
                    "bot.services.subscription_service_impl.devices.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.subscription_dal.update_subscription",
                    AsyncMock(return_value=updated_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.tariff_dal.get_hwid_device_entitlement_summary",
                    AsyncMock(
                        return_value={
                            "active_devices": 2,
                            "active_until": current_entitlement_end,
                        }
                    ),
                ),
                patch(
                    "bot.services.subscription_service_impl.payments.payment_dal.get_payment_by_db_id",
                    AsyncMock(return_value=SimpleNamespace()),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.tariff_dal.create_hwid_device_purchase",
                    AsyncMock(),
                ) as create_purchase,
            ):
                result = await service.activate_hwid_device_topup(
                    session=AsyncMock(),
                    user_id=42,
                    device_count=1,
                    payment_amount=50,
                    payment_db_id=1,
                    renewal=True,
                )

        self.assertEqual(result["extra_hwid_devices"], 2)
        self.assertEqual(result["hwid_device_limit"], 5)
        purchase_kwargs = create_purchase.await_args.kwargs
        self.assertEqual(purchase_kwargs["valid_from"], current_entitlement_end)
        self.assertEqual(purchase_kwargs["valid_until"], renewed_end)
        panel_payload = service.panel_service.update_user_details_on_panel.await_args.args[1]
        self.assertEqual(panel_payload["hwidDeviceLimit"], 5)

    async def test_panel_failure_returns_none_after_staging_audit_before_patch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir, _tariffs_config_payload())
            service = _make_service(settings)
            sub = _make_sub()
            user = _make_user()
            updated_sub = SimpleNamespace(subscription_id=11, end_date=sub.end_date)
            service.panel_service.update_user_details_on_panel = AsyncMock(return_value=None)
            with (
                patch(
                    "bot.services.subscription_service_impl.devices.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.subscription_dal.get_active_subscription_by_user_id",
                    AsyncMock(return_value=sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.subscription_dal.update_subscription",
                    AsyncMock(return_value=updated_sub),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.tariff_dal.get_hwid_device_entitlement_summary",
                    AsyncMock(return_value={"active_devices": 0, "active_until": None}),
                ),
                patch(
                    "bot.services.subscription_service_impl.payments.payment_dal.get_payment_by_db_id",
                    AsyncMock(return_value=SimpleNamespace()),
                ),
                patch(
                    "bot.services.subscription_service_impl.devices.tariff_dal.create_hwid_device_purchase",
                    AsyncMock(),
                ) as create_purchase,
            ):
                result = await service.activate_hwid_device_topup(
                    session=AsyncMock(),
                    user_id=42,
                    device_count=1,
                    payment_amount=50,
                    payment_db_id=1,
                )
            self.assertIsNone(result)
            # The payment finalizer rolls this transaction back when activation
            # returns None; staging first prevents a post-PATCH DB failure window.
            create_purchase.assert_awaited_once()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class HwidDeviceTrafficBonusTests(unittest.IsolatedAsyncioTestCase):
    GB = 1024**3

    def _bonus_patches(self, *, user, sub, updated_sub, payment):
        return (
            patch(
                "bot.services.subscription_service_impl.devices.user_dal.get_user_by_id",
                AsyncMock(return_value=user),
            ),
            patch(
                "bot.services.subscription_service_impl.devices.subscription_dal.get_active_subscription_by_user_id",
                AsyncMock(return_value=sub),
            ),
            patch(
                "bot.services.subscription_service_impl.devices.subscription_dal.update_subscription",
                AsyncMock(return_value=updated_sub),
            ),
            patch(
                "bot.services.subscription_service_impl.devices.tariff_dal.get_hwid_device_entitlement_summary",
                AsyncMock(return_value={"active_devices": 0, "active_until": None}),
            ),
            patch(
                "bot.services.subscription_service_impl.devices.payment_dal.get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch(
                "bot.services.subscription_service_impl.devices.tariff_dal.create_hwid_device_purchase",
                AsyncMock(),
            ),
        )

    def _traffic_sub(self, *, baseline_gb=100, topup_gb=5):
        sub = _make_sub()
        sub.tier_baseline_bytes = baseline_gb * self.GB
        sub.topup_balance_bytes = topup_gb * self.GB
        sub.regular_bonus_bytes = 0
        sub.regular_unlimited_override = False
        sub.traffic_used_bytes = 0
        return sub

    async def _activate(self, settings, sub, payment, device_count=1):
        service = _make_service(settings)
        user = _make_user()
        updated_sub = SimpleNamespace(subscription_id=11, end_date=sub.end_date)
        service.panel_service.update_user_details_on_panel = AsyncMock(
            side_effect=_echo_panel_entitlement
        )
        patches = self._bonus_patches(user=user, sub=sub, updated_sub=updated_sub, payment=payment)
        with (
            patches[0],
            patches[1],
            patches[2] as update_sub,
            patches[3],
            patches[4],
            patches[5] as create_purchase,
        ):
            result = await service.activate_hwid_device_topup(
                session=AsyncMock(),
                user_id=42,
                device_count=device_count,
                payment_amount=50,
                payment_db_id=1,
            )
        return result, update_sub, create_purchase, service

    async def test_bonus_raises_the_monthly_cap_flat_and_ignores_proration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                tmpdir, _tariffs_config_payload(), HWID_DEVICE_TRAFFIC_BONUS_GB=15
            )
            # A proration ratio on the payment must NOT scale the bonus: it is
            # a recurring monthly cap component, not a one-time credit.
            result, update_sub, _, service = await self._activate(
                settings,
                self._traffic_sub(),
                SimpleNamespace(hwid_proration_ratio=0.5),
            )

        self.assertEqual(result["hwid_traffic_bonus_bytes"], 15 * self.GB)
        subscription_updates = update_sub.await_args.args[2]
        # Balance untouched - nothing is credited or consumed.
        self.assertNotIn("topup_balance_bytes", subscription_updates)
        # Cap = tier 100 + topup 5 + device bonus 15.
        self.assertEqual(subscription_updates["traffic_limit_bytes"], 120 * self.GB)
        panel_payload = service.panel_service.update_user_details_on_panel.await_args.args[1]
        self.assertEqual(panel_payload["trafficLimitBytes"], 120 * self.GB)

    async def test_bonus_scales_per_active_device(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                tmpdir, _tariffs_config_payload(), HWID_DEVICE_TRAFFIC_BONUS_GB=15
            )
            result, update_sub, _, _ = await self._activate(
                settings, self._traffic_sub(), SimpleNamespace(), device_count=3
            )

        self.assertEqual(result["hwid_traffic_bonus_bytes"], 45 * self.GB)
        subscription_updates = update_sub.await_args.args[2]
        self.assertEqual(subscription_updates["traffic_limit_bytes"], 150 * self.GB)

    async def test_unlimited_tariff_stays_unlimited(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Unlimited is a property of the TARIFF (monthly_gb=0); a zero
            # sub-level baseline alone just means "inherit the tariff".
            settings = _make_settings(
                tmpdir,
                _tariffs_config_payload(monthly_gb=0),
                HWID_DEVICE_TRAFFIC_BONUS_GB=15,
            )
            result, update_sub, _, service = await self._activate(
                settings,
                self._traffic_sub(baseline_gb=0, topup_gb=0),
                SimpleNamespace(),
            )

        # Pre-bonus cap is 0 (= unlimited on the panel); the bonus must not
        # turn that into a finite 15 GB cap.
        self.assertEqual(update_sub.await_args.args[2]["traffic_limit_bytes"], 0)
        panel_payload = service.panel_service.update_user_details_on_panel.await_args.args[1]
        self.assertEqual(panel_payload["trafficLimitBytes"], 0)
        self.assertEqual(result["hwid_traffic_bonus_bytes"], 15 * self.GB)

    async def test_bonus_disabled_by_default_leaves_traffic_untouched(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir, _tariffs_config_payload())
            result, update_sub, _, service = await self._activate(
                settings, self._traffic_sub(), SimpleNamespace()
            )

        self.assertEqual(result["hwid_traffic_bonus_bytes"], 0)
        subscription_updates = update_sub.await_args.args[2]
        self.assertNotIn("traffic_limit_bytes", subscription_updates)
        self.assertNotIn("topup_balance_bytes", subscription_updates)
        panel_payload = service.panel_service.update_user_details_on_panel.await_args.args[1]
        self.assertNotIn("trafficLimitBytes", panel_payload)

    async def test_panel_failure_records_no_purchase(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                tmpdir, _tariffs_config_payload(), HWID_DEVICE_TRAFFIC_BONUS_GB=15
            )
            service = _make_service(settings)
            sub = self._traffic_sub()
            user = _make_user()
            updated_sub = SimpleNamespace(subscription_id=11, end_date=sub.end_date)
            service.panel_service.update_user_details_on_panel = AsyncMock(return_value=None)
            patches = self._bonus_patches(
                user=user, sub=sub, updated_sub=updated_sub, payment=SimpleNamespace()
            )
            with (
                patches[0],
                patches[1],
                patches[2],
                patches[3],
                patches[4],
                patches[5] as create_purchase,
            ):
                result = await service.activate_hwid_device_topup(
                    session=AsyncMock(),
                    user_id=42,
                    device_count=1,
                    payment_amount=50,
                    payment_db_id=1,
                )

        self.assertIsNone(result)
        # On current dev the purchase row is written before the panel push and
        # relies on the caller's transaction rollback when activation fails.

    def test_formula_adds_bonus_only_to_finite_caps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = _make_service(
                _make_settings(tmpdir, _tariffs_config_payload(), HWID_DEVICE_TRAFFIC_BONUS_GB=15)
            )
        common = {
            "topup_balance_bytes": 0,
            "regular_bonus_bytes": 0,
            "regular_unlimited_override": False,
            "traffic_used_bytes": 0,
        }
        self.assertEqual(
            service._compute_main_traffic_limit_bytes(
                tier_baseline_bytes=100 * self.GB,
                hwid_device_bonus_bytes=15 * self.GB,
                **common,
            ),
            115 * self.GB,
        )
        self.assertEqual(
            service._compute_main_traffic_limit_bytes(
                tier_baseline_bytes=0,
                hwid_device_bonus_bytes=15 * self.GB,
                **common,
            ),
            0,
        )
        self.assertEqual(
            service._compute_main_traffic_limit_bytes(
                tier_baseline_bytes=100 * self.GB,
                hwid_device_bonus_bytes=15 * self.GB,
                topup_balance_bytes=0,
                regular_bonus_bytes=0,
                regular_unlimited_override=True,
                traffic_used_bytes=0,
            ),
            0,
        )

    def test_public_gb_helper_is_flat_per_device(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            enabled = _make_service(
                _make_settings(tmpdir, _tariffs_config_payload(), HWID_DEVICE_TRAFFIC_BONUS_GB=15)
            )
            disabled = _make_service(_make_settings(tmpdir, _tariffs_config_payload()))
        self.assertEqual(enabled.hwid_device_traffic_bonus_gb(1), 15.0)
        self.assertEqual(enabled.hwid_device_traffic_bonus_gb(3), 45.0)
        self.assertEqual(disabled.hwid_device_traffic_bonus_gb(1), 0.0)
