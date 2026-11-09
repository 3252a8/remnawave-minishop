"""PayHot hosted payment provider."""

from .config import PayHotConfig
from .service import (
    SPEC,
    PayHotService,
    create_service,
    create_webapp_payment,
    pay_payhot_callback_handler,
    payhot_webhook_route,
    reuse_webapp_payment,
    router,
)

__all__ = [
    "SPEC",
    "PayHotConfig",
    "PayHotService",
    "create_service",
    "create_webapp_payment",
    "pay_payhot_callback_handler",
    "payhot_webhook_route",
    "reuse_webapp_payment",
    "router",
]
