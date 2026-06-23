"""Guard that the demo settings manifest snapshot stays in sync with Python.

The Mini App demo feeds its admin Settings screen from
``frontend/src/lib/webapp/settingsManifest.generated.json``, generated off the
real :func:`manifest_payload`. If a developer adds or changes a settings field
in Python without regenerating that snapshot, this test fails and tells them how
to refresh it — keeping the demo automatically in step with reality.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GENERATOR_PATH = _REPO_ROOT / "scripts" / "export_settings_manifest.py"

_spec = importlib.util.spec_from_file_location("export_settings_manifest", _GENERATOR_PATH)
export_settings_manifest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export_settings_manifest)

OUTPUT_PATH = export_settings_manifest.OUTPUT_PATH
build_demo_settings_sections = export_settings_manifest.build_demo_settings_sections


class SettingsManifestDemoSyncTests(unittest.TestCase):
    def test_committed_snapshot_matches_manifest(self):
        self.assertTrue(
            OUTPUT_PATH.exists(),
            "Generated settings manifest snapshot is missing; run "
            "`python scripts/export_settings_manifest.py`.",
        )
        committed = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        expected = build_demo_settings_sections()
        self.assertEqual(
            committed,
            expected,
            "Demo settings manifest is stale. Regenerate it with "
            "`python scripts/export_settings_manifest.py` and re-run Prettier.",
        )

    def test_snapshot_includes_remnawave_section(self):
        committed = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        section_ids = {section["id"] for section in committed}
        self.assertIn("remnawave", section_ids)


if __name__ == "__main__":
    unittest.main()
