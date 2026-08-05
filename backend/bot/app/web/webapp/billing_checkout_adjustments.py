"""Compatibility imports for checkout adjustment logic shared with Telegram flows."""

from bot.services.checkout_promos import (
    CheckoutPromoError,
    CheckoutPromoResult,
    resolve_checkout_promo,
)

_resolve_checkout_promo = resolve_checkout_promo

__all__ = ["CheckoutPromoError", "CheckoutPromoResult", "_resolve_checkout_promo"]
