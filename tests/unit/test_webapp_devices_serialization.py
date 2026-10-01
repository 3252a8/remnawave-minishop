import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

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
    last_connected = datetime(2099, 1, 3, 4, 5, 0, tzinfo=UTC)
    result = _serialize_device(
        {
            "hwid": "ABC123XYZ",
            "deviceModel": "iPhone 15",
            "platform": "iOS",
            "osVersion": "17.2",
            "userAgent": "TgWeb/1.0",
            "createdAt": created,
            "updatedAt": last_connected,
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
        "last_connected_at": last_connected.isoformat(),
        "last_connected_at_text": "03.01.2099 04:05",
        "hwid_short": "ABC123XYZ",
        "token": hashlib.sha256(b"ABC123XYZ").hexdigest()[:32],
        "can_disconnect": True,
        "default_name": "iPhone 15",
        "custom_name": None,
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
    assert result["last_connected_at"] is None
    assert result["last_connected_at_text"] == ""


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
    assert payload["last_connected_at"] == created_at.isoformat()
    assert payload["last_connected_at_text"] == "02.01.2099 03:04"
    json.dumps(payload)


def test_normalize_devices_response_accepts_panel_response_object():
    payload = {"response": {"total": 1, "devices": [{"hwid": "abcdef123456"}]}}

    assert _normalize_devices_response(payload) == [{"hwid": "abcdef123456"}]


def test_serialize_device_prefers_saved_name_and_keeps_default():
    token = _device_hwid_token("ABC123XYZ")
    result = _serialize_device(
        {"hwid": "ABC123XYZ", "deviceModel": "iPhone 15", "platform": "iOS"},
        2,
        {token: "Mom's phone", "other-token": "Unrelated"},
    )

    assert result["display_name"] == "Mom's phone"
    assert result["custom_name"] == "Mom's phone"
    assert result["default_name"] == "iPhone 15"


def test_serialize_device_without_hwid_ignores_saved_names():
    result = _serialize_device({"platform": "Android"}, 1, {"": "Ghost"})

    assert result["display_name"] == "Android"
    assert result["custom_name"] is None


class WebAppDevicesPayloadTests(IsolatedAsyncioTestCase):
    def setUp(self):
        from bot.app.web.webapp import devices as devices_module

        names_patch = patch.object(
            devices_module.device_name_dal, "get_device_names", AsyncMock(return_value={})
        )
        self.get_device_names = names_patch.start()
        self.addCleanup(names_patch.stop)

    async def test_load_devices_payload_applies_saved_device_names(self):
        panel_service = SimpleNamespace(
            get_user_devices=AsyncMock(
                return_value=[
                    {"hwid": "abcdef123456", "deviceModel": "Laptop"},
                    {"hwid": "zyx987654321", "deviceModel": "Pixel 9"},
                ]
            )
        )
        subscription_service = SimpleNamespace(
            get_active_subscription_details=AsyncMock(
                return_value={"user_id": "panel-user", "end_date": datetime(2099, 1, 2, tzinfo=UTC)}
            ),
            panel_service=panel_service,
        )
        self.get_device_names.return_value = {_device_hwid_token("abcdef123456"): "Work laptop"}
        session = AsyncMock()

        payload = await _load_devices_payload(subscription_service, session, 42)

        devices = payload["payload"]["devices"]
        self.assertEqual(devices[0]["display_name"], "Work laptop")
        self.assertEqual(devices[0]["default_name"], "Laptop")
        self.assertEqual(devices[1]["display_name"], "Pixel 9")
        self.assertIsNone(devices[1]["custom_name"])
        self.get_device_names.assert_awaited_once_with(session, 42)

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


class WebAppDeviceRenameRouteTests(IsolatedAsyncioTestCase):
    def _request(self, payload, *, active=None, db_user=None, devices=None):
        self.session = SimpleNamespace(commit=AsyncMock())
        self.settings = SimpleNamespace(MY_DEVICES_SECTION_ENABLED=True, DEFAULT_LANGUAGE="en")
        self.panel_service = SimpleNamespace(
            get_user_devices=AsyncMock(
                return_value=devices
                if devices is not None
                else [{"hwid": "OTHER-HWID"}, {"hwid": "ABC123XYZ", "deviceModel": "Laptop"}]
            ),
        )
        subscription_service = SimpleNamespace(
            get_active_subscription_details=AsyncMock(
                return_value={"user_id": "panel-user"} if active is None else active
            ),
            panel_service=self.panel_service,
        )
        self.db_user = db_user or SimpleNamespace(is_banned=False, panel_user_uuid=None)
        return _JsonRequest(
            payload,
            {
                "settings": self.settings,
                "async_session_factory": _SessionFactory(self.session),
                "subscription_service": subscription_service,
            },
        )

    async def _call(self, request):
        from bot.app.web.webapp import devices as devices_module

        with (
            patch.object(devices_module, "_require_user_id", return_value=42),
            patch.object(
                devices_module, "_enforce_webapp_rate_limit", AsyncMock(return_value=None)
            ),
            patch.object(
                devices_module.user_dal, "get_user_by_id", AsyncMock(return_value=self.db_user)
            ),
            patch.object(devices_module.device_name_dal, "set_device_name", AsyncMock()) as save,
            patch.object(
                devices_module, "invalidate_webapp_user_caches", AsyncMock()
            ) as invalidate_caches,
        ):
            response = await devices_module.rename_device_route(request)
        return response, json.loads(response.body), save, invalidate_caches

    async def test_rename_saves_normalized_name_and_returns_updated_device(self):
        token = _device_hwid_token("ABC123XYZ")
        request = self._request({"token": token, "name": "  Work\n\tlaptop  "})

        response, body, save, invalidate_caches = await self._call(request)

        self.assertEqual(response.status, 200)
        save.assert_awaited_once_with(self.session, 42, token, "Work laptop")
        self.session.commit.assert_awaited_once()
        invalidate_caches.assert_awaited_once_with(
            self.settings, 42, include_devices=True, include_me=False
        )
        self.assertEqual(body["device"]["index"], 2)
        self.assertEqual(body["device"]["display_name"], "Work laptop")
        self.assertEqual(body["device"]["default_name"], "Laptop")

    async def test_empty_name_restores_the_default(self):
        token = _device_hwid_token("ABC123XYZ")
        response, body, save, _ = await self._call(self._request({"token": token, "name": " "}))

        self.assertEqual(response.status, 200)
        save.assert_awaited_once_with(self.session, 42, token, "")
        self.assertIsNone(body["device"]["custom_name"])
        self.assertEqual(body["device"]["display_name"], "Laptop")

    async def test_too_long_name_is_rejected_before_touching_the_panel(self):
        request = self._request({"token": _device_hwid_token("ABC123XYZ"), "name": "x" * 33})

        response, body, save, invalidate_caches = await self._call(request)

        self.assertEqual(response.status, 400)
        self.assertEqual(body["error"], "device_name_too_long")
        save.assert_not_awaited()
        self.panel_service.get_user_devices.assert_not_awaited()
        invalidate_caches.assert_not_awaited()

    async def test_unknown_token_is_not_found_and_saves_nothing(self):
        request = self._request({"token": _device_hwid_token("NOT-MINE"), "name": "Mine now"})

        response, body, save, _ = await self._call(request)

        self.assertEqual(response.status, 404)
        self.assertEqual(body["error"], "device_not_found")
        save.assert_not_awaited()
        self.session.commit.assert_not_awaited()

    async def test_non_ascii_token_is_not_found_instead_of_crashing(self):
        request = self._request({"token": "ключ-устройства", "name": "Name"})

        response, body, save, _ = await self._call(request)

        self.assertEqual(response.status, 404)
        self.assertEqual(body["error"], "device_not_found")
        save.assert_not_awaited()

    async def test_inactive_subscription_uses_the_linked_panel_user(self):
        token = _device_hwid_token("ABC123XYZ")
        request = self._request(
            {"token": token, "name": "Old phone"},
            active={},
            db_user=SimpleNamespace(is_banned=False, panel_user_uuid="linked-panel-user"),
        )

        response, _, save, _ = await self._call(request)

        self.assertEqual(response.status, 200)
        self.panel_service.get_user_devices.assert_awaited_once_with("linked-panel-user")
        save.assert_awaited_once_with(self.session, 42, token, "Old phone")


class DeviceNameMergeWiringTests(IsolatedAsyncioTestCase):
    async def test_transfer_entitlement_ownership_moves_device_names(self):
        from db.dal import user_merge_entitlements

        session = MagicMock()
        session.execute = AsyncMock(return_value=MagicMock())
        for method in ("flush", "scalar", "get", "refresh", "delete"):
            setattr(session, method, AsyncMock(return_value=None))
        with patch.object(user_merge_entitlements, "merge_device_names", AsyncMock()) as merge:
            await user_merge_entitlements.transfer_entitlement_ownership(
                session, source_user_id=1, target_user_id=2, panel_user_uuid="panel-user"
            )

        merge.assert_awaited_once_with(session, 1, 2)
