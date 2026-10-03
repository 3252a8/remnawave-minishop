"""Regular and premium adapters share the same paid-overflow invariant."""

import pytest

from bot.services.traffic_topup_accounting import consume_topup_overflow


@pytest.mark.parametrize(
    ("balance", "already_used", "traffic", "allowance", "unlimited", "expected"),
    [
        (50, 0, 80, 50, False, (20, 30, 30)),
        (20, 30, 80, 50, False, (20, 30, 0)),
        (20, 30, 90, 50, False, (10, 40, 10)),
        (10, 40, 150, 50, False, (0, 50, 10)),
        (20, 30, 80, 100, False, (20, 30, 0)),
        (50, 0, 20, 0, False, (30, 20, 20)),
        (50, 0, 200, 0, True, (50, 0, 0)),
        (-10, -20, -30, -40, False, (0, 0, 0)),
    ],
)
def test_new_overflow_only(
    balance: int,
    already_used: int,
    traffic: int,
    allowance: int,
    unlimited: bool,
    expected: tuple[int, int, int],
) -> None:
    result = consume_topup_overflow(
        balance_bytes=balance,
        used_bytes=already_used,
        traffic_used_bytes=traffic,
        allowance_bytes=allowance,
        unlimited=unlimited,
    )
    assert (result.balance_bytes, result.used_bytes, result.consumed_bytes) == expected


def test_premium_purchase_preserves_the_cap_and_reset_drops_spent_bytes() -> None:
    first = consume_topup_overflow(balance_bytes=50, traffic_used_bytes=80, allowance_bytes=50)
    purchased = consume_topup_overflow(
        balance_bytes=first.balance_bytes + 20,
        used_bytes=first.used_bytes,
        traffic_used_bytes=80,
        allowance_bytes=50,
    )
    assert 50 + purchased.balance_bytes + purchased.used_bytes == 120
    reset = consume_topup_overflow(
        balance_bytes=purchased.balance_bytes,
        traffic_used_bytes=0,
        allowance_bytes=50,
    )
    assert reset.used_bytes == 0
    assert 50 + reset.balance_bytes == 90
