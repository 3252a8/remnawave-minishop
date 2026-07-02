"""In-process domain event bus.

The core publishes events at key points of the business flow; plugins (or
core modules) subscribe to react without the call sites knowing about them.
Typical subscribers register inside ``Plugin.setup``.

Design rules:

- ``emit`` never raises and never blocks the main flow beyond awaiting the
  subscribers sequentially; a failing subscriber is logged and skipped.
- Payloads are flat dicts of primitives (ids, numbers, strings, ISO-8601
  datetimes) - never ORM objects. Subscribers that need richer data re-read
  it from the database by id.
- Payment purchase units are normalized in :mod:`bot.infra.payment_events`.
  Plugins that introduce new payment-backed units can register purchase
  resolvers there while still subscribing to the plain event payload here.
- Events may be emitted shortly before the surrounding transaction commits;
  treat a payload as a notification, not as a guarantee the row is visible.

Event payload contracts live in :mod:`bot.infra.event_payloads`. Emit sites
construct those models first and publish their ``to_payload()`` dicts here;
third-party subscribers still receive the public ``(event_name, dict)``
signature.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from bot.infra.event_payloads import EventPayload

logger = logging.getLogger(__name__)

PAYMENT_SUCCEEDED = "payment.succeeded"
PAYMENT_CANCELED = "payment.canceled"
SUBSCRIPTION_CREATED = "subscription.created"
SUBSCRIPTION_EXTENDED = "subscription.extended"
SUBSCRIPTION_EXPIRED = "subscription.expired"
SUBSCRIPTION_LAPSED = "subscription.lapsed"
TRIAL_ACTIVATED = "trial.activated"
USER_REGISTERED = "user.registered"
ACCOUNT_EMAIL_LINKED = "account.email_linked"
ACCOUNT_TELEGRAM_LINKED = "account.telegram_linked"
ACCOUNT_MERGED = "account.merged"
PROMO_CODE_APPLIED = "promo_code.applied"
REFERRAL_BONUS_GRANTED = "referral.bonus_granted"
SUPPORT_TICKET_CREATED = "support.ticket_created"
PANEL_WEBHOOK_RECEIVED = "panel.webhook_received"

#: Handlers receive ``(event_name, payload)`` so one subscriber can serve
#: several events.
EventHandler = Callable[[str, dict[str, Any]], Awaitable[None]]

_subscribers: dict[str, list[EventHandler]] = {}


def subscribe(event_name: str, handler: EventHandler) -> None:
    """Register ``handler`` for ``event_name``."""
    _subscribers.setdefault(event_name, []).append(handler)


def unsubscribe(event_name: str, handler: EventHandler) -> None:
    """Remove a previously registered handler (no-op when absent)."""
    handlers = _subscribers.get(event_name)
    if handlers and handler in handlers:
        handlers.remove(handler)


def reset_subscribers() -> None:
    """Drop every subscription (for tests)."""
    _subscribers.clear()


def iso(value: datetime | None) -> str | None:
    """Format a datetime payload value as ISO-8601 (or pass None through)."""
    return value.isoformat() if isinstance(value, datetime) else None


async def emit(event_name: str, payload: dict[str, Any]) -> None:
    """Deliver ``payload`` to every subscriber of ``event_name``.

    Never raises: subscriber errors are logged and the remaining subscribers
    still run, so emitting can never break the publishing flow.
    """
    for handler in tuple(_subscribers.get(event_name, ())):
        try:
            await handler(event_name, payload)
        except Exception:
            logger.exception(
                "Event subscriber %r failed for event %s",
                getattr(handler, "__qualname__", handler),
                event_name,
            )


async def emit_model(
    payload: EventPayload,
    *,
    exclude_unset: bool = False,
    exclude_none: bool = False,
) -> None:
    """Deliver a typed event payload without changing the raw bus primitive."""
    await emit(
        payload.EVENT_NAME,
        payload.to_payload(exclude_unset=exclude_unset, exclude_none=exclude_none),
    )
