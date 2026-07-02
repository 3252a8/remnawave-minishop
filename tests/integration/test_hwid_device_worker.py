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
    def _build_panel_update_payload(
        *,
        panel_user_uuid=None,
        expire_at=None,
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
        )
        tariff = SimpleNamespace(hwid_device_limit=3)

        with patch(
            "bot.services.tariff_worker.tariff_dal.sum_active_hwid_devices",
            AsyncMock(return_value=0),
        ):
            await worker._sync_hwid_device_limit(
                session=AsyncMock(),
                sub=sub,
                tariff=tariff,
                panel_data={"hwidDeviceLimit": 5},
            )

        self.assertEqual(sub.extra_hwid_devices, 0)
        panel_payload = panel.update_user_details_on_panel.await_args.args[1]
        self.assertEqual(panel_payload["hwidDeviceLimit"], 3)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
