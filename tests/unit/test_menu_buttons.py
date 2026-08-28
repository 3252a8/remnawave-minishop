import json

import pytest

from config.menu_buttons import (
    localized_menu_button_label,
    normalize_menu_buttons_json,
    parse_menu_buttons,
    public_menu_buttons,
    telegram_menu_button_text,
    validate_menu_button_languages,
)


def _payload() -> list[dict[str, object]]:
    return [
        {
            "id": "support",
            "kind": "telegram",
            "target": "@help_center",
            "icon": "Send",
            "labels": {"ru": "Поддержка", "en": "Support"},
        },
        {
            "id": "devices",
            "kind": "webapp",
            "target": "/devices/",
            "icon": "⚡",
            "labels": {"ru": "Устройства", "en": "Devices"},
        },
    ]


def test_menu_buttons_are_normalized_and_keep_order() -> None:
    normalized = normalize_menu_buttons_json(_payload())
    buttons = parse_menu_buttons(normalized)

    assert [button.id for button in buttons] == ["support", "devices"]
    assert buttons[0].target == "https://t.me/help_center"
    assert buttons[1].target == "devices"
    assert buttons[0].show_in_bot is True
    assert buttons[0].show_in_webapp is True
    assert json.loads(normalized)[0]["show_in_bot"] is True
    assert json.loads(normalized)[0]["show_in_webapp"] is True


def test_menu_buttons_reject_unsafe_and_non_telegram_targets() -> None:
    payload = _payload()
    payload[0]["target"] = "https://example.com/help"

    with pytest.raises(ValueError, match=r"must use t\.me"):
        parse_menu_buttons(json.dumps(payload))

    payload[0]["kind"] = "external"
    payload[0]["target"] = "javascript:alert(1)"
    with pytest.raises(ValueError, match="HTTP"):
        parse_menu_buttons(json.dumps(payload))


def test_menu_buttons_require_every_configured_locale() -> None:
    buttons = parse_menu_buttons(_payload())

    with pytest.raises(ValueError, match="de"):
        validate_menu_button_languages(buttons, {"ru", "en", "de"})


def test_menu_button_labels_and_public_payload_use_locale_fallbacks() -> None:
    button = parse_menu_buttons(_payload())[0]

    assert localized_menu_button_label(button, "en-US") == "Support"
    assert telegram_menu_button_text(button, "ru") == "✈️ Поддержка"
    assert public_menu_buttons(_payload(), "en")[0] == {
        "id": "support",
        "kind": "telegram",
        "target": "https://t.me/help_center",
        "icon": "Send",
        "label": "Support",
    }


def test_menu_button_visibility_filters_webapp_payload() -> None:
    payload = _payload()
    payload[0]["show_in_webapp"] = False
    payload[1]["show_in_bot"] = False

    buttons = parse_menu_buttons(payload)

    assert buttons[0].show_in_bot is True
    assert buttons[0].show_in_webapp is False
    assert buttons[1].show_in_bot is False
    assert buttons[1].show_in_webapp is True
    assert [button["id"] for button in public_menu_buttons(payload, "en")] == ["devices"]
