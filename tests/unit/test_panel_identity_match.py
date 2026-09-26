from datetime import UTC, datetime
from types import SimpleNamespace

from bot.services.panel_identity_match import (
    panel_candidate_matches_account,
    panel_origin_fingerprint,
)


def test_matching_native_id_from_another_panel_does_not_prove_ownership() -> None:
    user = SimpleNamespace(
        telegram_id=12345,
        email="owner@example.test",
        email_verified_at=datetime.now(UTC),
        panel_username=None,
        minishop_id="ms_" + "a" * 32,
    )
    # The caller deliberately looked this up by the same native ID.
    other_panel_user = {
        "uuid": "5",
        "username": "ms_" + "b" * 32,
        "telegramId": 98765,
        "email": "other@example.test",
    }
    assert not panel_candidate_matches_account(user, other_panel_user)
    assert panel_candidate_matches_account(user, {**other_panel_user, "telegramId": 12345})
    assert panel_candidate_matches_account(
        user, {**other_panel_user, "telegramId": None, "email": "owner@example.test"}
    )


def test_unverified_email_does_not_claim_panel_user() -> None:
    user = SimpleNamespace(
        telegram_id=None,
        email="owner@example.test",
        email_verified_at=None,
        panel_username=None,
        minishop_id="ms_" + "a" * 32,
    )
    assert not panel_candidate_matches_account(
        user, {"email": "owner@example.test", "username": "unrelated"}
    )


def test_panel_origin_pin_changes_when_panel_changes() -> None:
    first = panel_origin_fingerprint("https://panel.example.test/api/")
    assert first == panel_origin_fingerprint("https://panel.example.test/api")
    assert first != panel_origin_fingerprint("https://other.example.test/api")
