import copy

import pytest

from bot.plugins.package_ui_composition import validate_admin_slots
from bot.plugins.package_user_ui import validate_user_frontend


def test_nested_user_pages_and_section_cards_are_additive():
    value = {
        "entry": "user.js",
        "pages": [
            {
                "id": "tool",
                "view": "tool",
                "label": "Tool",
                "parent": "invite",
                "navigation": "section",
            },
            {
                "id": "resources",
                "view": "resources",
                "label": "Resources",
                "parent": "support",
                "navigation": "section",
            },
        ],
        "slots": [
            {
                "id": "card",
                "view": "card",
                "label": "Card",
                "target": "user.invite.cards",
                "order": 0,
            },
            {
                "id": "codes",
                "view": "codes",
                "label": "Codes",
                "target": "user.invite.codes",
                "placement": "replace",
            },
        ],
    }
    validate_user_frontend(value, {"frontend/user.js": "digest"})
    duplicated = copy.deepcopy(value)
    duplicated["slots"][0]["id"] = "tool"
    with pytest.raises(ValueError, match="duplicate_user_view"):
        validate_user_frontend(duplicated, {"frontend/user.js": "digest"})


@pytest.mark.parametrize("parent", ["admin", "missing", [], None])
def test_user_subsection_rejects_invalid_parent(parent):
    with pytest.raises(ValueError, match="parent"):
        validate_user_frontend(
            {
                "entry": "user.js",
                "pages": [
                    {
                        "id": "resources",
                        "view": "resources",
                        "label": "Resources",
                        "parent": parent,
                        "navigation": "section",
                    }
                ],
            },
            {"frontend/user.js": "digest"},
        )


def test_subsection_requires_parent_and_preserves_legacy_slots():
    value = {
        "entry": "user.js",
        "pages": [
            {"id": "resources", "view": "resources", "label": "Resources", "navigation": "section"}
        ],
    }
    with pytest.raises(ValueError, match="parent"):
        validate_user_frontend(value, {"frontend/user.js": "digest"})
    validate_user_frontend(
        {
            "entry": "user.js",
            "slots": [
                {
                    "id": "card",
                    "view": "card",
                    "label": "Card",
                    "target": "user.home.cards",
                    "navigation": "hidden",
                }
            ],
        },
        {"frontend/user.js": "digest"},
    )


@pytest.mark.parametrize(
    "target",
    [
        "user.security.content",
        "user.invite.cards",
        "admin.plugins.content",
        "admin.users.detail.actions",
    ],
)
def test_recovery_and_additive_regions_cannot_be_replaced(target):
    slot = {"id": "card", "view": "card", "label": "Card", "target": target, "placement": "replace"}
    with pytest.raises(ValueError, match="protected"):
        if target.startswith("user."):
            validate_user_frontend(
                {"entry": "user.js", "slots": [slot]}, {"frontend/user.js": "digest"}
            )
        else:
            validate_admin_slots({"slots": [slot]})


def test_admin_cards_and_section_contents_accept_explicit_replacement():
    validate_admin_slots(
        {
            "slots": [
                {
                    "id": "resources",
                    "view": "resources",
                    "label": "Resources",
                    "target": "admin.support.content",
                    "placement": "before",
                },
                {
                    "id": "tariff",
                    "view": "tariff",
                    "label": "Tariff",
                    "target": "admin.users.detail.tariff",
                    "placement": "replace",
                },
            ]
        }
    )


@pytest.mark.parametrize(
    "change",
    [
        {"target": "admin.missing.unknown"},
        {"target": []},
        {"placement": []},
        {"placement": "hide"},
        {"order": True},
        {"order": 10001},
        {"label": ""},
        {"visibleWhenLocked": "yes"},
        {"id": "../escape"},
        {"unknown": 1},
    ],
)
def test_admin_slot_validation_fails_before_installation(change):
    slot = {
        "id": "resources",
        "view": "resources",
        "label": "Resources",
        "target": "admin.support.content",
        **change,
    }
    with pytest.raises(ValueError):
        validate_admin_slots({"slots": [slot]})
