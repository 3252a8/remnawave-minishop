"""Export the admin settings manifest as a demo-safe JSON snapshot.

The Mini App demo (docs site) has no backend, so its admin Settings screen is
fed by a mock. Previously the section/field structure was frozen inside the
externally-generated ``demoDataset.js`` snapshot, which drifted from the real
manifest (e.g. the Remnawave Panel section was missing).

This script regenerates ``frontend/src/lib/webapp/settingsManifest.generated.json``
straight from :func:`manifest_payload` — the same source of truth the live
``/admin/settings`` endpoint uses — grouped into sections exactly like
``admin_settings_get_route``. The demo overlays its realistic values on top of
this structure, so adding a field in Python is enough to keep the demo in sync.

Usage::

    python scripts/export_settings_manifest.py

A pytest drift guard (``tests/test_settings_manifest_demo_sync.py``) compares the
committed JSON against a fresh build, so the snapshot cannot silently drift.
After regenerating, run Prettier so the file matches the frontend code style::

    npx --prefix frontend prettier --write src/lib/webapp/settingsManifest.generated.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for _path in (str(BACKEND), str(ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from bot.app.web.admin_settings_manifest import manifest_payload  # noqa: E402

OUTPUT_PATH = ROOT / "frontend" / "src" / "lib" / "webapp" / "settingsManifest.generated.json"


def build_demo_settings_sections() -> list[dict[str, Any]]:
    """Group the manifest into ordered sections with demo-safe field values.

    Mirrors :func:`bot.app.web.admin_api_impl.settings.admin_settings_get_route`
    but without any database- or settings-derived values: every field starts
    empty/unoverridden and secrets expose no value. The demo fills in realistic
    values per field key at runtime.
    """
    fields = manifest_payload()
    sections: dict[str, dict[str, Any]] = {}
    for field in fields:
        section_id = field["section"]
        if section_id not in sections:
            sections[section_id] = {
                "id": section_id,
                "order": field["section_order"],
                "fields": [],
            }
        is_secret = bool(field.get("secret"))
        response_field: dict[str, Any] = {
            **field,
            "value": "",
            "overridden": False,
            "updated_at": None,
        }
        if is_secret:
            response_field["has_value"] = False
        webhook_path = str(response_field.get("webhook_path") or "").strip()
        if webhook_path:
            if not webhook_path.startswith("/"):
                webhook_path = f"/{webhook_path}"
            response_field["webhook_path"] = webhook_path
            response_field["webhook_base_url_configured"] = False
        sections[section_id]["fields"].append(response_field)

    return sorted(sections.values(), key=lambda section: section["order"])


def render_json(sections: list[dict[str, Any]]) -> str:
    return json.dumps(sections, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    sections = build_demo_settings_sections()
    OUTPUT_PATH.write_text(render_json(sections), encoding="utf-8")
    field_count = sum(len(section["fields"]) for section in sections)
    print(
        f"Wrote {len(sections)} sections / {field_count} fields to {OUTPUT_PATH.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
