"""Validate the separately authorized customer UI surface of a signed package."""

import re
from typing import Any

_ID = re.compile(r"[a-z][a-z0-9-]{1,63}\Z")
USER_TARGETS = frozenset(
    {"user.home.cards", "user.profile.actions", "user.subscription.actions", "user.install.blocks"}
)


def validate_user_frontend(value: Any, files: dict[str, Any]) -> None:
    if not isinstance(value, dict):
        raise ValueError("invalid_user_frontend")
    if set(value) - {"entry", "styles", "assets", "pages", "slots"}:
        raise ValueError("invalid_user_frontend")
    if not isinstance(value.get("entry"), str):
        raise ValueError("invalid_user_frontend")
    for key in ("styles", "assets", "pages", "slots"):
        if not isinstance(value.get(key, []), list) or len(value.get(key, [])) > 128:
            raise ValueError("invalid_user_frontend")
    for path in [value["entry"], *value.get("styles", []), *value.get("assets", [])]:
        if not isinstance(path, str) or f"frontend/{path}" not in files:
            raise ValueError("invalid_user_frontend_asset")
    ids: set[str] = set()
    for collection in ("pages", "slots"):
        for view in value.get(collection, []):
            if not isinstance(view, dict) or set(view) - {
                "id",
                "view",
                "label",
                "i18nKey",
                "order",
                "target",
                "icon",
                "navigation",
            }:
                raise ValueError("invalid_user_view")
            for key in ("id", "view"):
                if not isinstance(view.get(key), str) or not _ID.fullmatch(view[key]):
                    raise ValueError("invalid_user_view")
            if view["id"] in ids:
                raise ValueError("duplicate_user_view")
            ids.add(view["id"])
            if not isinstance(view.get("label"), str) or not 1 <= len(view["label"]) <= 200:
                raise ValueError("invalid_user_view_label")
            if not isinstance(view.get("i18nKey", ""), str):
                raise ValueError("invalid_user_view_label")
            if (
                type(view.get("order", 100)) is not int
                or not -10000 <= view.get("order", 100) <= 10000
            ):
                raise ValueError("invalid_user_view_order")
            if collection == "slots" and view.get("target") not in USER_TARGETS:
                raise ValueError("invalid_user_view_target")
            if collection == "pages" and view.get("target", "page") != "page":
                raise ValueError("invalid_user_view_target")
            if view.get("icon", "star") not in {
                "star",
                "gift",
                "device",
                "home",
                "support",
                "settings",
                "shield",
            }:
                raise ValueError("invalid_user_view_icon")
            if view.get("navigation", "primary") not in {"primary", "hidden"}:
                raise ValueError("invalid_user_view_navigation")
