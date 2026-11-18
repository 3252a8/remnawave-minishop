"""Derive checkout prices in whole Stars from RUB product prices."""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal
from math import isfinite
from typing import TYPE_CHECKING

from config.tariffs_config import HwidDevicePackageSet, PackageSet

if TYPE_CHECKING:
    from config.settings import Settings
    from config.tariffs_config import TariffsConfig


def rub_to_stars(price: float, rub_per_star: float) -> int:
    if not isfinite(price) or price <= 0:
        return 0
    amount = Decimal(str(price)) / Decimal(str(rub_per_star))
    return int(amount.to_integral_value(rounding=ROUND_CEILING))


def trial_stars_price(settings: Settings, currency: str) -> int:
    rate = settings.STARS_RUB_PER_STAR
    if currency == "rub" and rate and settings.TRIAL_PAYMENT_PRICE:
        return rub_to_stars(settings.TRIAL_PAYMENT_PRICE, rate)
    return max(0, int(settings.TRIAL_PAYMENT_STARS_PRICE or 0))


def _convert_traffic_prices(packages: PackageSet | None, rate: float) -> PackageSet | None:
    if packages is None or not packages.rub:
        return packages
    stars = {package.gb: package for package in packages.stars}
    stars.update(
        (package.gb, package.model_copy(update={"price": rub_to_stars(package.price, rate)}))
        for package in packages.rub
    )
    return PackageSet(packages.root | {"stars": list(stars.values())})


def _convert_device_prices(
    packages: HwidDevicePackageSet | None, rate: float
) -> HwidDevicePackageSet | None:
    if packages is None or not packages.rub:
        return packages
    stars = {package.count: package for package in packages.stars}
    for package in packages.rub:
        stars[package.count] = package.model_copy(
            update={
                "price": rub_to_stars(package.price, rate),
                "prices": {
                    period: rub_to_stars(price, rate) for period, price in package.prices.items()
                },
                "min_price": (
                    rub_to_stars(package.min_price, rate) if package.min_price is not None else None
                ),
            }
        )
    return HwidDevicePackageSet(packages.root | {"stars": list(stars.values())})


def apply_catalog_stars_rate(config: TariffsConfig, rate: float) -> TariffsConfig:
    """Update a just-loaded catalog for use by displays and server-side quoting."""
    config.topup_packages_default = _convert_traffic_prices(config.topup_packages_default, rate)
    for tariff in config.tariffs:
        if rub_prices := tariff.prices.get("rub"):
            tariff.prices_stars = tariff.prices_stars | {
                period: rub_to_stars(price, rate) for period, price in rub_prices.items()
            }
            tariff.prices["stars"] = tariff.prices_stars
        tariff.traffic_packages = _convert_traffic_prices(tariff.traffic_packages, rate)
        tariff.topup_packages = _convert_traffic_prices(tariff.topup_packages, rate)
        tariff.premium_topup_packages = _convert_traffic_prices(tariff.premium_topup_packages, rate)
        tariff.hwid_device_packages = _convert_device_prices(tariff.hwid_device_packages, rate)
        if config.default_currency != "rub":
            continue
        device = tariff.checkout_addons.devices
        if device.price_per_device is not None:
            device.stars_price_per_device = rub_to_stars(device.price_per_device, rate)
        for limit in (tariff.flexible_traffic_limit, tariff.premium_flexible_traffic_limit):
            if limit is not None:
                limit.stars_price_per_step = rub_to_stars(limit.price_per_step, rate)
    return config
