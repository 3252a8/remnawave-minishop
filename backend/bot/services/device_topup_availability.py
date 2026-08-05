"""Shared eligibility contract for purchasing additional HWID devices."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from config.settings import Settings
from config.tariffs_config import Tariff, default_currency_key_for_settings


class DeviceTopupUnavailableReason(StrEnum):
    SECTION_DISABLED = "section_disabled"
    TARIFFS_UNAVAILABLE = "tariffs_unavailable"
    SUBSCRIPTION_INACTIVE = "subscription_inactive"
    MISSING_TARIFF = "missing_tariff"
    TRIAL_SUBSCRIPTION = "trial_subscription"
    TARIFF_NOT_FOUND = "tariff_not_found"
    TARIFF_DISABLED = "tariff_disabled"
    UNSUPPORTED_BILLING_MODEL = "unsupported_billing_model"
    UNLIMITED_DEVICES = "unlimited_devices"
    NO_PURCHASABLE_PACKAGES = "no_purchasable_packages"
    TARIFF_MISMATCH = "tariff_mismatch"


@dataclass(frozen=True)
class DeviceTopupAvailability:
    allowed: bool
    reason: DeviceTopupUnavailableReason | None
    tariff: Tariff | None
    default_currency: str
    default_currency_counts: tuple[int, ...] = ()
    stars_counts: tuple[int, ...] = ()

    @property
    def package_counts(self) -> tuple[int, ...]:
        return tuple(sorted(set(self.default_currency_counts) | set(self.stars_counts)))

    @property
    def available_currencies(self) -> tuple[str, ...]:
        currencies: list[str] = []
        if self.default_currency_counts:
            currencies.append(self.default_currency)
        if self.stars_counts:
            currencies.append("stars")
        return tuple(currencies)

    def supports(self, device_count: int, currency: str) -> bool:
        count = int(device_count)
        normalized_currency = str(currency or "").strip().lower()
        if normalized_currency == "stars":
            return count in self.stars_counts
        return (
            normalized_currency == self.default_currency and count in self.default_currency_counts
        )

    @property
    def error_code(self) -> str:
        reason = self.reason or DeviceTopupUnavailableReason.NO_PURCHASABLE_PACKAGES
        return f"device_topup_{reason.value}"


def _coerce_device_limit(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _package_counts(tariff: Tariff, currency: str) -> tuple[int, ...]:
    packages = tariff.hwid_device_packages
    if packages is None:
        return ()
    for_currency = getattr(packages, "for_currency", None)
    currency_packages = (
        for_currency(currency)
        if callable(for_currency)
        else getattr(packages, str(currency).lower(), [])
    )
    return tuple(
        sorted(
            {
                int(package.count)
                for package in currency_packages
                if int(package.count) > 0 and float(getattr(package, "price", 1) or 0) > 0
            }
        )
    )


def _has_purchasable_device_tariff(settings: Settings, config: Any) -> bool:
    default_currency = default_currency_key_for_settings(settings)
    return any(
        any(
            (tariff.period_price(months, default_currency) or 0) > 0
            or (tariff.period_price(months, "stars") or 0) > 0
            for months in tariff.enabled_periods
        )
        and (_coerce_device_limit(tariff.hwid_device_limit) or 0) > 0
        and bool(_package_counts(tariff, default_currency) or _package_counts(tariff, "stars"))
        for tariff in config.enabled_tariffs
        if tariff.billing_model == "period"
    )


def _configured_tariff(config: Any, key: str) -> Tariff | None:
    getter = getattr(config, "get", None)
    if callable(getter):
        return getter(key)
    require = getattr(config, "require", None)
    if not callable(require):
        return None
    try:
        return require(key)
    except Exception:
        return None


def resolve_device_topup_availability(
    settings: Settings,
    *,
    subscription_active: bool,
    tariff_key: Any,
    max_devices: Any,
    expected_tariff_key: Any | None = None,
    subscription_is_trial: bool = False,
) -> DeviceTopupAvailability:
    """Resolve the complete device top-up gate without performing I/O."""

    default_currency = default_currency_key_for_settings(settings)

    def unavailable(
        reason: DeviceTopupUnavailableReason | None,
        tariff: Tariff | None = None,
    ) -> DeviceTopupAvailability:
        return DeviceTopupAvailability(
            allowed=False,
            reason=reason,
            tariff=tariff,
            default_currency=default_currency,
        )

    normalized_tariff_key = str(tariff_key or "").strip()
    if subscription_is_trial and not normalized_tariff_key:
        if not settings.MY_DEVICES_SECTION_ENABLED:
            return unavailable(None)
        config = settings.tariffs_config
        device_limit = _coerce_device_limit(max_devices)
        reason = (
            DeviceTopupUnavailableReason.TRIAL_SUBSCRIPTION
            if config is not None
            and (device_limit or 0) > 0
            and _has_purchasable_device_tariff(settings, config)
            else None
        )
        return unavailable(reason)
    if not settings.MY_DEVICES_SECTION_ENABLED:
        return unavailable(DeviceTopupUnavailableReason.SECTION_DISABLED)

    config = settings.tariffs_config
    if config is None:
        return unavailable(DeviceTopupUnavailableReason.TARIFFS_UNAVAILABLE)
    if not subscription_active:
        return unavailable(DeviceTopupUnavailableReason.SUBSCRIPTION_INACTIVE)

    if not normalized_tariff_key:
        return unavailable(DeviceTopupUnavailableReason.MISSING_TARIFF)

    tariff = _configured_tariff(config, normalized_tariff_key)
    if tariff is None:
        return unavailable(DeviceTopupUnavailableReason.TARIFF_NOT_FOUND)
    expected = str(expected_tariff_key or "").strip()
    expected_tariff = _configured_tariff(config, expected) if expected else None
    if expected and (expected_tariff is None or expected_tariff.key != tariff.key):
        return unavailable(DeviceTopupUnavailableReason.TARIFF_MISMATCH, tariff)
    if not bool(getattr(tariff, "enabled", True)):
        return unavailable(DeviceTopupUnavailableReason.TARIFF_DISABLED, tariff)
    if tariff.billing_model != "period":
        return unavailable(DeviceTopupUnavailableReason.UNSUPPORTED_BILLING_MODEL, tariff)

    device_limit = _coerce_device_limit(max_devices)
    if device_limit in (None, 0):
        return unavailable(DeviceTopupUnavailableReason.UNLIMITED_DEVICES, tariff)

    default_counts = _package_counts(tariff, default_currency)
    stars_counts = _package_counts(tariff, "stars")
    if not default_counts and not stars_counts:
        return unavailable(DeviceTopupUnavailableReason.NO_PURCHASABLE_PACKAGES, tariff)

    return DeviceTopupAvailability(
        allowed=True,
        reason=None,
        tariff=tariff,
        default_currency=default_currency,
        default_currency_counts=default_counts,
        stars_counts=stars_counts,
    )


def device_topup_reason_locale_key(
    reason: DeviceTopupUnavailableReason | None,
    *,
    webapp: bool = False,
) -> str:
    prefix = "wa_device_topup_unavailable" if webapp else "device_topup_unavailable"
    suffix = (reason or DeviceTopupUnavailableReason.NO_PURCHASABLE_PACKAGES).value
    return f"{prefix}_{suffix}"


__all__ = [
    "DeviceTopupAvailability",
    "DeviceTopupUnavailableReason",
    "device_topup_reason_locale_key",
    "resolve_device_topup_availability",
]
