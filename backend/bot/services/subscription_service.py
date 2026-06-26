"""Compatibility facade for the subscription service."""

from bot.services.subscription_service_impl.core import SubscriptionService

SubscriptionService.__module__ = __name__

__all__ = ["SubscriptionService"]
