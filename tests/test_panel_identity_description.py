from types import SimpleNamespace

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
