import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service import SubscriptionService
from bot.services.subscription_service_impl.hwid_limits import HwidDeviceLimits
from config.settings import Settings


def _service(**overrides) -> SubscriptionService:
    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
        **overrides,
    )
    return SubscriptionService(settings, AsyncMock(spec=PanelApiService))


class ResolveHwidDeviceLimitsTests(unittest.IsolatedAsyncioTestCase):
    async def test_subscription_override_wins_and_adds_extras(self):
        service = _service()
        service._active_hwid_extra_devices_for_sub = AsyncMock(return_value=2)
        sub = SimpleNamespace(hwid_device_limit=5)

        limits = await service._resolve_hwid_device_limits(None, sub, None)

        self.assertEqual(limits, HwidDeviceLimits(base=5, extra=2, effective=7))

    async def test_falls_back_to_tariff_limit_when_no_override(self):
        service = _service()
        service._active_hwid_extra_devices_for_sub = AsyncMock(return_value=1)
        sub = SimpleNamespace(hwid_device_limit=None)
        tariff = SimpleNamespace(hwid_device_limit=3)

        limits = await service._resolve_hwid_device_limits(None, sub, tariff)

        self.assertEqual(limits, HwidDeviceLimits(base=3, extra=1, effective=4))

    async def test_settings_default_applies_when_no_override_or_tariff(self):
        service = _service(USER_HWID_DEVICE_LIMIT=4)
        service._active_hwid_extra_devices_for_sub = AsyncMock(return_value=1)
        sub = SimpleNamespace(hwid_device_limit=None)

        limits = await service._resolve_hwid_device_limits(None, sub, None)

        self.assertEqual(limits, HwidDeviceLimits(base=4, extra=1, effective=5))

    async def test_no_base_limit_yields_zero_effective(self):
        service = _service()
        service._active_hwid_extra_devices_for_sub = AsyncMock(return_value=4)
        sub = SimpleNamespace(hwid_device_limit=None)

        limits = await service._resolve_hwid_device_limits(None, sub, None)

        self.assertEqual(limits, HwidDeviceLimits(base=None, extra=4, effective=0))


if __name__ == "__main__":
    unittest.main()
