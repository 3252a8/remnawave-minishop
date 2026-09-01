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
    *,
    is_override: bool = False,
) -> int | None:
    """Resolve an explicit override or the current tariff-owned base.

    Inherited values follow the configuration in both directions, including
    finite-to-unlimited and unlimited-to-finite transitions. ``0`` means an
    explicit or configured unlimited value.
    """
    stored = max(0, int(stored_base)) if stored_base is not None else None
    configured = max(0, int(configured_base)) if configured_base is not None else None
    if is_override and stored is not None:
        return stored
    return configured


@dataclass(frozen=True)
class HwidDeviceLimits:
    """Resolved HWID device limits for one subscription."""

    base: int | None
    extra: int
    effective: int | None
