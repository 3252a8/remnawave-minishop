"""Persist gift delivery intent in the immutable checkout shared by providers."""

import hashlib
import json
from dataclasses import replace

from bot.services.trial_days import TrialDaysStrategy

from .billing_checkout_bundle import CheckoutBundle
from .payloads import WebAppPaymentCreatePayload


def attach_gift_delivery(
    bundle: CheckoutBundle,
    payload: WebAppPaymentCreatePayload,
    trial_days_strategy: TrialDaysStrategy,
) -> CheckoutBundle:
    # Metadata-only checkout has no v3 add-on duration fields; the payment
    # separately freezes the purchased period in subscription_terms_snapshot.
    snapshot = json.loads(bundle.snapshot) if bundle.snapshot else {"version": 2, "items": []}
    snapshot["gift_recipient_email"] = (
        str(payload.gift_recipient_email or "").strip().lower() or None
    )
    snapshot.pop("active_context", None)
    snapshot["trial_days_strategy"] = trial_days_strategy
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return replace(bundle, snapshot=encoded, digest=hashlib.sha256(encoded.encode()).hexdigest())
