import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from bot.utils.text_sanitizer import sanitize_display_name, sanitize_username, username_for_display


def test_sanitize_username_preserves_underscore_suffixes():
    assert sanitize_username("ik_end") == "ik_end"
    assert sanitize_username("name_service") == "name_service"
    assert sanitize_username("@client_support") == "client_support"
    assert sanitize_username("telegram_user") == "telegram_user"
    assert username_for_display("ik_end", with_at=True) == "@ik_end"
    assert username_for_display("name_service", with_at=True) == "@name_service"


def test_sanitize_username_rejects_free_form_values_instead_of_truncating():
    assert sanitize_username("https://t.me/name_service") is None
    assert sanitize_username("name service") is None


def test_display_name_filters_still_apply_to_free_form_names():
    assert sanitize_display_name("Name service") == "Name"
