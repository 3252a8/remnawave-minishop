"""Addressed guide links share the same stable target across delivery surfaces."""

import asyncio
import copy
import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
from aiohttp import web

from bot.app.web.admin_api_impl import message_targets
from bot.app.web.admin_api_impl.schemas import AdminBroadcastButtonBody
from bot.app.web.webapp.guide_document import remnawave_v1_to_guide_document
from bot.services.message_composition import (
    MessageButtonInput,
    email_links_for_buttons,
    mini_app_section_link,
    resolve_message_buttons,
    telegram_markup_for_buttons,
)
from bot.services.support_message_buttons import (
    decode_support_buttons,
    encode_support_buttons,
    support_buttons_payload,
)
from bot.utils.mini_app_url import (
    subscription_mini_app_install_url,
    subscription_public_install_url,
)
from config.menu_buttons import normalize_menu_buttons_json, public_menu_buttons
from config.subscription_guides_config import (
    SubscriptionGuidesConfigError,
    default_subscription_guides_config_text,
    validate_subscription_guides_config,
)
from tests.support.settings_stub import settings_stub


def test_addressed_button_keeps_the_same_target_in_telegram_email_and_support() -> None:
    source = AdminBroadcastButtonBody.model_validate(
        {
            "kind": "webapp_section",
            "section": "install",
            "label": "Install",
            "platform": " androidTV ",
            "app": " stable-client_2 ",
        }
    )
    assert source.platform == "androidTV"
    assert source.app == "stable-client_2"
    [button] = resolve_message_buttons(
        [source],
        mini_app_url="https://shop.example/app?lang=en&startapp=plans#top",
        bot_username="shop_bot",
    )
    assert button.url == (
        "https://shop.example/app/install?lang=en&platform=androidTV&app=stable-client_2#top"
    )
    markup = telegram_markup_for_buttons([button])
    assert markup is not None
    web_app = markup.inline_keyboard[0][0].web_app
    assert web_app is not None and web_app.url == button.url
    assert email_links_for_buttons([button]) == [("Install", button.url)]
    encoded = encode_support_buttons([button])
    assert decode_support_buttons(encoded) == [button]
    assert support_buttons_payload(encoded)[0]["app"] == "stable-client_2"


def test_legacy_plugin_specs_and_constructor_positions_keep_working() -> None:
    legacy = SimpleNamespace(
        kind="webapp_section", label="Install", section="install", url="", promo_code=""
    )
    [button] = resolve_message_buttons(
        [cast(Any, legacy)], mini_app_url="https://shop.example", bot_username=None
    )
    assert button.url == "https://shop.example?startapp=install"
    positional = MessageButtonInput("webapp_section", "Install", "", "", "install")
    assert positional.platform == positional.app == ""


@pytest.mark.parametrize("base", [None, "http://shop.example/app"])
def test_telegram_fallback_opens_generic_install_when_direct_https_is_unavailable(base) -> None:
    [button] = resolve_message_buttons(
        [
            MessageButtonInput(
                "webapp_section", "Install", section="install", platform="ios", app="x"
            )
        ],
        mini_app_url=base,
        bot_username="shop_bot",
    )
    assert button.url == "https://t.me/shop_bot?startapp=install"
    assert button.telegram_web_app_url is None


def test_options_are_scoped_to_install_and_require_a_platform() -> None:
    assert mini_app_section_link("https://shop.example", "plans", platform="ios", app="x") == (
        "https://shop.example?startapp=plans"
    )
    assert mini_app_section_link("https://shop.example", "install", app="x") == (
        "https://shop.example?startapp=install"
    )
    link = mini_app_section_link(
        "https://shop.example", "install", platform="custom--ios", app="a&b"
    )
    assert link is not None
    assert parse_qs(urlsplit(link).query) == {"platform": ["custom--ios"], "app": ["a&b"]}


def test_menu_and_personal_and_public_helpers_preserve_install_targets() -> None:
    raw = normalize_menu_buttons_json(
        [
            {
                "id": "install",
                "kind": "webapp",
                "target": "install",
                "labels": {"en": "Install"},
                "platform": "ios",
                "app": "client",
            }
        ]
    )
    assert json.loads(raw)[0]["app"] == "client"
    assert public_menu_buttons(raw, "en")[0]["platform"] == "ios"
    settings = settings_stub(SUBSCRIPTION_MINI_APP_URL="https://shop.example/app?lang=en")
    assert subscription_mini_app_install_url(settings, platform="ios", app="client") == (
        "https://shop.example/app/install?lang=en&platform=ios&app=client"
    )
    token = "a" * 32
    assert subscription_public_install_url(settings, token, platform="ios", app="client") == (
        f"https://shop.example/s/{token}?platform=ios&app=client"
    )


def test_personal_os_only_target_replaces_stale_base_navigation() -> None:
    settings = settings_stub(
        SUBSCRIPTION_MINI_APP_URL="https://shop.example/app?app=old&platform=ios&startapp=plans"
    )
    assert subscription_mini_app_install_url(settings, platform="android") == (
        "https://shop.example/app/install?platform=android"
    )


def test_optional_target_schema_has_no_generated_client_required_default() -> None:
    schema = AdminBroadcastButtonBody.model_json_schema()
    for key in ("platform", "app"):
        assert key not in schema.get("required", [])
        assert "default" not in schema["properties"][key]
    assert AdminBroadcastButtonBody().platform == ""
    assert AdminBroadcastButtonBody().app == ""


def test_app_ids_survive_reorder_and_explicit_ids_survive_rename() -> None:
    config = json.loads(default_subscription_guides_config_text())
    apps = next(iter(config["platforms"].values()))["apps"]
    apps[0]["id"] = "preferred-client"
    before = validate_subscription_guides_config(config)
    apps[0]["name"] = "Renamed client"
    apps.reverse()
    after = validate_subscription_guides_config(config)
    before_apps = remnawave_v1_to_guide_document(before)["platforms"][0]["apps"]
    after_apps = remnawave_v1_to_guide_document(after)["platforms"][0]["apps"]
    assert {app["id"] for app in after_apps} == {app["id"] for app in before_apps}
    document = remnawave_v1_to_guide_document(after)
    assert "preferred-client" in {app["id"] for app in document["platforms"][0]["apps"]}


def test_legacy_duplicate_names_remain_valid_but_explicit_duplicate_ids_are_rejected() -> None:
    config = json.loads(default_subscription_guides_config_text())
    apps = next(iter(config["platforms"].values()))["apps"]
    apps[:] = [copy.deepcopy(apps[0]), copy.deepcopy(apps[0])]
    normalized = validate_subscription_guides_config(config)
    assert validate_subscription_guides_config(normalized) == normalized
    for app in apps:
        app["id"] = "same-client"
    with pytest.raises(SubscriptionGuidesConfigError, match="app ids must be unique"):
        validate_subscription_guides_config(config)


@pytest.mark.parametrize("identifier", ["../client", "bad client", "x" * 65])
def test_explicit_app_ids_must_be_safe_stable_identifiers(identifier: str) -> None:
    config = json.loads(default_subscription_guides_config_text())
    next(iter(config["platforms"].values()))["apps"][0]["id"] = identifier
    with pytest.raises(SubscriptionGuidesConfigError, match="id is invalid"):
        validate_subscription_guides_config(config)


def test_admin_catalog_exposes_localized_ids_without_guide_content_or_subscription_secrets(
    monkeypatch,
) -> None:
    document = {
        "platforms": [
            {
                "id": "plugin--provider--ios",
                "displayName": {"ru": "Localized platform", "en": "Platform"},
                "apps": [
                    {
                        "id": "preferred-client",
                        "name": "Preferred client",
                        "blocks": [{"link": "https://private.example/secret-token"}],
                    }
                ],
            }
        ]
    }
    load = AsyncMock(return_value=({"enabled": True}, document))
    monkeypatch.setattr(message_targets, "_require_admin_user_id", lambda request: 99)
    monkeypatch.setattr(message_targets, "_admin_language", AsyncMock(return_value="ru"))
    monkeypatch.setattr(message_targets, "get_i18n", lambda request: None)
    monkeypatch.setattr(message_targets, "get_session_factory", lambda request: lambda: AsyncMock())
    monkeypatch.setattr(message_targets, "message_pages", AsyncMock(return_value=[]))
    monkeypatch.setattr(message_targets, "load_guide_content", load)
    request = cast(web.Request, SimpleNamespace())
    response = asyncio.run(message_targets.admin_message_targets_route(request))
    load.assert_awaited_once_with(request, user_id=99)
    assert response.text is not None
    assert json.loads(response.text) == {
        "ok": True,
        "sections": [],
        "install_platforms": [
            {
                "id": "plugin--provider--ios",
                "label": "Localized platform",
                "apps": [{"id": "preferred-client", "name": "Preferred client"}],
            }
        ],
    }
