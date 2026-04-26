import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bot.app.web import subscription_webapp


class WebAppAssetTests(unittest.IsolatedAsyncioTestCase):
    def test_resolve_webapp_js_asset_name_prefers_latest_minified_build(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            asset_dir = Path(tmpdir)
            (asset_dir / "subscription_webapp.js").write_text("console.log('fallback');", encoding="utf-8")
            old_asset = asset_dir / "subscription_webapp.min.11111111.js"
            new_asset = asset_dir / "subscription_webapp.min.22222222.js"
            old_asset.write_text("console.log('old');", encoding="utf-8")
            new_asset.write_text("console.log('new');", encoding="utf-8")
            os.utime(old_asset, (1, 1))
            os.utime(new_asset, (2, 2))

            with patch.object(subscription_webapp, "ASSET_DIR", asset_dir):
                self.assertEqual(
                    subscription_webapp._resolve_webapp_js_asset_name(),
                    "subscription_webapp.min.22222222.js",
                )

    async def test_js_asset_route_sets_immutable_cache_control_for_minified_asset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            asset_dir = Path(tmpdir)
            minified_asset = asset_dir / "subscription_webapp.min.abcdef12.js"
            minified_asset.write_text("console.log('minified');", encoding="utf-8")

            request = SimpleNamespace(
                app={"settings": SimpleNamespace(WEBAPP_ENABLED=True)},
                match_info={"asset_hash": "abcdef12"},
            )

            with patch.object(subscription_webapp, "ASSET_DIR", asset_dir):
                response = await subscription_webapp.js_asset_route(request)

            self.assertEqual(response.headers["Cache-Control"], "public, max-age=31536000, immutable")
            self.assertEqual(response.text, "console.log('minified');")
