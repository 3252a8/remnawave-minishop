"""Platega provider facade."""

from bot.payment_providers.platega.service import (
    CRYPTO_SPEC,
    SBP_SPEC,
    SPECS,
    PlategaConfig,
    PlategaCryptoPresentation,
    PlategaSbpPresentation,
    PlategaService,
    create_crypto_webapp_payment,
    create_sbp_webapp_payment,
    create_service,
    pay_platega_callback_handler,
    platega_webhook_route,
    reuse_webapp_payment,
    router,
)

__all__ = [
    "CRYPTO_SPEC",
    "SBP_SPEC",
    "SPECS",
    "PlategaConfig",
    "PlategaCryptoPresentation",
    "PlategaSbpPresentation",
    "PlategaService",
    "create_crypto_webapp_payment",
    "create_sbp_webapp_payment",
    "create_service",
    "pay_platega_callback_handler",
    "platega_webhook_route",
    "reuse_webapp_payment",
    "router",
]
