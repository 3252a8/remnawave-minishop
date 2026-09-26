import copy
import json
from pathlib import Path

import pytest

from bot.app.web.webapp.guide_document import remnawave_v1_to_guide_document
from config.subscription_guides_config import default_subscription_guides_config_text


def test_remnawave_adapter_preserves_existing_instruction_content() -> None:
    default = json.loads(default_subscription_guides_config_text())
    multiapp_path = (
        Path(__file__).parents[2] / "backend/config/defaults/subscription_page_multiapp.json"
    )
    multiapp = json.loads(multiapp_path.read_text(encoding="utf-8"))
    for config in (default, multiapp):
        document = remnawave_v1_to_guide_document(config, source="panel")
        restored = {
            key: copy.deepcopy(value)
            for key, value in document.items()
            if key not in {"schemaVersion", "revision", "source", "resources", "platforms"}
        }
        restored["version"] = "1"
        restored["platforms"] = {}
        for platform in document["platforms"]:
            content = copy.deepcopy(platform)
            platform_id = content.pop("id")
            for app in content.get("apps", []):
                for block in app.get("blocks", []):
                    for button in block.get("buttons", []):
                        assert button["action"]["kind"] in {"copy", "open"}
                        button.pop("action")
            restored["platforms"][platform_id] = content
        assert restored == config


def test_guide_document_rejects_unknown_ingress_version() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        remnawave_v1_to_guide_document({"version": "2", "platforms": {}})


def test_guide_document_preserves_each_crypto_resource_representation() -> None:
    links = [
        "{{SUBSCRIPTION_LINK}}",
        "{{HAPP_CRYPT3_LINK}}",
        "{{HAPP_CRYPT4_LINK}}",
        "{{INCY_CRYPT1_LINK}}",
        "incy://import/{{SUBSCRIPTION_LINK}}",
    ]
    config = {
        "version": "1",
        "platforms": {
            "windows": {
                "apps": [
                    {
                        "blocks": [
                            {
                                "buttons": [
                                    {"type": "subscriptionLink", "link": link} for link in links
                                ]
                            }
                        ]
                    }
                ]
            }
        },
    }

    document = remnawave_v1_to_guide_document(config)
    buttons = document["platforms"][0]["apps"][0]["blocks"][0]["buttons"]
    assert [button["action"]["target"] for button in buttons] == [
        {"kind": "resource", "resourceId": "primary-subscription", "representation": "http"},
        {
            "kind": "resource",
            "resourceId": "primary-subscription",
            "representation": "happ-crypt3",
        },
        {"kind": "resource", "resourceId": "primary-subscription", "representation": "happ"},
        {
            "kind": "resource",
            "resourceId": "primary-subscription",
            "representation": "incy-crypt1",
        },
        {"kind": "literal", "value": "incy://import/{{SUBSCRIPTION_LINK}}"},
    ]
