import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp.devices import (
    _device_hwid_token,
    _load_devices_payload,
    _normalize_devices_response,
    _serialize_device,
)


class _SessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _JsonRequest:
    def __init__(self, payload, app):
        self._payload = payload
        self.app = app

    async def json(self):
        return self._payload


def test_serialize_device_matches_contract():
    created = datetime(2099, 1, 2, 3, 4, 0, tzinfo=UTC)
    result = _serialize_device(
        {
            "hwid": "ABC123XYZ",
            "deviceModel": "iPhone 15",
            "platform": "iOS",
            "osVersion": "17.2",
            "userAgent": "TgWeb/1.0",
            "createdAt": created,
        },
        3,
    )
    expected = {
        "index": 3,
        "display_name": "iPhone 15",
        "platform": "iOS",
        "os_version": "17.2",
        "platform_label": "iOS 17.2",
        "user_agent": "TgWeb/1.0",
        "created_at": created.isoformat(),
        "created_at_text": "02.01.2099 03:04",
        "hwid_short": "ABC123XYZ",
        "token": hashlib.sha256(b"ABC123XYZ").hexdigest()[:32],
        "can_disconnect": True,
    }
    assert result == expected
    assert list(result.keys()) == list(expected.keys())


def test_serialize_device_without_hwid_cannot_disconnect():
    result = _serialize_device({"platform": "Android"}, 1)
    assert result["token"] == ""
    assert result["can_disconnect"] is False
    assert result["display_name"] == "Android"
    assert result["created_at"] is None
    assert result["created_at_text"] == ""


def test_device_serializer_accepts_datetime_created_at():
    created_at = datetime(2099, 1, 2, 3, 4, tzinfo=UTC)

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


def test_normalize_devices_response_accepts_panel_response_object():
    payload = {"response": {"total": 1, "devices": [{"hwid": "abcdef123456"}]}}

    assert _normalize_devices_response(payload) == [{"hwid": "abcdef123456"}]


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

    async def test_load_devices_payload_reports_panel_none_as_error(self):
        panel_service = SimpleNamespace(get_user_devices=AsyncMock(return_value=None))
        subscription_service = SimpleNamespace(
            get_active_subscription_details=AsyncMock(
                return_value={
                    "user_id": "panel-user",
                    "end_date": datetime(2099, 1, 2, tzinfo=UTC),
                    "max_devices": 3,
                }
            ),
            panel_service=panel_service,
        )

        payload = await _load_devices_payload(subscription_service, AsyncMock(), 42)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], 502)
        self.assertEqual(payload["error"], "devices_load_failed")

    async def test_load_devices_payload_keeps_empty_devices_list_successful(self):
        panel_service = SimpleNamespace(get_user_devices=AsyncMock(return_value=[]))
        subscription_service = SimpleNamespace(
            get_active_subscription_details=AsyncMock(
                return_value={
                    "user_id": "panel-user",
                    "end_date": datetime(2099, 1, 2, tzinfo=UTC),
                    "max_devices": 3,
                }
            ),
            panel_service=panel_service,
        )

        payload = await _load_devices_payload(subscription_service, AsyncMock(), 42)

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["payload"]["subscription_active"])
        self.assertEqual(payload["payload"]["current_devices"], 0)
        self.assertEqual(payload["payload"]["devices"], [])

    async def test_disconnect_device_route_invalidates_webapp_devices_cache(self):
        session = SimpleNamespace(commit=AsyncMock())
        settings = SimpleNamespace(MY_DEVICES_SECTION_ENABLED=True, DEFAULT_LANGUAGE="en")
        panel_service = SimpleNamespace(
            get_user_devices=AsyncMock(return_value=[{"hwid": "ABC123XYZ"}]),
            disconnect_device=AsyncMock(return_value=True),
        )
        subscription_service = SimpleNamespace(
            get_active_subscription_details=AsyncMock(return_value={"user_id": "panel-user"}),
            panel_service=panel_service,
        )
        request = _JsonRequest(
            {"token": _device_hwid_token("ABC123XYZ")},
            {
                "settings": settings,
                "async_session_factory": _SessionFactory(session),
                "subscription_service": subscription_service,
            },
        )

        from bot.app.web.webapp import devices as devices_module

        with (
            patch.object(devices_module, "_require_user_id", return_value=42),
            patch.object(
                devices_module, "_enforce_webapp_rate_limit", AsyncMock(return_value=None)
            ),
            patch.object(
                devices_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=SimpleNamespace(is_banned=False)),
            ),
            patch.object(
                devices_module,
                "invalidate_webapp_user_caches",
                AsyncMock(),
            ) as invalidate_caches,
        ):
            response = await devices_module.disconnect_device_route(request)

        self.assertEqual(response.status, 200)
        panel_service.disconnect_device.assert_awaited_once_with("panel-user", "ABC123XYZ")
        invalidate_caches.assert_awaited_once_with(
            settings,
            42,
            include_devices=True,
            include_me=False,
        )
        session.commit.assert_awaited_once()
