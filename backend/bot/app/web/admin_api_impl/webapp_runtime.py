from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from bot.app.web.context import (
    get_settings,
)
from bot.app.web.webapp.cache_helpers import (
    invalidate_all_webapp_user_payloads,
    reset_subscription_guides_cache,
    reset_webapp_settings_cache,
)

WEBAPP_APPEARANCE_SETTING_KEYS = frozenset(
    {
        "WEBAPP_TITLE",
        "WEBAPP_LOGO_URL",
        "WEBAPP_FAVICON_URL",
        "WEBAPP_FAVICON_USE_CUSTOM",
        "WEBAPP_LOGO_FAVICON_URL",
    }
)

WEBAPP_DEVICE_PAYLOAD_SETTING_KEYS = frozenset(
    {
        "MY_DEVICES_SECTION_ENABLED",
        "USER_HWID_DEVICE_LIMIT",
        "USER_TRAFFIC_LIMIT_GB",
        "USER_TRAFFIC_STRATEGY",
    }
)


def changed_setting_keys(
    updates: Mapping[str, Any] | None = None,
    deletes: Sequence[Any] | None = None,
) -> set[str]:
    keys = {str(key) for key in (updates or {}).keys()}
    keys.update(str(key) for key in (deletes or []) if key is not None)
    return keys


async def refresh_webapp_runtime_after_settings_change(
    request: Any,
    *,
    updates: Mapping[str, Any] | None = None,
    deletes: Sequence[Any] | None = None,
    include_user_payloads: bool = True,
) -> None:
    settings = get_settings(request)
    keys = changed_setting_keys(updates, deletes)

    reset_webapp_settings_cache(request.app)
    reset_subscription_guides_cache(request.app)

    if include_user_payloads:
        await invalidate_all_webapp_user_payloads(
            settings,
            include_devices=bool(keys & WEBAPP_DEVICE_PAYLOAD_SETTING_KEYS),
        )

    if keys & WEBAPP_APPEARANCE_SETTING_KEYS:
        request.app["webapp_logo_cache"] = None
        from bot.app.web.admin_api_impl.themes import prune_unused_appearance_assets

        prune_unused_appearance_assets(settings)
