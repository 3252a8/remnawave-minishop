"""Typed resolution of a subscription's HWID device limits.

Several traffic/top-up flows recompute the same trio: the *base* device limit
(an explicit per-subscription override, else the tariff default), the *extra*
devices the user has purchased, and the *effective* panel-facing limit
(base + extra). Grouping them into one named value object removes the
duplicated inline branching and makes the panel-facing device limit a single,
directly-testable decision.
"""

from __future__ import annotations

from dataclasses import dataclass


def resolve_hwid_base_limit(
    stored_base: int | None,
    configured_base: int | None,
) -> int | None:
    """Raise a stored finite base to the configured floor without lowering it.

    ``0`` means unlimited and therefore wins over every finite value. A higher
    stored value may be an explicit per-subscription override, so tariff
    reconciliation must preserve it.
    """
    stored = max(0, int(stored_base)) if stored_base is not None else None
    configured = max(0, int(configured_base)) if configured_base is not None else None
    if stored == 0 or configured == 0:
        return 0
    if stored is None:
        return configured
    if configured is None:
        return stored
    return max(stored, configured)


@dataclass(frozen=True)
class HwidDeviceLimits:
    """Resolved HWID device limits for one subscription."""

    base: int | None
    extra: int
    effective: int | None
