"""In-process domain event bus.

The core publishes events at key points of the business flow; plugins (or
core modules) subscribe to react without the call sites knowing about them.
Typical subscribers register inside ``Plugin.setup``.

Design rules:

- ``emit`` never raises and never blocks the main flow beyond awaiting the
  subscribers sequentially; a failing subscriber is logged and skipped.
- Payloads are flat dicts of primitives (ids, numbers, strings, ISO-8601
  datetimes) — never ORM objects. Subscribers that need richer data re-read
  it from the database by id.
- Events may be emitted shortly before the surrounding transaction commits;
  treat a payload as a notification, not as a guarantee the row is visible.

Event payload conventions (keys may be ``None`` when unknown):

- ``PAYMENT_SUCCEEDED``: user_id, payment_db_id, provider, amount, currency,
  sale_mode, months, traffic_gb, end_date, is_auto_renew.
- ``PAYMENT_CANCELED``: user_id, payment_db_id, provider,
  provider_payment_id, status.
- ``SUBSCRIPTION_CREATED`` / ``SUBSCRIPTION_EXTENDED``: user_id,
  subscription_id, tariff_key, end_date, provider, months, payment_db_id.
- ``TRIAL_ACTIVATED``: user_id, end_date, days, traffic_gb.
- ``USER_REGISTERED``: user_id, language, referred_by_id.
- ``PROMO_CODE_APPLIED``: user_id, code, bonus_days, new_end_date.
- ``REFERRAL_BONUS_GRANTED``: referee_user_id, referee_bonus_days,
  referee_new_end_date, inviter_bonus_applied, payment_db_id.
- ``SUPPORT_TICKET_CREATED``: user_id, ticket_id, category, priority.
- ``PANEL_WEBHOOK_RECEIVED``: event, panel_user_uuid, telegram_id.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

PAYMENT_SUCCEEDED = "payment.succeeded"
PAYMENT_CANCELED = "payment.canceled"
SUBSCRIPTION_CREATED = "subscription.created"
SUBSCRIPTION_EXTENDED = "subscription.extended"
TRIAL_ACTIVATED = "trial.activated"
USER_REGISTERED = "user.registered"
PROMO_CODE_APPLIED = "promo_code.applied"
REFERRAL_BONUS_GRANTED = "referral.bonus_granted"
SUPPORT_TICKET_CREATED = "support.ticket_created"
PANEL_WEBHOOK_RECEIVED = "panel.webhook_received"

#: Handlers receive ``(event_name, payload)`` so one subscriber can serve
#: several events.
EventHandler = Callable[[str, Dict[str, Any]], Awaitable[None]]

_subscribers: Dict[str, List[EventHandler]] = {}


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


def iso(value: Optional[datetime]) -> Optional[str]:
    """Format a datetime payload value as ISO-8601 (or pass None through)."""
    return value.isoformat() if isinstance(value, datetime) else None


async def emit(event_name: str, payload: Dict[str, Any]) -> None:
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
