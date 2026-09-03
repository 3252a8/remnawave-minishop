from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field, model_validator


class CheckoutDeviceAddonConfig(BaseModel):
    enabled: bool = False
    max_extra_devices: int | None = Field(default=None, ge=1)
    price_per_device: float | None = Field(default=None, ge=0)
    stars_price_per_device: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_finite_price(self) -> CheckoutDeviceAddonConfig:
        if self.price_per_device is not None and not math.isfinite(self.price_per_device):
            raise ValueError("checkout device price must be finite")
        return self


class CheckoutTrafficAddonConfig(BaseModel):
    enabled: bool = False


class FlexibleTrafficLimitConfig(BaseModel):
    step_gb: float = Field(gt=0)
    max_total_gb: float = Field(gt=0)
    price_per_step: float = Field(ge=0)
    stars_price_per_step: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_finite_values(self) -> FlexibleTrafficLimitConfig:
        for value in (self.step_gb, self.max_total_gb, self.price_per_step):
            if not math.isfinite(value):
                raise ValueError("flexible traffic limit values must be finite")
        return self


class CheckoutAddonsConfig(BaseModel):
    devices: CheckoutDeviceAddonConfig = Field(default_factory=CheckoutDeviceAddonConfig)
    traffic: CheckoutTrafficAddonConfig = Field(default_factory=CheckoutTrafficAddonConfig)
    premium_traffic: CheckoutTrafficAddonConfig = Field(default_factory=CheckoutTrafficAddonConfig)

    def any_enabled(self) -> bool:
        return bool(self.devices.enabled or self.traffic.enabled or self.premium_traffic.enabled)


def _same_units(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=0, abs_tol=1e-9)


def _traffic_options(
    *,
    base_units: float,
    limit: FlexibleTrafficLimitConfig | None,
    months: float,
) -> list[dict[str, Any]]:
    if limit is None or limit.max_total_gb <= base_units:
        return []
    step_count_raw = (float(limit.max_total_gb) - float(base_units)) / float(limit.step_gb)
    step_count = round(step_count_raw)
    if step_count <= 0 or not _same_units(step_count_raw, step_count):
        return []
    options: list[dict[str, Any]] = [
        {
            "extra_units": 0.0,
            "total_units": float(base_units),
            "price": 0.0,
            "stars_price": 0,
            "monthly_price": 0.0,
            "monthly_stars_price": 0,
        }
    ]
    for steps in range(1, step_count + 1):
        extra_units = float(limit.step_gb) * steps
        total_units = float(base_units) + extra_units
        monthly_price = float(limit.price_per_step) * steps
        item: dict[str, Any] = {
            "extra_units": extra_units,
            "total_units": total_units,
            "price": monthly_price * float(months),
            "monthly_price": monthly_price,
        }
        stars_price = int(limit.stars_price_per_step or 0) * steps
        if stars_price > 0:
            item["stars_price"] = round(stars_price * float(months))
            item["monthly_stars_price"] = stars_price
        options.append(item)
    return options


def _device_options(
    *,
    base_units: int,
    config: CheckoutDeviceAddonConfig,
    months: float,
) -> list[dict[str, Any]]:
    maximum_extra = int(config.max_extra_devices or 0)
    if maximum_extra <= 0 or config.price_per_device is None:
        return []
    options: list[dict[str, Any]] = [
        {
            "extra_units": 0,
            "total_units": int(base_units),
            "price": 0.0,
            "stars_price": 0,
            "traffic_bonus_gb": 0.0,
            "monthly_price": 0.0,
            "monthly_stars_price": 0,
        }
    ]
    for extra_units in range(1, maximum_extra + 1):
        total_units = int(base_units) + extra_units
        monthly_price = float(config.price_per_device) * extra_units
        item: dict[str, Any] = {
            "extra_units": extra_units,
            "total_units": total_units,
            "price": monthly_price * float(months),
            "monthly_price": monthly_price,
            "traffic_bonus_gb": 0.0,
        }
        monthly_stars = int(config.stars_price_per_device or 0) * extra_units
        if monthly_stars > 0:
            item["stars_price"] = round(monthly_stars * float(months))
            item["monthly_stars_price"] = monthly_stars
        options.append(item)
    return options


def serialize_checkout_addons(
    tariff: Any,
    *,
    default_currency: str,
    months: int,
    fallback_hwid_limit: int | None,
    devices_feature_enabled: bool,
) -> dict[str, dict[str, Any]]:
    config: CheckoutAddonsConfig | None = getattr(tariff, "checkout_addons", None)
    if config is None or tariff.billing_model != "period":
        return {}

    period_factor = (
        tariff.addon_period_factor(months)
        if callable(getattr(tariff, "addon_period_factor", None))
        else float(months)
    )
    result: dict[str, dict[str, Any]] = {}
    base_devices_raw = tariff.hwid_device_limit
    if base_devices_raw is None:
        base_devices_raw = fallback_hwid_limit
    base_devices = max(0, int(base_devices_raw or 0))
    device_options = (
        _device_options(
            base_units=base_devices,
            config=config.devices,
            months=period_factor,
        )
        if config.devices.enabled and devices_feature_enabled and base_devices > 0
        else []
    )
    if len(device_options) > 1:
        result["devices"] = {
            "kind": "devices",
            "base_units": base_devices,
            "max_total_units": base_devices + int(config.devices.max_extra_devices or 0),
            "options": device_options,
        }

    regular_base = float(tariff.monthly_gb or 0)
    traffic_limit = tariff.flexible_traffic_limit
    traffic_options = (
        _traffic_options(
            base_units=regular_base,
            limit=traffic_limit,
            months=period_factor,
        )
        if config.traffic.enabled and regular_base > 0
        else []
    )
    if len(traffic_options) > 1:
        result["traffic"] = {
            "kind": "traffic",
            "base_units": regular_base,
            "max_total_units": float(traffic_limit.max_total_gb),
            "options": traffic_options,
        }

    premium_base = float(tariff.premium_monthly_gb or 0)
    premium_options = (
        _traffic_options(
            base_units=premium_base,
            limit=tariff.premium_flexible_traffic_limit,
            months=period_factor,
        )
        if (
            config.premium_traffic.enabled
            and not tariff.premium_unlimited
            and bool(tariff.premium_squad_uuids)
        )
        else []
    )
    if len(premium_options) > 1:
        result["premium_traffic"] = {
            "kind": "premium_traffic",
            "base_units": premium_base,
            "max_total_units": float(tariff.premium_flexible_traffic_limit.max_total_gb),
            "options": premium_options,
        }
    return result


def validate_checkout_addons(tariff: Any, *, default_currency: str) -> None:
    config: CheckoutAddonsConfig | None = getattr(tariff, "checkout_addons", None)
    if config is None or not config.any_enabled():
        return
    if tariff.billing_model != "period":
        raise ValueError(f"tariff {tariff.key}: checkout_addons require a period tariff")
    if config.traffic.enabled and float(tariff.monthly_gb or 0) <= 0:
        raise ValueError(f"tariff {tariff.key}: checkout traffic requires a limited base quota")
    if config.premium_traffic.enabled and (
        tariff.premium_unlimited or not tariff.premium_squad_uuids
    ):
        raise ValueError(
            f"tariff {tariff.key}: checkout premium traffic requires limited premium squads"
        )
    if config.devices.enabled and tariff.hwid_device_limit == 0:
        raise ValueError(f"tariff {tariff.key}: checkout devices are invalid for unlimited HWID")

    checks = (
        (
            "traffic",
            float(tariff.monthly_gb or 0),
            tariff.flexible_traffic_limit,
        ),
        (
            "premium_traffic",
            float(tariff.premium_monthly_gb or 0),
            tariff.premium_flexible_traffic_limit,
        ),
    )
    for kind, base, limit in checks:
        enabled = getattr(config, kind).enabled
        if not enabled:
            continue
        options = _traffic_options(
            base_units=base,
            limit=limit,
            months=max(1, int(tariff.enabled_periods[0] if tariff.enabled_periods else 1)),
        )
        if len(options) <= 1:
            raise ValueError(
                f"tariff {tariff.key}: checkout {kind} requires a valid flexible limit"
            )
    if config.devices.enabled:
        options = _device_options(
            base_units=max(0, int(tariff.hwid_device_limit or 0)),
            config=config.devices,
            months=max(1, int(tariff.enabled_periods[0] if tariff.enabled_periods else 1)),
        )
        if len(options) <= 1:
            raise ValueError(
                f"tariff {tariff.key}: checkout devices require a maximum and per-device price"
            )
