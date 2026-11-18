import json
from pathlib import Path

from config.settings import Settings
from config.stars_pricing import trial_stars_price
from config.tariffs_config import load_tariffs_config


def test_catalog_stars_prices_are_derived_without_changing_stored_prices(tmp_path: Path) -> None:
    path = tmp_path / "tariffs.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "period_unit": "day",
                "default_tariff": "base",
                "tariffs": [
                    {
                        "key": "base",
                        "billing_model": "period",
                        "period_unit": "day",
                        "monthly_gb": 10,
                        "enabled_periods": [1, 3],
                        "prices": {"rub": {"1": 100}, "stars": {"1": 80, "3": 250}},
                        "topup_packages": {"rub": [{"gb": 20, "price": 19}]},
                        "hwid_device_packages": {
                            "rub": [{"count": 2, "price": 28, "prices": {"3": 57}, "min_price": 5}]
                        },
                        "hwid_device_limit": 3,
                        "checkout_addons": {
                            "devices": {
                                "enabled": True,
                                "max_extra_devices": 5,
                                "price_per_device": 9.5,
                            }
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(TARIFFS_CONFIG_PATH=str(path), STARS_RUB_PER_STAR=0.95)
    converted = settings.tariffs_config
    stored = load_tariffs_config(path)
    assert converted is not None and stored is not None
    tariff = converted.default
    assert tariff.period_price(1, "stars") == 106
    assert tariff.period_price(3, "stars") == 250
    assert stored.default.period_price(1, "stars") == 80
    assert tariff.topup_packages is not None
    assert tariff.topup_packages.stars[0].price == 20
    assert tariff.hwid_device_packages is not None
    devices = tariff.hwid_device_packages.stars[0]
    assert devices.price_for_period(3) == 60
    assert devices.min_price == 6
    assert tariff.checkout_addons.devices.stars_price_per_device == 10


def test_legacy_and_trial_prices_share_the_rate_and_keep_manual_prices_by_default() -> None:
    settings = Settings(
        STARS_ENABLED=True,
        DEFAULT_CURRENCY_SYMBOL="RUB",
        RUB_PRICE_1_MONTH=100,
        STARS_PRICE_1_MONTH=80,
        TRAFFIC_PACKAGES="10:19",
        STARS_TRAFFIC_PACKAGES="10:15,20:25",
        TRIAL_PAYMENT_PRICE=9.5,
        TRIAL_PAYMENT_STARS_PRICE=7,
    )
    assert settings.stars_subscription_options[1] == 80
    assert settings.stars_traffic_packages == {10: 15, 20: 25}
    assert trial_stars_price(settings, "rub") == 7

    converted = settings.model_copy(update={"STARS_RUB_PER_STAR": 0.95})
    assert converted.stars_subscription_options[1] == 106
    assert converted.stars_traffic_packages == {10: 20, 20: 25}
    assert trial_stars_price(converted, "rub") == 10
    assert trial_stars_price(converted, "usd") == 7
