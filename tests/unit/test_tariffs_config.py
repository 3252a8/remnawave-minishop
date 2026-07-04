import json
import unittest

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

    def test_default_must_be_enabled(self):
        data = _valid_config()
        data["default_tariff"] = "missing"

        with self.assertRaises(ValueError):
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
            "rub": [{"count": 1, "price": 99, "prices": {"3": 249}, "min_price": 20}],
            "stars": [{"count": 1, "price": 2500}],
        }

        config = TariffsConfig.model_validate(data)

        tariff = config.require("standard")
        self.assertEqual(tariff.hwid_device_limit, 5)
        self.assertTrue(tariff.has_hwid_device_packages())
        self.assertEqual(tariff.hwid_device_packages.rub[0].count, 1)
        self.assertEqual(tariff.hwid_device_packages.rub[0].price_for_period(3), 249)
        self.assertEqual(tariff.hwid_device_packages.rub[0].price_for_period(6), 594)
        self.assertEqual(tariff.hwid_device_packages.rub[0].min_price, 20)

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

    def test_premium_limit_requires_premium_squad(self):
        data = _valid_config()
        data["tariffs"][0]["premium_monthly_gb"] = 50

        with self.assertRaises(ValueError):
            TariffsConfig.model_validate(data)
