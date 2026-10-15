"""Stable, optional installation-guide targets shared by authored links."""

import re


def legacy_install_app_id(name: str) -> str:
    """Keep old unnamed applications addressable independently of list order."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:64] or "app"


def install_target_params(platform: str | None, app: str | None) -> dict[str, str]:
    platform_id = str(platform or "").strip()
    if not platform_id:
        return {}
    result = {"platform": platform_id}
    app_id = str(app or "").strip()
    if app_id:
        result["app"] = app_id
    return result
