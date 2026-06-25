"""Severpay provider facade.

Public surface only: the provider spec, service, config/presentation classes,
and the entrypoints registered on ``SPEC``. Internal helpers live in
``.service`` (import that module directly when patching in tests).
"""

from bot.payment_providers.severpay.service import (
    SPEC,
    SeverPayConfig,
    SeverPayPresentation,
    SeverPayService,
    create_service,
    create_webapp_payment,
    pay_severpay_callback_handler,
    reuse_webapp_payment,
    severpay_webhook_route,
)

__all__ = [
    "SPEC",
    "SeverPayConfig",
    "SeverPayPresentation",
    "SeverPayService",
    "create_service",
    "create_webapp_payment",
    "pay_severpay_callback_handler",
    "reuse_webapp_payment",
    "severpay_webhook_route",
]
