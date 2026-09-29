from __future__ import annotations

import json
from pathlib import Path

from bot.app.web.admin_api_impl import translations
from bot.middlewares.i18n import JsonI18n
from bot.plugins.spec import PluginLocaleGroup


def _write_locale(path: Path, language: str, messages: dict[str, str]) -> None:
    (path / f"{language}.json").write_text(
        json.dumps(messages, ensure_ascii=False),
        encoding="utf-8",
    )


def test_admin_translations_payload_cache_tracks_override_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(locales, "en", {"welcome": "Hello"})
    _write_locale(locales, "ru", {"welcome": "Привет"})
    i18n = JsonI18n(str(locales), default="en")
    first_overrides = [
        {
            "lang": "en",
            "key": "welcome",
            "value": "Welcome",
            "updated_at": "2026-09-21T00:00:00+00:00",
            "updated_by": 7,
        }
    ]
    original_builder = translations._admin_translations_payload
    calls = 0

    def counted_builder(current_i18n, overrides):
        nonlocal calls
        calls += 1
        return original_builder(current_i18n, overrides)

    monkeypatch.setattr(translations, "_admin_translations_payload", counted_builder)

    first = translations._cached_admin_translations_payload(i18n, first_overrides)
    repeated = translations._cached_admin_translations_payload(i18n, first_overrides)
    changed = translations._cached_admin_translations_payload(
        i18n,
        [{**first_overrides[0], "value": "Hello again"}],
    )

    assert repeated is first
    assert changed is not first
    assert calls == 2


def test_plugin_keys_have_separate_nested_editor_groups(tmp_path: Path) -> None:
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(locales, "en", {"shared": "Core"})
    _write_locale(locales, "ru", {"shared": "Ядро"})
    i18n = JsonI18n(str(locales), default="en")
    i18n.plugin_locale_groups["sample"] = (
        PluginLocaleGroup(("Billing",), ("sample_billing_",)),
        PluginLocaleGroup(("Billing", "Renewals"), ("sample_billing_renewal_",)),
    )
    i18n.merge_base_locales(
        {
            "en": {"sample_billing_renewal_title": "Renew", "sample_misc": "Other"},
            "ru": {"shared": "Plugin collision"},
        },
        source="sample",
    )
    payload = translations._cached_admin_translations_payload(i18n, [])
    plugin_groups = [group for group in payload["groups"] if group["plugin"] == "sample"]
    assert {
        (tuple(group["path"]), tuple(item["key"] for item in group["items"]))
        for group in plugin_groups
    } == {
        (("Billing", "Renewals"), ("sample_billing_renewal_title",)),
        ((), ("sample_misc",)),
    }
    assert (
        next(group for group in payload["groups"] if group["id"] == "common")["items"][0]["key"]
        == "shared"
    )

    i18n.merge_base_locales(
        {"en": {"another_title": "Another"}, "ru": {"sample_misc": "Другой"}},
        source="another",
    )
    assert i18n.plugin_locale_sources["sample_misc"] == "sample"
    regrouped = translations._cached_admin_translations_payload(i18n, [])
    assert any(group["plugin"] == "another" for group in regrouped["groups"])

    i18n.merge_base_locales({"en": {"sample_extra": "New"}}, source="sample")
    assert translations._cached_admin_translations_payload(i18n, []) is not regrouped
