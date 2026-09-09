"""Safe normalization for Remnawave HWID device webhook events."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

HWID_DEVICE_ADDED_EVENT = "user_hwid_devices.added"
HWID_DEVICE_DELETED_EVENT = "user_hwid_devices.deleted"
HWID_DEVICE_EVENTS = frozenset({HWID_DEVICE_ADDED_EVENT, HWID_DEVICE_DELETED_EVENT})

_DEVICE_KEYS = ("hwidDevice", "hwidUserDevice", "device")


def _bounded_text(value: Any, *, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _device_payload(event_data: dict[str, Any]) -> dict[str, Any]:
    for key in _DEVICE_KEYS:
        candidate = event_data.get(key)
        if isinstance(candidate, dict):
            return candidate
    for key, candidate in event_data.items():
        if key == "user" or not isinstance(candidate, dict):
            continue
        if "hwid" in candidate:
            return candidate
    return {}


def _fingerprint(secret: str, device: dict[str, Any], event_data: dict[str, Any]) -> str:
    hwid = _bounded_text(device.get("hwid"), limit=128)
    created_at = _bounded_text(
        device.get("createdAt") or device.get("created_at"),
        limit=64,
    )
    if hwid:
        # Remnawave reuses the HWID when a removed device is connected again.
        # Its new creation timestamp distinguishes that legitimate new event,
        # while duplicate deliveries of the same webhook keep one fingerprint.
        material = f"{hwid}\0{created_at}" if created_at else hwid
    else:
        safe_fallback = {
            "platform": device.get("platform"),
            "osVersion": device.get("osVersion"),
            "deviceModel": device.get("deviceModel"),
            "createdAt": device.get("createdAt"),
            "eventKeys": sorted(str(key) for key in event_data if key != "user"),
        }
        material = json.dumps(
            safe_fallback,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    if secret:
        return hmac.new(secret.encode(), material.encode(), hashlib.sha256).hexdigest()[:24]
    return hashlib.sha256(material.encode()).hexdigest()[:24]


def hwid_device_webhook_context(
    event_data: dict[str, Any],
    *,
    secret: str,
) -> dict[str, str]:
    """Return only user-safe device fields plus an opaque dedupe fingerprint.

    Raw HWID, request IP, and user-agent values are deliberately excluded from
    the queue payload, logs, domain events, and user notifications.
    """

    device = _device_payload(event_data)
    context = {
        "fingerprint": _fingerprint(secret, device, event_data),
        "platform": _bounded_text(device.get("platform"), limit=80),
        "os_version": _bounded_text(
            device.get("osVersion") or device.get("os_version"),
            limit=80,
        ),
        "device_model": _bounded_text(
            device.get("deviceModel") or device.get("device_model"),
            limit=120,
        ),
        "created_at": _bounded_text(
            device.get("createdAt") or device.get("created_at"),
            limit=64,
        ),
    }
    return {key: value for key, value in context.items() if value}


def hwid_device_context_fingerprint(context: dict[str, Any] | None) -> str:
    value = str((context or {}).get("fingerprint") or "").strip().lower()
    if len(value) == 24 and all(char in "0123456789abcdef" for char in value):
        return value
    return ""


__all__ = [
    "HWID_DEVICE_ADDED_EVENT",
    "HWID_DEVICE_DELETED_EVENT",
    "HWID_DEVICE_EVENTS",
    "hwid_device_context_fingerprint",
    "hwid_device_webhook_context",
]
