"""Auto-renew capability flags for the Web App subscription payload.

Two disjoint provider families reach the same toggle:

* saved-method providers (YooKassa, CloudPayments, Stripe), where our renewal
  worker initiates the charge — the customer may switch the toggle both ways;
* provider-managed mandates (Platega SBP subscriptions), where the provider
  owns the schedule — the toggle may only be switched *off*, which cancels the
  mandate upstream. ``can_enable`` stays False so the Web App never offers to
  turn one back on; the payer authorizes a new mandate at checkout instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AutoRenewCapabilities:
    supported: bool
    service_active: bool
    provider_label: str | None

    def payload_fields(self, *, enabled: bool) -> dict[str, Any]:
        return {
            "auto_renew_available": bool(self.supported and (enabled or self.service_active)),
            "auto_renew_can_enable": bool(self.supported and self.service_active),
            "auto_renew_provider_label": self.provider_label,
        }


def resolve_auto_renew_capabilities(
    provider: str | None,
    *,
    settings: Any,
    language: str,
    subscription_service: Any = None,
) -> AutoRenewCapabilities:
    if not provider:
        return AutoRenewCapabilities(False, False, provider or None)
    try:
        from bot.payment_providers import (
            provider_label_map,
            provider_manages_recurring,
            provider_supports_recurring,
        )
        from bot.payment_providers.shared import service_supports_recurring

        saved_method_recurring = provider_supports_recurring(provider)
        supported = saved_method_recurring or provider_manages_recurring(provider)
        service_active = False
        if saved_method_recurring and subscription_service is not None:
            resolver = getattr(subscription_service, "recurring_service_for", None)
            service = resolver(provider) if callable(resolver) else None
            service_active = service_supports_recurring(service)
        label = provider_label_map(settings, language=language).get(provider, provider)
        return AutoRenewCapabilities(supported, service_active, label)
    except Exception:
        return AutoRenewCapabilities(False, False, provider)
