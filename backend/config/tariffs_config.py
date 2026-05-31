import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, RootModel, ValidationError, model_validator

DEFAULT_TARIFF_CURRENCY = "rub"
STARS_TARIFF_CURRENCY = "stars"

Currency = str
BillingModel = Literal["period", "traffic"]


def normalize_currency_key(value: Any, default: str = DEFAULT_TARIFF_CURRENCY) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return default
    aliases = {
        "rur": "rub",
        "xtr": STARS_TARIFF_CURRENCY,
        "star": STARS_TARIFF_CURRENCY,
        "stars": STARS_TARIFF_CURRENCY,
    }
    normalized = aliases.get(text, text)
    cleaned = "".join(ch for ch in normalized if ch.isalnum() or ch in {"_", "-"}).strip("_-")
    return cleaned or default


def payment_currency_code(currency: Any, default: str = "RUB") -> str:
    key = normalize_currency_key(currency, default=normalize_currency_key(default))
    if key == STARS_TARIFF_CURRENCY:
        return "XTR"
    return key.upper()


def default_currency_key_for_settings(settings: Any) -> str:
    try:
        config = getattr(settings, "tariffs_config", None)
    except Exception:
        config = None
    if config is not None and getattr(config, "default_currency", None):
        return normalize_currency_key(config.default_currency)
    return normalize_currency_key(getattr(settings, "DEFAULT_CURRENCY_SYMBOL", None))


def default_payment_currency_code_for_settings(settings: Any) -> str:
    return payment_currency_code(default_currency_key_for_settings(settings))


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
    prices: Dict[str, float] = Field(default_factory=dict)
    min_price: Optional[float] = None

    @model_validator(mode="after")
    def validate_values(self) -> "HwidDevicePackage":
        if self.count <= 0:
            raise ValueError("device package count must be greater than zero")
        if self.price < 0:
            raise ValueError("device package price must be non-negative")
        normalized_prices: Dict[str, float] = {}
        for period, value in (self.prices or {}).items():
            period_key = str(period).strip()
            if not period_key:
                raise ValueError("device package price period must not be empty")
            try:
                period_months = int(period_key)
            except (TypeError, ValueError) as exc:
                raise ValueError("device package price period must be an integer") from exc
            if period_months <= 0:
                raise ValueError("device package price period must be positive")
            if float(value) < 0:
                raise ValueError("device package period price must be non-negative")
            normalized_prices[str(period_months)] = float(value)
        self.prices = normalized_prices
        if self.min_price is not None and self.min_price < 0:
            raise ValueError("device package min_price must be non-negative")
        return self

    def price_for_period(self, months: int) -> float:
        months_int = max(1, int(months or 1))
        value = self.prices.get(str(months_int))
        if value is not None:
            return float(value)
        return float(self.price) * months_int


class PackageSet(RootModel[Dict[str, List[TrafficPackage]]]):
    root: Dict[str, List[TrafficPackage]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_input(cls, data: Any) -> Any:
        if data is None:
            return {}
        if not isinstance(data, dict):
            return data
        normalized: Dict[str, Any] = {}
        for currency, packages in data.items():
            key = normalize_currency_key(currency, default="")
            if not key:
                raise ValueError("package currency must not be empty")
            normalized[key] = packages or []
        return normalized

    def for_currency(self, currency: Currency) -> List[TrafficPackage]:
        return list(self.root.get(normalize_currency_key(currency), []) or [])

    @property
    def rub(self) -> List[TrafficPackage]:
        return self.for_currency("rub")

    @property
    def stars(self) -> List[TrafficPackage]:
        return self.for_currency("stars")

    @property
    def non_stars_currencies(self) -> List[str]:
        return [currency for currency, packages in self.root.items() if currency != "stars" and packages]

    def has_any(self) -> bool:
        return any(bool(packages) for packages in self.root.values())


class HwidDevicePackageSet(RootModel[Dict[str, List[HwidDevicePackage]]]):
    root: Dict[str, List[HwidDevicePackage]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_input(cls, data: Any) -> Any:
        if data is None:
            return {}
        if not isinstance(data, dict):
            return data
        normalized: Dict[str, Any] = {}
        for currency, packages in data.items():
            key = normalize_currency_key(currency, default="")
            if not key:
                raise ValueError("device package currency must not be empty")
            normalized[key] = packages or []
        return normalized

    def for_currency(self, currency: Currency) -> List[HwidDevicePackage]:
        return list(self.root.get(normalize_currency_key(currency), []) or [])

    @property
    def rub(self) -> List[HwidDevicePackage]:
        return self.for_currency("rub")

    @property
    def stars(self) -> List[HwidDevicePackage]:
        return self.for_currency("stars")

    def has_any(self) -> bool:
        return any(bool(packages) for packages in self.root.values())


class Tariff(BaseModel):
    key: str
    names: Dict[str, str] = Field(default_factory=dict)
    descriptions: Dict[str, str] = Field(default_factory=dict)
    premium_names: Dict[str, str] = Field(default_factory=dict)
    squad_uuids: List[str] = Field(default_factory=list)
    billing_model: BillingModel
    enabled: bool = True

    monthly_gb: Optional[float] = None
    prices: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    prices_rub: Dict[str, float] = Field(default_factory=dict)
    prices_stars: Dict[str, float] = Field(default_factory=dict)
    referral_bonus_days_inviter: Dict[str, int] = Field(default_factory=dict)
    referral_bonus_days_referee: Dict[str, int] = Field(default_factory=dict)
    enabled_periods: List[int] = Field(default_factory=list)
    topup_packages: Optional[PackageSet] = None

    traffic_packages: Optional[PackageSet] = None
    conversion_rate_per_gb: Optional[float] = None
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
            raise ValueError(
                f"tariff {self.key}: premium_topup_packages require premium_squad_uuids"
            )
        if self.premium_monthly_gb and self.premium_monthly_gb > 0 and not self.premium_squad_uuids:
            raise ValueError(f"tariff {self.key}: premium_monthly_gb requires premium_squad_uuids")

        self.prices = self._normalize_prices_by_currency(self.prices)
        self.prices_rub = self._normalize_period_price_map(self.prices_rub, "prices_rub")
        self.prices_stars = self._normalize_period_price_map(
            self.prices_stars,
            "prices_stars",
        )
        if self.prices_rub:
            self.prices["rub"] = dict(self.prices_rub)
        elif self.prices.get("rub"):
            self.prices_rub = dict(self.prices["rub"])
        if self.prices_stars:
            self.prices["stars"] = dict(self.prices_stars)
        elif self.prices.get("stars"):
            self.prices_stars = dict(self.prices["stars"])

        if self.conversion_rate_per_gb is None and self.conversion_rate_rub_per_gb is not None:
            self.conversion_rate_per_gb = float(self.conversion_rate_rub_per_gb)
        if self.conversion_rate_per_gb is not None and self.conversion_rate_per_gb <= 0:
            raise ValueError(f"traffic tariff {self.key}: conversion_rate_per_gb must be > 0")

        if self.billing_model == "period":
            if self.monthly_gb is None or self.monthly_gb < 0:
                raise ValueError(f"period tariff {self.key}: monthly_gb must be >= 0")
            self.referral_bonus_days_inviter = self._normalize_referral_bonus_map(
                self.referral_bonus_days_inviter,
                "referral_bonus_days_inviter",
            )
            self.referral_bonus_days_referee = self._normalize_referral_bonus_map(
                self.referral_bonus_days_referee,
                "referral_bonus_days_referee",
            )
            if not self.enabled_periods:
                raise ValueError(f"period tariff {self.key}: enabled_periods is required")
            for months in self.enabled_periods:
                if months <= 0:
                    raise ValueError(f"period tariff {self.key}: enabled periods must be positive")
                period_prices = [
                    float(prices.get(str(months), 0) or 0) for prices in self.prices.values()
                ]
                if not any(price > 0 for price in period_prices):
                    raise ValueError(
                        f"period tariff {self.key}: period {months} needs a non-zero price"
                    )
            return self

        if not self.traffic_packages or not self.traffic_packages.has_any():
            raise ValueError(f"traffic tariff {self.key}: traffic_packages is required")
        if not self.traffic_packages.non_stars_currencies and self.conversion_rate_per_gb is None:
            raise ValueError(
                f"traffic tariff {self.key}: conversion_rate_per_gb is required without fiat packages"  # noqa: E501
            )
        return self

    def _normalize_period_price_map(
        self,
        values: Dict[str, float],
        field_name: str,
    ) -> Dict[str, float]:
        normalized: Dict[str, float] = {}
        for period, value in (values or {}).items():
            try:
                months = int(float(str(period).strip()))
                price = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"tariff {self.key}: {field_name} contains invalid entry") from exc
            if months <= 0:
                raise ValueError(f"tariff {self.key}: {field_name} periods must be positive")
            if price < 0:
                raise ValueError(f"tariff {self.key}: {field_name} prices must be >= 0")
            normalized[str(months)] = price
        return normalized

    def _normalize_prices_by_currency(
        self,
        values: Dict[str, Dict[str, float]],
    ) -> Dict[str, Dict[str, float]]:
        normalized: Dict[str, Dict[str, float]] = {}
        for currency, price_map in (values or {}).items():
            key = normalize_currency_key(currency, default="")
            if not key:
                raise ValueError(f"tariff {self.key}: price currency must not be empty")
            normalized[key] = self._normalize_period_price_map(price_map or {}, f"prices.{key}")
        return normalized

    def _normalize_referral_bonus_map(
        self, values: Dict[str, int], field_name: str
    ) -> Dict[str, int]:
        normalized: Dict[str, int] = {}
        for period, days in (values or {}).items():
            try:
                months = int(float(str(period).strip()))
                bonus_days = int(float(days))
            except (TypeError, ValueError):
                raise ValueError(f"tariff {self.key}: {field_name} contains invalid entry")
            if months <= 0:
                raise ValueError(f"tariff {self.key}: {field_name} periods must be positive")
            if bonus_days < 0:
                raise ValueError(f"tariff {self.key}: {field_name} days must be >= 0")
            normalized[str(months)] = bonus_days
        return normalized

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
        source = self.prices.get(normalize_currency_key(currency), {})
        value = source.get(str(months))
        return float(value) if value is not None else None

    def referral_inviter_bonus_days(self, months: int) -> Optional[int]:
        value = self.referral_bonus_days_inviter.get(str(int(months)))
        return int(value) if value is not None else None

    def referral_referee_bonus_days(self, months: int) -> Optional[int]:
        value = self.referral_bonus_days_referee.get(str(int(months)))
        return int(value) if value is not None else None

    def min_period_price(self, currency: Currency = "rub") -> Optional[float]:
        key = normalize_currency_key(currency)
        source = self.prices.get(key, {})
        prices = [
            float(source[str(months)])
            for months in self.enabled_periods
            if source.get(str(months), 0) and source.get(str(months), 0) > 0
        ]
        return min(prices) if prices else None

    def min_period_price_rub(self) -> Optional[float]:
        return self.min_period_price("rub")

    def min_traffic_package(self, currency: Currency = "rub") -> Optional[TrafficPackage]:
        packages = self.traffic_packages.for_currency(currency) if self.traffic_packages else []
        return min(packages, key=lambda pkg: pkg.price) if packages else None

    def min_traffic_package_rub(self) -> Optional[TrafficPackage]:
        return self.min_traffic_package("rub")

    def currency_per_gb_for_conversion(self, currency: Currency = "rub") -> float:
        if self.conversion_rate_per_gb:
            return float(self.conversion_rate_per_gb)
        packages = self.traffic_packages.for_currency(currency) if self.traffic_packages else []
        if not packages and self.traffic_packages:
            for key in self.traffic_packages.non_stars_currencies:
                packages = self.traffic_packages.for_currency(key)
                if packages:
                    break
        return min(float(pkg.price) / float(pkg.gb) for pkg in packages)

    def rub_per_gb_for_conversion(self) -> float:
        return self.currency_per_gb_for_conversion("rub")

    def has_hwid_device_packages(self) -> bool:
        return bool(self.hwid_device_packages and self.hwid_device_packages.has_any())

    @property
    def premium_monthly_bytes(self) -> int:
        if self.premium_monthly_gb is None or self.premium_monthly_gb <= 0:
            return 0
        return int(float(self.premium_monthly_gb) * (1024**3))

    def has_premium_squad_limit(self) -> bool:
        return bool(
            self.premium_squad_uuids
            and (self.premium_monthly_bytes > 0 or self.premium_topup_packages)
        )


class TariffsConfig(BaseModel):
    default_tariff: str
    default_currency: str = DEFAULT_TARIFF_CURRENCY
    topup_packages_default: Optional[PackageSet] = None
    tariffs: List[Tariff]

    @model_validator(mode="after")
    def validate_config(self) -> "TariffsConfig":
        self.default_currency = normalize_currency_key(self.default_currency)
        if self.default_currency == STARS_TARIFF_CURRENCY:
            raise ValueError("default_currency must be a non-Stars payment currency")
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

    @property
    def default_payment_currency_code(self) -> str:
        return payment_currency_code(self.default_currency)

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
