"""Cross-provider recurring (auto-renew) building blocks.

Auto-renew used to be hard-wired to YooKassa. This module defines the small,
provider-agnostic contract the renewal worker speaks to, so any provider that
can charge a previously saved payment method (a YooKassa ``payment_method_id``,
a CloudPayments ``Token``, etc.) participates through the same code path.

A provider service opts in by implementing two members:

* ``recurring_active`` - a property that is truthy when the provider is
  configured *and* recurring charges are switched on for it.
* ``charge_saved_payment_method(context)`` - an async method that initiates a
  charge against the saved method and returns a :class:`RecurringChargeResult`.

The renewal worker discovers such services through
``SubscriptionService.recurring_service_for(provider)`` (wired in
``build_core_services``) and never imports a concrete provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class RecurringChargeContext:
    """Everything a provider needs to charge a saved payment method.

    ``metadata`` mirrors the YooKassa-style key/value bag (the YooKassa webhook
    reconstructs the renewal from it). Providers that finalize the payment from
    their own DB record (e.g. CloudPayments) read the structured fields and
    ``hwid_quote`` instead.
    """

    session: Any
    user_id: int
    subscription_id: int
    saved_method: Any
    amount: float
    currency: str
    months: int
    sale_mode: str
    description: str
    metadata: Mapping[str, str] = field(default_factory=dict)
    hwid_quote: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class RecurringChargeResult:
    """Outcome of a saved-method charge attempt.

    ``initiated`` is True when the charge was accepted by the provider, either
    finalized synchronously or left pending for the provider webhook to
    complete. The renewal worker treats ``initiated`` as "handled".
    """

    initiated: bool
    provider_payment_id: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None

    @classmethod
    def failed(cls, message: Optional[str] = None) -> "RecurringChargeResult":
        return cls(initiated=False, message=message)

    @classmethod
    def ok(
        cls,
        *,
        provider_payment_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> "RecurringChargeResult":
        return cls(initiated=True, provider_payment_id=provider_payment_id, status=status)


def service_supports_recurring(service: Any) -> bool:
    """True when a wired provider service exposes an active recurring capability."""
    return bool(service is not None and getattr(service, "recurring_active", False))
