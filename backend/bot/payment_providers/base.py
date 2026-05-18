from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Optional, Sequence


@dataclass(frozen=True)
class ServiceFactoryContext:
    settings: Any
    bot: Any
    async_session_factory: Any
    i18n: Any
    bot_username_for_default_return: str
    subscription_service: Any
    referral_service: Any


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

    @property
    def settings_key(self) -> str:
        return self.id.upper()

    @property
    def default_telegram_emoji(self) -> str:
        return self.telegram_emoji or self.emoji

    @property
    def method_ids(self) -> tuple[str, ...]:
        return (self.id, *tuple(self.aliases))

    def is_enabled(self, settings: Any) -> bool:
        return bool(self.enabled(settings))

    def is_service_configured(self, app: Any) -> bool:
        if not self.requires_configured_service:
            return True
        if not self.service_key:
            return True
        service = app.get(self.service_key) if hasattr(app, "get") else None
        return bool(service and getattr(service, "configured", False))

    def is_visible(self, settings: Any, app: Any) -> bool:
        return self.is_enabled(settings) and self.is_service_configured(app)

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
