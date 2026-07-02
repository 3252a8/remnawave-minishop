from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

from aiohttp import web
from pydantic_settings import BaseSettings, SettingsConfigDict


def provider_env_file() -> str | None:
    """Resolve the env file every provider config should read.

    Tests set ``PROVIDER_ENV_FILE=""`` via conftest so per-provider
    BaseSettings models don't pick up real credentials from the project's
    .env. Production reads from ``.env`` as usual.
    """
    value = os.environ.get("PROVIDER_ENV_FILE")
    if value is None:
        return ".env"
    return value or None


class ProviderEnvConfig(BaseSettings):
    """Base class for per-provider env-config models.

    Subclasses declare their own ``env_prefix`` (e.g. ``HELEKET_``) and
    fields, so the provider module is the single source of truth for the
    env vars it consumes — no edits in the global ``Settings`` required.
    """

    ADMIN_ONLY_ENABLED: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


def provider_runtime_enabled(config: Any, *admin_only_attrs: str) -> bool:
    """Return True when a provider should run for public or admin-only payments."""

    if bool(getattr(config, "ENABLED", False)):
        return True
    attrs = admin_only_attrs or ("ADMIN_ONLY_ENABLED",)
    return any(bool(getattr(config, attr, False)) for attr in attrs)


@dataclass(frozen=True)
class ProviderConfigBundle:
    """Functional config + presentation overrides for a single provider."""

    config: ProviderEnvConfig | None = None
    presentation: ProviderEnvConfig | None = None


@dataclass(frozen=True)
class ProviderManifestField:
    """Self-contained manifest entry declared by a provider module.

    Aggregated by the registry into the admin settings manifest, so the
    admin UI gets per-provider fields without anyone editing
    ``admin_settings_manifest.py``.
    """

    key: str
    type: str
    label: str
    description: str = ""
    placeholder: str = ""
    secret: bool = False
    optional: bool = True
    min: float | None = None
    max: float | None = None
    choices: Sequence[tuple[str, str]] | None = None
    subsection: str | None = None
    target: str = "config"  # "config" or "presentation" — which bundle slot it writes to
    attr: str | None = (
        None  # attribute name on the target model; defaults to key without env_prefix
    )
    i18n_label_key: str | None = None
    i18n_description_key: str | None = None
    i18n_subsection_key: str | None = None


@dataclass(frozen=True)
class ServiceFactoryContext:
    settings: Any
    bot: Any
    async_session_factory: Any
    i18n: Any
    bot_username_for_default_return: str
    subscription_service: Any
    referral_service: Any
    provider_configs: Mapping[str, ProviderConfigBundle] = field(default_factory=dict)

    def config_for(self, service_key: str | None) -> ProviderConfigBundle | None:
        if not service_key:
            return None
        return self.provider_configs.get(service_key)


@dataclass(frozen=True)
class WebAppPaymentContext:
    request: Any
    session: Any
    user_id: int
    method: str
    months: Any
    price: float
    stars_price: int | None
    description: str
    sale_mode: str
    currency: str = "RUB"
    traffic_gb: float | None = None
    hwid_device_count: int | None = None
    hwid_valid_from: Any | None = None
    hwid_valid_until: Any | None = None
    hwid_pricing_period_months: int | None = None
    hwid_proration_ratio: float | None = None
    hwid_full_price: float | None = None
    promo_code_id: int | None = None
    promo_effect_summary: str | None = None
    promo_bonus_days: int | None = None
    promo_discount_percent: float | None = None
    promo_duration_multiplier: float | None = None
    promo_traffic_multiplier: float | None = None
    promo_applies_to: str | None = None
    promo_min_subscription_months: int | None = None
    promo_min_traffic_gb: float | None = None
    checkout_base_amount: float | None = None
    checkout_discount_amount: float | None = None
    checkout_charged_months: int | None = None
    checkout_charged_gb: float | None = None
    checkout_quoted_at: Any | None = None


@dataclass(frozen=True)
class ProviderWebhookPayload:
    raw_body: bytes
    signature: str = ""
    data: Mapping[str, Any] | None = None


class BaseProviderService(ABC):
    provider_key: ClassVar[str] = "provider"
    disabled_response_text: ClassVar[str | None] = None

    @property
    @abstractmethod
    def configured(self) -> bool:
        """Return whether the provider is configured for runtime webhook handling."""

    @property
    def webhook_available(self) -> bool:
        return self.configured

    async def parse_payload(self, request: web.Request) -> ProviderWebhookPayload:
        return ProviderWebhookPayload(raw_body=await request.read())

    @abstractmethod
    def verify_signature(self, payload: ProviderWebhookPayload) -> bool:
        """Return True when the provider webhook signature is trusted."""

    @abstractmethod
    async def handle_verified_webhook(
        self,
        request: web.Request,
        payload: ProviderWebhookPayload,
    ) -> web.Response:
        """Process a verified provider webhook payload."""

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.webhook_available:
            return web.Response(status=503, text=self.disabled_response_text)
        payload = await self.parse_payload(request)
        if not self.verify_signature(payload):
            return web.Response(status=401)
        return await self.handle_verified_webhook(request, payload)


EnabledPredicate = Callable[[Any], bool]
ServiceFactory = Callable[[ServiceFactoryContext], object]
WebhookPathGetter = Callable[[Any], str]
WebhookRoute = Callable[[Any], Awaitable[Any]]
WebAppPaymentFactory = Callable[[WebAppPaymentContext], Awaitable[Any]]
ReusableWebAppPaymentResolver = Callable[[WebAppPaymentContext, Any], Awaitable[str | None]]
CurrencySupportResolver = Callable[[Any], Sequence[str] | None]
PaymentAmountResolver = Callable[[Any, Any, Any], bool]
PaymentMinimumResolver = Callable[[Any, Any], Mapping[str, Any] | None]


def normalize_payment_currency_code(value: Any, default: str = "RUB") -> str:
    text = str(value or "").strip().upper()
    if not text:
        text = str(default).strip().upper() if default is not None else ""
    if not text:
        return ""
    aliases = {"RUR": "RUB", "STARS": "XTR", "STAR": "XTR"}
    normalized = aliases.get(text, text)
    return "".join(ch for ch in normalized if ch.isalnum() or ch in {"_", "-"}).strip("_-")


def parse_supported_currency_codes(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raw_items = value.replace(";", ",").split(",")
    else:
        raw_items = list(value)
    currencies: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        code = normalize_payment_currency_code(item, default="")
        if not code or code in seen:
            continue
        seen.add(code)
        currencies.append(code)
    return tuple(currencies)


@dataclass(frozen=True)
class PaymentProviderSpec:
    id: str
    provider_key: str
    label: str
    pending_status: str
    enabled: EnabledPredicate
    service_key: str | None = None
    callback_prefix: str | None = None
    webapp_label: str | None = None
    webapp_labels: Mapping[str, str] | None = None
    telegram_labels: Mapping[str, str] | None = None
    aliases: Sequence[str] = ()
    router: Any = None
    create_service: ServiceFactory | None = None
    webhook_path: WebhookPathGetter | None = None
    webhook_route: WebhookRoute | None = None
    webhook_requires_base_url: bool = False
    create_webapp_payment: WebAppPaymentFactory | None = None
    reuse_webapp_payment: ReusableWebAppPaymentResolver | None = None
    requires_configured_service: bool = True
    price_source: str = "rub"
    emoji: str = "💳"
    webapp_icon: str | None = None
    telegram_emoji: str | None = None
    config_class: type[ProviderEnvConfig] | None = None
    presentation_class: type[ProviderEnvConfig] | None = None
    manifest_fields: Sequence[ProviderManifestField] = ()
    enabled_manifest_key: str | None = None
    admin_only_manifest_key: str | None = None
    admin_only_config_attr: str = "ADMIN_ONLY_ENABLED"
    admin_only_enabled: EnabledPredicate | None = None
    supports_recurring: bool = False
    supported_currencies: Sequence[str] | None = ("RUB",)
    supported_currencies_resolver: CurrencySupportResolver | None = None
    payment_amount_resolver: PaymentAmountResolver | None = None
    payment_minimum_resolver: PaymentMinimumResolver | None = None
    currency_support_note: str = ""
    currency_support_url: str | None = None

    @property
    def settings_key(self) -> str:
        return self.id.upper()

    @property
    def enabled_field_key(self) -> str:
        return self.enabled_manifest_key or f"{self.settings_key}_ENABLED"

    @property
    def admin_only_field_key(self) -> str:
        return self.admin_only_manifest_key or f"{self.settings_key}_ADMIN_ONLY_ENABLED"

    @property
    def default_telegram_emoji(self) -> str:
        return self.telegram_emoji or self.emoji

    @property
    def method_ids(self) -> tuple[str, ...]:
        return (self.id, *tuple(self.aliases))

    def _predicate_value(self, predicate: EnabledPredicate, source: Any) -> bool:
        # If this spec carries a provider-local config_class, prefer the live
        # config bundle so callers can pass plain Settings without having to
        # know about provider-local env layouts.
        if self.config_class is not None and self.service_key:
            from .registry import get_provider_bundle

            bundle = get_provider_bundle(self.service_key)
            if bundle and bundle.config is not None:
                return bool(predicate(bundle.config))
        return bool(predicate(source))

    def is_enabled(self, source: Any) -> bool:
        return self._predicate_value(self.enabled, source)

    def is_admin_only_enabled(self, source: Any) -> bool:
        if self.admin_only_enabled is not None:
            return self._predicate_value(self.admin_only_enabled, source)
        if self.config_class is not None and self.service_key:
            from .registry import get_provider_bundle

            bundle = get_provider_bundle(self.service_key)
            if bundle and bundle.config is not None:
                return bool(getattr(bundle.config, self.admin_only_config_attr, False))
        return bool(getattr(source, self.admin_only_field_key, False))

    def is_effectively_enabled(self, source: Any) -> bool:
        return self.is_enabled(source) or self.is_admin_only_enabled(source)

    def _is_admin_user(
        self,
        source: Any,
        *,
        user_id: int | None = None,
        is_admin: bool | None = None,
    ) -> bool:
        if is_admin is not None:
            return bool(is_admin)
        if user_id is None:
            return False
        try:
            normalized_user_id = int(user_id)
        except (TypeError, ValueError):
            return False
        try:
            admin_ids = {int(item) for item in (getattr(source, "ADMIN_IDS", None) or [])}
        except (TypeError, ValueError):
            return False
        return normalized_user_id in admin_ids

    def is_service_configured(self, app: Any) -> bool:
        if not self.requires_configured_service:
            return True
        if not self.service_key:
            return True
        service = app.get(self.service_key) if hasattr(app, "get") else None
        return bool(service and getattr(service, "configured", False))

    def _currency_source(self, source: Any) -> Any:
        if self.config_class is not None and self.service_key:
            from .registry import get_provider_bundle

            bundle = get_provider_bundle(self.service_key)
            if bundle and bundle.config is not None:
                return bundle.config
        return source

    def supported_currency_codes(self, source: Any = None) -> tuple[str, ...] | None:
        if self.price_source == "stars":
            return ("XTR",)
        source_for_currency = self._currency_source(source)
        if self.supported_currencies_resolver is not None:
            resolved = self.supported_currencies_resolver(source_for_currency)
            if resolved is None:
                return None
            return parse_supported_currency_codes(resolved)
        if self.supported_currencies is None:
            return None
        return parse_supported_currency_codes(self.supported_currencies)

    def supports_currency(self, source: Any, currency: Any) -> bool:
        supported = self.supported_currency_codes(source)
        if supported is None:
            return True
        return normalize_payment_currency_code(currency) in supported

    def is_usable_for_payment_currency(self, source: Any, currency: Any) -> bool:
        if self.price_source == "stars":
            return True
        return self.supports_currency(source, currency)

    def payment_minimum(self, source: Any, currency: Any) -> Mapping[str, Any] | None:
        if self.payment_minimum_resolver is None:
            return None
        source_for_amount = self._currency_source(source)
        try:
            return self.payment_minimum_resolver(source_for_amount, currency)
        except Exception:
            return None

    def is_usable_for_payment_amount(self, source: Any, currency: Any, amount: Any) -> bool:
        if self.price_source == "stars" or self.payment_amount_resolver is None:
            return True
        source_for_amount = self._currency_source(source)
        try:
            return bool(self.payment_amount_resolver(source_for_amount, currency, amount))
        except Exception:
            return True

    def is_usable_for_payment(self, source: Any, currency: Any, amount: Any) -> bool:
        return self.is_usable_for_payment_currency(
            source,
            currency,
        ) and self.is_usable_for_payment_amount(source, currency, amount)

    def is_visible(self, source: Any, app: Any) -> bool:
        return self.is_enabled(source) and self.is_service_configured(app)

    def is_available_to_user(
        self,
        source: Any,
        app: Any = None,
        *,
        user_id: int | None = None,
        is_admin: bool | None = None,
        require_configured: bool = True,
    ) -> bool:
        public_enabled = self.is_enabled(source)
        admin_only_visible = self.is_admin_only_enabled(source) and self._is_admin_user(
            source,
            user_id=user_id,
            is_admin=is_admin,
        )
        if not (public_enabled or admin_only_visible):
            return False
        if require_configured and app is not None and not self.is_service_configured(app):
            return False
        return True

    def is_visible_for_user(
        self,
        source: Any,
        app: Any,
        *,
        user_id: int | None = None,
        is_admin: bool | None = None,
    ) -> bool:
        return self.is_available_to_user(
            source,
            app,
            user_id=user_id,
            is_admin=is_admin,
            require_configured=True,
        )

    def load_router(self) -> Any:
        return self.router

    def load_webhook_route(self) -> WebhookRoute | None:
        return self.webhook_route

    def callback_data(
        self,
        *,
        value: str,
        rub_price: float,
        stars_price: int | None,
        sale_mode: str,
    ) -> str | None:
        if not self.callback_prefix:
            return None
        if self.price_source == "stars":
            if stars_price is None:
                return None
            price: Any = stars_price
        else:
            price = rub_price
        return f"{self.callback_prefix}:{value}:{price}:{sale_mode}"


@dataclass(frozen=True)
class PaymentProviderPresentation:
    webapp_label: str
    webapp_icon: str | None
    telegram_label: str
    telegram_emoji: str
    telegram_customized: bool
