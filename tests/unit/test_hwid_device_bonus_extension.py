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


class HwidDeviceBonusExtensionTests(unittest.IsolatedAsyncioTestCase):
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
