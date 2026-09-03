"""Keep Mini App translations complete and retire unreferenced catalog entries."""

from __future__ import annotations

import json
import re
from pathlib import Path

from bot.app.web.webapp.assets_static import WEBAPP_BOOTSTRAP_I18N_KEYS
from bot.middlewares.i18n import resolve_locale_key

REPO_ROOT = Path(__file__).resolve().parents[2]
_TRANSLATION_CALL = re.compile(r"""\bt\(\s*["']([a-z0-9_]+)["']""")
_WEBAPP_KEY = re.compile(r"\bwa_[a-z0-9_]+\b")
_DYNAMIC_PREFIX = re.compile(r"\b(wa_[a-z0-9_]*)\$?\{")


def _runtime_sources() -> dict[Path, str]:
    return {
        path.relative_to(REPO_ROOT): path.read_text(encoding="utf-8")
        for root in (REPO_ROOT / "backend", REPO_ROOT / "frontend/src")
        for path in root.rglob("*")
        if path.suffix in {".py", ".ts", ".svelte", ".html"}
        and not any(marker in path.name for marker in (".test.", ".spec.", ".generated."))
    }


def test_every_webapp_string_is_translated_in_both_base_locales() -> None:
    requested = {
        str(path): {resolve_locale_key(key) for key in _TRANSLATION_CALL.findall(source)}
        for path, source in _runtime_sources().items()
        if path.parts[0] == "frontend"
    }
    assert any(requested.values()), "no frontend translation calls were found"

    for language in ("ru", "en"):
        messages = json.loads((REPO_ROOT / "locales" / f"{language}.json").read_text("utf-8"))
        missing = {
            path: sorted(key for key in keys if not str(messages.get(key, "")).strip())
            for path, keys in requested.items()
            if any(not str(messages.get(key, "")).strip() for key in keys)
        }
        assert not missing, f"frontend strings without a {language} translation: {missing}"


def test_webapp_catalog_keys_have_runtime_references() -> None:
    source = "\n".join(_runtime_sources().values())
    referenced = set(_WEBAPP_KEY.findall(source))
    # Statuses, plural forms and other template keys are assembled at runtime.
    # Treat their prefixes conservatively instead of deleting valid variants.
    dynamic_prefixes = tuple(sorted(set(_DYNAMIC_PREFIX.findall(source))))
    assert referenced, "no Mini App translation references were found"

    for language in ("ru", "en"):
        messages = json.loads((REPO_ROOT / "locales" / f"{language}.json").read_text("utf-8"))
        unused = sorted(
            key
            for key in messages
            if key.startswith("wa_")
            and key not in referenced
            and not key.startswith(dynamic_prefixes)
        )
        assert not unused, f"unreferenced {language} Mini App translations: {unused}"


def test_webapp_bootstrap_extra_keys_match_mini_app_usage() -> None:
    mini_app_roots = (
        "frontend/src/webapp/",
        "frontend/src/lib/webapp/",
        "frontend/src/lib/components/patterns/webapp/",
    )
    extra_keys = {
        resolve_locale_key(key)
        for path, source in _runtime_sources().items()
        if (
            path.as_posix().startswith(mini_app_roots)
            or path.as_posix() == "frontend/src/App.svelte"
        )
        for key in _TRANSLATION_CALL.findall(source)
        if not resolve_locale_key(key).startswith("wa_")
    }
    assert extra_keys == WEBAPP_BOOTSTRAP_I18N_KEYS
