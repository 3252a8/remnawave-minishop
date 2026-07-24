import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.scripts import resync_traffic_limits


class ResyncTrafficLimitsScriptTests(unittest.IsolatedAsyncioTestCase):
    async def test_zero_bonus_still_recomputes_existing_limits(self) -> None:
        gb = 1024**3
        subscription = SimpleNamespace(user_id=42, traffic_limit_bytes=120 * gb)
        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = [subscription]
        session = AsyncMock()
        session.execute.return_value = query_result
        session_context = AsyncMock()
        session_context.__aenter__.return_value = session
        session_factory = MagicMock(return_value=session_context)
        panel = SimpleNamespace(close=AsyncMock())
        service = SimpleNamespace()
        target_limit = AsyncMock(return_value=(100 * gb, 1))

        output = StringIO()
        with (
            patch.object(
                resync_traffic_limits,
                "Settings",
                return_value=SimpleNamespace(HWID_DEVICE_TRAFFIC_BONUS_GB=0.0),
            ),
            patch.object(
                resync_traffic_limits,
                "init_db_connection",
                return_value=session_factory,
            ),
            patch.object(
                resync_traffic_limits,
                "load_overrides_from_db",
                AsyncMock(return_value=0),
            ),
            patch.object(resync_traffic_limits, "PanelApiService", return_value=panel),
            patch.object(resync_traffic_limits, "SubscriptionService", return_value=service),
            patch.object(resync_traffic_limits, "_target_limit", target_limit),
            patch.object(resync_traffic_limits, "APPLY", False),
            redirect_stdout(output),
        ):
            await resync_traffic_limits.main()

        target_limit.assert_awaited_once_with(service, session, subscription)
        self.assertIn("legacy HWID_DEVICE_TRAFFIC_BONUS_GB fallback = 0.0", output.getvalue())
        self.assertIn("120 GB -> 100 GB", output.getvalue())
        panel.close.assert_awaited_once()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
