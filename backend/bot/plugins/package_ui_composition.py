"""Stable, versioned UI boundaries for separately shipped frontend packages."""

import re
from typing import Any

USER_SECTIONS = frozenset(
    {
        "home",
        "invite",
        "support",
        "settings",
        "install",
        "devices",
        "partner",
        "notifications",
        "security",
        "status",
        "trial",
    }
)
USER_CARD_TARGETS = frozenset(
    {
        "user.invite.gifts",
        "user.invite.codes",
        "user.invite.referrals",
        "user.home.summary",
        "user.home.balance",
        "user.home.subscription",
        "user.home.traffic",
        "user.home.status",
        "user.settings.profile",
        "user.settings.codes",
    }
)
USER_TARGETS = (
    USER_CARD_TARGETS
    | {f"user.{section}.{region}" for section in USER_SECTIONS for region in ("content", "cards")}
    | {"user.profile.actions", "user.subscription.actions", "user.install.blocks"}
)
ADMIN_CARD_TARGETS = frozenset(
    f"admin.users.detail.{card}"
    for card in (
        "tariff",
        "balance",
        "traffic-strategy",
        "premium-traffic",
        "regular-traffic",
        "hwid",
        "traffic-grant",
        "squads",
        "actions",
    )
)
_ADMIN_SECTION_TARGET = re.compile(r"admin\.[a-z][a-z0-9-]{1,63}\.content\Z")
PROTECTED_TARGETS = frozenset({"admin.plugins.content", "user.security.content"})


def validate_placement(view: dict[str, Any], *, user: bool) -> None:
    target = view.get("target")
    if not isinstance(target, str) or (
        target not in USER_TARGETS
        if user
        else target not in ADMIN_CARD_TARGETS and not _ADMIN_SECTION_TARGET.fullmatch(target)
    ):
        raise ValueError("invalid_ui_slot_target")
    placement = view.get("placement", "after")
    if not isinstance(placement, str) or placement not in {"before", "after", "replace"}:
        raise ValueError("invalid_ui_slot_placement")
    if placement == "replace" and (
        target in PROTECTED_TARGETS
        or target == "admin.users.detail.actions"
        or (user and target not in USER_CARD_TARGETS and not target.endswith(".content"))
    ):
        raise ValueError("protected_ui_slot_target")


def validate_admin_slots(frontend: dict[str, Any]) -> None:
    slots = frontend.get("slots", [])
    if not isinstance(slots, list) or len(slots) > 128:
        raise ValueError("invalid_ui_slots")
    ids: set[str] = set()
    for slot in slots:
        if not isinstance(slot, dict) or set(slot) - {
            "id",
            "view",
            "target",
            "placement",
            "order",
            "label",
            "i18nKey",
            "requiredFeature",
            "visibleWhenLocked",
        }:
            raise ValueError("invalid_ui_slot")
        for key in ("id", "view"):
            if not isinstance(slot.get(key), str) or not re.fullmatch(
                r"[a-z][a-z0-9-]{1,63}", slot[key]
            ):
                raise ValueError("invalid_ui_slot")
        if slot["id"] in ids:
            raise ValueError("duplicate_ui_slot")
        ids.add(slot["id"])
        if not isinstance(slot.get("label"), str) or not 1 <= len(slot["label"]) <= 200:
            raise ValueError("invalid_ui_slot")
        for key in ("i18nKey", "requiredFeature"):
            if not isinstance(slot.get(key, ""), str):
                raise ValueError("invalid_ui_slot")
        if type(slot.get("order", 100)) is not int or not -10000 <= slot.get("order", 100) <= 10000:
            raise ValueError("invalid_ui_slot")
        if type(slot.get("visibleWhenLocked", False)) is not bool:
            raise ValueError("invalid_ui_slot")
        validate_placement(slot, user=False)
