"""Versioned install document and Remnawave v1 ingress adapter."""

import copy
import hashlib
import json
import re
from typing import Any

from aiohttp import web

from .guides_panel_config import _subscription_guides_status_for_request

_PLATFORM_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_EXACT_RESOURCE = re.compile(
    r"\{\{\s*(SUBSCRIPTION_LINK|HAPP_CRYPT3_LINK|HAPP_CRYPT4_LINK|INCY_CRYPT1_LINK)\s*\}\}\Z"
)
_RESOURCE_REPRESENTATIONS = {
    "SUBSCRIPTION_LINK": "http",
    "HAPP_CRYPT3_LINK": "happ-crypt3",
    "HAPP_CRYPT4_LINK": "happ",
    "INCY_CRYPT1_LINK": "incy-crypt1",
}


def remnawave_v1_to_guide_document(
    config: dict[str, Any], *, source: str | None = None
) -> dict[str, Any]:
    if config.get("version") != "1":
        raise ValueError("Unsupported Remnawave guide version")
    platforms = config.get("platforms")
    if not isinstance(platforms, dict):
        raise ValueError("Invalid Remnawave platforms")
    document = copy.deepcopy({key: value for key, value in config.items() if key != "platforms"})
    document.pop("version", None)
    converted: list[dict[str, Any]] = []
    for platform_id, raw_platform in platforms.items():
        if not isinstance(platform_id, str) or not _PLATFORM_ID.fullmatch(platform_id):
            raise ValueError("Invalid platform ID")
        if not isinstance(raw_platform, dict):
            raise ValueError("Invalid platform")
        platform = {"id": platform_id, **copy.deepcopy(raw_platform)}
        for app in platform.get("apps", []):
            for block in app.get("blocks", []):
                for button in block.get("buttons", []):
                    link = str(button.get("link") or "")
                    resource = _EXACT_RESOURCE.fullmatch(link)
                    target: dict[str, str]
                    if resource:
                        target = {
                            "kind": "resource",
                            "resourceId": "primary-subscription",
                            "representation": _RESOURCE_REPRESENTATIONS[resource.group(1)],
                        }
                    else:
                        target = {"kind": "literal", "value": link}
                    button["action"] = {
                        "kind": "copy" if button.get("type") == "copyButton" else "open",
                        "target": target,
                    }
        converted.append(platform)
    document["schemaVersion"] = 1
    document["source"] = source
    document["revision"] = hashlib.sha256(
        json.dumps(config, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    document["platforms"] = converted
    document["resources"] = [{"id": "primary-subscription", "kind": "subscription"}]
    return document


async def load_guide_content(
    request: web.Request,
    *,
    user_id: int | None = None,
    panel_short_uuid: str | None = None,
    panel_user_uuid: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Keep the established panel/JSON/file/default priority at the source boundary."""
    status = await _subscription_guides_status_for_request(
        request,
        user_id=user_id,
        panel_short_uuid=panel_short_uuid,
        panel_user_uuid=panel_user_uuid,
    )
    config = status.get("config")
    if user_id is not None:
        from bot.app.web.context import get_session_factory, get_settings
        from bot.plugins.extensions import UserContext
        from bot.plugins.extensions.guides import merge_guides
        from bot.plugins.extensions.registry import get_registry
        from db.dal import user_dal

        if get_settings(request).SUBSCRIPTION_GUIDES_ENABLED and any(
            entry.contributions.guides for entry in get_registry().owners().values()
        ):
            async with get_session_factory(request)() as session:
                user = await user_dal.get_user_by_id(session, user_id)
                if user is not None and not user.is_banned:
                    merged = await merge_guides(
                        UserContext(session, user_id, str(user.language_code or "en")),
                        config if isinstance(config, dict) and status.get("enabled") else None,
                    )
                    if merged is not None:
                        config = merged
                        status = {**status, "enabled": True, "config": merged}
    if not status.get("enabled") or not isinstance(config, dict):
        return status, None
    return status, remnawave_v1_to_guide_document(config, source=str(status.get("source") or ""))
