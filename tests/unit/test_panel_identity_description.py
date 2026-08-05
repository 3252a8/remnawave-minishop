import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.services.subscription_service_impl.panel_identity import PanelIdentityMixin


def test_subscription_panel_identity_payload_excludes_description_updates():
    user = SimpleNamespace(
        email="linked@example.com",
        username="alice",
        first_name="Alice",
        last_name="Smith",
        telegram_id=42,
        user_id=42,
    )

    payload = PanelIdentityMixin()._panel_identity_payload_for_user(user)

    assert "description" not in payload
    assert payload["email"] == "linked@example.com"
    assert payload["telegramId"] == 42


def test_subscription_panel_description_filters_broken_lines_for_creation():
    user = SimpleNamespace(
        email="linked@example.com",
        username="alice??",
        first_name="????",
        last_name="Smith",
        telegram_id=42,
        user_id=42,
    )

    assert PanelIdentityMixin()._panel_description_for_user(user) == "alice??\nSmith"


def test_panel_identity_does_not_duplicate_user_after_inconclusive_upgrade_lookup():
    mixin = PanelIdentityMixin()
    mixin.settings = SimpleNamespace(
        user_traffic_limit_bytes=0,
        USER_TRAFFIC_STRATEGY="NO_RESET",
        parsed_user_squad_uuids=[],
        parsed_user_external_squad_uuid=None,
    )
    mixin.panel_service = SimpleNamespace(
        get_users_by_filter=AsyncMock(side_effect=[None, []]),
        get_user_by_uuid_lookup=AsyncMock(
            return_value={
                "ok": False,
                "user": None,
                "not_found": False,
                "failure_reason": "classification=incompatible_user_reference",
            }
        ),
        create_panel_user=AsyncMock(),
    )
    db_user = SimpleNamespace(
        user_id=42,
        telegram_id=42,
        email=None,
        panel_user_uuid="legacy-user-uuid",
    )

    link = asyncio.run(mixin._get_or_create_panel_user_link(AsyncMock(), 42, db_user))

    assert link.panel_user_uuid == "legacy-user-uuid"
    assert link.panel_user is None
    mixin.panel_service.create_panel_user.assert_not_awaited()
