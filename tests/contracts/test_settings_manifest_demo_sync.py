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
assert _spec is not None
assert _spec.loader is not None
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

    def test_hosted_payment_methods_share_one_provider_subsection(self):
        sections = build_demo_settings_sections()
        payments = next(section for section in sections if section["id"] == "payments")
        for prefix, subsection in (("CRYPTOMUS_", "Cryptomus"), ("CISPAY_", "CisPay")):
            with self.subTest(provider=subsection):
                fields = [
                    field
                    for field in payments["fields"]
                    if field["key"].startswith((prefix, f"PAYMENT_{prefix}"))
                ]
                self.assertTrue(fields)
                self.assertEqual({field["subsection"] for field in fields}, {subsection})
                keys = [field["key"] for field in fields]
                self.assertEqual(len(keys), len(set(keys)))
                self.assertTrue(any("SUBSCRIPTION_" in key for key in keys))


if __name__ == "__main__":
    unittest.main()
