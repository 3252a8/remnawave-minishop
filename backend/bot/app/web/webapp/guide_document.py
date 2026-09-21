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
    r"\{\{\s*(SUBSCRIPTION_LINK|HAPP_CRYPT3_LINK|HAPP_CRYPT4_LINK)\s*\}\}\Z"
)


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
                            "representation": (
                                "http" if resource.group(1) == "SUBSCRIPTION_LINK" else "happ"
                            ),
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
    if not status.get("enabled") or not isinstance(config, dict):
        return status, None
    return status, remnawave_v1_to_guide_document(config, source=str(status.get("source") or ""))
