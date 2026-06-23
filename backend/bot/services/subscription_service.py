"""Compatibility facade for the subscription service."""

# ruff: noqa: F401

from bot.services.subscription_service_impl._runtime import (
    TYPE_CHECKING,
    Any,
    AsyncSession,
    Bot,
    Dict,
    EmailAuthService,
    JsonI18n,
    List,
    Optional,
    PanelApiService,
    Settings,
    Subscription,
    SubscriptionServiceMixinContract,
    Tariff,
    TariffsConfig,
    Tuple,
    User,
    add_months,
    datetime,
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
    logging,
    math,
    month_start,
    normalize_traffic_limit_strategy,
    panel_description_from_profile,
    payment_dal,
    prepare_config_links,
    promo_code_dal,
    render_payment_success,
    subscription_dal,
    tariff_dal,
    timedelta,
    timezone,
    user_billing_dal,
    user_dal,
)
from bot.services.subscription_service_impl.core import SubscriptionService

SubscriptionService.__module__ = __name__

__all__ = ["SubscriptionService"]
