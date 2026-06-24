"""Cloudpayments provider facade."""

from bot.payment_providers.cloudpayments.service import (
    SPEC,
    CloudPaymentsConfig,
    CloudPaymentsPresentation,
    CloudPaymentsService,
    cloudpayments_webhook_route,
    create_service,
    create_webapp_payment,
    pay_cloudpayments_callback_handler,
    reuse_webapp_payment,
    router,
)

__all__ = [
    "SPEC",
    "CloudPaymentsConfig",
    "CloudPaymentsPresentation",
    "CloudPaymentsService",
    "cloudpayments_webhook_route",
    "create_service",
    "create_webapp_payment",
    "pay_cloudpayments_callback_handler",
    "reuse_webapp_payment",
    "router",
]
