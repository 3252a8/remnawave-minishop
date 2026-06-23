import json

import pytest

from config.subscription_guides_config import (
    SubscriptionGuidesConfigError,
    default_subscription_guides_config_text,
    extract_subscription_guides_config_from_panel,
    load_subscription_guides_config,
    panel_subscription_page_allowed,
    subscription_guides_admin_config_json,
    validate_panel_subscription_guides_config,
    validate_subscription_guides_config,
    validate_subscription_guides_config_text,
)
from tests.support.settings_stub import settings_stub

BASE_TRANSLATION_KEYS = (
    "active",
    "bandwidth",
    "connectionKeysHeader",
    "copyLink",
    "expired",
    "expires",
    "expiresIn",
    "getLink",
    "inactive",
    "indefinitely",
    "installationGuideHeader",
    "linkCopied",
    "linkCopiedToClipboard",
    "name",
    "scanQrCode",
    "scanQrCodeDescription",
    "scanToImport",
    "status",
    "unknown",
)


def _localized(text):
    return {"ru": text, "en": text}


def _config(app_name="Streisand"):
    return {
        "version": "1",
        "locales": ["ru", "en"],
        "brandingSettings": {
            "title": "Demo",
            "logoUrl": "https://example.com/logo.svg",
            "supportUrl": "https://t.me/support",
        },
        "uiConfig": {
            "subscriptionInfoBlockType": "collapsed",
            "installationGuidesBlockType": "cards",
        },
        "baseSettings": {
            "metaTitle": "Subscription",
            "metaDescription": "Subscription",
            "showConnectionKeys": False,
            "hideGetLinkButton": False,
        },
        "baseTranslations": {key: _localized(key) for key in BASE_TRANSLATION_KEYS},
        "svgLibrary": {
            "App": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"></svg>',
            "Copy": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"></svg>',
            "Download": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"></svg>',
            "Phone": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"></svg>',
        },
        "platforms": {
            "ios": {
                "displayName": "iOS",
                "svgIconKey": "Phone",
                "apps": [
                    {
                        "name": app_name,
                        "svgIconKey": "App",
                        "featured": True,
                        "blocks": [
                            {
                                "svgIconKey": "Download",
                                "svgIconColor": "green",
                                "title": _localized("Install app"),
                                "description": _localized("Install and import the subscription."),
                                "buttons": [
                                    {
                                        "type": "external",
                                        "link": "https://apps.apple.com/app/example",
                                        "text": _localized("Open store"),
                                        "svgIconKey": "Download",
                                    },
                                    {
                                        "type": "copyButton",
                                        "link": "{{SUBSCRIPTION_LINK}}",
                                        "text": _localized("Copy link"),
                                        "svgIconKey": "Copy",
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        },
    }


def test_valid_multiapp_like_config_is_normalized():
    config = validate_subscription_guides_config(_config())

    assert config["version"] == "1"
    assert config["locales"] == ["ru", "en"]
    assert config["platforms"]["ios"]["apps"][0]["name"] == "Streisand"


def test_bundled_default_multiapp_config_is_valid():
    config = validate_subscription_guides_config_text(default_subscription_guides_config_text())

    assert set(config["platforms"]) == {
        "android",
        "androidTV",
        "appleTV",
        "ios",
        "linux",
        "macos",
        "windows",
    }
    assert config["platforms"]["ios"]["displayName"]["ru"] == "iOS"


def test_missing_locale_string_is_rejected():
    config = _config()
    del config["platforms"]["ios"]["apps"][0]["blocks"][0]["title"]["en"]

    with pytest.raises(SubscriptionGuidesConfigError, match="title.en"):
        validate_subscription_guides_config(config)


def test_bad_platform_is_rejected():
    config = _config()
    config["platforms"]["bsd"] = config["platforms"].pop("ios")

    with pytest.raises(SubscriptionGuidesConfigError, match="Unsupported platform"):
        validate_subscription_guides_config(config)


def test_missing_svg_key_is_rejected():
    config = _config()
    config["platforms"]["ios"]["svgIconKey"] = "Missing"

    with pytest.raises(SubscriptionGuidesConfigError, match="missing svgLibrary key"):
        validate_subscription_guides_config(config)


def test_unsafe_svg_is_rejected():
    config = _config()
    config["svgLibrary"]["App"] = '<svg viewBox="0 0 24 24" onload="alert(1)"></svg>'

    with pytest.raises(SubscriptionGuidesConfigError, match="unsafe SVG"):
        validate_subscription_guides_config(config)


def test_unsafe_external_link_is_rejected():
    config = _config()
    config["platforms"]["ios"]["apps"][0]["blocks"][0]["buttons"][0]["link"] = "javascript:alert(1)"

    with pytest.raises(SubscriptionGuidesConfigError, match="unsafe URL scheme"):
        validate_subscription_guides_config(config)


def test_external_custom_scheme_is_allowed_for_multiapp_compatibility():
    config = _config()
    config["platforms"]["ios"]["apps"][0]["blocks"][0]["buttons"][0]["link"] = (
        "streisand://import/demo"
    )

    validated = validate_subscription_guides_config(config)

    assert (
        validated["platforms"]["ios"]["apps"][0]["blocks"][0]["buttons"][0]["link"]
        == "streisand://import/demo"
    )


def test_panel_response_config_wrapper_is_supported():
    payload = {"response": {"config": json.dumps(_config(app_name="Panel App"))}}

    validated = validate_panel_subscription_guides_config(payload)

    assert validated["platforms"]["ios"]["apps"][0]["name"] == "Panel App"


def test_panel_response_direct_v1_config_is_supported():
    payload = {"response": _config(app_name="Panel Direct App")}

    extracted = extract_subscription_guides_config_from_panel(payload)
    validated = validate_panel_subscription_guides_config(payload)

    assert extracted["version"] == "1"
    assert validated["platforms"]["ios"]["apps"][0]["name"] == "Panel Direct App"


def test_panel_response_without_v1_config_is_rejected():
    with pytest.raises(SubscriptionGuidesConfigError, match="does not contain"):
        validate_panel_subscription_guides_config({"response": {"config": {"version": "2"}}})


def test_panel_response_with_allowed_default_uses_bundled_config():
    validated = validate_panel_subscription_guides_config(
        {"response": {"subpageConfigUuid": None, "webpageAllowed": True}},
        allow_default_when_missing=True,
    )

    assert panel_subscription_page_allowed({"response": {"webpageAllowed": True}})
    assert validated["version"] == "1"
    assert set(validated["platforms"]) >= {"ios", "android", "windows"}


def test_admin_json_overrides_file_path(tmp_path):
    file_config = _config(app_name="File App")
    json_config = _config(app_name="JSON App")
    config_path = tmp_path / "multiapp.json"
    config_path.write_text(json.dumps(file_config), encoding="utf-8")
    settings = settings_stub(
        SUBSCRIPTION_PAGE_CONFIG_PATH=str(config_path),
        SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED=True,
        SUBSCRIPTION_PAGE_CONFIG_JSON=json.dumps(json_config),
    )

    loaded, source = load_subscription_guides_config(settings)

    assert source == "admin_json"
    assert loaded["platforms"]["ios"]["apps"][0]["name"] == "JSON App"


def test_admin_json_is_ignored_when_override_switch_is_disabled(tmp_path):
    file_config = _config(app_name="File App")
    json_config = _config(app_name="JSON App")
    config_path = tmp_path / "multiapp.json"
    config_path.write_text(json.dumps(file_config), encoding="utf-8")
    settings = settings_stub(
        SUBSCRIPTION_PAGE_CONFIG_PATH=str(config_path),
        SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED=False,
        SUBSCRIPTION_PAGE_CONFIG_JSON=json.dumps(json_config),
    )

    loaded, source = load_subscription_guides_config(settings)

    assert source == "file"
    assert loaded["platforms"]["ios"]["apps"][0]["name"] == "File App"


def test_file_path_is_used_when_admin_json_is_empty(tmp_path):
    file_config = _config(app_name="File App")
    config_path = tmp_path / "multiapp.json"
    config_path.write_text(json.dumps(file_config), encoding="utf-8")
    settings = settings_stub(
        SUBSCRIPTION_PAGE_CONFIG_PATH=str(config_path),
        SUBSCRIPTION_PAGE_CONFIG_JSON="",
    )

    loaded, source = load_subscription_guides_config(settings)

    assert source == "file"
    assert loaded["platforms"]["ios"]["apps"][0]["name"] == "File App"


def test_missing_file_path_is_not_created_implicitly(tmp_path):
    config_path = tmp_path / "subpage-config" / "multiapp.json"
    settings = settings_stub(
        SUBSCRIPTION_PAGE_CONFIG_PATH=str(config_path),
        SUBSCRIPTION_PAGE_CONFIG_JSON="",
    )

    with pytest.raises(SubscriptionGuidesConfigError, match="does not exist"):
        load_subscription_guides_config(settings)

    assert not config_path.exists()


def test_admin_json_editor_is_empty_when_override_is_empty(tmp_path):
    config_path = tmp_path / "subpage-config" / "multiapp.json"
    settings = settings_stub(
        SUBSCRIPTION_PAGE_CONFIG_PATH=str(config_path),
        SUBSCRIPTION_PAGE_CONFIG_JSON="",
    )

    raw, source = subscription_guides_admin_config_json(settings)

    assert source == "empty"
    assert raw == ""
    assert not config_path.exists()


def test_admin_json_editor_keeps_admin_override_without_creating_file(tmp_path):
    config_path = tmp_path / "subpage-config" / "multiapp.json"
    override = json.dumps(_config(app_name="JSON App"))
    settings = settings_stub(
        SUBSCRIPTION_PAGE_CONFIG_PATH=str(config_path),
        SUBSCRIPTION_PAGE_CONFIG_JSON=override,
    )

    raw, source = subscription_guides_admin_config_json(settings)

    assert not config_path.exists()
    assert source == "admin_json"
    assert json.loads(raw)["platforms"]["ios"]["apps"][0]["name"] == "JSON App"
