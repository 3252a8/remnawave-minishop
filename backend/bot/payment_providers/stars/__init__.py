"""Stars provider facade."""

from bot.payment_providers.stars.service import (
    SPEC,
    StarsPresentation,
    StarsService,
    create_service,
    create_webapp_payment,
    handle_pre_checkout_query,
    handle_successful_stars_payment,
    pay_stars_callback_handler,
    router,
)

__all__ = [
    "SPEC",
    "StarsPresentation",
    "StarsService",
    "create_service",
    "create_webapp_payment",
    "handle_pre_checkout_query",
    "handle_successful_stars_payment",
    "pay_stars_callback_handler",
    "router",
]
