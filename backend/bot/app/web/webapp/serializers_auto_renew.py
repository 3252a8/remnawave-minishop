"""Auto-renew capability flags for the Web App subscription payload.

Two disjoint provider families reach the same toggle:

* saved-method providers (YooKassa, CloudPayments, Stripe) and balance renewal,
  where our renewal worker initiates the charge — the customer may switch the
  toggle both ways, but turning it on needs a method to charge (a saved card);
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
    can_enable: bool
    provider_label: str | None

    def payload_fields(self, *, enabled: bool) -> dict[str, Any]:
        return {
            "auto_renew_available": bool(self.supported and (enabled or self.can_enable)),
            "auto_renew_can_enable": bool(self.supported and self.can_enable),
            "auto_renew_provider_label": self.provider_label,
        }


def resolve_auto_renew_capabilities(
    provider: str | None,
    *,
    settings: Any,
    language: str,
    chargeable: bool = False,
) -> AutoRenewCapabilities:
    """Describe the cabinet switch for the subscription's renewal provider.

    ``chargeable`` is :func:`bot.infra.auto_renew.auto_renew_chargeable` for this
    customer: without a live recurring service and a method it can charge, the
    switch is shown only while auto-renew is on, so it can be turned off.
    """
    if not provider:
        return AutoRenewCapabilities(False, False, provider or None)
    try:
        from bot.payment_providers import (
            provider_label_map,
            provider_manages_recurring,
            provider_supports_recurring,
        )

        saved_method_recurring = provider_supports_recurring(provider)
        supported = saved_method_recurring or provider_manages_recurring(provider)
        label = provider_label_map(settings, language=language).get(provider, provider)
        return AutoRenewCapabilities(supported, bool(saved_method_recurring and chargeable), label)
    except Exception:
        return AutoRenewCapabilities(False, False, provider)
