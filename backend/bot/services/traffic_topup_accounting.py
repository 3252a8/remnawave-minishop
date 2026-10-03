"""Counter-independent consumption of a carried-over traffic balance."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TopupConsumption:
    balance_bytes: int
    used_bytes: int
    consumed_bytes: int


def consume_topup_overflow(
    *,
    balance_bytes: int,
    used_bytes: int = 0,
    traffic_used_bytes: int,
    allowance_bytes: int,
    unlimited: bool = False,
) -> TopupConsumption:
    """Charge only new overflow; never restore consumption or make a balance negative.

    ``used_bytes`` is the part already charged in this counter period. Premium
    retains it in its panel cap until reset; regular accounting closes a period
    with zero already charged bytes. Zero allowance is not intrinsically unlimited:
    the adapter must supply the meaning of its panel's zero-limit contract.
    """
    balance = max(0, int(balance_bytes))
    used = max(0, int(used_bytes))
    overflow = max(0, int(traffic_used_bytes) - max(0, int(allowance_bytes)))
    consumed = 0 if unlimited else min(balance, max(0, overflow - used))
    return TopupConsumption(balance - consumed, used + consumed, consumed)
