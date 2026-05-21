from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Optional, Sequence, Type

from pydantic_settings import BaseSettings, SettingsConfigDict


def provider_env_file() -> Optional[str]:
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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@dataclass(frozen=True)
class ProviderConfigBundle:
    """Functional config + presentation overrides for a single provider."""

    config: Optional[ProviderEnvConfig] = None
    presentation: Optional[ProviderEnvConfig] = None


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
    min: Optional[float] = None
    max: Optional[float] = None
    choices: Optional[Sequence[tuple[str, str]]] = None
    subsection: Optional[str] = None
    target: str = "config"  # "config" or "presentation" — which bundle slot it writes to
    attr: Optional[str] = (
        None  # attribute name on the target model; defaults to key without env_prefix
    )


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

    def config_for(self, service_key: Optional[str]) -> Optional[ProviderConfigBundle]:
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
    stars_price: Optional[int]
    description: str
    sale_mode: str
    traffic_gb: Optional[float] = None


EnabledPredicate = Callable[[Any], bool]
ServiceFactory = Callable[[ServiceFactoryContext], Any]
WebhookPathGetter = Callable[[Any], str]
WebhookRoute = Callable[[Any], Awaitable[Any]]
WebAppPaymentFactory = Callable[[WebAppPaymentContext], Awaitable[Any]]


@dataclass(frozen=True)
class PaymentProviderSpec:
    id: str
    provider_key: str
    label: str
    pending_status: str
    enabled: EnabledPredicate
    service_key: Optional[str] = None
    callback_prefix: Optional[str] = None
    webapp_label: Optional[str] = None
    webapp_labels: Optional[Mapping[str, str]] = None
    telegram_labels: Optional[Mapping[str, str]] = None
    aliases: Sequence[str] = ()
    router: Any = None
    create_service: Optional[ServiceFactory] = None
    webhook_path: Optional[WebhookPathGetter] = None
    webhook_route: Optional[WebhookRoute] = None
    webhook_requires_base_url: bool = False
    create_webapp_payment: Optional[WebAppPaymentFactory] = None
    requires_configured_service: bool = True
    price_source: str = "rub"
    emoji: str = "💳"
    webapp_icon: Optional[str] = None
    telegram_emoji: Optional[str] = None
    config_class: Optional[Type[ProviderEnvConfig]] = None
    presentation_class: Optional[Type[ProviderEnvConfig]] = None
    manifest_fields: Sequence[ProviderManifestField] = ()

    @property
    def settings_key(self) -> str:
        return self.id.upper()

    @property
    def default_telegram_emoji(self) -> str:
        return self.telegram_emoji or self.emoji

    @property
    def method_ids(self) -> tuple[str, ...]:
        return (self.id, *tuple(self.aliases))

    def is_enabled(self, source: Any) -> bool:
        # If this spec carries a provider-local config_class, prefer the live
        # config bundle so callers can pass plain Settings without having to
        # know about provider-local env layouts.
        if self.config_class is not None and self.service_key:
            from .registry import get_provider_bundle

            bundle = get_provider_bundle(self.service_key)
            if bundle and bundle.config is not None:
                return bool(self.enabled(bundle.config))
        return bool(self.enabled(source))

    def is_service_configured(self, app: Any) -> bool:
        if not self.requires_configured_service:
            return True
        if not self.service_key:
            return True
        service = app.get(self.service_key) if hasattr(app, "get") else None
        return bool(service and getattr(service, "configured", False))

    def is_visible(self, source: Any, app: Any) -> bool:
        return self.is_enabled(source) and self.is_service_configured(app)

    def load_router(self) -> Any:
        return self.router

    def load_webhook_route(self) -> Optional[WebhookRoute]:
        return self.webhook_route

    def callback_data(
        self,
        *,
        value: str,
        rub_price: float,
        stars_price: Optional[int],
        sale_mode: str,
    ) -> Optional[str]:
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
    webapp_icon: Optional[str]
    telegram_label: str
    telegram_emoji: str
    telegram_customized: bool
