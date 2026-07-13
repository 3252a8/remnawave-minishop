import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from db.dal import tariff_dal


class _ScalarResult:
    def __init__(self, records):
        self._records = records

    def scalars(self):
        return self

    def all(self):
        return self._records


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class HwidDeviceBonusExtensionTests(unittest.IsolatedAsyncioTestCase):
    async def test_combined_subscription_payment_uses_only_hwid_component_for_conversion(self):
        valid_from = datetime(2099, 1, 1, tzinfo=UTC)
        valid_until = datetime(2099, 2, 1, tzinfo=UTC)
        session = SimpleNamespace(
            execute=AsyncMock(
                return_value=_RowsResult(
                    [
                        (
                            7,
                            1,
                            valid_from,
                            valid_until,
                            valid_from,
                            1100.0,
                            "RUB",
                            "subscription@standard",
                            100.0,
                            1.0,
                            None,
                        ),
                        (
                            8,
                            1,
                            valid_from,
                            valid_until,
                            valid_from,
                            40.0,
                            "RUB",
                            "hwid_devices@standard",
                            100.0,
                            0.4,
                            None,
                        ),
                        (
                            9,
                            1,
                            valid_from,
                            valid_until,
                            valid_from,
                            550.0,
                            "RUB",
                            "subscription@standard",
                            100.0,
                            1.0,
                            1100.0,
                        ),
                    ]
                )
            )
        )

        entries = await tariff_dal.get_hwid_device_value_entries(
            session,
            subscription_id=10,
            at=valid_from,
        )

        self.assertEqual([entry["amount"] for entry in entries], [100.0, 40.0, 50.0])

    async def test_extends_tail_purchase_when_it_covers_subscription_end(self):
        subscription_end = datetime(2099, 2, 1, tzinfo=UTC)
        future_purchase = SimpleNamespace(
            valid_until=subscription_end,
        )
        session = SimpleNamespace(
            execute=AsyncMock(return_value=_ScalarResult([future_purchase])),
            flush=AsyncMock(),
        )

        updated = await tariff_dal.extend_hwid_device_purchases_for_subscription_bonus(
            session,
            subscription_id=10,
            at=datetime(2099, 1, 1, tzinfo=UTC),
            subscription_end_before=subscription_end,
            delta=timedelta(days=7),
        )

        self.assertEqual(updated, 1)
        self.assertEqual(future_purchase.valid_until, subscription_end + timedelta(days=7))
        session.flush.assert_awaited_once()
        self.assertEqual(session.execute.await_count, 1)

    async def test_extends_active_purchase_when_no_tail_purchase_exists(self):
        active_until = datetime(2099, 1, 16, tzinfo=UTC)
        active_purchase = SimpleNamespace(valid_until=active_until)
        session = SimpleNamespace(
            execute=AsyncMock(
                side_effect=[
                    _ScalarResult([]),
                    _ScalarResult([active_purchase]),
                ]
            ),
            flush=AsyncMock(),
        )

        updated = await tariff_dal.extend_hwid_device_purchases_for_subscription_bonus(
            session,
            subscription_id=10,
            at=datetime(2099, 1, 1, tzinfo=UTC),
            subscription_end_before=datetime(2099, 2, 1, tzinfo=UTC),
            delta=timedelta(days=7),
        )

        self.assertEqual(updated, 1)
        self.assertEqual(active_purchase.valid_until, active_until + timedelta(days=7))
        session.flush.assert_awaited_once()
        self.assertEqual(session.execute.await_count, 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
