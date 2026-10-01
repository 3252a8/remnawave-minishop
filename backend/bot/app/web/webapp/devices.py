import hashlib
import hmac
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_session_factory,
    get_settings,
    get_subscription_service,
)
from bot.app.web.http_contracts import HttpResponseModel
from bot.app.web.webapp.cache_helpers import (
    invalidate_webapp_user_caches,
    webapp_cached_user_payload,
)
from bot.services.device_names import DEVICE_NAME_MAX_LENGTH, normalize_device_name
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings
from db.dal import device_name_dal, user_dal

from .assets import (
    _enforce_webapp_rate_limit,
)
from .common import (
    _coerce_int_or_none,
    _json_error,
    _parse_model_payload,
    _require_user_id,
)
from .payloads import (
    WebAppDeviceDisconnectPayload,
    WebAppDeviceRenamePayload,
)
from .response_helpers import json_response

logger = logging.getLogger(__name__)


async def devices_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    if not settings.MY_DEVICES_SECTION_ENABLED:
        return _json_error(404, "devices_disabled", "Devices section is disabled")

    async_session_factory: sessionmaker = get_session_factory(request)
    subscription_service: SubscriptionService = get_subscription_service(request)
    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")

        result = await webapp_cached_user_payload(
            settings,
            "devices",
            user_id,
            int(settings.WEBAPP_DEVICES_CACHE_TTL_SECONDS or 0),
            lambda: _load_devices_payload(
                subscription_service,
                session,
                user_id,
                fallback_panel_user_uuid=str(getattr(db_user, "panel_user_uuid", "") or "").strip()
                or None,
            ),
        )
    if isinstance(result, dict) and result.get("ok") is True:
        return json_response({"ok": True, **(result.get("payload") or {})})
    if isinstance(result, dict) and not result.get("error"):
        # Backward-compatible with payloads written by older versions under
        # the same Redis cache key.
        return json_response({"ok": True, **result})
    if not isinstance(result, dict):
        result = {}
    if not result.get("ok"):
        return _json_error(
            int(result.get("status") or 500),
            str(result.get("error") or "devices_load_failed"),
            str(result.get("message") or "Failed to load devices"),
        )
    return json_response({"ok": True, **(result.get("payload") or {})})


async def _load_devices_payload(
    subscription_service: SubscriptionService,
    session: AsyncSession,
    user_id: int,
    fallback_panel_user_uuid: str | None = None,
) -> dict[str, Any]:
    active = await subscription_service.get_active_subscription_details(session, user_id)
    panel_user_uuid = str((active or {}).get("user_id") or fallback_panel_user_uuid or "").strip()
    if not panel_user_uuid:
        return _empty_inactive_devices_payload()

    panel_service = getattr(subscription_service, "panel_service", None)
    if not panel_service:
        return {
            "ok": False,
            "status": 503,
            "error": "panel_unavailable",
            "message": "Panel service unavailable",
        }

    try:
        devices_response = await panel_service.get_user_devices(panel_user_uuid)
    except Exception:
        logger.exception("Failed to load WebApp devices for user %s", user_id)
        return {
            "ok": False,
            "status": 502,
            "error": "devices_load_failed",
            "message": "Failed to load devices",
        }
    if devices_response is None:
        return {
            "ok": False,
            "status": 502,
            "error": "devices_load_failed",
            "message": "Failed to load devices",
        }

    devices = _normalize_devices_response(devices_response)
    device_names = await device_name_dal.get_device_names(session, user_id)
    max_devices = _coerce_int_or_none(active.get("max_devices")) if active else None
    return {
        "ok": True,
        "payload": {
            "enabled": True,
            "subscription_active": _devices_subscription_is_active(active),
            "current_devices": len(devices),
            "max_devices": max_devices,
            "max_devices_label": _format_devices_limit(max_devices),
            "devices": [
                _serialize_device(device, index, device_names)
                for index, device in enumerate(devices, start=1)
            ],
        },
    }


def _empty_inactive_devices_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "payload": {
            "enabled": True,
            "subscription_active": False,
            "current_devices": 0,
            "max_devices": None,
            "max_devices_label": _format_devices_limit(None),
            "devices": [],
        },
    }


def _devices_subscription_is_active(active: dict[str, Any] | None) -> bool:
    if not active:
        return False
    end_date = active.get("end_date")
    if not isinstance(end_date, datetime):
        return False
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=UTC)
    return end_date > datetime.now(UTC)


async def disconnect_device_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    rate_limit_response = await _enforce_webapp_rate_limit(
        request,
        user_id=user_id,
        action="devices_disconnect",
    )
    if rate_limit_response:
        return rate_limit_response

    settings: Settings = get_settings(request)
    if not settings.MY_DEVICES_SECTION_ENABLED:
        return _json_error(404, "devices_disabled", "Devices section is disabled")

    disconnect_payload = await _parse_model_payload(request, WebAppDeviceDisconnectPayload)
    token = str(disconnect_payload.token or "").strip()

    async_session_factory: sessionmaker = get_session_factory(request)
    subscription_service: SubscriptionService = get_subscription_service(request)
    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")

        active = await subscription_service.get_active_subscription_details(session, user_id)
        panel_user_uuid = active.get("user_id") if active else None
        if not panel_user_uuid:
            return _json_error(400, "subscription_not_active", "Subscription is not active")

        panel_service = getattr(subscription_service, "panel_service", None)
        if not panel_service:
            return _json_error(503, "panel_unavailable", "Panel service unavailable")

        try:
            devices_response = await panel_service.get_user_devices(panel_user_uuid)
        except Exception:
            logger.exception("Failed to load WebApp devices before disconnect for user %s", user_id)
            return _json_error(502, "devices_load_failed", "Failed to load devices")

        target_hwid = None
        for device in _normalize_devices_response(devices_response):
            hwid = str(device.get("hwid") or "").strip()
            if hwid and hmac.compare_digest(_device_hwid_token(hwid), token):
                target_hwid = hwid
                break

        if not target_hwid:
            return _json_error(404, "device_not_found", "Device not found")

        success = await panel_service.disconnect_device(panel_user_uuid, target_hwid)
        if not success:
            return _json_error(502, "device_disconnect_failed", "Failed to disconnect device")
        await invalidate_webapp_user_caches(
            settings,
            user_id,
            include_devices=True,
            include_me=False,
        )
        await session.commit()

    return json_response({"ok": True})


async def rename_device_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    rate_limit_response = await _enforce_webapp_rate_limit(
        request,
        user_id=user_id,
        action="devices_rename",
    )
    if rate_limit_response:
        return rate_limit_response

    settings: Settings = get_settings(request)
    if not settings.MY_DEVICES_SECTION_ENABLED:
        return _json_error(404, "devices_disabled", "Devices section is disabled")

    rename_payload = await _parse_model_payload(request, WebAppDeviceRenamePayload)
    token = str(rename_payload.token or "").strip()
    name = normalize_device_name(rename_payload.name)
    if len(name) > DEVICE_NAME_MAX_LENGTH:
        return _json_error(400, "device_name_too_long", "Device name is too long")

    async_session_factory: sessionmaker = get_session_factory(request)
    subscription_service: SubscriptionService = get_subscription_service(request)
    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")

        # Same owner resolution as the device list, so every listed device can be named.
        active = await subscription_service.get_active_subscription_details(session, user_id)
        panel_user_uuid = str(
            (active or {}).get("user_id") or getattr(db_user, "panel_user_uuid", "") or ""
        ).strip()
        panel_service = getattr(subscription_service, "panel_service", None)
        if not panel_user_uuid:
            return _json_error(404, "device_not_found", "Device not found")
        if not panel_service:
            return _json_error(503, "panel_unavailable", "Panel service unavailable")

        try:
            devices_response = await panel_service.get_user_devices(panel_user_uuid)
        except Exception:
            logger.exception("Failed to load WebApp devices before rename for user %s", user_id)
            return _json_error(502, "devices_load_failed", "Failed to load devices")

        match = _find_device_by_token(_normalize_devices_response(devices_response), token)
        if match is None:
            return _json_error(404, "device_not_found", "Device not found")
        index, device, device_token = match

        await device_name_dal.set_device_name(session, user_id, device_token, name)
        await session.commit()

    await invalidate_webapp_user_caches(
        settings,
        user_id,
        include_devices=True,
        include_me=False,
    )
    return json_response(
        {"ok": True, "device": _serialize_device(device, index, {device_token: name})}
    )


def _find_device_by_token(
    devices: list[dict[str, Any]], token: str
) -> tuple[int, dict[str, Any], str] | None:
    expected = token.encode()
    for index, device in enumerate(devices, start=1):
        hwid = str(device.get("hwid") or "").strip()
        if not hwid:
            continue
        device_token = _device_hwid_token(hwid)
        if hmac.compare_digest(device_token.encode(), expected):
            return index, device, device_token
    return None


def _device_hwid_token(hwid: str) -> str:
    return hashlib.sha256(str(hwid or "").encode()).hexdigest()[:32]


def _shorten_hwid_for_display(hwid: str | None, max_length: int = 24) -> str:
    value = str(hwid or "").strip()
    if len(value) <= max_length:
        return value
    return f"{value[:8]}...{value[-6:]}"


def _normalize_devices_response(devices_response: Any) -> list[dict[str, Any]]:
    if isinstance(devices_response, dict):
        response = devices_response.get("response")
        if isinstance(response, dict):
            devices = response.get("devices") or []
        elif isinstance(response, list):
            devices = response
        else:
            devices = devices_response.get("devices") or devices_response.get("data") or []
    else:
        devices = devices_response or []
    if not isinstance(devices, list):
        return []
    return [device for device in devices if isinstance(device, dict)]


def _format_devices_limit(max_devices: int | None) -> str:
    if max_devices in (None, 0):
        return "Unlimited"
    return str(max_devices)


def _format_device_datetime(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    try:
        normalized = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return normalized.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return text


def _serialize_device_datetime(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=UTC)
        return normalized.isoformat()
    return str(value)


class WebAppDeviceOut(HttpResponseModel):
    # Field order mirrors the legacy ``_serialize_device`` dict.
    index: int
    # The user's label when set, otherwise ``default_name``.
    display_name: str
    platform: str
    os_version: str
    platform_label: str
    user_agent: str
    created_at: str | None = None
    created_at_text: str
    last_connected_at: str | None = None
    last_connected_at_text: str
    hwid_short: str
    token: str
    can_disconnect: bool
    default_name: str = ""
    custom_name: str | None = None

    @classmethod
    def from_panel_device(
        cls, device: dict[str, Any], index: int, custom_name: str | None = None
    ) -> "WebAppDeviceOut":
        hwid = str(device.get("hwid") or "").strip()
        model = str(device.get("deviceModel") or "").strip()
        platform = str(device.get("platform") or "").strip()
        os_version = str(device.get("osVersion") or "").strip()
        user_agent = str(device.get("userAgent") or "").strip()
        default_name = model or platform or f"Device {index}"
        platform_label = " ".join(part for part in (platform, os_version) if part).strip()
        last_connected_at = device.get("updatedAt") or device.get("createdAt")
        return cls(
            index=index,
            display_name=custom_name or default_name,
            platform=platform,
            os_version=os_version,
            platform_label=platform_label,
            user_agent=user_agent,
            created_at=_serialize_device_datetime(device.get("createdAt")),
            created_at_text=_format_device_datetime(device.get("createdAt")),
            last_connected_at=_serialize_device_datetime(last_connected_at),
            last_connected_at_text=_format_device_datetime(last_connected_at),
            hwid_short=_shorten_hwid_for_display(hwid),
            token=_device_hwid_token(hwid) if hwid else "",
            can_disconnect=bool(hwid),
            default_name=default_name,
            custom_name=custom_name or None,
        )


def _serialize_device(
    device: dict[str, Any],
    index: int,
    device_names: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    hwid = str(device.get("hwid") or "").strip()
    custom_name = (device_names or {}).get(_device_hwid_token(hwid)) if hwid else None
    return WebAppDeviceOut.from_panel_device(device, index, custom_name).model_dump(mode="json")
