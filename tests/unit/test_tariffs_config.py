import json
import unittest
from copy import deepcopy

from config.tariffs_config import TariffsConfig, load_tariffs_config, normalize_currency_key


def _valid_config():
    return {
        "default_tariff": "standard",
        "topup_packages_default": {
            "rub": [{"gb": 10, "price": 99}],
            "stars": [{"gb": 10, "price": 2500}],
        },
        "tariffs": [
            {
                "key": "standard",
                "names": {"ru": "Стандарт", "en": "Standard"},
                "descriptions": {"ru": "Base"},
                "squad_uuids": ["uuid-1"],
                "billing_model": "period",
                "monthly_gb": 500,
                "prices_rub": {"1": 150},
                "prices_stars": {"1": 0},
                "enabled_periods": [1],
                "enabled": True,
            },
            {
                "key": "traffic",
                "names": {"ru": "Гигабайты"},
                "descriptions": {},
                "squad_uuids": ["uuid-1"],
                "billing_model": "traffic",
                "traffic_packages": {"rub": [{"gb": 10, "price": 199}], "stars": []},
                "enabled": True,
            },
        ],
    }


class TariffsConfigTests(unittest.TestCase):
    def test_valid_tariffs_config_loads(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tariffs.json"
            path.write_text(json.dumps(_valid_config()), encoding="utf-8")

            config = load_tariffs_config(path)

            self.assertIsNotNone(config)
            self.assertEqual(config.default.key, "standard")
            self.assertEqual(config.require("traffic").rub_per_gb_for_conversion(), 19.9)

    def test_tariffs_config_with_utf8_bom_loads(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tariffs.json"
            path.write_text(json.dumps(_valid_config()), encoding="utf-8-sig")

            config = load_tariffs_config(path)

            self.assertIsNotNone(config)
            self.assertEqual(config.default.key, "standard")

    def test_period_tariff_without_topup_packages_has_no_topup(self):
        config = TariffsConfig.model_validate(_valid_config())

        self.assertIsNone(config.topup_packages_for(config.require("standard")))

    def test_period_tariff_traffic_strategy_is_optional_for_legacy_configs(self):
        config = TariffsConfig.model_validate(_valid_config())

        self.assertIsNone(config.require("standard").traffic_limit_strategy)
        self.assertIsNone(config.require("standard").premium_traffic_limit_strategy)
        self.assertIsNone(config.require("traffic").premium_traffic_limit_strategy)

    def test_period_tariff_traffic_strategy_loads(self):
        data = _valid_config()
        data["tariffs"][0]["traffic_limit_strategy"] = "WEEK"

        config = TariffsConfig.model_validate(data)

        self.assertEqual(config.require("standard").traffic_limit_strategy, "WEEK")

    def test_invalid_period_tariff_traffic_strategy_rejected(self):
        data = _valid_config()
        data["tariffs"][0]["traffic_limit_strategy"] = "YEAR"

        with self.assertRaises(ValueError):
            TariffsConfig.model_validate(data)

    def test_traffic_tariff_rejects_reset_strategy(self):
        data = _valid_config()
        data["tariffs"][1]["traffic_limit_strategy"] = "WEEK"

        with self.assertRaises(ValueError):
            TariffsConfig.model_validate(data)

    def test_premium_traffic_strategy_loads_for_period_and_traffic_tariffs(self):
        data = _valid_config()
        data["tariffs"][0]["premium_traffic_limit_strategy"] = "WEEK"
        data["tariffs"][1]["premium_traffic_limit_strategy"] = "MONTH"

        config = TariffsConfig.model_validate(data)

        self.assertEqual(config.require("standard").premium_traffic_limit_strategy, "WEEK")
        self.assertEqual(config.require("traffic").premium_traffic_limit_strategy, "MONTH")

    def test_invalid_premium_traffic_strategy_rejected(self):
        data = _valid_config()
        data["tariffs"][0]["premium_traffic_limit_strategy"] = "YEAR"

        with self.assertRaises(ValueError):
            TariffsConfig.model_validate(data)

    def test_period_tariff_uses_only_own_topup_packages(self):
        data = _valid_config()
        data["tariffs"][0]["topup_packages"] = {
            "rub": [{"gb": 25, "price": 199}],
            "stars": [],
        }
        config = TariffsConfig.model_validate(data)

        packages = config.topup_packages_for(config.require("standard"))

        self.assertIsNotNone(packages)
        self.assertEqual(packages.rub[0].gb, 25)

    def test_period_tariff_referral_bonuses_load(self):
        data = _valid_config()
        data["tariffs"][0]["referral_bonus_days_inviter"] = {"2": 5, "4": 10}
        data["tariffs"][0]["referral_bonus_days_referee"] = {"2": 1, "4": 2}
        data["tariffs"][0]["prices_rub"] = {"2": 400, "4": 800}
        data["tariffs"][0]["prices_stars"] = {}
        data["tariffs"][0]["enabled_periods"] = [2, 4]

        config = TariffsConfig.model_validate(data)
        tariff = config.require("standard")

        self.assertEqual(tariff.referral_inviter_bonus_days(2), 5)
        self.assertEqual(tariff.referral_referee_bonus_days(4), 2)
        self.assertIsNone(tariff.referral_inviter_bonus_days(8))

    def test_tribute_config_normalizes_periods_and_resolves_target(self):
        data = _valid_config()
        data["tariffs"][0]["prices_rub"] = {"1": 150, "3": 400}
        data["tariffs"][0]["enabled_periods"] = [1, 3]
        data["tariffs"][0]["tribute"] = {
            "link": " https://t.me/tribute/app?startapp=subscription ",
            "subscription_id": 101,
            "period_ids": {"01": 1001, "3.0": 1003},
        }

        config = TariffsConfig.model_validate(data)
        tariff = config.require("standard")

        self.assertIsNotNone(tariff.tribute)
        self.assertEqual(tariff.tribute.link, "https://t.me/tribute/app?startapp=subscription")
        self.assertEqual(tariff.tribute.period_ids, {"1": 1001, "3": 1003})
        self.assertEqual(tariff.tribute.period_id_for_months(3), 1003)
        self.assertEqual(tariff.tribute.months_for_period_id(1001), 1)
        self.assertEqual(config.tribute_target(101, 1003), (tariff, 3))
        self.assertIsNone(config.tribute_target(101, 9999))

    def test_tribute_link_accepts_only_official_https_hosts(self):
        valid_links = (
            "https://telegram.me/tribute/app?startapp=subscription",
            "https://tribute.tg/subscriptions/101",
            "https://web.tribute.tg/subscriptions/101",
            "https://web.tribute.tg:443/subscriptions/101",
        )
        for link in valid_links:
            with self.subTest(link=link):
                data = _valid_config()
                data["tariffs"][0]["tribute"] = {
                    "link": link,
                    "subscription_id": 101,
                    "period_ids": {"1": 1001},
                }
                config = TariffsConfig.model_validate(data)
                self.assertEqual(config.require("standard").tribute.link, link)

        invalid_links = (
            "http://t.me/tribute/app?startapp=subscription",
            "https://example.com/subscriptions/101",
            "https://tribute.tg.evil.example/subscriptions/101",
            "https://user:password@tribute.tg/subscriptions/101",
            "https://tribute.tg:8443/subscriptions/101",
        )
        for link in invalid_links:
            with self.subTest(link=link):
                data = _valid_config()
                data["tariffs"][0]["tribute"] = {
                    "link": link,
                    "subscription_id": 101,
                    "period_ids": {"1": 1001},
                }
                with self.assertRaises(ValueError):
                    TariffsConfig.model_validate(data)

    def test_tribute_period_mapping_must_be_positive_unique_and_enabled(self):
        invalid_period_maps = (
            {"0": 1001},
            {"1.5": 1001},
            {"1": 1001, "01": 1002},
            {"1": 1001, "3": 1001},
            {"1": 0},
        )
        for period_ids in invalid_period_maps:
            with self.subTest(period_ids=period_ids):
                data = _valid_config()
                data["tariffs"][0]["tribute"] = {
                    "link": "https://t.me/tribute/app?startapp=subscription",
                    "subscription_id": 101,
                    "period_ids": period_ids,
                }
                with self.assertRaises(ValueError):
                    TariffsConfig.model_validate(data)

        data = _valid_config()
        data["tariffs"][0]["tribute"] = {
            "link": "https://t.me/tribute/app?startapp=subscription",
            "subscription_id": 101,
            "period_ids": {"3": 1003},
        }
        with self.assertRaisesRegex(ValueError, "must be enabled tariff periods"):
            TariffsConfig.model_validate(data)

    def test_tribute_subscription_id_must_be_positive(self):
        data = _valid_config()
        data["tariffs"][0]["tribute"] = {
            "link": "https://t.me/tribute/app?startapp=subscription",
            "subscription_id": 0,
            "period_ids": {"1": 1001},
        }

        with self.assertRaises(ValueError):
            TariffsConfig.model_validate(data)

    def test_tribute_can_map_only_a_subset_of_enabled_periods(self):
        data = _valid_config()
        data["tariffs"][0]["prices_rub"] = {"1": 150, "3": 400}
        data["tariffs"][0]["enabled_periods"] = [1, 3]
        data["tariffs"][0]["tribute"] = {
            "link": "https://t.me/tribute/app?startapp=subscription",
            "subscription_id": 101,
            "period_ids": {"3": 1003},
        }

        config = TariffsConfig.model_validate(data)

        tribute = config.require("standard").tribute
        self.assertIsNotNone(tribute)
        self.assertEqual(tribute.period_ids, {"3": 1003})

    def test_tribute_product_only_config_loads_for_traffic_tariff(self):
        data = _valid_config()
        data["tariffs"][1]["tribute"] = {
            "traffic_products": {
                "010.00": {
                    "product_id": 501,
                    "link": " https://web.tribute.tg/products/501 ",
                }
            }
        }

        config = TariffsConfig.model_validate(data)
        tariff = config.require("traffic")
        tribute = tariff.tribute

        self.assertIsNotNone(tribute)
        self.assertFalse(tribute.has_subscription)
        self.assertEqual(list(tribute.traffic_products), ["10"])
        product = tribute.product_for_units("traffic", 10)
        self.assertIsNotNone(product)
        self.assertEqual(product.product_id, 501)
        self.assertEqual(product.link, "https://web.tribute.tg/products/501")
        self.assertEqual(config.tribute_product_target(501), (tariff, "traffic", 10.0))

    def test_tribute_products_map_period_topups_and_premium_topups(self):
        data = _valid_config()
        tariff_data = data["tariffs"][0]
        tariff_data["topup_packages"] = {
            "rub": [{"gb": 20.5, "price": 149}],
            "stars": [{"gb": 20.5, "price": 75}],
        }
        tariff_data["premium_squad_uuids"] = ["premium-squad"]
        tariff_data["premium_topup_packages"] = {
            "rub": [{"gb": 5, "price": 99}],
        }
        tariff_data["tribute"] = {
            "traffic_products": {
                "20.500": {
                    "product_id": 501,
                    "link": "https://t.me/tribute/app?startapp=product-501",
                }
            },
            "premium_traffic_products": {
                "5.0": {
                    "product_id": 502,
                    "link": "https://tribute.tg/products/502",
                }
            },
        }

        config = TariffsConfig.model_validate(data)
        tariff = config.require("standard")
        tribute = tariff.tribute

        self.assertIsNotNone(tribute)
        self.assertEqual(list(tribute.traffic_products), ["20.5"])
        self.assertEqual(list(tribute.premium_traffic_products), ["5"])
        self.assertEqual(config.tribute_product_target(501), (tariff, "traffic", 20.5))
        self.assertEqual(config.tribute_product_target(502), (tariff, "premium_traffic", 5.0))

    def test_tribute_product_units_must_reference_logical_packages(self):
        data = _valid_config()
        data["tariffs"][1]["tribute"] = {
            "traffic_products": {
                "25": {
                    "product_id": 501,
                    "link": "https://tribute.tg/products/501",
                }
            }
        }

        with self.assertRaisesRegex(ValueError, "must reference existing traffic_packages"):
            TariffsConfig.model_validate(data)

        data = _valid_config()
        data["tariffs"][0]["premium_squad_uuids"] = ["premium-squad"]
        data["tariffs"][0]["premium_topup_packages"] = {
            "rub": [{"gb": 5, "price": 99}],
        }
        data["tariffs"][0]["tribute"] = {
            "premium_traffic_products": {
                "10": {
                    "product_id": 502,
                    "link": "https://tribute.tg/products/502",
                }
            }
        }
        with self.assertRaisesRegex(ValueError, "must reference existing premium_topup_packages"):
            TariffsConfig.model_validate(data)

    def test_tribute_product_units_must_be_positive_and_canonical_unique(self):
        invalid_product_maps = (
            {
                "0": {
                    "product_id": 501,
                    "link": "https://tribute.tg/products/501",
                }
            },
            {
                "1.5.0": {
                    "product_id": 501,
                    "link": "https://tribute.tg/products/501",
                }
            },
            {
                "10": {
                    "product_id": 501,
                    "link": "https://tribute.tg/products/501",
                },
                "10.0": {
                    "product_id": 502,
                    "link": "https://tribute.tg/products/502",
                },
            },
        )
        for traffic_products in invalid_product_maps:
            with self.subTest(traffic_products=traffic_products):
                data = _valid_config()
                data["tariffs"][1]["tribute"] = {"traffic_products": traffic_products}
                with self.assertRaises(ValueError):
                    TariffsConfig.model_validate(data)

    def test_tribute_product_requires_positive_id_and_official_link(self):
        invalid_products = (
            {"product_id": 0, "link": "https://tribute.tg/products/501"},
            {"product_id": 501, "link": "http://tribute.tg/products/501"},
            {"product_id": 501, "link": "https://example.com/products/501"},
        )
        for product in invalid_products:
            with self.subTest(product=product):
                data = _valid_config()
                data["tariffs"][1]["tribute"] = {"traffic_products": {"10": product}}
                with self.assertRaises(ValueError):
                    TariffsConfig.model_validate(data)

    def test_tribute_product_id_cannot_map_to_multiple_targets(self):
        data = _valid_config()
        data["tariffs"][0]["topup_packages"] = {
            "rub": [{"gb": 20, "price": 149}],
        }
        data["tariffs"][0]["tribute"] = {
            "traffic_products": {
                "20": {
                    "product_id": 501,
                    "link": "https://tribute.tg/products/501",
                }
            }
        }
        data["tariffs"][1]["tribute"] = {
            "traffic_products": {
                "10": {
                    "product_id": 501,
                    "link": "https://tribute.tg/products/501",
                }
            }
        }

        with self.assertRaisesRegex(ValueError, "cannot map to both"):
            TariffsConfig.model_validate(data)

    def test_tribute_subscription_fields_must_be_complete(self):
        invalid_configs = (
            {"link": "https://tribute.tg/subscriptions/101"},
            {"subscription_id": 101},
            {"period_ids": {"1": 1001}},
            {},
        )
        for tribute in invalid_configs:
            with self.subTest(tribute=tribute):
                data = _valid_config()
                data["tariffs"][0]["tribute"] = tribute
                with self.assertRaises(ValueError):
                    TariffsConfig.model_validate(data)

    def test_tribute_subscription_cannot_be_shared_between_tariffs(self):
        data = _valid_config()
        second_period_tariff = deepcopy(data["tariffs"][0])
        second_period_tariff["key"] = "plus"
        data["tariffs"].append(second_period_tariff)
        data["tariffs"][0]["tribute"] = {
            "link": "https://t.me/tribute/app?startapp=standard",
            "subscription_id": 101,
            "period_ids": {"1": 1001},
        }
        second_period_tariff["tribute"] = {
            "link": "https://t.me/tribute/app?startapp=plus",
            "subscription_id": 101,
            "period_ids": {"1": 2001},
        }

        with self.assertRaisesRegex(ValueError, "cannot belong to both tariffs"):
            TariffsConfig.model_validate(data)

    def test_tribute_period_cannot_map_to_multiple_tariff_targets(self):
        data = _valid_config()
        second_period_tariff = deepcopy(data["tariffs"][0])
        second_period_tariff["key"] = "plus"
        data["tariffs"].append(second_period_tariff)
        for tariff in (data["tariffs"][0], second_period_tariff):
            tariff["tribute"] = {
                "link": f"https://t.me/tribute/app?startapp={tariff['key']}",
                "subscription_id": 101,
                "period_ids": {"1": 1001},
            }

        with self.assertRaisesRegex(ValueError, "cannot map to both"):
            TariffsConfig.model_validate(data)

    def test_traffic_tariff_rejects_tribute_config(self):
        data = _valid_config()
        data["tariffs"][1]["tribute"] = {
            "link": "https://t.me/tribute/app?startapp=traffic",
            "subscription_id": 101,
            "period_ids": {},
        }

        with self.assertRaisesRegex(ValueError, "only valid for period tariffs"):
            TariffsConfig.model_validate(data)

    def test_negative_tariff_referral_bonus_rejected(self):
        data = _valid_config()
        data["tariffs"][0]["referral_bonus_days_inviter"] = {"1": -1}

        with self.assertRaises(ValueError):
            TariffsConfig.model_validate(data)

    def test_missing_config_returns_none(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertIsNone(load_tariffs_config(Path(tmpdir) / "missing.json"))

    def test_duplicate_keys_rejected(self):
        data = _valid_config()
        data["tariffs"][1]["key"] = "standard"

        with self.assertRaises(ValueError):
            TariffsConfig.model_validate(data)

    def test_legacy_key_resolves_to_current_tariff(self):
        data = _valid_config()
        data["tariffs"][0]["key"] = "current"
        data["tariffs"][0]["legacy_keys"] = [" old-key ", "old-key"]
        data["default_tariff"] = "current"

        config = TariffsConfig.model_validate(data)

        self.assertEqual(config.require("old-key").key, "current")
        self.assertEqual(config.require("current").legacy_keys, ["old-key"])

    def test_hidden_tariff_is_available_only_when_assigned(self):
        data = _valid_config()
        data["tariffs"][1]["enabled"] = False
        data["tariffs"][1]["legacy_keys"] = ["private-old"]

        config = TariffsConfig.model_validate(data)

        with self.assertRaises(KeyError):
            config.require("traffic")
        self.assertEqual(config.require_configured("traffic").key, "traffic")
        self.assertEqual(config.require_for_user("private-old", "traffic").key, "traffic")
        with self.assertRaises(KeyError):
            config.require_for_user("traffic", "standard")
        self.assertEqual(
            [tariff.key for tariff in config.available_tariffs_for_user(None)],
            ["standard"],
        )
        self.assertEqual(
            [tariff.key for tariff in config.available_tariffs_for_user("private-old")],
            ["standard", "traffic"],
        )

    def test_legacy_key_cannot_shadow_another_tariff(self):
        data = _valid_config()
        data["tariffs"][0]["legacy_keys"] = ["traffic"]

        with self.assertRaisesRegex(ValueError, "keys and legacy_keys must be unique"):
            TariffsConfig.model_validate(data)

    def test_default_must_be_enabled(self):
        data = _valid_config()
        data["default_tariff"] = "missing"

        with self.assertRaises(ValueError):
            TariffsConfig.model_validate(data)

    def test_referral_welcome_tariff_defaults_to_default_tariff(self):
        config = TariffsConfig.model_validate(_valid_config())

        self.assertIsNone(config.referral_welcome_bonus_tariff)
        self.assertEqual(config.referral_welcome_bonus_tariff_key, "standard")

    def test_referral_welcome_tariff_accepts_enabled_period_tariff(self):
        data = _valid_config()
        period_tariff = deepcopy(data["tariffs"][0])
        period_tariff["key"] = "starter"
        data["tariffs"].append(period_tariff)
        data["referral_welcome_bonus_tariff"] = "starter"

        config = TariffsConfig.model_validate(data)

        self.assertEqual(config.referral_welcome_bonus_tariff, "starter")
        self.assertEqual(config.referral_welcome_bonus_tariff_key, "starter")

    def test_referral_welcome_tariff_rejects_missing_or_disabled_tariff(self):
        for key in ("missing", "disabled"):
            with self.subTest(key=key):
                data = _valid_config()
                if key == "disabled":
                    disabled_tariff = deepcopy(data["tariffs"][0])
                    disabled_tariff["key"] = "disabled"
                    disabled_tariff["enabled"] = False
                    data["tariffs"].append(disabled_tariff)
                data["referral_welcome_bonus_tariff"] = key

                with self.assertRaisesRegex(ValueError, "must reference an enabled tariff"):
                    TariffsConfig.model_validate(data)

    def test_referral_welcome_tariff_rejects_traffic_tariff(self):
        data = _valid_config()
        data["referral_welcome_bonus_tariff"] = "traffic"

        with self.assertRaisesRegex(ValueError, "must reference a period tariff"):
            TariffsConfig.model_validate(data)

    def test_period_price_required_for_enabled_period(self):
        data = _valid_config()
        data["tariffs"][0]["prices_rub"] = {"1": 0}
        data["tariffs"][0]["prices_stars"] = {"1": 0}

        with self.assertRaises(ValueError):
            TariffsConfig.model_validate(data)

    def test_traffic_without_rub_needs_conversion_rate(self):
        data = _valid_config()
        data["tariffs"][1]["traffic_packages"] = {"rub": [], "stars": [{"gb": 10, "price": 2500}]}

        with self.assertRaises(ValueError):
            TariffsConfig.model_validate(data)

    def test_default_currency_prices_load_from_generic_map(self):
        data = _valid_config()
        data["default_currency"] = "USD"
        data["tariffs"][0].pop("prices_rub")
        data["tariffs"][0]["prices"] = {"usd": {"1": 4.99}}
        data["tariffs"][1]["traffic_packages"] = {"usd": [{"gb": 10, "price": 2.5}]}

        config = TariffsConfig.model_validate(data)
        period = config.require("standard")
        traffic = config.require("traffic")

        self.assertEqual(config.default_currency, "usd")
        self.assertEqual(config.default_payment_currency_code, "USD")
        self.assertEqual(period.period_price(1, "usd"), 4.99)
        self.assertIsNone(period.period_price(1, "rub"))
        self.assertEqual(traffic.traffic_packages.for_currency("usd")[0].price, 2.5)
        self.assertEqual(traffic.currency_per_gb_for_conversion("usd"), 0.25)

    def test_currency_symbol_falls_back_to_default_key(self):
        self.assertEqual(normalize_currency_key("₽"), "rub")

    def test_hwid_device_limit_and_packages_load(self):
        data = _valid_config()
        data["tariffs"][0]["hwid_device_limit"] = 5
        data["tariffs"][0]["hwid_device_packages"] = {
            "rub": [
                {
                    "count": 1,
                    "price": 99,
                    "prices": {"3": 249},
                    "min_price": 20,
                    "traffic_bonus_gb": 15,
                }
            ],
            "stars": [{"count": 1, "price": 2500, "traffic_bonus_gb": 15}],
        }

        config = TariffsConfig.model_validate(data)

        tariff = config.require("standard")
        self.assertEqual(tariff.hwid_device_limit, 5)
        self.assertTrue(tariff.has_hwid_device_packages())
        self.assertEqual(tariff.hwid_device_packages.rub[0].count, 1)
        self.assertEqual(tariff.hwid_device_packages.rub[0].price_for_period(3), 249)
        self.assertEqual(tariff.hwid_device_packages.rub[0].price_for_period(6), 594)
        self.assertEqual(tariff.hwid_device_packages.rub[0].min_price, 20)
        self.assertEqual(tariff.hwid_device_packages.rub[0].traffic_bonus_gb, 15)

    def test_hwid_device_package_traffic_bonus_defaults_to_zero(self):
        data = _valid_config()
        data["tariffs"][0]["hwid_device_packages"] = {
            "rub": [{"count": 1, "price": 99}],
        }

        config = TariffsConfig.model_validate(data)

        self.assertEqual(config.require("standard").hwid_device_packages.rub[0].traffic_bonus_gb, 0)

    def test_invalid_hwid_device_package_traffic_bonus_rejected(self):
        for invalid in (-1, float("inf"), float("nan")):
            with self.subTest(invalid=invalid):
                data = _valid_config()
                data["tariffs"][0]["hwid_device_packages"] = {
                    "rub": [{"count": 1, "price": 99, "traffic_bonus_gb": invalid}],
                }
                with self.assertRaises(ValueError):
                    TariffsConfig.model_validate(data)

    def test_hwid_device_package_bonus_must_match_across_currencies(self):
        data = _valid_config()
        data["tariffs"][0]["hwid_device_packages"] = {
            "rub": [{"count": 1, "price": 99, "traffic_bonus_gb": 15}],
            "stars": [{"count": 1, "price": 50, "traffic_bonus_gb": 10}],
        }

        with self.assertRaisesRegex(ValueError, "must match across currencies"):
            TariffsConfig.model_validate(data)

    def test_hwid_device_package_counts_must_be_unique_per_currency(self):
        data = _valid_config()
        data["tariffs"][0]["hwid_device_packages"] = {
            "rub": [
                {"count": 1, "price": 99},
                {"count": 1, "price": 149},
            ],
        }

        with self.assertRaisesRegex(ValueError, "duplicate device package count 1"):
            TariffsConfig.model_validate(data)

    def test_negative_hwid_device_limit_rejected(self):
        data = _valid_config()
        data["tariffs"][0]["hwid_device_limit"] = -1

        with self.assertRaises(ValueError):
            TariffsConfig.model_validate(data)

    def test_premium_squad_limit_and_topups_load(self):
        data = _valid_config()
        data["tariffs"][0]["premium_squad_uuids"] = [" premium-squad "]
        data["tariffs"][0]["premium_names"] = {"ru": "Обход глушилок", "en": "Anti-jamming"}
        data["tariffs"][0]["premium_monthly_gb"] = 50
        data["tariffs"][0]["premium_topup_packages"] = {
            "rub": [{"gb": 10, "price": 99}],
            "stars": [],
        }

        config = TariffsConfig.model_validate(data)
        tariff = config.require("standard")

        self.assertEqual(tariff.premium_squad_uuids, ["premium-squad"])
        self.assertEqual(tariff.premium_name("ru"), "Обход глушилок")
        self.assertEqual(tariff.premium_name("en"), "Anti-jamming")
        self.assertEqual(tariff.premium_monthly_bytes, 50 * 1024**3)
        self.assertTrue(tariff.has_premium_squad_limit())

    def test_premium_squads_cannot_overlap_base_squads(self):
        data = _valid_config()
        data["tariffs"][0]["squad_uuids"] = ["base-squad", "shared-squad"]
        data["tariffs"][0]["premium_squad_uuids"] = ["shared-squad"]

        with self.assertRaisesRegex(
            ValueError,
            "squad_uuids and premium_squad_uuids must not overlap: shared-squad",
        ):
            TariffsConfig.model_validate(data)

    def test_premium_limit_requires_premium_squad(self):
        data = _valid_config()
        data["tariffs"][0]["premium_monthly_gb"] = 50

        with self.assertRaises(ValueError):
            TariffsConfig.model_validate(data)

    def test_zero_premium_limit_is_explicitly_quota_controlled(self):
        data = _valid_config()
        data["tariffs"][0]["premium_squad_uuids"] = ["premium-squad"]
        data["tariffs"][0]["premium_monthly_gb"] = 0

        tariff = TariffsConfig.model_validate(data).require("standard")

        self.assertEqual(tariff.premium_monthly_bytes, 0)
        self.assertTrue(tariff.has_premium_squad_limit())

    def test_explicit_premium_unlimited_disables_quota_control(self):
        data = _valid_config()
        data["tariffs"][0]["premium_squad_uuids"] = ["premium-squad"]
        data["tariffs"][0]["premium_monthly_gb"] = 50
        data["tariffs"][0]["premium_unlimited"] = True

        tariff = TariffsConfig.model_validate(data).require("standard")

        self.assertEqual(tariff.premium_monthly_bytes, 0)
        self.assertFalse(tariff.has_premium_squad_limit())
