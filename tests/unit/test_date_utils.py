import unittest
from datetime import datetime, timezone

from bot.utils.date_utils import month_start


class DateUtilsTests(unittest.TestCase):
    def test_month_start_normalizes_aware_datetime(self):
        dt = datetime(2026, 4, 28, 15, 45, tzinfo=timezone.utc)

        result = month_start(dt)

        self.assertEqual(result, datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc))

    def test_month_start_normalizes_naive_datetime_as_utc(self):
        dt = datetime(2026, 12, 31, 23, 59)

        result = month_start(dt)

        self.assertEqual(result, datetime(2026, 12, 1, 0, 0, tzinfo=timezone.utc))
