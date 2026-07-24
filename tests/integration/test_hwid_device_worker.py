import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.services.tariff_worker import TariffTrafficWorker


class _Service:
    def _base_hwid_limit_for_tariff(self, tariff):
        return tariff.hwid_device_limit

    @staticmethod
    def _effective_hwid_limit(base_limit, extra_devices=0):
        if base_limit is None:
            return None
        base_int = max(0, int(base_limit))
        if base_int == 0:
            return 0
        return base_int + max(0, int(extra_devices or 0))

    @staticmethod
    def _hwid_traffic_bonus_bytes_from_summary(summary):
        return int(summary.get("traffic_bonus_bytes") or 0)

    @staticmethod
    def _compute_main_traffic_limit_bytes(
        *,
        tier_baseline_bytes,
        topup_balance_bytes,
        regular_bonus_bytes,
        regular_unlimited_override,
        traffic_used_bytes,
        hwid_device_bonus_bytes,
    ):
        if regular_unlimited_override or tier_baseline_bytes == 0:
            return 0
        return (
            tier_baseline_bytes
            + topup_balance_bytes
            + regular_bonus_bytes
            + hwid_device_bonus_bytes
        )

    @staticmethod
    def _build_panel_update_payload(
        *,
        panel_user_uuid=None,
        expire_at=None,
        traffic_limit_bytes=None,
        hwid_device_limit=None,
        include_default_squads=True,
        **_kwargs,
    ):
        payload = {}
        if panel_user_uuid:
            payload["uuid"] = panel_user_uuid
        if expire_at:
            payload["expireAt"] = expire_at.isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            )
        if traffic_limit_bytes is not None:
            payload["trafficLimitBytes"] = int(traffic_limit_bytes)
        if hwid_device_limit is not None:
            payload["hwidDeviceLimit"] = int(hwid_device_limit)
        return payload


class HwidDeviceWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_resets_expired_hwid_entitlement_on_panel(self):
        panel = SimpleNamespace(update_user_details_on_panel=AsyncMock(return_value={"ok": True}))
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(),
            session_factory=None,
            panel_service=panel,
            subscription_service=_Service(),
        )
        sub = SimpleNamespace(
            subscription_id=11,
            panel_user_uuid="panel-user",
            end_date=datetime(2099, 1, 1, tzinfo=UTC),
            hwid_device_limit=3,
            extra_hwid_devices=2,
            tier_baseline_bytes=100,
            topup_balance_bytes=0,
            regular_bonus_bytes=0,
            regular_unlimited_override=False,
            traffic_used_bytes=20,
            traffic_limit_bytes=115,
        )
        tariff = SimpleNamespace(hwid_device_limit=3, billing_model="period", monthly_bytes=100)

        with patch(
            "bot.services.tariff_worker.tariff_dal.get_hwid_device_entitlement_summary",
            AsyncMock(
                return_value={
                    "active_devices": 0,
                    "traffic_bonus_bytes": 0,
                    "legacy_active_devices": 0,
                }
            ),
        ):
            await worker._sync_hwid_device_limit(
                session=AsyncMock(),
                sub=sub,
                tariff=tariff,
                panel_data={"hwidDeviceLimit": 5, "trafficLimitBytes": 115},
            )

        self.assertEqual(sub.extra_hwid_devices, 0)
        self.assertEqual(sub.traffic_limit_bytes, 100)
        panel_payload = panel.update_user_details_on_panel.await_args.args[1]
        self.assertEqual(panel_payload["hwidDeviceLimit"], 3)
        self.assertEqual(panel_payload["trafficLimitBytes"], 100)

    async def test_worker_applies_bonus_for_active_hwid_entitlement(self):
        panel = SimpleNamespace(update_user_details_on_panel=AsyncMock(return_value={"ok": True}))
        worker = TariffTrafficWorker(
            settings=SimpleNamespace(),
            session_factory=None,
            panel_service=panel,
            subscription_service=_Service(),
        )
        sub = SimpleNamespace(
            subscription_id=12,
            panel_user_uuid="panel-user",
            end_date=datetime(2099, 1, 1, tzinfo=UTC),
            hwid_device_limit=3,
            extra_hwid_devices=1,
            tier_baseline_bytes=100,
            topup_balance_bytes=0,
            regular_bonus_bytes=0,
            regular_unlimited_override=False,
            traffic_used_bytes=20,
            traffic_limit_bytes=100,
        )
        tariff = SimpleNamespace(hwid_device_limit=3, billing_model="period", monthly_bytes=100)

        with patch(
            "bot.services.tariff_worker.tariff_dal.get_hwid_device_entitlement_summary",
            AsyncMock(
                return_value={
                    "active_devices": 1,
                    "traffic_bonus_bytes": 15,
                    "legacy_active_devices": 0,
                }
            ),
        ):
            await worker._sync_hwid_device_limit(
                session=AsyncMock(),
                sub=sub,
                tariff=tariff,
                panel_data={"hwidDeviceLimit": 4, "trafficLimitBytes": 100},
            )

        self.assertEqual(sub.extra_hwid_devices, 1)
        self.assertEqual(sub.traffic_limit_bytes, 115)
        panel_payload = panel.update_user_details_on_panel.await_args.args[1]
        self.assertNotIn("hwidDeviceLimit", panel_payload)
        self.assertEqual(panel_payload["trafficLimitBytes"], 115)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
