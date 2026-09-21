"""Subscription install guides routes and response shaping.

Panel config resolution lives in ``guides_panel_config``; the public
share-token subscription payload lives in ``guides_public``. This module
keeps the route handlers and re-exports the shared surface.
"""

import json
import logging
from typing import Any

from aiohttp import web

from db.dal import subscription_dal, user_dal  # noqa: F401  (patched via this namespace in tests)

from .common import (
    _require_user_id,
)
from .guide_document import load_guide_content
from .guides_panel_config import (  # noqa: F401
    PANEL_DEFAULT_SUBPAGE_CONFIG_UUID,
    SUBSCRIPTION_GUIDES_CACHE_ERROR_TTL_SECONDS,
    SUBSCRIPTION_GUIDES_RESOLVED_CACHE_MAX_ITEMS,
    SUBSCRIPTION_GUIDES_RESOLVED_CACHE_TTL_SECONDS,
    _PanelSubscriptionPageConfigUnavailable,
    _subscription_guides_status_for_request,
    _subscription_guides_status_from_panel_short_uuid_cached,
    _subscription_guides_status_shared,
    _warm_panel_subscription_page_configs,
)
from .guides_public import (  # noqa: F401
    SUBSCRIPTION_GUIDES_PUBLIC_CACHE_TTL_SECONDS,
    _public_subscription_payload_cached,
)
from .response_helpers import json_response
from .subscription_access import PanelLookupUnavailable

logger = logging.getLogger(__name__)

SUBSCRIPTION_GUIDES_BROWSER_CACHE_CONTROL = "private, no-store"


def _subscription_guides_json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _subscription_guides_json_response(
    payload: dict[str, Any],
    *,
    status: int = 200,
    cache_control: str | None = None,
) -> web.Response:
    response = json_response(payload, status=status, dumps=_subscription_guides_json_dumps)
    if cache_control:
        response.headers["Cache-Control"] = cache_control
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


async def warm_subscription_guides_config(app: web.Application) -> None:
    try:
        await _subscription_guides_status_shared(app)
    except Exception as exc:
        logger.warning("Failed to warm subscription guides config: %s", exc)
    try:
        await _warm_panel_subscription_page_configs(app)
    except Exception as exc:
        logger.warning("Failed to warm panel subscription page configs: %s", exc)


async def subscription_guides_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    status, guide_document = await load_guide_content(request, user_id=user_id)
    payload = {
        "enabled": bool(status.get("enabled")),
        "config": _subscription_guides_response_config(status.get("config"))
        if status.get("enabled")
        else None,
        "source": status.get("source"),
        "guide_document": guide_document,
    }
    if status.get("error"):
        payload["error"] = status["error"]
    return _subscription_guides_json_response(
        {"ok": True, **payload},
        cache_control=SUBSCRIPTION_GUIDES_BROWSER_CACHE_CONTROL if status.get("enabled") else None,
    )


async def public_subscription_guides_route(request: web.Request) -> web.Response:
    share_token = subscription_dal.normalize_install_share_token(
        request.match_info.get("share_token")
    )
    if not share_token:
        return json_response({"ok": False, "error": "invalid_share_token"}, status=404)

    try:
        subscription = await _public_subscription_payload_cached(request, share_token)
    except PanelLookupUnavailable:
        return _subscription_guides_json_response(
            {"ok": False, "error": "subscription_unavailable"},
            status=503,
            cache_control=SUBSCRIPTION_GUIDES_BROWSER_CACHE_CONTROL,
        )
    if not subscription.get("active"):
        return _subscription_guides_json_response(
            {
                "ok": False,
                "enabled": False,
                "config": None,
                "source": None,
                "subscription": subscription,
                "error": "subscription_unavailable",
            },
            status=404,
        )

    panel_user_uuid = str(subscription.pop("_panel_user_uuid", "") or "").strip()
    status, guide_document = await load_guide_content(
        request,
        panel_short_uuid=subscription.get("panel_short_uuid"),
        panel_user_uuid=panel_user_uuid,
    )
    payload = {
        "enabled": bool(status.get("enabled")),
        "config": _subscription_guides_response_config(status.get("config"))
        if status.get("enabled")
        else None,
        "source": status.get("source"),
        "guide_document": guide_document,
        "subscription": subscription,
    }
    if status.get("error"):
        payload["error"] = status["error"]
    return _subscription_guides_json_response(
        {"ok": True, **payload},
        cache_control=SUBSCRIPTION_GUIDES_BROWSER_CACHE_CONTROL if status.get("enabled") else None,
    )


def _subscription_guides_response_config(config: Any) -> Any:
    if not isinstance(config, dict):
        return config

    svg_library = config.get("svgLibrary")
    if not isinstance(svg_library, dict) or not svg_library:
        return config

    referenced_keys = _subscription_guides_referenced_svg_keys(config)
    if not referenced_keys:
        return config

    compact_svg_library = {
        key: svg_library[key] for key in sorted(referenced_keys) if key in svg_library
    }
    if len(compact_svg_library) == len(svg_library):
        return config

    compact_config = dict(config)
    compact_config["svgLibrary"] = compact_svg_library
    return compact_config


def _subscription_guides_referenced_svg_keys(config: dict[str, Any]) -> set[str]:
    keys: set[str] = set()

    def add(value: Any) -> None:
        key = str(value or "").strip()
        if key:
            keys.add(key)

    platforms = config.get("platforms")
    if not isinstance(platforms, dict):
        return keys

    for platform in platforms.values():
        if not isinstance(platform, dict):
            continue
        add(platform.get("svgIconKey"))
        for app in platform.get("apps") or []:
            if not isinstance(app, dict):
                continue
            add(app.get("svgIconKey"))
            for block in app.get("blocks") or []:
                if not isinstance(block, dict):
                    continue
                add(block.get("svgIconKey"))
                for button in block.get("buttons") or []:
                    if isinstance(button, dict):
                        add(button.get("svgIconKey"))
    return keys
