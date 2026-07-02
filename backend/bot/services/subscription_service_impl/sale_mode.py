"""Typed parsing of the ``sale_mode`` activation token.

``sale_mode`` strings arrive from payment callbacks/webapp flows and encode both
the activation *base* (``subscription`` / ``topup`` / ``hwid_devices`` / ...) and,
optionally, an attached tariff key after an ``@`` or ``|`` separator. Activation
dispatch keys off the parsed base, so the parse is a pure, branch-bearing decision
worth isolating and unit-testing on its own.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SaleModeContext:
    """Parsed sale-mode token: the base activation mode plus an optional tariff key."""

    base: str
    tariff_key: str | None


def parse_sale_mode_context(
    sale_mode: str,
    explicit_tariff_key: str | None = None,
) -> SaleModeContext:
    """Split a raw ``sale_mode`` token into its base mode and tariff key.

    Behavior preserved verbatim from the former ``TariffMixin._parse_sale_mode_context``:
    an explicit tariff key always wins; otherwise the first ``@``/``|`` separator splits
    the base from a suffix tariff key, with the legacy ``|bot`` suffix treated as "no key".
    """

    mode = (sale_mode or "subscription").strip()
    tariff_key = explicit_tariff_key
    for separator in ("@", "|"):
        if separator in mode:
            base, suffix = mode.split(separator, 1)
            mode = base or mode
            suffix_key = suffix.split("|", 1)[0]
            if separator == "|" and suffix_key in {"bot"}:
                suffix_key = ""
            tariff_key = tariff_key or suffix_key or None
            break
    return SaleModeContext(base=mode, tariff_key=tariff_key)
