import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from bot.utils.text_sanitizer import (
    looks_like_broken_panel_text,
    panel_description_from_profile,
    sanitize_display_name,
    sanitize_username,
    username_for_display,
)


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


def test_panel_broken_text_detection_is_conservative_about_question_marks():
    assert not looks_like_broken_panel_text("?")
    assert not looks_like_broken_panel_text("alice??")
    assert not looks_like_broken_panel_text("??? 123")
    assert not looks_like_broken_panel_text("\U0001f0cf")


def test_panel_broken_text_detection_filters_replacement_garbage():
    assert looks_like_broken_panel_text("????")
    assert looks_like_broken_panel_text("???!")
    assert looks_like_broken_panel_text("\ufffd\ufffd")


def test_panel_description_filters_only_broken_lines():
    assert panel_description_from_profile("alice??", "????", "Smith") == "alice??\nSmith"
    assert panel_description_from_profile(None, "????", "\ufffd\ufffd") == ""
