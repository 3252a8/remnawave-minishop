"""Wata provider facade."""

from bot.payment_providers.wata.config import (
    WataConfig,
    WataCryptoPresentation,
    WataPresentation,
    WataSubscriptionPresentation,
)
from bot.payment_providers.wata.provider import (
    CRYPTO_SPEC,
    SPEC,
    SPECS,
    SUBSCRIPTION_SPEC,
    create_service,
    create_webapp_payment,
    pay_wata_callback_handler,
    reuse_webapp_payment,
    router,
)
from bot.payment_providers.wata.service import WataService
from bot.payment_providers.wata.webhook import wata_webhook_route

__all__ = [
    "CRYPTO_SPEC",
    "SPEC",
    "SPECS",
    "SUBSCRIPTION_SPEC",
    "WataConfig",
    "WataCryptoPresentation",
    "WataPresentation",
    "WataService",
    "WataSubscriptionPresentation",
    "create_service",
    "create_webapp_payment",
    "pay_wata_callback_handler",
    "reuse_webapp_payment",
    "router",
    "wata_webhook_route",
]
