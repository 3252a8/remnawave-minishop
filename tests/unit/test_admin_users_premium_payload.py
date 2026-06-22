"""Admin user list: premium traffic payload must not misuse ``premium_is_limited``."""

import unittest
from types import SimpleNamespace

from bot.app.web.admin_api import _premium_traffic_list_payload


class AdminPremiumTrafficPayloadTests(unittest.TestCase):
    def test_under_quota_shows_good_when_premium_is_limited_flag_false(self):
        """DB ``premium_is_limited`` is 'depleted' flag; under quota it is False."""

        gb = 1024**3
        sub = SimpleNamespace(
            premium_unlimited_override=False,
            premium_is_limited=False,
            premium_used_bytes=5 * gb,
            premium_baseline_bytes=25 * gb,
            premium_topup_balance_bytes=0,
            premium_topup_used_bytes=0,
            premium_bonus_bytes=0,
        )
        payload = _premium_traffic_list_payload(sub)
        self.assertEqual(payload["state"], "good")
        self.assertEqual(payload["percent"], 20)

    def test_over_quota_critical_even_when_column_semantics_differ(self):
        gb = 1024**3
        sub = SimpleNamespace(
            premium_unlimited_override=False,
            premium_is_limited=True,
            premium_used_bytes=30 * gb,
            premium_baseline_bytes=25 * gb,
            premium_topup_balance_bytes=0,
            premium_topup_used_bytes=0,
            premium_bonus_bytes=0,
        )
        payload = _premium_traffic_list_payload(sub)
        self.assertEqual(payload["state"], "critical")


if __name__ == "__main__":
    unittest.main()
