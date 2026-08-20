import json
import logging
import math
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal, NamedTuple

from pydantic import (
    BaseModel,
    Field,
    RootModel,
    ValidationError,
    field_validator,
    model_validator,
)

from config.tariff_checkout import (
    CheckoutAddonsConfig,
    FlexibleTrafficLimitConfig,
    validate_checkout_addons,
)
from config.tariff_tribute import (
    _normalize_tribute_map_keys,
    canonical_tribute_product_unit,
    validate_tribute_link,
)

logger = logging.getLogger(__name__)

DEFAULT_TARIFF_CURRENCY = "rub"
STARS_TARIFF_CURRENCY = "stars"

Currency = str
BillingModel = Literal["period", "traffic"]
TrafficLimitStrategy = Literal["NO_RESET", "DAY", "WEEK", "MONTH", "MONTH_ROLLING"]
TributeProductKind = Literal["traffic", "premium_traffic"]
TRIBUTE_PRODUCT_KINDS: tuple[TributeProductKind, ...] = ("traffic", "premium_traffic")
PositiveStrictInt = Annotated[int, Field(strict=True, gt=0)]


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
        config = settings.tariffs_config
    except Exception:
        config = None
    if config is not None and getattr(config, "default_currency", None):
        return normalize_currency_key(config.default_currency)
    return normalize_currency_key(settings.DEFAULT_CURRENCY_SYMBOL)


def default_payment_currency_code_for_settings(settings: Any) -> str:
    return payment_currency_code(default_currency_key_for_settings(settings))


def referral_welcome_bonus_tariff_key_for_settings(settings: Any) -> str | None:
    config = settings.tariffs_config
    if config is None:
        return None
    resolved_key = str(getattr(config, "referral_welcome_bonus_tariff_key", "") or "").strip()
    if resolved_key:
        return resolved_key
    configured_key = str(getattr(config, "referral_welcome_bonus_tariff", "") or "").strip()
    default_key = str(getattr(config, "default_tariff", "") or "").strip()
    return configured_key or default_key or None


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
    traffic_bonus_gb: float = 0.0
    prices: dict[str, float] = Field(default_factory=dict)
    min_price: float | None = None

    @model_validator(mode="after")
    def validate_values(self) -> "HwidDevicePackage":
        if self.count <= 0:
            raise ValueError("device package count must be greater than zero")
        if self.price < 0:
            raise ValueError("device package price must be non-negative")
        if not math.isfinite(self.traffic_bonus_gb) or self.traffic_bonus_gb < 0:
            raise ValueError("device package traffic_bonus_gb must be finite and non-negative")
        normalized_prices: dict[str, float] = {}
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


class PackageSet(RootModel[dict[str, list[TrafficPackage]]]):
    root: dict[str, list[TrafficPackage]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_input(cls, data: Any) -> Any:
        if data is None:
            return {}
        if not isinstance(data, dict):
            return data
        normalized: dict[str, Any] = {}
        for currency, packages in data.items():
            key = normalize_currency_key(currency, default="")
            if not key:
                raise ValueError("package currency must not be empty")
            normalized[key] = packages or []
        return normalized

    def for_currency(self, currency: Currency) -> list[TrafficPackage]:
        return list(self.root.get(normalize_currency_key(currency), []) or [])

    @property
    def rub(self) -> list[TrafficPackage]:
        return self.for_currency("rub")

    @property
    def stars(self) -> list[TrafficPackage]:
        return self.for_currency("stars")

    @property
    def non_stars_currencies(self) -> list[str]:
        return [
            currency for currency, packages in self.root.items() if currency != "stars" and packages
        ]

    def has_any(self) -> bool:
        return any(bool(packages) for packages in self.root.values())


class HwidDevicePackageSet(RootModel[dict[str, list[HwidDevicePackage]]]):
    root: dict[str, list[HwidDevicePackage]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_input(cls, data: Any) -> Any:
        if data is None:
            return {}
        if not isinstance(data, dict):
            return data
        normalized: dict[str, Any] = {}
        for currency, packages in data.items():
            key = normalize_currency_key(currency, default="")
            if not key:
                raise ValueError("device package currency must not be empty")
            normalized[key] = packages or []
        return normalized

    @model_validator(mode="after")
    def validate_logical_packages(self) -> "HwidDevicePackageSet":
        bonuses_by_count: dict[int, float] = {}
        for currency, packages in self.root.items():
            seen_counts: set[int] = set()
            for package in packages:
                if package.count in seen_counts:
                    raise ValueError(
                        f"duplicate device package count {package.count} for currency {currency}"
                    )
                seen_counts.add(package.count)
                expected_bonus = bonuses_by_count.setdefault(
                    package.count, float(package.traffic_bonus_gb)
                )
                if not math.isclose(
                    expected_bonus,
                    float(package.traffic_bonus_gb),
                    rel_tol=0,
                    abs_tol=1e-9,
                ):
                    raise ValueError(
                        "device package traffic_bonus_gb must match across currencies "
                        f"for count {package.count}"
                    )
        return self

    def for_currency(self, currency: Currency) -> list[HwidDevicePackage]:
        return list(self.root.get(normalize_currency_key(currency), []) or [])

    @property
    def rub(self) -> list[HwidDevicePackage]:
        return self.for_currency("rub")

    @property
    def stars(self) -> list[HwidDevicePackage]:
        return self.for_currency("stars")

    def has_any(self) -> bool:
        return any(bool(packages) for packages in self.root.values())


class TributeProductConfig(BaseModel):
    product_id: PositiveStrictInt
    link: str

    @field_validator("link")
    @classmethod
    def validate_link(cls, value: str) -> str:
        return validate_tribute_link(value)


class TributePeriodSubscription(NamedTuple):
    """One local period resolved to the Tribute subscription that sells it."""

    months: int
    link: str
    subscription_id: int
    period_id: int


class TributeTariffConfig(BaseModel):
    """Creator-side mapping for one tariff.

    A period may be sold by its own Tribute subscription, with its own share
    link and subscription id, because Tribute publishes one subscription per
    offer rather than one per tariff. ``period_links`` and
    ``period_subscription_ids`` carry those overrides; the tariff-level
    ``link``/``subscription_id`` pair stays as the default for periods that do
    not declare their own, which is what a single-subscription tariff uses.
    """

    link: str | None = None
    subscription_id: PositiveStrictInt | None = None
    period_ids: dict[str, PositiveStrictInt] = Field(default_factory=dict)
    period_links: dict[str, str] = Field(default_factory=dict)
    period_subscription_ids: dict[str, PositiveStrictInt] = Field(default_factory=dict)
    traffic_products: dict[str, TributeProductConfig] = Field(default_factory=dict)
    premium_traffic_products: dict[str, TributeProductConfig] = Field(default_factory=dict)

    @field_validator("link")
    @classmethod
    def validate_link(cls, value: str | None) -> str | None:
        return validate_tribute_link(value) if value is not None else None

    @field_validator("period_links")
    @classmethod
    def validate_period_links(cls, value: dict[str, str]) -> dict[str, str]:
        return {months: validate_tribute_link(link) for months, link in value.items()}

    @field_validator(
        "period_ids",
        "period_links",
        "period_subscription_ids",
        mode="before",
    )
    @classmethod
    def normalize_period_ids(cls, value: Any) -> Any:
        return _normalize_tribute_map_keys(
            value,
            integer=True,
            label="Tribute period month",
        )

    @field_validator("traffic_products", "premium_traffic_products", mode="before")
    @classmethod
    def normalize_product_units(cls, value: Any) -> Any:
        return _normalize_tribute_map_keys(
            value,
            integer=False,
            label="Tribute product unit",
        )

    @model_validator(mode="after")
    def validate_config(self) -> "TributeTariffConfig":
        if (self.link is None) != (self.subscription_id is None):
            raise ValueError("Tribute subscription link and subscription_id must be set together")
        for months in (*self.period_links, *self.period_subscription_ids):
            if months not in self.period_ids:
                raise ValueError(
                    f"Tribute period {months} needs a period_id to override its subscription"
                )
        unresolved = sorted(
            int(months)
            for months in self.period_ids
            if self._resolved_link(months) is None or self._resolved_subscription_id(months) is None
        )
        if unresolved:
            raise ValueError(
                "Tribute periods need a subscription link and subscription_id, either "
                f"their own or the tariff default: {unresolved}"
            )
        period_ids = list(self.period_ids.values())
        if len(period_ids) != len(set(period_ids)):
            raise ValueError("Tribute period IDs must be unique within a tariff")
        provider_periods = [
            (item.subscription_id, item.period_id) for item in self.iter_period_subscriptions()
        ]
        if len(provider_periods) != len(set(provider_periods)):
            raise ValueError("Tribute subscription periods must be unique within a tariff")
        if (
            not self.has_subscription
            and not self.traffic_products
            and not self.premium_traffic_products
        ):
            raise ValueError("Tribute tariff config must define a subscription or digital product")
        return self

    def _resolved_link(self, months: str) -> str | None:
        return self.period_links.get(months) or self.link

    def _resolved_subscription_id(self, months: str) -> int | None:
        return self.period_subscription_ids.get(months) or self.subscription_id

    @property
    def has_subscription(self) -> bool:
        return self.subscription_id is not None or bool(self.period_ids)

    def period_id_for_months(self, months: int) -> int | None:
        return self.period_ids.get(str(int(months)))

    def subscription_for_months(self, months: int) -> TributePeriodSubscription | None:
        """The Tribute subscription that sells one local period, if mapped."""

        key = str(int(months))
        period_id = self.period_ids.get(key)
        link = self._resolved_link(key)
        subscription_id = self._resolved_subscription_id(key)
        if period_id is None or link is None or subscription_id is None:
            return None
        return TributePeriodSubscription(
            months=int(months),
            link=link,
            subscription_id=int(subscription_id),
            period_id=int(period_id),
        )

    def iter_period_subscriptions(self) -> list[TributePeriodSubscription]:
        resolved = (self.subscription_for_months(int(months)) for months in self.period_ids)
        return [item for item in resolved if item is not None]

    def months_for_provider_period(self, subscription_id: int, period_id: int) -> int | None:
        return next(
            (
                item.months
                for item in self.iter_period_subscriptions()
                if item.subscription_id == subscription_id and item.period_id == period_id
            ),
            None,
        )

    def months_for_period_id(self, period_id: int) -> int | None:
        return next(
            (
                int(months)
                for months, configured_period_id in self.period_ids.items()
                if configured_period_id == period_id
            ),
            None,
        )

    def products(self, kind: TributeProductKind) -> dict[str, TributeProductConfig]:
        if kind == "traffic":
            return self.traffic_products
        return self.premium_traffic_products

    def product_for_units(
        self,
        kind: TributeProductKind,
        units: float,
    ) -> TributeProductConfig | None:
        return self.products(kind).get(canonical_tribute_product_unit(units))

    def product_target(self, product_id: int) -> tuple[TributeProductKind, float] | None:
        for kind in TRIBUTE_PRODUCT_KINDS:
            for units, product in self.products(kind).items():
                if product.product_id == product_id:
                    return kind, float(units)
        return None

    def iter_products(
        self,
    ) -> list[tuple[TributeProductKind, str, TributeProductConfig]]:
        return [
            (kind, units, product)
            for kind in TRIBUTE_PRODUCT_KINDS
            for units, product in self.products(kind).items()
        ]


class Tariff(BaseModel):
    key: str
    legacy_keys: list[str] = Field(default_factory=list)
    names: dict[str, str] = Field(default_factory=dict)
    descriptions: dict[str, str] = Field(default_factory=dict)
    premium_names: dict[str, str] = Field(default_factory=dict)
    squad_uuids: list[str] = Field(default_factory=list)
    billing_model: BillingModel
    enabled: bool = True

    monthly_gb: float | None = None
    # None keeps legacy tariffs compatible with USER_TRAFFIC_STRATEGY. The
    # admin editor writes an explicit value for new tariffs and whenever an
    # administrator selects a tariff-specific strategy.
    traffic_limit_strategy: TrafficLimitStrategy | None = None
    prices: dict[str, dict[str, float]] = Field(default_factory=dict)
    prices_rub: dict[str, float] = Field(default_factory=dict)
    prices_stars: dict[str, float] = Field(default_factory=dict)
    referral_bonus_days_inviter: dict[str, int] = Field(default_factory=dict)
    referral_bonus_days_referee: dict[str, int] = Field(default_factory=dict)
    enabled_periods: list[int] = Field(default_factory=list)
    tribute: TributeTariffConfig | None = None
    topup_packages: PackageSet | None = None
    # A resettable quota sold together with a subscription. Slider marks are
    # generated from its step and maximum; price_per_step is a monthly tariff
    # surcharge. This is separate from consumable non-expiring top-ups.
    flexible_traffic_limit: FlexibleTrafficLimitConfig | None = None
    # Admin toggle: offer regular-traffic top-ups regardless of how much of
    # the monthly limit is used (by default the offer unlocks only after
    # usage crosses the unlock threshold, mirroring the web app).
    topup_always_available: bool = False

    traffic_packages: PackageSet | None = None
    conversion_rate_per_gb: float | None = None
    conversion_rate_rub_per_gb: float | None = None
    hwid_device_limit: int | None = None
    hwid_device_packages: HwidDevicePackageSet | None = None
    premium_squad_uuids: list[str] = Field(default_factory=list)
    premium_monthly_gb: float | None = None
    # Premium traffic is quota-controlled by default, including an explicit
    # zero-byte quota. Unlimited premium access must be enabled separately so
    # zero can represent a top-up-only tariff without granting premium squads.
    premium_unlimited: bool = False
    # None means that premium traffic follows the effective regular-traffic
    # strategy. This includes a per-user Remnawave override for period tariffs;
    # traffic tariffs therefore inherit their fixed NO_RESET behavior.
    premium_traffic_limit_strategy: TrafficLimitStrategy | None = None
    premium_topup_packages: PackageSet | None = None
    premium_flexible_traffic_limit: FlexibleTrafficLimitConfig | None = None
    # Same toggle as topup_always_available, scoped to premium-squad traffic.
    premium_topup_always_available: bool = False
    checkout_addons: CheckoutAddonsConfig = Field(default_factory=CheckoutAddonsConfig)

    @model_validator(mode="after")
    def validate_tariff(self) -> "Tariff":
        if not self.key.strip():
            raise ValueError("tariff key must not be empty")
        self.key = self.key.strip()
        self.legacy_keys = list(
            dict.fromkeys(str(key).strip() for key in self.legacy_keys if str(key).strip())
        )
        if self.key in self.legacy_keys:
            raise ValueError(f"tariff {self.key}: legacy_keys must not include the current key")
        self.squad_uuids = list(
            dict.fromkeys(uuid.strip() for uuid in self.squad_uuids if uuid.strip())
        )
        self.premium_squad_uuids = list(
            dict.fromkeys(uuid.strip() for uuid in self.premium_squad_uuids if uuid.strip())
        )
        base_squad_uuids = set(self.squad_uuids)
        overlapping_squads = [uuid for uuid in self.premium_squad_uuids if uuid in base_squad_uuids]
        if overlapping_squads:
            raise ValueError(
                f"tariff {self.key}: squad_uuids and premium_squad_uuids "
                f"must not overlap: {', '.join(overlapping_squads)}"
            )
        if self.hwid_device_limit is not None and self.hwid_device_limit < 0:
            raise ValueError(f"tariff {self.key}: hwid_device_limit must be >= 0")
        if self.premium_monthly_gb is not None and self.premium_monthly_gb < 0:
            raise ValueError(f"tariff {self.key}: premium_monthly_gb must be >= 0")
        if self.premium_topup_packages and not self.premium_squad_uuids:
            raise ValueError(
                f"tariff {self.key}: premium_topup_packages require premium_squad_uuids"
            )
        if self.premium_flexible_traffic_limit and not self.premium_squad_uuids:
            raise ValueError(
                f"tariff {self.key}: premium_flexible_traffic_limit requires premium_squad_uuids"
            )
        if self.premium_monthly_gb and self.premium_monthly_gb > 0 and not self.premium_squad_uuids:
            raise ValueError(f"tariff {self.key}: premium_monthly_gb requires premium_squad_uuids")
        if self.tribute is not None:
            self._validate_tribute_products(
                self.tribute.premium_traffic_products,
                self.premium_topup_packages,
                "premium_topup_packages",
            )

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
            if self.tribute is not None and self.tribute.has_subscription:
                enabled_periods = set(self.enabled_periods)
                unknown_periods = sorted(
                    int(months)
                    for months in self.tribute.period_ids
                    if int(months) not in enabled_periods
                )
                if unknown_periods:
                    raise ValueError(
                        f"period tariff {self.key}: Tribute periods {unknown_periods} "
                        "must be enabled tariff periods"
                    )
            if self.tribute is not None:
                self._validate_tribute_products(
                    self.tribute.traffic_products,
                    self.topup_packages,
                    "topup_packages",
                )
            return self

        if self.tribute is not None and self.tribute.has_subscription:
            raise ValueError(
                f"traffic tariff {self.key}: Tribute subscriptions are only valid "
                "for period tariffs"
            )
        if self.traffic_limit_strategy is not None:
            raise ValueError(
                f"traffic tariff {self.key}: traffic_limit_strategy is only valid "
                "for period tariffs"
            )
        if not self.traffic_packages or not self.traffic_packages.has_any():
            raise ValueError(f"traffic tariff {self.key}: traffic_packages is required")
        if not self.traffic_packages.non_stars_currencies and self.conversion_rate_per_gb is None:
            raise ValueError(
                f"traffic tariff {self.key}: conversion_rate_per_gb is required without fiat packages"  # noqa: E501
            )
        if self.tribute is not None:
            self._validate_tribute_products(
                self.tribute.traffic_products,
                self.traffic_packages,
                "traffic_packages",
            )
        return self

    def _validate_tribute_products(
        self,
        products: dict[str, TributeProductConfig],
        package_set: PackageSet | None,
        package_field: str,
    ) -> None:
        if not products:
            return
        available_units = {
            canonical_tribute_product_unit(package.gb)
            for packages in (package_set.root.values() if package_set is not None else [])
            for package in packages
        }
        unknown_units = sorted(
            set(products) - available_units,
            key=lambda value: Decimal(value),
        )
        if unknown_units:
            raise ValueError(
                f"tariff {self.key}: Tribute product units {unknown_units} "
                f"must reference existing {package_field}"
            )

    def _normalize_period_price_map(
        self,
        values: dict[str, float],
        field_name: str,
    ) -> dict[str, float]:
        normalized: dict[str, float] = {}
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
        values: dict[str, dict[str, float]],
    ) -> dict[str, dict[str, float]]:
        normalized: dict[str, dict[str, float]] = {}
        for currency, price_map in (values or {}).items():
            key = normalize_currency_key(currency, default="")
            if not key:
                raise ValueError(f"tariff {self.key}: price currency must not be empty")
            normalized[key] = self._normalize_period_price_map(price_map or {}, f"prices.{key}")
        return normalized

    def _normalize_referral_bonus_map(
        self, values: dict[str, int], field_name: str
    ) -> dict[str, int]:
        normalized: dict[str, int] = {}
        for period, days in (values or {}).items():
            try:
                months = int(float(str(period).strip()))
                bonus_days = int(float(days))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"tariff {self.key}: {field_name} contains invalid entry") from exc
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

    def premium_name(self, lang: str, fallback: str = "ru", default: str | None = None) -> str:
        return (
            self.premium_names.get(lang)
            or self.premium_names.get(fallback)
            or (default or "Premium servers")
        )

    @property
    def monthly_bytes(self) -> int:
        if self.monthly_gb is None or self.monthly_gb <= 0:
            return 0
        return int(float(self.monthly_gb) * (1024**3))

    def period_price(self, months: int, currency: Currency = "rub") -> float | None:
        source = self.prices.get(normalize_currency_key(currency), {})
        value = source.get(str(months))
        return float(value) if value is not None else None

    def referral_inviter_bonus_days(self, months: int) -> int | None:
        value = self.referral_bonus_days_inviter.get(str(int(months)))
        return int(value) if value is not None else None

    def referral_referee_bonus_days(self, months: int) -> int | None:
        value = self.referral_bonus_days_referee.get(str(int(months)))
        return int(value) if value is not None else None

    def min_period_price(self, currency: Currency = "rub") -> float | None:
        key = normalize_currency_key(currency)
        source = self.prices.get(key, {})
        prices = [
            float(source[str(months)])
            for months in self.enabled_periods
            if source.get(str(months), 0) and source.get(str(months), 0) > 0
        ]
        return min(prices) if prices else None

    def min_period_price_rub(self) -> float | None:
        return self.min_period_price("rub")

    def min_traffic_package(self, currency: Currency = "rub") -> TrafficPackage | None:
        packages = self.traffic_packages.for_currency(currency) if self.traffic_packages else []
        return min(packages, key=lambda pkg: pkg.price) if packages else None

    def min_traffic_package_rub(self) -> TrafficPackage | None:
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
        if self.premium_unlimited or self.premium_monthly_gb is None:
            return 0
        return max(0, int(float(self.premium_monthly_gb) * (1024**3)))

    def has_premium_squad_limit(self) -> bool:
        return bool(self.premium_squad_uuids and not self.premium_unlimited)


class TariffsConfig(BaseModel):
    default_tariff: str
    referral_welcome_bonus_tariff: str | None = None
    default_currency: str = DEFAULT_TARIFF_CURRENCY
    topup_packages_default: PackageSet | None = None
    tariffs: list[Tariff]

    @model_validator(mode="after")
    def validate_config(self) -> "TariffsConfig":
        self.default_currency = normalize_currency_key(self.default_currency)
        if self.default_currency == STARS_TARIFF_CURRENCY:
            raise ValueError("default_currency must be a non-Stars payment currency")
        key_owners: dict[str, str] = {}
        tribute_subscription_owners: dict[int, str] = {}
        tribute_period_owners: dict[tuple[int, int], tuple[str, int]] = {}
        tribute_product_owners: dict[int, tuple[str, TributeProductKind, str]] = {}
        for tariff in self.tariffs:
            validate_checkout_addons(tariff, default_currency=self.default_currency)
            for key in (tariff.key, *tariff.legacy_keys):
                previous_owner = key_owners.get(key)
                if previous_owner is not None:
                    raise ValueError(
                        f"tariff keys and legacy_keys must be unique: {key} "
                        f"is used by {previous_owner} and {tariff.key}"
                    )
                key_owners[key] = tariff.key
            tribute = tariff.tribute
            if tribute is None:
                continue
            # A period may carry its own subscription, so ownership is checked
            # per resolved (subscription, period) pair rather than once per
            # tariff.
            for item in tribute.iter_period_subscriptions():
                target = (tariff.key, item.months)
                provider_period = (item.subscription_id, item.period_id)
                previous_target = tribute_period_owners.get(provider_period)
                if previous_target is not None and previous_target != target:
                    raise ValueError(
                        "Tribute subscription period "
                        f"{item.subscription_id}/{item.period_id} cannot map to both "
                        f"{previous_target[0]}/{previous_target[1]} and "
                        f"{target[0]}/{target[1]}"
                    )
                tribute_period_owners[provider_period] = target
                previous_subscription_owner = tribute_subscription_owners.get(item.subscription_id)
                if (
                    previous_subscription_owner is not None
                    and previous_subscription_owner != tariff.key
                ):
                    raise ValueError(
                        f"Tribute subscription {item.subscription_id} cannot belong to "
                        f"both tariffs {previous_subscription_owner} and {tariff.key}"
                    )
                tribute_subscription_owners[item.subscription_id] = tariff.key
            for kind, units, product in tribute.iter_products():
                product_target_owner = (tariff.key, kind, units)
                previous_product_target = tribute_product_owners.get(product.product_id)
                if previous_product_target is not None:
                    raise ValueError(
                        f"Tribute product {product.product_id} cannot map to both "
                        f"{previous_product_target[0]}/{previous_product_target[1]}/"
                        f"{previous_product_target[2]} and {product_target_owner[0]}/"
                        f"{product_target_owner[1]}/{product_target_owner[2]}"
                    )
                tribute_product_owners[product.product_id] = product_target_owner
        active = [tariff for tariff in self.tariffs if tariff.enabled]
        if not active:
            raise ValueError("at least one enabled tariff is required")
        active_keys = {tariff.key for tariff in active}
        if self.default_tariff not in active_keys:
            raise ValueError("default_tariff must reference an enabled tariff")
        welcome_tariff_key = str(self.referral_welcome_bonus_tariff or "").strip()
        if welcome_tariff_key:
            welcome_tariff = self.get(welcome_tariff_key)
            if welcome_tariff is None or not welcome_tariff.enabled:
                raise ValueError("referral_welcome_bonus_tariff must reference an enabled tariff")
            if welcome_tariff.billing_model != "period":
                raise ValueError("referral_welcome_bonus_tariff must reference a period tariff")
            self.referral_welcome_bonus_tariff = welcome_tariff.key
        else:
            self.referral_welcome_bonus_tariff = None
        return self

    @property
    def referral_welcome_bonus_tariff_key(self) -> str:
        return self.referral_welcome_bonus_tariff or self.default_tariff

    @property
    def enabled_tariffs(self) -> list[Tariff]:
        return [tariff for tariff in self.tariffs if tariff.enabled]

    def get(self, key: str) -> Tariff | None:
        return next(
            (tariff for tariff in self.tariffs if tariff.key == key or key in tariff.legacy_keys),
            None,
        )

    def require(self, key: str) -> Tariff:
        tariff = self.get(key)
        if not tariff or not tariff.enabled:
            raise KeyError(f"Unknown or disabled tariff: {key}")
        return tariff

    def tribute_target(self, subscription_id: int, period_id: int) -> tuple[Tariff, int] | None:
        for tariff in self.tariffs:
            tribute = tariff.tribute
            if tribute is None:
                continue
            months = tribute.months_for_provider_period(subscription_id, period_id)
            if months is not None:
                return tariff, months
        return None

    def tribute_product_target(
        self,
        product_id: int,
    ) -> tuple[Tariff, TributeProductKind, float] | None:
        for tariff in self.tariffs:
            tribute = tariff.tribute
            if tribute is None:
                continue
            target = tribute.product_target(product_id)
            if target is not None:
                kind, units = target
                return tariff, kind, units
        return None

    @property
    def default(self) -> Tariff:
        return self.require(self.default_tariff)

    @property
    def default_payment_currency_code(self) -> str:
        return payment_currency_code(self.default_currency)

    def topup_packages_for(self, tariff: Tariff) -> PackageSet | None:
        if tariff.billing_model == "traffic":
            return tariff.traffic_packages
        return tariff.topup_packages


def load_tariffs_config(path: str | Path) -> TariffsConfig | None:
    config_path = Path(path)
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
        return TariffsConfig.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        logger.critical("Failed to load tariffs config from %s: %s", config_path, exc)
        raise
