"""Platega provider facade."""

from bot.payment_providers.platega.service import (
    CRYPTO_SPEC,
    SBP_SPEC,
    SPECS,
    SUBSCRIPTION_SPEC,
    PlategaConfig,
    PlategaCryptoPresentation,
    PlategaSbpPresentation,
    PlategaService,
    PlategaSubscriptionPresentation,
    create_crypto_webapp_payment,
    create_sbp_webapp_payment,
    create_service,
    create_subscription_webapp_payment,
    pay_platega_callback_handler,
    platega_webhook_route,
    reuse_webapp_payment,
    router,
)
from bot.payment_providers.platega.subscriptions import (
    SUBSCRIPTION_INTERVAL_BY_MONTHS,
    subscription_interval_for_months,
)

__all__ = [
    "CRYPTO_SPEC",
    "SBP_SPEC",
    "SPECS",
    "SUBSCRIPTION_INTERVAL_BY_MONTHS",
    "SUBSCRIPTION_SPEC",
    "PlategaConfig",
    "PlategaCryptoPresentation",
    "PlategaSbpPresentation",
    "PlategaService",
    "PlategaSubscriptionPresentation",
    "create_crypto_webapp_payment",
    "create_sbp_webapp_payment",
    "create_service",
    "create_subscription_webapp_payment",
    "pay_platega_callback_handler",
    "platega_webhook_route",
    "reuse_webapp_payment",
    "router",
    "subscription_interval_for_months",
]
