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


@dataclass(frozen=True)
class HwidDeviceLimits:
    """Resolved HWID device limits for one subscription."""

    base: int | None
    extra: int
    effective: int | None
