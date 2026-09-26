from __future__ import annotations

import json
from pathlib import Path

from bot.app.web.admin_api_impl import translations
from bot.middlewares.i18n import JsonI18n


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
