from types import SimpleNamespace

from bot.services.subscription_service_impl.panel_identity import PanelIdentityMixin


def test_subscription_panel_description_excludes_email():
    user = SimpleNamespace(
        email="linked@example.com",
        username="alice",
        first_name="Alice",
        last_name="Smith",
        telegram_id=42,
        user_id=42,
    )

    payload = PanelIdentityMixin()._panel_identity_payload_for_user(user)

    assert payload["description"] == "alice\nAlice\nSmith"
    assert payload["email"] == "linked@example.com"
    assert payload["telegramId"] == 42
