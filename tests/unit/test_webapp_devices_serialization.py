import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp.devices import _load_devices_payload, _serialize_device


def test_device_serializer_accepts_datetime_created_at():
    created_at = datetime(2099, 1, 2, 3, 4, tzinfo=timezone.utc)

    payload = _serialize_device(
        {
            "hwid": "abcdef123456",
            "deviceModel": "Laptop",
            "createdAt": created_at,
        },
        1,
    )

    assert payload["created_at"] == created_at.isoformat()
    assert payload["created_at_text"] == "02.01.2099 03:04"
    json.dumps(payload)


class WebAppDevicesPayloadTests(IsolatedAsyncioTestCase):
    async def test_load_devices_payload_returns_empty_payload_without_subscription(self):
        panel_service = SimpleNamespace(get_user_devices=AsyncMock())
        subscription_service = SimpleNamespace(
            get_active_subscription_details=AsyncMock(return_value=None),
            panel_service=panel_service,
        )

        payload = await _load_devices_payload(subscription_service, AsyncMock(), 42)

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["payload"]["subscription_active"])
        self.assertEqual(payload["payload"]["current_devices"], 0)
        self.assertEqual(payload["payload"]["devices"], [])
        panel_service.get_user_devices.assert_not_awaited()

    async def test_load_devices_payload_uses_fallback_panel_uuid_for_inactive_devices(self):
        panel_service = SimpleNamespace(
            get_user_devices=AsyncMock(
                return_value=[
                    {
                        "hwid": "abcdef123456",
                        "deviceModel": "Laptop",
                    }
                ]
            )
        )
        subscription_service = SimpleNamespace(
            get_active_subscription_details=AsyncMock(return_value=None),
            panel_service=panel_service,
        )

        payload = await _load_devices_payload(
            subscription_service,
            AsyncMock(),
            42,
            fallback_panel_user_uuid="panel-user",
        )

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["payload"]["subscription_active"])
        self.assertEqual(payload["payload"]["current_devices"], 1)
        self.assertEqual(payload["payload"]["devices"][0]["display_name"], "Laptop")
        panel_service.get_user_devices.assert_awaited_once_with("panel-user")
