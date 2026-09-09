from __future__ import annotations

import logging
from typing import Any, Protocol

from .user_schemas import AdminUserHwidDevicesOut

logger = logging.getLogger(__name__)


class PanelDevicesReader(Protocol):
    async def get_user_devices(
        self,
        user_uuid: str,
        *,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]] | None: ...


class DeviceLimitSettings(Protocol):
    USER_HWID_DEVICE_LIMIT: int | None


def _positive_device_limit(value: Any) -> int | None:
    try:
        limit = int(value) if value is not None else 0
    except (TypeError, ValueError):
        return None
    return limit if limit > 0 else None


def _effective_device_limit(
    panel_user_snapshot: dict[str, Any] | None,
    active_subscription: object | None,
    settings: DeviceLimitSettings,
) -> int | None:
    panel_limit = (
        panel_user_snapshot.get("hwidDeviceLimit") if panel_user_snapshot is not None else None
    )
    if panel_limit is not None:
        return _positive_device_limit(panel_limit)

    base_limit = getattr(active_subscription, "hwid_device_limit", None)
    if base_limit is None:
        base_limit = settings.USER_HWID_DEVICE_LIMIT
    normalized_base = _positive_device_limit(base_limit)
    if normalized_base is None:
        return None
    extra_devices = max(0, int(getattr(active_subscription, "extra_hwid_devices", 0) or 0))
    return normalized_base + extra_devices


async def build_admin_user_hwid_devices(
    *,
    panel_service: PanelDevicesReader | None,
    panel_user_uuid: str | None,
    panel_user_snapshot: dict[str, Any] | None,
    active_subscription: object | None,
    settings: DeviceLimitSettings,
) -> AdminUserHwidDevicesOut:
    current_devices: int | None = 0 if not panel_user_uuid else None
    if panel_service is not None and panel_user_uuid:
        try:
            devices = await panel_service.get_user_devices(panel_user_uuid)
            current_devices = len(devices) if devices is not None else None
        except Exception as exc:  # pragma: no cover - defensive admin enrichment
            logger.warning(
                "Failed to fetch HWID devices for admin user %s: %s",
                panel_user_uuid,
                exc,
            )

    return AdminUserHwidDevicesOut(
        current_devices=current_devices,
        max_devices=_effective_device_limit(
            panel_user_snapshot,
            active_subscription,
            settings,
        ),
    )
