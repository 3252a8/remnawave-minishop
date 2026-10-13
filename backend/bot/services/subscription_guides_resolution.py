"""Canonical Panel subscription-page identity and configuration resolution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from config.subscription_guides_config import (
    SubscriptionGuidesConfigError,
    validate_panel_subscription_guides_config,
)

PANEL_DEFAULT_SUBPAGE_CONFIG_UUID = "00000000-0000-0000-0000-000000000000"


def _panel_subpage_config_uuid(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in (
        "subpageConfigUuid",
        "subscriptionPageConfigUuid",
        "subPageConfigUuid",
        "subpage_config_uuid",
    ):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    for key in (
        "response",
        "data",
        "result",
    ):
        nested = _panel_subpage_config_uuid(payload.get(key))
        if nested:
            return nested
    for key in (
        "subscriptionPageConfig",
        "subpageConfig",
        "subPageConfig",
    ):
        nested_payload = payload.get(key)
        nested = _panel_subpage_config_uuid(nested_payload)
        if nested:
            return nested
        if isinstance(nested_payload, dict):
            nested_uuid = str(nested_payload.get("uuid") or "").strip()
            if nested_uuid:
                return nested_uuid
    nested_uuid = str(payload.get("uuid") or "").strip()
    if nested_uuid and not _looks_like_panel_subscription_page_config(payload):
        return nested_uuid
    return ""


async def _default_panel_subscription_page_config_uuid(panel_service: Any) -> str:
    get_list = getattr(panel_service, "get_subscription_page_config_list", None)
    if not callable(get_list):
        return ""
    payload = await get_list()
    configs = _panel_subscription_page_config_items(payload)
    if not configs:
        return ""

    candidates: list[dict[str, Any]] = configs
    for item in candidates:
        uuid = str(item.get("uuid") or "").strip()
        if uuid == PANEL_DEFAULT_SUBPAGE_CONFIG_UUID:
            return uuid

    candidates.sort(key=lambda item: int(item.get("viewPosition") or 0))
    for item in candidates:
        uuid = str(item.get("uuid") or "").strip()
        if uuid:
            return uuid
    return ""


def _panel_subscription_page_config_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("configs", "items", "subscriptionPageConfigs", "subpageConfigs"):
        items = payload.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    for key in ("response", "data", "result"):
        items = _panel_subscription_page_config_items(payload.get(key))
        if items:
            return items
    return []


def _panel_external_squad_uuid_from_user(panel_user: Any) -> str:
    if not isinstance(panel_user, dict):
        return ""
    for key in ("externalSquadUuid", "external_squad_uuid", "externalSquadUUID"):
        value = str(panel_user.get(key) or "").strip()
        if value:
            return value
    return ""


def _looks_like_panel_subscription_page_config(payload: dict[str, Any]) -> bool:
    return "config" in payload or "viewPosition" in payload or "webpageAllowed" in payload


async def resolve_panel_subscription_guides_config(
    detail: dict[str, Any],
    *,
    owner_configuration: Callable[[], Awaitable[str]],
    configuration_by_uuid: Callable[[str], Awaitable[dict[str, Any]]],
    default_configuration: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Use the same assigned, owner-squad, embedded and default precedence everywhere."""
    config_uuid = _panel_subpage_config_uuid(detail) or await owner_configuration()
    if config_uuid:
        return await configuration_by_uuid(config_uuid)
    try:
        return validate_panel_subscription_guides_config(detail)
    except SubscriptionGuidesConfigError:
        return await default_configuration()
