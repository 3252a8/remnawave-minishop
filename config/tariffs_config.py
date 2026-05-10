import json
import logging
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, model_validator


Currency = Literal["rub", "stars"]
BillingModel = Literal["period", "traffic"]


class TrafficPackage(BaseModel):
    gb: float
    price: float

    @model_validator(mode="after")
    def validate_values(self) -> "TrafficPackage":
        if self.gb <= 0:
            raise ValueError("package gb must be greater than zero")
        if self.price < 0:
            raise ValueError("package price must be non-negative")
        return self


class HwidDevicePackage(BaseModel):
    count: int
    price: float

    @model_validator(mode="after")
    def validate_values(self) -> "HwidDevicePackage":
        if self.count <= 0:
            raise ValueError("device package count must be greater than zero")
        if self.price < 0:
            raise ValueError("device package price must be non-negative")
        return self


class PackageSet(BaseModel):
    rub: List[TrafficPackage] = Field(default_factory=list)
    stars: List[TrafficPackage] = Field(default_factory=list)

    def for_currency(self, currency: Currency) -> List[TrafficPackage]:
        return list(getattr(self, currency) or [])

    def has_any(self) -> bool:
        return bool(self.rub or self.stars)


class HwidDevicePackageSet(BaseModel):
    rub: List[HwidDevicePackage] = Field(default_factory=list)
    stars: List[HwidDevicePackage] = Field(default_factory=list)

    def for_currency(self, currency: Currency) -> List[HwidDevicePackage]:
        return list(getattr(self, currency) or [])

    def has_any(self) -> bool:
        return bool(self.rub or self.stars)


class Tariff(BaseModel):
    key: str
    names: Dict[str, str] = Field(default_factory=dict)
    descriptions: Dict[str, str] = Field(default_factory=dict)
    premium_names: Dict[str, str] = Field(default_factory=dict)
    squad_uuids: List[str] = Field(default_factory=list)
    billing_model: BillingModel
    enabled: bool = True

    monthly_gb: Optional[float] = None
    prices_rub: Dict[str, float] = Field(default_factory=dict)
    prices_stars: Dict[str, float] = Field(default_factory=dict)
    enabled_periods: List[int] = Field(default_factory=list)
    topup_packages: Optional[PackageSet] = None

    traffic_packages: Optional[PackageSet] = None
    conversion_rate_rub_per_gb: Optional[float] = None
    hwid_device_limit: Optional[int] = None
    hwid_device_packages: Optional[HwidDevicePackageSet] = None
    premium_squad_uuids: List[str] = Field(default_factory=list)
    premium_monthly_gb: Optional[float] = None
    premium_topup_packages: Optional[PackageSet] = None

    @model_validator(mode="after")
    def validate_tariff(self) -> "Tariff":
        if not self.key.strip():
            raise ValueError("tariff key must not be empty")
        self.key = self.key.strip()
        self.squad_uuids = [uuid.strip() for uuid in self.squad_uuids if uuid.strip()]
        self.premium_squad_uuids = [
            uuid.strip() for uuid in self.premium_squad_uuids if uuid.strip()
        ]
        if self.hwid_device_limit is not None and self.hwid_device_limit < 0:
            raise ValueError(f"tariff {self.key}: hwid_device_limit must be >= 0")
        if self.premium_monthly_gb is not None and self.premium_monthly_gb < 0:
            raise ValueError(f"tariff {self.key}: premium_monthly_gb must be >= 0")
        if self.premium_topup_packages and not self.premium_squad_uuids:
            raise ValueError(f"tariff {self.key}: premium_topup_packages require premium_squad_uuids")
        if self.premium_monthly_gb and self.premium_monthly_gb > 0 and not self.premium_squad_uuids:
            raise ValueError(f"tariff {self.key}: premium_monthly_gb requires premium_squad_uuids")

        if self.billing_model == "period":
            if self.monthly_gb is None or self.monthly_gb < 0:
                raise ValueError(f"period tariff {self.key}: monthly_gb must be >= 0")
            if not self.enabled_periods:
                raise ValueError(f"period tariff {self.key}: enabled_periods is required")
            for months in self.enabled_periods:
                if months <= 0:
                    raise ValueError(f"period tariff {self.key}: enabled periods must be positive")
                rub_price = self.prices_rub.get(str(months), 0) or 0
                stars_price = self.prices_stars.get(str(months), 0) or 0
                if rub_price <= 0 and stars_price <= 0:
                    raise ValueError(
                        f"period tariff {self.key}: period {months} needs a non-zero rub or stars price"
                    )
            return self

        if not self.traffic_packages or not self.traffic_packages.has_any():
            raise ValueError(f"traffic tariff {self.key}: traffic_packages is required")
        if self.conversion_rate_rub_per_gb is not None and self.conversion_rate_rub_per_gb <= 0:
            raise ValueError(f"traffic tariff {self.key}: conversion_rate_rub_per_gb must be > 0")
        if not self.traffic_packages.rub and self.conversion_rate_rub_per_gb is None:
            raise ValueError(
                f"traffic tariff {self.key}: conversion_rate_rub_per_gb is required without RUB packages"
            )
        return self

    def name(self, lang: str, fallback: str = "ru") -> str:
        return self.names.get(lang) or self.names.get(fallback) or self.key

    def description(self, lang: str, fallback: str = "ru") -> str:
        return self.descriptions.get(lang) or self.descriptions.get(fallback) or ""

    def premium_name(self, lang: str, fallback: str = "ru") -> str:
        default = "Premium-серверы" if (lang or fallback) == "ru" else "Premium servers"
        return self.premium_names.get(lang) or self.premium_names.get(fallback) or default

    @property
    def monthly_bytes(self) -> int:
        if self.monthly_gb is None or self.monthly_gb <= 0:
            return 0
        return int(float(self.monthly_gb) * (1024**3))

    def period_price(self, months: int, currency: Currency = "rub") -> Optional[float]:
        source = self.prices_rub if currency == "rub" else self.prices_stars
        value = source.get(str(months))
        return float(value) if value is not None else None

    def min_period_price_rub(self) -> Optional[float]:
        prices = [
            float(self.prices_rub[str(months)])
            for months in self.enabled_periods
            if self.prices_rub.get(str(months), 0) and self.prices_rub.get(str(months), 0) > 0
        ]
        return min(prices) if prices else None

    def min_traffic_package_rub(self) -> Optional[TrafficPackage]:
        packages = self.traffic_packages.rub if self.traffic_packages else []
        return min(packages, key=lambda pkg: pkg.price) if packages else None

    def rub_per_gb_for_conversion(self) -> float:
        if self.conversion_rate_rub_per_gb:
            return float(self.conversion_rate_rub_per_gb)
        packages = self.traffic_packages.rub if self.traffic_packages else []
        return min(float(pkg.price) / float(pkg.gb) for pkg in packages)

    def has_hwid_device_packages(self) -> bool:
        return bool(self.hwid_device_packages and self.hwid_device_packages.has_any())

    @property
    def premium_monthly_bytes(self) -> int:
        if self.premium_monthly_gb is None or self.premium_monthly_gb <= 0:
            return 0
        return int(float(self.premium_monthly_gb) * (1024**3))

    def has_premium_squad_limit(self) -> bool:
        return bool(self.premium_squad_uuids and (self.premium_monthly_bytes > 0 or self.premium_topup_packages))


class TariffsConfig(BaseModel):
    default_tariff: str
    topup_packages_default: Optional[PackageSet] = None
    tariffs: List[Tariff]

    @model_validator(mode="after")
    def validate_config(self) -> "TariffsConfig":
        keys = [tariff.key for tariff in self.tariffs]
        if len(keys) != len(set(keys)):
            raise ValueError("tariff keys must be unique")
        active = [tariff for tariff in self.tariffs if tariff.enabled]
        if not active:
            raise ValueError("at least one enabled tariff is required")
        active_keys = {tariff.key for tariff in active}
        if self.default_tariff not in active_keys:
            raise ValueError("default_tariff must reference an enabled tariff")
        return self

    @property
    def enabled_tariffs(self) -> List[Tariff]:
        return [tariff for tariff in self.tariffs if tariff.enabled]

    def get(self, key: str) -> Optional[Tariff]:
        return next((tariff for tariff in self.tariffs if tariff.key == key), None)

    def require(self, key: str) -> Tariff:
        tariff = self.get(key)
        if not tariff or not tariff.enabled:
            raise KeyError(f"Unknown or disabled tariff: {key}")
        return tariff

    @property
    def default(self) -> Tariff:
        return self.require(self.default_tariff)

    def topup_packages_for(self, tariff: Tariff) -> Optional[PackageSet]:
        if tariff.billing_model == "traffic":
            return tariff.traffic_packages
        return tariff.topup_packages


def load_tariffs_config(path: str | Path) -> Optional[TariffsConfig]:
    config_path = Path(path)
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        return TariffsConfig.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        logging.critical("Failed to load tariffs config from %s: %s", config_path, exc)
        raise
