from datetime import UTC, datetime

import pytest

from bot.handlers.admin.sync_admin_relink import PanelSyncIdentityIndex, bind_sync_panel_identity
from db.models import User


@pytest.mark.parametrize(
    "case",
    [
        "old_reference_exists",
        "two_telegram_profiles",
        "two_email_profiles",
        "two_username_profiles",
        "unverified_email",
        "conflicting_telegram",
        "conflicting_email",
        "two_local_owners",
    ],
)
def test_stale_reference_recovery_rejects_ambiguous_or_unproven_identity(case):
    user = User(
        user_id=71,
        panel_user_uuid="old-reference",
        panel_username="legacy_profile",
        minishop_id="ms_synthetic",
        telegram_id=910000071,
        email="synthetic@example.test",
        email_verified_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    candidate = {
        "uuid": "701",
        "username": "legacy_profile",
        "telegramId": 910000071,
        "email": "synthetic@example.test",
    }
    panel_users = [candidate]
    local_users = {71: user}
    if case == "old_reference_exists":
        panel_users.append({"uuid": "old-reference", "telegramId": 910000099})
    elif case.startswith("two_") and case.endswith("_profiles"):
        field = {
            "two_telegram_profiles": "telegramId",
            "two_email_profiles": "email",
            "two_username_profiles": "username",
        }[case]
        panel_users.append({"uuid": "702", field: candidate[field]})
    elif case == "unverified_email":
        candidate.pop("telegramId")
        candidate.pop("username")
        user.email_verified_at = None
    elif case == "conflicting_telegram":
        candidate["telegramId"] = 910000099
    elif case == "conflicting_email":
        candidate["email"] = "another@example.test"
    elif case == "two_local_owners":
        local_users[72] = User(user_id=72, panel_username="legacy_profile")
    assert PanelSyncIdentityIndex(panel_users).stale_owner(candidate, local_users) is None
    assert user.panel_user_uuid == "old-reference"


def test_relink_rejects_changed_panel_origin_without_mutating_identity():
    user = User(
        user_id=71,
        panel_user_uuid="old-reference",
        panel_origin="original-origin",
        panel_username="legacy_profile",
    )
    assert not bind_sync_panel_identity(
        user,
        {"uuid": "701", "username": "legacy_profile"},
        "different-origin",
        telegram_duplicate=False,
    )
    assert user.panel_origin == "original-origin"
    assert user.panel_username == "legacy_profile"
    assert user.panel_user_uuid == "old-reference"
