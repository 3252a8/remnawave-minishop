"""Read-only, owner-scoped connection diagnostics for support processors."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlsplit

from bot.services.message_composition import MINI_APP_SECTIONS, mini_app_section_link
from bot.services.panel_activity import panel_user_last_connected_datetime
from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_guides_resolution import (
    PANEL_DEFAULT_SUBPAGE_CONFIG_UUID,
    _default_panel_subscription_page_config_uuid,
    _panel_external_squad_uuid_from_user,
    _panel_subpage_config_uuid,
    resolve_panel_subscription_guides_config,
)
from config.subscription_guides_config import (
    SubscriptionGuidesConfigError,
    subscription_guides_status,
    validate_panel_subscription_guides_config,
)


def _string(value: object, limit: int = 256) -> str | None:
    return value[:limit] if isinstance(value, str) and value else None


def project_panel_diagnostics(
    user: dict[str, Any], devices: list[dict[str, Any]] | None
) -> dict[str, object]:
    """Unknown last device/server stays unknown; device update is not a connection."""
    traffic = user.get("userTraffic")
    containers = [user, traffic] if isinstance(traffic, dict) else [user]
    connected = panel_user_last_connected_datetime(user)
    result: dict[str, object] = {"last_connected_at": connected.isoformat() if connected else None}
    for target, names in (
        ("last_connected_hwid", ("lastConnectedHwid", "lastConnectedHWID")),
        ("last_server_uuid", ("lastConnectedNodeUuid", "lastConnectedNodeUUID")),
    ):
        result[target] = next(
            (
                _string(item.get(name))
                for item in containers
                for name in names
                if _string(item.get(name))
            ),
            None,
        )
    node = next(
        (
            item.get("lastConnectedNode")
            for item in containers
            if isinstance(item.get("lastConnectedNode"), dict)
        ),
        None,
    )
    result["last_server"] = (
        {key: _string(node.get(key)) for key in ("uuid", "name", "countryCode")}
        if isinstance(node, dict)
        else None
    )
    result["devices"] = (
        None
        if devices is None
        else [
            {
                key: _string(device.get(key), 512)
                for key in (
                    "hwid",
                    "deviceModel",
                    "platform",
                    "osVersion",
                    "userAgent",
                    "createdAt",
                    "updatedAt",
                )
            }
            for device in devices[:100]
        ]
    )
    result["devices_truncated"] = bool(devices and len(devices) > 100)
    result["panel_status"] = _string(user.get("status"))
    result["subscription_url"] = _string(user.get("subscriptionUrl"), 4096)
    return result


def guide_links(config: object) -> list[dict[str, object]]:
    """Expose configured download URLs, never invented store identifiers."""
    if not isinstance(config, dict) or not isinstance(config.get("platforms"), dict):
        return []
    result: list[dict[str, object]] = []
    for platform, data in config["platforms"].items():
        if not isinstance(data, dict):
            continue
        for app in data.get("apps", []):
            if not isinstance(app, dict):
                continue
            for block in app.get("blocks", []):
                if not isinstance(block, dict):
                    continue
                for button in block.get("buttons", []):
                    if not isinstance(button, dict) or button.get("type") != "external":
                        continue
                    link = button.get("link")
                    if (
                        not isinstance(link, str)
                        or urlsplit(link).scheme != "https"
                        or not urlsplit(link).netloc
                    ):
                        continue
                    result.append(
                        {
                            "platform": str(platform),
                            "app": app.get("name"),
                            "labels": button.get("text"),
                            "url": link,
                        }
                    )
                    if len(result) >= 64:
                        return result
    return result


async def connection_diagnostics(
    settings: Any, panel_user_uuid: str | None, short_uuid: str | None
) -> dict[str, object]:
    """Network reads happen outside the ticket transaction and have a total deadline."""
    result: dict[str, object] = {
        "panel_source": "unavailable",
        "devices": None,
        "last_server": None,
    }
    base_url = settings.SUBSCRIPTION_MINI_APP_URL
    result["app_sections"] = {
        section: link
        for section in MINI_APP_SECTIONS
        if (link := mini_app_section_link(base_url, section))
    }
    prefer_panel = bool(settings.SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED) and not (
        settings.SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED
        and settings.SUBSCRIPTION_PAGE_CONFIG_JSON
    )
    try:
        local = subscription_guides_status(settings)
        result["download_links"] = guide_links(local.get("config"))
    except (AttributeError, ValueError):
        result["download_links"] = []
    if not panel_user_uuid or not settings.PANEL_API_URL or not settings.PANEL_API_KEY:
        return result
    try:
        async with asyncio.timeout(8), PanelApiService(settings) as panel:
            user: object
            devices: object
            user, devices = await asyncio.gather(
                panel.get_user_by_uuid(panel_user_uuid, use_cache=False),
                panel.get_user_devices(panel_user_uuid, force_refresh=True),
                return_exceptions=True,
            )
            if isinstance(user, dict) and str(user.get("uuid", panel_user_uuid)) == panel_user_uuid:
                # Some panel versions include an owner reference on device records.
                scoped = (
                    None
                    if not isinstance(devices, list)
                    else [
                        item
                        for item in devices
                        if str(item.get("userUuid", panel_user_uuid)) == panel_user_uuid
                    ]
                )
                result.update(project_panel_diagnostics(user, scoped))
                result["panel_source"] = "live"

                async def server_summary() -> None:
                    node_uuid = result.get("last_server_uuid")
                    if isinstance(node_uuid, str) and not result.get("last_server"):
                        node = await panel.get_node_summary(node_uuid)
                        if (
                            isinstance(node, dict)
                            and str(node.get("uuid", "")).lower() == node_uuid.lower()
                        ):
                            result["last_server"] = {
                                key: _string(node.get(key))
                                for key in ("uuid", "name", "countryCode")
                            }

                async def download_configuration() -> None:
                    resolved_short = _string(user.get("shortUuid")) or short_uuid
                    if not resolved_short or not prefer_panel:
                        return
                    config = await _resolved_guide_configuration(
                        panel, settings, user, resolved_short
                    )
                    result["download_links"] = guide_links(config)

                # Optional node reads must not suppress the owner's client configuration.
                await asyncio.gather(
                    server_summary(), download_configuration(), return_exceptions=True
                )
    except Exception:
        # No provider error bodies or credentials enter the support projection.
        pass
    return result


async def _resolved_guide_configuration(
    panel: PanelApiService, settings: Any, user: dict[str, Any], short_uuid: str
) -> dict[str, Any]:
    async def configuration_by_uuid(config_uuid: str) -> dict[str, Any]:
        detail = await panel.get_subscription_page_config_by_uuid(config_uuid)
        if detail is None:
            raise SubscriptionGuidesConfigError("Panel configuration is unavailable")
        return validate_panel_subscription_guides_config(detail)

    async def owner_configuration() -> str:
        squad_uuid = _panel_external_squad_uuid_from_user(user)
        if not squad_uuid:
            return ""
        squad = await panel.get_external_squad(squad_uuid)
        return _panel_subpage_config_uuid(squad)

    async def default_configuration() -> dict[str, Any]:
        selected = str(getattr(settings, "SUBSCRIPTION_PAGE_CONFIG_UUID", "") or "").strip()
        selected = selected or await _default_panel_subscription_page_config_uuid(panel)
        selected = selected or PANEL_DEFAULT_SUBPAGE_CONFIG_UUID
        try:
            return await configuration_by_uuid(selected)
        except SubscriptionGuidesConfigError:
            if selected == PANEL_DEFAULT_SUBPAGE_CONFIG_UUID:
                raise
            return await configuration_by_uuid(PANEL_DEFAULT_SUBPAGE_CONFIG_UUID)

    try:
        detail = await panel.get_subscription_page_config_by_short_uuid(short_uuid)
        if not isinstance(detail, dict):
            raise SubscriptionGuidesConfigError("Resolved configuration is unavailable")
        return await resolve_panel_subscription_guides_config(
            detail,
            owner_configuration=owner_configuration,
            configuration_by_uuid=configuration_by_uuid,
            default_configuration=default_configuration,
        )
    except SubscriptionGuidesConfigError:
        return await default_configuration()
