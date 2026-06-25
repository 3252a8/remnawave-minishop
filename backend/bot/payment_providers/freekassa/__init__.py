"""Freekassa provider facade."""

from bot.payment_providers.freekassa.service import (
    SPEC,
    FreeKassaConfig,
    FreeKassaPresentation,
    FreeKassaService,
    create_service,
    create_webapp_payment,
    freekassa_webhook_route,
    pay_fk_callback_handler,
    reuse_webapp_payment,
    router,
)

__all__ = [
    "SPEC",
    "FreeKassaConfig",
    "FreeKassaPresentation",
    "FreeKassaService",
    "create_service",
    "create_webapp_payment",
    "freekassa_webhook_route",
    "pay_fk_callback_handler",
    "reuse_webapp_payment",
    "router",
]
