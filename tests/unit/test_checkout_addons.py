from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from bot.app.web.webapp.billing_checkout_adjustments import _resolve_checkout_promo
from bot.app.web.webapp.billing_checkout_bundle import (
    CheckoutBundleError,
    CheckoutPricingContext,
    CheckoutPricingWindow,
    build_checkout_bundle,
    normalize_checkout_device_selection,
)
from bot.app.web.webapp.billing_quotes import BasePaymentQuote
from bot.app.web.webapp.payloads import WebAppPaymentCreatePayload
from bot.services.checkout_addons import checkout_addon_grants
from config.tariff_checkout import serialize_checkout_addons
from config.tariffs_config import TariffsConfig


def _checkout_config() -> TariffsConfig:
    return TariffsConfig.model_validate(
        {
            "default_tariff": "standard",
            "tariffs": [
                {
                    "key": "standard",
                    "billing_model": "period",
                    "monthly_gb": 100,
                    "premium_monthly_gb": 20,
                    "premium_squad_uuids": ["premium-squad"],
                    "hwid_device_limit": 5,
                    "enabled_periods": [1, 3],
                    "prices_rub": {"1": 100, "3": 300},
                    "prices_stars": {"1": 50, "3": 150},
                    "topup_packages": {
                        "rub": [{"gb": 50, "price": 40}],
                        "stars": [{"gb": 50, "price": 20}],
                    },
                    "flexible_traffic_limit": {
                        "step_gb": 50,
                        "max_total_gb": 150,
                        "price_per_step": 40,
                        "stars_price_per_step": 20,
                    },
                    "premium_topup_packages": {
                        "rub": [{"gb": 10, "price": 20}],
                        "stars": [{"gb": 10, "price": 10}],
                    },
                    "premium_flexible_traffic_limit": {
                        "step_gb": 10,
                        "max_total_gb": 30,
                        "price_per_step": 20,
                        "stars_price_per_step": 10,
                    },
                    "hwid_device_packages": {
                        "rub": [
                            {
                                "count": 2,
                                "price": 30,
                                "traffic_bonus_gb": 15,
                            }
                        ],
                        "stars": [
                            {
                                "count": 2,
                                "price": 15,
                                "traffic_bonus_gb": 15,
                            }
                        ],
                    },
                    "checkout_addons": {
                        "devices": {
                            "enabled": True,
                            "max_extra_devices": 2,
                            "price_per_device": 15,
                            "stars_price_per_device": 10,
                        },
                        "traffic": {"enabled": True},
                        "premium_traffic": {"enabled": True},
                    },
                }
            ],
        }
    )


def _settings(config: TariffsConfig) -> SimpleNamespace:
    return SimpleNamespace(
        tariffs_config=config,
        TARIFFS_CONFIG=config,
        DEFAULT_PAYMENT_CURRENCY="RUB",
        USER_HWID_DEVICE_LIMIT=5,
        MY_DEVICES_SECTION_ENABLED=True,
        PROMO_DURATION_MULTIPLIER_MAX=12,
        PROMO_TRAFFIC_MULTIPLIER_MAX=12,
        MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED=False,
    )


def _payload() -> WebAppPaymentCreatePayload:
    return WebAppPaymentCreatePayload.model_validate(
        {
            "method": "yookassa",
            "months": 1,
            "tariff_key": "standard",
            "sale_mode": "subscription",
            "checkout_addons": {
                "device_count": 2,
                "regular_limit_gb": 150,
                "premium_limit_gb": 30,
            },
        }
    )


class CheckoutAddonConfigTests(TestCase):
    def test_device_checkout_addon_takes_precedence_over_legacy_renewal(self) -> None:
        payload = _payload().model_copy(update={"renew_hwid_devices": True})

        normalized = normalize_checkout_device_selection(payload)

        self.assertTrue(payload.renew_hwid_devices)
        self.assertFalse(normalized.renew_hwid_devices)
        self.assertEqual(2, normalized.checkout_addons.device_count)

    def test_serializes_linear_device_marks_separately_from_topup_packages(self) -> None:
        config = _checkout_config()

        addons = serialize_checkout_addons(
            config.require("standard"),
            default_currency="rub",
            months=1,
            fallback_hwid_limit=5,
            devices_feature_enabled=True,
        )

        self.assertEqual(
            [5, 6, 7],
            [item["total_units"] for item in addons["devices"]["options"]],
        )
        self.assertEqual(
            [0.0, 15.0, 30.0],
            [item["monthly_price"] for item in addons["devices"]["options"]],
        )
        self.assertEqual(
            [100.0, 150.0],
            [item["total_units"] for item in addons["traffic"]["options"]],
        )
        self.assertEqual(
            [20.0, 30.0],
            [item["total_units"] for item in addons["premium_traffic"]["options"]],
        )

    def test_rejects_maximum_without_a_matching_package_mark(self) -> None:
        data = _checkout_config().model_dump(mode="json")
        data["tariffs"][0]["flexible_traffic_limit"]["max_total_gb"] = 175

        with self.assertRaisesRegex(ValueError, "valid flexible limit"):
            TariffsConfig.model_validate(data)

    def test_bundle_snapshot_restores_all_entitlement_grants(self) -> None:
        config = _checkout_config()
        quote, bundle = build_checkout_bundle(
            BasePaymentQuote(
                payment_units=1,
                price=100,
                stars_price=50,
                sale_mode="subscription@standard",
                traffic_gb_for_payment=None,
                default_currency_code="RUB",
            ),
            settings=_settings(config),
            payment_payload=_payload(),
            method="yookassa",
        )

        grants = checkout_addon_grants(bundle.snapshot)

        self.assertEqual(190, quote.price)
        self.assertEqual(90, bundle.addon_amount)
        self.assertEqual(2, grants.device_count)
        self.assertEqual(0, grants.device_traffic_bonus_gb)
        self.assertEqual(150, grants.regular_limit_gb)
        self.assertEqual(30, grants.premium_limit_gb)
        self.assertEqual(0, grants.legacy_regular_topup_gb)
        self.assertEqual(0, grants.legacy_premium_topup_gb)

    def test_flexible_limit_surcharge_is_charged_for_every_purchased_month(self) -> None:
        config = _checkout_config()
        payload = _payload().model_copy(update={"months": 3})
        quote, bundle = build_checkout_bundle(
            BasePaymentQuote(
                payment_units=3,
                price=300,
                stars_price=150,
                sale_mode="subscription@standard",
                traffic_gb_for_payment=None,
                default_currency_code="RUB",
            ),
            settings=_settings(config),
            payment_payload=payload,
            method="yookassa",
        )

        self.assertEqual(570, quote.price)
        self.assertEqual(270, bundle.addon_amount)

    def test_active_upgrade_adds_prorated_uplift_without_refunding_downgrades(self) -> None:
        config = _checkout_config()
        context = CheckoutPricingContext(
            active_subscription_id=7,
            active_tariff_key="standard",
            active_end_at=datetime.now(UTC) + timedelta(days=15),
            current_device_count=0,
            current_regular_limit_gb=100,
            current_premium_limit_gb=20,
        )
        upgraded, upgrade_bundle = build_checkout_bundle(
            BasePaymentQuote(
                payment_units=1,
                price=100,
                stars_price=50,
                sale_mode="subscription@standard",
                traffic_gb_for_payment=None,
                default_currency_code="RUB",
            ),
            settings=_settings(config),
            payment_payload=_payload(),
            method="yookassa",
            pricing_context=context,
        )
        self.assertGreater(upgraded.price, 234.9)
        self.assertLess(upgraded.price, 235.1)
        device_upgrade = next(item for item in upgrade_bundle.items if item["kind"] == "devices")
        self.assertTrue(device_upgrade["immediate_applies"])
        self.assertGreater(device_upgrade["immediate_amount"], 0)

        base_payload = WebAppPaymentCreatePayload.model_validate(
            {
                "method": "yookassa",
                "months": 1,
                "tariff_key": "standard",
                "sale_mode": "subscription",
                "checkout_addons": {
                    "device_count": 0,
                    "regular_limit_gb": 100,
                    "premium_limit_gb": 20,
                },
            }
        )
        downgraded, downgrade_bundle = build_checkout_bundle(
            BasePaymentQuote(
                payment_units=1,
                price=100,
                stars_price=50,
                sale_mode="subscription@standard",
                traffic_gb_for_payment=None,
                default_currency_code="RUB",
            ),
            settings=_settings(config),
            payment_payload=base_payload,
            method="yookassa",
            pricing_context=CheckoutPricingContext(
                active_subscription_id=7,
                active_tariff_key="standard",
                active_end_at=datetime.now(UTC) + timedelta(days=15),
                current_device_count=2,
                current_regular_limit_gb=150,
                current_premium_limit_gb=30,
            ),
        )
        self.assertEqual(100, downgraded.price)
        self.assertEqual(0, downgrade_bundle.addon_amount)
        self.assertEqual(
            ["traffic", "premium_traffic"],
            [item["kind"] for item in downgrade_bundle.items],
        )

    def test_trial_carryover_does_not_add_prorated_checkout_charges(self) -> None:
        config = _checkout_config()
        context = CheckoutPricingContext(
            active_subscription_id=7,
            active_tariff_key=None,
            active_end_at=datetime.now(UTC) + timedelta(days=15),
            complimentary_remaining_period=True,
        )

        quote, bundle = build_checkout_bundle(
            BasePaymentQuote(
                payment_units=1,
                price=100,
                stars_price=50,
                sale_mode="subscription@standard",
                traffic_gb_for_payment=None,
                default_currency_code="RUB",
            ),
            settings=_settings(config),
            payment_payload=_payload(),
            method="yookassa",
            pricing_context=context,
        )

        self.assertEqual(190, quote.price)
        self.assertEqual(90, bundle.addon_amount)
        grants = checkout_addon_grants(bundle.snapshot)
        self.assertTrue(grants.active_context_present)
        self.assertEqual(7, grants.active_subscription_id)
        self.assertEqual(context.active_end_at, grants.active_end_at)
        self.assertTrue(grants.regular_immediate_applies)
        self.assertTrue(grants.premium_immediate_applies)

    def test_plain_base_limits_do_not_create_an_addon_bundle(self) -> None:
        config = _checkout_config()
        payload = WebAppPaymentCreatePayload.model_validate(
            {
                "method": "yookassa",
                "months": 1,
                "tariff_key": "standard",
                "sale_mode": "subscription",
                "checkout_addons": {
                    "device_count": 0,
                    "regular_limit_gb": 100,
                    "premium_limit_gb": 20,
                },
            }
        )

        quote, bundle = build_checkout_bundle(
            BasePaymentQuote(
                payment_units=1,
                price=100,
                stars_price=50,
                sale_mode="subscription@standard",
                traffic_gb_for_payment=None,
                default_currency_code="RUB",
            ),
            settings=_settings(config),
            payment_payload=payload,
            method="yookassa",
        )

        self.assertEqual(100, quote.price)
        self.assertFalse(bundle.has_addons)
        self.assertIsNone(bundle.snapshot)

    def test_zero_device_selection_is_ignored_without_device_addons(self) -> None:
        data = _checkout_config().model_dump(mode="json")
        data["tariffs"][0]["checkout_addons"] = {}
        config = TariffsConfig.model_validate(data)
        payload = WebAppPaymentCreatePayload.model_validate(
            {
                "method": "yookassa",
                "months": 1,
                "tariff_key": "standard",
                "sale_mode": "subscription",
                "checkout_addons": {"device_count": 0},
            }
        )

        quote, bundle = build_checkout_bundle(
            BasePaymentQuote(
                payment_units=1,
                price=100,
                stars_price=50,
                sale_mode="subscription@standard",
                traffic_gb_for_payment=None,
                default_currency_code="RUB",
            ),
            settings=_settings(config),
            payment_payload=payload,
            method="yookassa",
        )

        self.assertEqual(100, quote.price)
        self.assertFalse(bundle.has_addons)
        self.assertIsNone(bundle.snapshot)

        positive_payload = WebAppPaymentCreatePayload.model_validate(
            {
                "method": "yookassa",
                "months": 1,
                "tariff_key": "standard",
                "sale_mode": "subscription",
                "checkout_addons": {"device_count": 1},
            }
        )
        with self.assertRaises(CheckoutBundleError) as raised:
            build_checkout_bundle(
                BasePaymentQuote(
                    payment_units=1,
                    price=100,
                    stars_price=50,
                    sale_mode="subscription@standard",
                    traffic_gb_for_payment=None,
                    default_currency_code="RUB",
                ),
                settings=_settings(config),
                payment_payload=positive_payload,
                method="yookassa",
            )
        self.assertEqual("checkout_addon_unavailable", raised.exception.code)

    def test_repeated_early_renewal_prices_each_existing_limit_window(self) -> None:
        config = _checkout_config()
        context = CheckoutPricingContext(
            active_subscription_id=7,
            active_tariff_key="standard",
            active_end_at=datetime.now(UTC) + timedelta(days=45),
            current_regular_limit_gb=150,
            current_regular_monthly_price=40,
            regular_windows=(
                CheckoutPricingWindow(
                    current_units=150,
                    month_fraction=0.5,
                    monthly_price=40,
                ),
                CheckoutPricingWindow(
                    current_units=100,
                    month_fraction=1.0,
                    monthly_price=0,
                ),
            ),
        )
        payload = WebAppPaymentCreatePayload.model_validate(
            {
                "method": "yookassa",
                "months": 1,
                "tariff_key": "standard",
                "sale_mode": "subscription",
                "checkout_addons": {"regular_limit_gb": 150},
            }
        )

        quote, bundle = build_checkout_bundle(
            BasePaymentQuote(
                payment_units=1,
                price=100,
                stars_price=50,
                sale_mode="subscription@standard",
                traffic_gb_for_payment=None,
                default_currency_code="RUB",
            ),
            settings=_settings(config),
            payment_payload=payload,
            method="yookassa",
            pricing_context=context,
        )
        grants = checkout_addon_grants(bundle.snapshot)

        self.assertEqual(180, quote.price)
        self.assertEqual(80, bundle.addon_amount)
        self.assertTrue(grants.regular_immediate_applies)


class CheckoutAddonPromoTests(IsolatedAsyncioTestCase):
    async def test_percentage_discount_applies_to_entire_fiat_cart(self) -> None:
        config = _checkout_config()
        quote, _bundle = build_checkout_bundle(
            BasePaymentQuote(
                payment_units=1,
                price=100,
                stars_price=50,
                sale_mode="subscription@standard",
                traffic_gb_for_payment=None,
                default_currency_code="RUB",
            ),
            settings=_settings(config),
            payment_payload=_payload(),
            method="yookassa",
        )
        promo = SimpleNamespace(
            promo_code_id=7,
            code="CART20",
            bonus_days=0,
            bonus_requires_payment=False,
            discount_percent=20,
            duration_multiplier=None,
            traffic_multiplier=None,
            regular_traffic_gb=None,
            premium_traffic_gb=None,
            applies_to="all",
            min_subscription_months=None,
            min_traffic_gb=None,
        )

        with (
            patch(
                "bot.services.checkout_promos.promo_code_dal.get_active_promo_code_by_code_str",
                AsyncMock(return_value=promo),
            ),
            patch(
                "bot.services.checkout_promos.evaluate_promo_redemption",
                AsyncMock(return_value=SimpleNamespace(allowed=True, reason_key=None)),
            ),
        ):
            result, error = await _resolve_checkout_promo(
                session=AsyncMock(),
                settings=_settings(config),
                user_id=42,
                code_input="CART20",
                sale_mode="subscription@standard",
                payment_units=1,
                traffic_gb=None,
                method="yookassa",
                base_amount=quote.price,
                base_stars=quote.stars_price,
            )

        self.assertIsNone(error)
        assert result is not None
        self.assertEqual(190, result.base_amount)
        self.assertEqual(152, result.effective_amount)
        self.assertEqual(38, result.discount_amount)

    async def test_percentage_discount_applies_to_entire_stars_cart(self) -> None:
        config = _checkout_config()
        quote, _bundle = build_checkout_bundle(
            BasePaymentQuote(
                payment_units=1,
                price=100,
                stars_price=50,
                sale_mode="subscription@standard",
                traffic_gb_for_payment=None,
                default_currency_code="RUB",
            ),
            settings=_settings(config),
            payment_payload=_payload(),
            method="stars",
        )
        promo = SimpleNamespace(
            promo_code_id=8,
            code="STARS20",
            bonus_days=0,
            bonus_requires_payment=False,
            discount_percent=20,
            duration_multiplier=None,
            traffic_multiplier=None,
            regular_traffic_gb=None,
            premium_traffic_gb=None,
            applies_to="all",
            min_subscription_months=None,
            min_traffic_gb=None,
        )

        with (
            patch(
                "bot.services.checkout_promos.promo_code_dal.get_active_promo_code_by_code_str",
                AsyncMock(return_value=promo),
            ),
            patch(
                "bot.services.checkout_promos.evaluate_promo_redemption",
                AsyncMock(return_value=SimpleNamespace(allowed=True, reason_key=None)),
            ),
        ):
            result, error = await _resolve_checkout_promo(
                session=AsyncMock(),
                settings=_settings(config),
                user_id=42,
                code_input="STARS20",
                sale_mode="subscription@standard",
                payment_units=1,
                traffic_gb=None,
                method="stars",
                base_amount=quote.price,
                base_stars=quote.stars_price,
            )

        self.assertIsNone(error)
        assert result is not None
        self.assertEqual(100, quote.stars_price)
        self.assertEqual(80, result.effective_stars)
