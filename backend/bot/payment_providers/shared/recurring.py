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

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class RecurringChargeContext:
    """Everything a provider needs to charge a saved payment method.

    ``metadata`` mirrors the YooKassa-style key/value bag.  YooKassa adds a
    pre-created local payment id to it before charging, then validates the
    successful webhook against that immutable order. Providers that finalize
    the payment from their own DB record (e.g. CloudPayments) read the
    structured fields and ``hwid_quote`` instead.
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
    hwid_quote: Mapping[str, Any] | None = None
    # A provider-safe stable key for one renewal attempt.  YooKassa persists
    # it on the local order and sends it as Idempotence-Key, while providers
    # that do not support that contract may ignore it.
    idempotence_key: str | None = None
    renewal_cycle_end: datetime | None = None


@dataclass(frozen=True)
class RecurringChargeResult:
    """Outcome of a saved-method charge attempt.

    ``initiated`` is True when the charge was accepted by the provider, either
    finalized synchronously or left pending for the provider webhook to
    complete. The renewal worker treats ``initiated`` as "handled".
    """

    initiated: bool
    provider_payment_id: str | None = None
    payment_db_id: int | None = None
    status: str | None = None
    message: str | None = None

    @classmethod
    def failed(
        cls,
        message: str | None = None,
        *,
        provider_payment_id: str | None = None,
        payment_db_id: int | None = None,
    ) -> RecurringChargeResult:
        return cls(
            initiated=False,
            message=message,
            provider_payment_id=provider_payment_id,
            payment_db_id=payment_db_id,
        )

    @classmethod
    def ok(
        cls,
        *,
        provider_payment_id: str | None = None,
        payment_db_id: int | None = None,
        status: str | None = None,
    ) -> RecurringChargeResult:
        return cls(
            initiated=True,
            provider_payment_id=provider_payment_id,
            payment_db_id=payment_db_id,
            status=status,
        )


class RecurringProviderService(Protocol):
    @property
    def configured(self) -> bool: ...

    @property
    def recurring_active(self) -> bool: ...

    async def charge_saved_payment_method(
        self,
        context: RecurringChargeContext,
    ) -> RecurringChargeResult: ...


def service_supports_recurring(service: object | None) -> bool:
    """True when a wired provider service exposes an active recurring capability."""
    return bool(service is not None and getattr(service, "recurring_active", False))
