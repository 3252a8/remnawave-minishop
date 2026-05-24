import asyncio
import gzip
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from PIL import Image

from bot.app.web import subscription_webapp
from bot.app.web.admin_api_impl import themes as admin_themes
from bot.app.web.webapp import assets as webapp_assets
from bot.app.web.webapp import cache_helpers
from config.settings import Settings
from config.webapp_themes_config import WebappThemesConfig, builtin_webapp_themes_config


class WebAppAssetTests(unittest.IsolatedAsyncioTestCase):
    def test_serialize_plans_prefers_tariffs_config_over_legacy_packages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tariffs.json"
            path.write_text(
                json.dumps(
                    {
                        "default_tariff": "standard",
                        "tariffs": [
                            {
                                "key": "standard",
                                "names": {"en": "Standard"},
                                "descriptions": {"en": "100 GB monthly"},
                                "squad_uuids": ["uuid"],
                                "billing_model": "period",
                                "monthly_gb": 100,
                                "hwid_device_limit": 5,
                                "hwid_device_packages": {
                                    "rub": [{"count": 1, "price": 99}],
                                    "stars": [{"count": 1, "price": 2500}],
                                },
                                "prices_rub": {"1": 150},
                                "prices_stars": {"1": 0},
                                "enabled_periods": [1],
                                "enabled": True,
                            },
                            {
                                "key": "traffic",
                                "names": {"en": "Traffic"},
                                "descriptions": {"en": "Pay as you go"},
                                "squad_uuids": ["uuid"],
                                "billing_model": "traffic",
                                "traffic_packages": {
                                    "rub": [{"gb": 50, "price": 799}],
                                    "stars": [{"gb": 50, "price": 2500}],
                                },
                                "enabled": True,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings(
                _env_file=None,
                BOT_TOKEN="token",
                POSTGRES_USER="app_user",
                POSTGRES_PASSWORD="app_password",
                TARIFFS_CONFIG_PATH=str(path),
                TRAFFIC_PACKAGES="10:199",
            )

            plans = subscription_webapp._serialize_plans(settings, "en")

        self.assertEqual([plan["tariff_key"] for plan in plans], ["standard", "traffic"])
        self.assertEqual(plans[0]["sale_mode"], "subscription")
        self.assertEqual(plans[0]["months"], 1)
        self.assertEqual(plans[0]["hwid_device_limit"], 5)
        self.assertEqual(plans[0]["hwid_device_packages"][0]["device_count"], 1)
        self.assertEqual(plans[1]["sale_mode"], "traffic_package")
        self.assertEqual(plans[1]["traffic_gb"], 50.0)
        self.assertEqual(plans[1]["stars_price"], 2500)

    def test_subscription_template_does_not_block_on_telegram_sdk(self):
        html = subscription_webapp.TEMPLATE_PATH.read_text(encoding="utf-8")

        self.assertNotIn("https://telegram.org/js/telegram-web-app.js", html)
        self.assertNotIn("https://fonts.googleapis.com", html)
        self.assertNotIn('id="logo-preload"', html)
        self.assertNotIn('href=""', html)
        self.assertLess(html.index("/subscription_webapp.css"), html.index("WEBAPP_JS_SCRIPT"))

    def test_https_webapp_logo_uses_same_origin_proxy(self):
        settings = SimpleNamespace(WEBAPP_LOGO_URL="https://cdn.example.com/logo.png")

        self.assertRegex(
            subscription_webapp._resolve_webapp_logo_url(settings),
            r"^/webapp-logo\?v=[0-9a-f]{12}$",
        )

    def test_uploaded_webapp_logo_url_is_served_directly(self):
        settings = SimpleNamespace(
            WEBAPP_LOGO_URL="/webapp-uploaded-logo/logo-abcdef1234567890.png"
        )

        self.assertEqual(
            subscription_webapp._resolve_webapp_logo_url(settings),
            "/webapp-uploaded-logo/logo-abcdef1234567890.png",
        )

    async def test_webapp_logo_route_serves_configured_uploaded_logo(self):
        settings = SimpleNamespace(
            WEBAPP_LOGO_USE_EMOJI=False,
            WEBAPP_LOGO_URL="/webapp-uploaded-logo/logo-1111111111111111.png",
        )
        request = SimpleNamespace(app={"settings": settings})

        with tempfile.TemporaryDirectory() as tmpdir:
            logo_dir = Path(tmpdir)
            (logo_dir / "logo-1111111111111111.png").write_bytes(b"logo")
            with patch.object(webapp_assets, "WEBAPP_UPLOADED_LOGO_DIR", logo_dir):
                response = await webapp_assets.webapp_logo_route(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "image/png")
        self.assertEqual(response.body, b"logo")

    def test_webapp_logo_is_hidden_when_emoji_logo_is_enabled(self):
        settings = SimpleNamespace(
            WEBAPP_LOGO_USE_EMOJI=True,
            WEBAPP_LOGO_URL="/webapp-uploaded-logo/logo-abcdef1234567890.png",
        )

        self.assertEqual(subscription_webapp._resolve_webapp_logo_url(settings), "")

    def test_custom_webapp_favicon_takes_precedence(self):
        settings = SimpleNamespace(
            WEBAPP_FAVICON_USE_CUSTOM=True,
            WEBAPP_FAVICON_URL="/webapp-favicon/abcdef1234567890/icon-180.png",
            WEBAPP_LOGO_FAVICON_URL="/webapp-favicon/1111111111111111/icon-180.png",
        )

        self.assertEqual(
            subscription_webapp._resolve_webapp_favicon_url(settings, "/logo.png"),
            "/webapp-favicon/abcdef1234567890/icon-180.png",
        )

    def test_logo_generated_favicon_is_used_when_custom_disabled(self):
        settings = SimpleNamespace(
            WEBAPP_FAVICON_USE_CUSTOM=False,
            WEBAPP_FAVICON_URL="/webapp-favicon/abcdef1234567890/icon-180.png",
            WEBAPP_LOGO_FAVICON_URL="/webapp-favicon/1111111111111111/icon-180.png",
        )

        self.assertEqual(
            subscription_webapp._resolve_webapp_favicon_url(settings, "/logo.png"),
            "/webapp-favicon/1111111111111111/icon-180.png",
        )

    def test_logo_generated_favicon_is_not_used_without_logo(self):
        settings = SimpleNamespace(
            WEBAPP_FAVICON_USE_CUSTOM=False,
            WEBAPP_FAVICON_URL="/webapp-favicon/abcdef1234567890/icon-180.png",
            WEBAPP_LOGO_FAVICON_URL="/webapp-favicon/1111111111111111/icon-180.png",
        )

        self.assertEqual(subscription_webapp._resolve_webapp_favicon_url(settings, ""), "")

    def test_favicon_head_markup_includes_touch_icon(self):
        markup = subscription_webapp._favicon_head_markup(
            "/webapp-favicon/abcdef1234567890/icon-180.png"
        )

        self.assertIn('rel="apple-touch-icon"', markup)
        self.assertIn("/webapp-favicon/abcdef1234567890/icon-32.png", markup)

    def test_webapp_head_metadata_replaces_static_title_and_favicon(self):
        html = (
            '<html><head><link id="app-favicon" rel="icon" href="data:," sizes="any" />'
            "<title>/minishop</title></head><body></body></html>"
        )

        rendered = subscription_webapp._apply_webapp_head_metadata(
            html,
            "Brand & <VPN>",
            "/webapp-favicon/abcdef1234567890/icon-180.png",
        )

        self.assertIn("<title>Brand &amp; &lt;VPN&gt;</title>", rendered)
        self.assertIn('property="og:title" content="Brand &amp; &lt;VPN&gt;"', rendered)
        self.assertIn("/webapp-favicon/abcdef1234567890/icon-32.png", rendered)
        self.assertNotIn('href="data:,"', rendered)

    def test_favicon_set_generation_writes_common_icon_sizes(self):
        buffer = io.BytesIO()
        Image.new("RGBA", (2, 2), (0, 254, 122, 255)).save(buffer, format="PNG")
        png_body = buffer.getvalue()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(admin_themes, "WEBAPP_FAVICON_DIR", Path(tmpdir)):
                payload = admin_themes._write_favicon_set(png_body, "image/png", "icon.png")

            self.assertRegex(
                payload["favicon_url"],
                r"^/webapp-favicon/[0-9a-f]{16}/icon-180\.png$",
            )
            digest = payload["favicon_url"].split("/")[2]
            self.assertTrue((Path(tmpdir) / digest / "icon-32.png").exists())
            self.assertTrue((Path(tmpdir) / digest / "apple-touch-icon.png").exists())
            self.assertTrue((Path(tmpdir) / digest / "favicon.ico").exists())

    def test_prune_unused_appearance_assets_keeps_only_referenced_logo_and_favicons(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            uploads = root / "uploads"
            favicons = root / "favicons"
            emoji = root / "emoji"
            uploads.mkdir()
            favicons.mkdir()
            emoji.mkdir()
            (uploads / "logo-1111111111111111.png").write_bytes(b"keep")
            (uploads / "logo-2222222222222222.png").write_bytes(b"remove")
            (favicons / "aaaaaaaaaaaaaaaa").mkdir()
            (favicons / "bbbbbbbbbbbbbbbb").mkdir()
            (favicons / "cccccccccccccccc").mkdir()
            (favicons / "aaaaaaaaaaaaaaaa" / "icon-180.png").write_bytes(b"keep")
            (favicons / "bbbbbbbbbbbbbbbb" / "icon-180.png").write_bytes(b"keep")
            (favicons / "cccccccccccccccc" / "icon-180.png").write_bytes(b"remove")
            (emoji / "1f929.512.gif").write_bytes(b"keep")
            (emoji / "1f929.512.webp").write_bytes(b"keep")
            (emoji / "1f525.512.gif").write_bytes(b"remove")
            settings = SimpleNamespace(
                WEBAPP_LOGO_URL="/webapp-uploaded-logo/logo-1111111111111111.png",
                WEBAPP_FAVICON_URL="/webapp-favicon/aaaaaaaaaaaaaaaa/icon-180.png",
                WEBAPP_LOGO_FAVICON_URL="/webapp-favicon/bbbbbbbbbbbbbbbb/icon-180.png",
                WEBAPP_LOGO_USE_EMOJI=True,
                WEBAPP_LOGO_EMOJI="🤩",
                WEBAPP_LOGO_EMOJI_FONT="noto-color-animated",
            )

            with (
                patch.object(admin_themes, "WEBAPP_UPLOADED_LOGO_DIR", uploads),
                patch.object(admin_themes, "WEBAPP_FAVICON_DIR", favicons),
                patch.object(admin_themes, "WEBAPP_EMOJI_CACHE_DIR", emoji),
            ):
                admin_themes.prune_unused_appearance_assets(settings)

            self.assertTrue((uploads / "logo-1111111111111111.png").exists())
            self.assertFalse((uploads / "logo-2222222222222222.png").exists())
            self.assertTrue((favicons / "aaaaaaaaaaaaaaaa").exists())
            self.assertTrue((favicons / "bbbbbbbbbbbbbbbb").exists())
            self.assertFalse((favicons / "cccccccccccccccc").exists())
            self.assertTrue((emoji / "1f929.512.gif").exists())
            self.assertTrue((emoji / "1f929.512.webp").exists())
            self.assertFalse((emoji / "1f525.512.gif").exists())

    async def test_persist_appearance_upload_writes_overrides_and_clears_caches(self):
        settings = SimpleNamespace()
        request = SimpleNamespace(
            app={
                "settings": settings,
                "async_session_factory": object(),
                "webapp_settings_cache": {"ts": 123.0, "data": {"stale": True}},
                "webapp_logo_cache": ("url", b"body", "image/png"),
            }
        )
        updates = {
            "WEBAPP_LOGO_URL": "/webapp-uploaded-logo/logo-1111111111111111.png",
            "WEBAPP_LOGO_USE_EMOJI": False,
        }

        with (
            patch.object(
                admin_themes,
                "update_overrides",
                AsyncMock(return_value={"ok": True}),
            ) as update_mock,
            patch.object(admin_themes, "prune_unused_appearance_assets") as prune_mock,
        ):
            persisted = await admin_themes._persist_appearance_upload(request, updates, 42)

        self.assertTrue(persisted)
        update_mock.assert_awaited_once_with(
            settings,
            request.app["async_session_factory"],
            updates=updates,
            deletes=[],
            actor_id=42,
        )
        self.assertEqual(request.app["webapp_settings_cache"], {"ts": 0.0, "data": {}})
        self.assertIsNone(request.app["webapp_logo_cache"])
        prune_mock.assert_called_once_with(settings)

    def test_initial_theme_head_markup_includes_css_and_tokens(self):
        cfg = builtin_webapp_themes_config("#123456")
        theme = cfg.theme_by_key("light")
        request = SimpleNamespace(get=lambda key, default="": "nonce-value")

        markup = subscription_webapp._initial_theme_head_markup(request, theme, "#123456")

        self.assertIn("/webapp-theme-css/light/style.css?v=", markup)
        self.assertIn('nonce="nonce-value"', markup)
        self.assertIn("--accent:#123456", markup)
        self.assertIn("color-scheme:light", markup)

    def test_theme_asset_version_bumps_for_saved_default_css_theme(self):
        previous = WebappThemesConfig(
            default_theme="dark",
            themes=[
                {
                    "key": "dark",
                    "default": True,
                    "tokens": {"color_scheme": "dark"},
                },
                {
                    "key": "custom",
                    "default": False,
                    "css_file": "style.css",
                    "assets_version": 3,
                    "tokens": {"color_scheme": "dark"},
                },
            ],
        )
        updated = WebappThemesConfig(
            default_theme="custom",
            themes=[
                {
                    "key": "dark",
                    "default": False,
                    "tokens": {"color_scheme": "dark"},
                },
                {
                    "key": "custom",
                    "default": True,
                    "css_file": "style.css",
                    "assets_version": 3,
                    "tokens": {"color_scheme": "dark"},
                },
            ],
        )

        bumped = admin_themes._bump_theme_asset_versions(updated, previous)

        self.assertEqual(bumped.theme_by_key("custom").assets_version, 4)

    def test_animated_emoji_asset_path_uses_same_origin_route(self):
        self.assertEqual(
            subscription_webapp._webapp_animated_emoji_asset_path("🤩"),
            "/webapp-emoji/1f929/512.gif",
        )

    def test_telegram_avatar_url_uses_same_origin_account_route(self):
        avatar = SimpleNamespace(
            user_id=123,
            image_bytes=b"avatar",
            updated_at=datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(
            subscription_webapp._telegram_avatar_url(avatar),
            f"/api/account/avatar?v={int(avatar.updated_at.timestamp())}",
        )

    def test_select_compact_telegram_photo_size_prefers_small_suitable_photo(self):
        small = SimpleNamespace(width=80, height=80, file_size=5000)
        medium = SimpleNamespace(width=160, height=160, file_size=12000)
        large = SimpleNamespace(width=640, height=640, file_size=90000)

        self.assertIs(
            subscription_webapp._select_compact_telegram_photo_size([small, large, medium]),
            medium,
        )

    def test_serialize_plans_uses_traffic_packages_in_traffic_mode(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            TARIFFS_CONFIG_PATH="missing-tariffs.json",
            TRAFFIC_PACKAGES="10:199,50:799",
            STARS_TRAFFIC_PACKAGES="50:2500",
        )

        plans = subscription_webapp._serialize_plans(settings, "en")

        self.assertEqual([plan["traffic_gb"] for plan in plans], [10.0, 50.0])
        self.assertEqual(plans[0]["sale_mode"], "traffic")
        self.assertEqual(plans[0]["price"], 199.0)
        self.assertEqual(plans[1]["stars_price"], 2500)

    def test_serialize_payment_methods_respects_runtime_provider_toggles(self):
        # Provider toggles now live in per-provider BaseSettings models. Disable
        # all providers by giving each one an empty bundle (default ENABLED is
        # False for everything except cryptopay/yookassa, so override those too).
        from bot.payment_providers import (
            build_provider_configs,
            current_provider_configs,
        )

        build_provider_configs(force=True)
        configs = current_provider_configs()
        for service_key in ("cryptopay_service", "yookassa_service"):
            bundle = configs.get(service_key)
            if bundle and bundle.config is not None and hasattr(bundle.config, "ENABLED"):
                bundle.config.ENABLED = False

        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            TARIFFS_CONFIG_PATH="missing-tariffs.json",
            YOOKASSA_ENABLED=False,
            PLATEGA_ENABLED=False,
            STARS_ENABLED=False,
        )
        configured_service = SimpleNamespace(configured=True)
        app = {
            "cryptopay_service": configured_service,
            "freekassa_service": configured_service,
            "severpay_service": configured_service,
            "yookassa_service": configured_service,
            "platega_service": configured_service,
        }

        methods = subscription_webapp._serialize_payment_methods(settings, app)

        self.assertEqual(methods, [])

    def test_serialize_payment_methods_includes_provider_presentation(self):
        from bot.payment_providers import (
            build_provider_configs,
            get_provider_bundle,
            get_spec_presentation,
        )

        build_provider_configs(force=True)
        bundle = get_provider_bundle("yookassa_service")
        if bundle and bundle.config is not None:
            bundle.config.ENABLED = True
        presentation = get_spec_presentation("yookassa")
        if presentation is not None:
            presentation.WEBAPP_LABEL_RU = "Карта"
            presentation.WEBAPP_LABEL_EN = "Bank card"
            presentation.WEBAPP_ICON = "WalletCards"

        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            TARIFFS_CONFIG_PATH="missing-tariffs.json",
            PAYMENT_METHODS_ORDER="yookassa",
            STARS_ENABLED=False,
        )
        app = {"yookassa_service": SimpleNamespace(configured=True)}

        methods = subscription_webapp._serialize_payment_methods(settings, app, "en")

        # Only yookassa is configured/enabled; every other provider gets
        # filtered out by is_visible even though they're auto-appended to the
        # order list now.
        self.assertEqual(
            methods,
            [{"id": "yookassa", "name": "Bank card", "icon": "WalletCards"}],
        )

    def test_serialize_payment_methods_includes_wata_from_provider_config(self):
        from bot.payment_providers import build_provider_configs, get_provider_bundle

        build_provider_configs(force=True)
        bundle = get_provider_bundle("wata_service")
        self.assertIsNotNone(bundle)
        bundle.config.ENABLED = True
        bundle.config.API_TOKEN = "wata-token"

        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            TARIFFS_CONFIG_PATH="missing-tariffs.json",
            PAYMENT_METHODS_ORDER="wata",
            STARS_ENABLED=False,
        )
        app = {"wata_service": SimpleNamespace(configured=True)}

        methods = subscription_webapp._serialize_payment_methods(settings, app, "en")

        self.assertEqual(methods, [{"id": "wata", "name": "Wata", "icon": "WalletCards"}])

    async def test_invalidate_all_webapp_user_caches_clears_cached_me_payload(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            REDIS_URL=None,
        )
        calls = 0

        async def loader():
            nonlocal calls
            calls += 1
            return {"payment_methods": [{"id": f"method-{calls}"}]}

        first = await cache_helpers.webapp_cached_user_payload(settings, "me", 42, 60, loader)
        second = await cache_helpers.webapp_cached_user_payload(settings, "me", 42, 60, loader)

        self.assertEqual(first, {"payment_methods": [{"id": "method-1"}]})
        self.assertEqual(second, first)
        self.assertEqual(calls, 1)

        await cache_helpers.invalidate_all_webapp_user_caches(settings)
        third = await cache_helpers.webapp_cached_user_payload(settings, "me", 42, 60, loader)

        self.assertEqual(third, {"payment_methods": [{"id": "method-2"}]})
        self.assertEqual(calls, 2)

    def test_serialize_plans_includes_stars_only_subscription_options(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            YOOKASSA_ENABLED=False,
            CRYPTOPAY_ENABLED=False,
            TARIFFS_CONFIG_PATH="missing-tariffs.json",
            RUB_PRICE_1_MONTH=None,
            STARS_PRICE_1_MONTH=250,
        )

        plans = subscription_webapp._serialize_plans(settings, "en")

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["months"], 1)
        self.assertEqual(plans[0]["price"], 0.0)
        self.assertEqual(plans[0]["stars_price"], 250)

    def test_resolve_webapp_js_asset_name_prefers_latest_minified_build(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            asset_dir = Path(tmpdir)
            (asset_dir / "subscription_webapp.js").write_text(
                "console.log('fallback');", encoding="utf-8"
            )
            old_asset = asset_dir / "subscription_webapp.min.11111111.js"
            new_asset = asset_dir / "subscription_webapp.min.22222222.js"
            old_asset.write_text("console.log('old');", encoding="utf-8")
            new_asset.write_text("console.log('new');", encoding="utf-8")
            os.utime(old_asset, (1, 1))
            os.utime(new_asset, (2, 2))

            with patch.object(webapp_assets, "ASSET_DIR", asset_dir):
                self.assertEqual(
                    subscription_webapp._resolve_webapp_js_asset_name(),
                    "subscription_webapp.min.22222222.js",
                )

    def test_resolve_webapp_admin_asset_names_use_stable_runtime_builds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            asset_dir = Path(tmpdir)
            (asset_dir / "subscription_webapp_admin.js").write_text(
                "console.log('admin fallback');", encoding="utf-8"
            )
            (asset_dir / "subscription_webapp_admin.css").write_text(
                ".admin{color:red}", encoding="utf-8"
            )
            old_js = asset_dir / "subscription_webapp_admin.min.11111111.js"
            new_js = asset_dir / "subscription_webapp_admin.min.22222222.js"
            old_css = asset_dir / "subscription_webapp_admin.11111111.css"
            new_css = asset_dir / "subscription_webapp_admin.22222222.css"
            old_js.write_text("console.log('old');", encoding="utf-8")
            new_js.write_text("console.log('new');", encoding="utf-8")
            old_css.write_text(".old{}", encoding="utf-8")
            new_css.write_text(".new{}", encoding="utf-8")
            os.utime(old_js, (1, 1))
            os.utime(old_css, (1, 1))
            os.utime(new_js, (2, 2))
            os.utime(new_css, (2, 2))

            with patch.object(webapp_assets, "ASSET_DIR", asset_dir):
                self.assertEqual(
                    subscription_webapp._resolve_webapp_admin_js_asset_name(),
                    "subscription_webapp_admin.js",
                )
                self.assertEqual(
                    subscription_webapp._resolve_webapp_admin_css_asset_name(),
                    "subscription_webapp_admin.css",
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

            with patch.object(webapp_assets, "ASSET_DIR", asset_dir):
                response = await subscription_webapp.js_asset_route(request)

            self.assertEqual(
                response.headers["Cache-Control"], "public, max-age=31536000, immutable"
            )
            self.assertEqual(response.text, "console.log('minified');")

    async def test_admin_js_asset_route_serves_admin_bundle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            asset_dir = Path(tmpdir)
            minified_asset = asset_dir / "subscription_webapp_admin.min.abcdef12.js"
            minified_asset.write_text("console.log('admin');", encoding="utf-8")

            request = SimpleNamespace(
                app={"settings": SimpleNamespace(WEBAPP_ENABLED=True)},
                match_info={"asset_hash": "abcdef12"},
            )

            with patch.object(webapp_assets, "ASSET_DIR", asset_dir):
                response = await subscription_webapp.admin_js_asset_route(request)

            self.assertEqual(
                response.headers["Cache-Control"], "public, max-age=31536000, immutable"
            )
            self.assertEqual(response.text, "console.log('admin');")

    async def test_js_asset_route_prefers_precompressed_brotli_asset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            asset_dir = Path(tmpdir)
            minified_asset = asset_dir / "subscription_webapp.min.abcdef12.js"
            minified_asset.write_text("console.log('minified');", encoding="utf-8")
            (asset_dir / "subscription_webapp.min.abcdef12.js.br").write_bytes(b"br-body")

            request = SimpleNamespace(
                app={"settings": SimpleNamespace(WEBAPP_ENABLED=True)},
                match_info={"asset_hash": "abcdef12"},
                headers={"Accept-Encoding": "gzip, br"},
            )

            with patch.object(webapp_assets, "ASSET_DIR", asset_dir):
                response = await subscription_webapp.js_asset_route(request)

            self.assertEqual(response.body, b"br-body")
            self.assertEqual(response.headers["Content-Encoding"], "br")
            self.assertEqual(response.headers["Vary"], "Accept-Encoding")
            self.assertEqual(
                response.headers["Cache-Control"], "public, max-age=31536000, immutable"
            )

    async def test_css_asset_route_falls_back_to_precompressed_gzip_asset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            asset_dir = Path(tmpdir)
            css_asset = asset_dir / "subscription_webapp.abcdef12.css"
            css_asset.write_text(".app{color:red}", encoding="utf-8")
            (asset_dir / "subscription_webapp.abcdef12.css.gz").write_bytes(b"gz-body")

            request = SimpleNamespace(
                app={"settings": SimpleNamespace(WEBAPP_ENABLED=True)},
                match_info={"asset_hash": "abcdef12"},
                headers={"Accept-Encoding": "gzip"},
            )

            with patch.object(webapp_assets, "ASSET_DIR", asset_dir):
                response = await subscription_webapp.css_asset_route(request)

            self.assertEqual(response.body, b"gz-body")
            self.assertEqual(response.headers["Content-Encoding"], "gzip")
            self.assertEqual(response.headers["Vary"], "Accept-Encoding")
            self.assertEqual(
                response.headers["Cache-Control"], "public, max-age=31536000, immutable"
            )

    async def test_theme_css_asset_route_serves_file_from_configured_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            themes_dir = Path(tmpdir)
            (themes_dir / "custom").mkdir()
            (themes_dir / "custom" / "theme.css").write_text(
                ".theme-key-custom { --bg: red; }", encoding="utf-8"
            )
            request = SimpleNamespace(
                app={
                    "settings": SimpleNamespace(
                        WEBAPP_ENABLED=True,
                        WEBAPP_THEMES_DIR=str(themes_dir),
                    )
                },
                match_info={"path": "custom/theme.css"},
            )

            response = await subscription_webapp.theme_css_asset_route(request)

            self.assertEqual(response.content_type, "text/css")
            self.assertEqual(response.headers["Cache-Control"], "no-cache")
            self.assertIn("ETag", response.headers)
            self.assertIn("--bg: red", response.text)

    async def test_theme_css_asset_route_uses_immutable_cache_when_versioned(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            themes_dir = Path(tmpdir)
            (themes_dir / "custom").mkdir()
            (themes_dir / "custom" / "theme.css").write_text(
                ".theme-key-custom { --bg: red; }", encoding="utf-8"
            )
            request = SimpleNamespace(
                app={
                    "settings": SimpleNamespace(
                        WEBAPP_ENABLED=True,
                        WEBAPP_THEMES_DIR=str(themes_dir),
                    )
                },
                match_info={"path": "custom/theme.css"},
                query={"v": "2"},
            )

            response = await subscription_webapp.theme_css_asset_route(request)

            self.assertEqual(
                response.headers["Cache-Control"], "public, max-age=31536000, immutable"
            )

    async def test_theme_css_asset_route_returns_not_modified_for_matching_etag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            themes_dir = Path(tmpdir)
            (themes_dir / "custom").mkdir()
            (themes_dir / "custom" / "theme.css").write_text(
                ".theme-key-custom { --bg: red; }", encoding="utf-8"
            )
            request = SimpleNamespace(
                app={
                    "settings": SimpleNamespace(
                        WEBAPP_ENABLED=True,
                        WEBAPP_THEMES_DIR=str(themes_dir),
                    )
                },
                match_info={"path": "custom/theme.css"},
                headers={},
            )

            response = await subscription_webapp.theme_css_asset_route(request)
            etag = response.headers["ETag"]
            cached_request = SimpleNamespace(
                app=request.app,
                match_info=request.match_info,
                headers={"If-None-Match": etag},
            )

            cached_response = await subscription_webapp.theme_css_asset_route(cached_request)

            self.assertEqual(cached_response.status, 304)
            self.assertEqual(cached_response.headers["ETag"], etag)
            self.assertEqual(cached_response.headers["Cache-Control"], "no-cache")

    async def test_theme_css_asset_route_serves_cached_gzip_when_accepted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            themes_dir = Path(tmpdir)
            (themes_dir / "custom").mkdir()
            (themes_dir / "custom" / "theme.css").write_text(
                ".theme-key-custom { --bg: red; }\n", encoding="utf-8"
            )
            request = SimpleNamespace(
                app={
                    "settings": SimpleNamespace(
                        WEBAPP_ENABLED=True,
                        WEBAPP_THEMES_DIR=str(themes_dir),
                    )
                },
                match_info={"path": "custom/theme.css"},
                headers={"Accept-Encoding": "gzip"},
            )

            response = await subscription_webapp.theme_css_asset_route(request)

            self.assertEqual(response.headers["Content-Encoding"], "gzip")
            self.assertEqual(response.headers["Vary"], "Accept-Encoding")
            self.assertEqual(
                gzip.decompress(response.body).decode("utf-8"),
                ".theme-key-custom { --bg: red; }\n",
            )

    async def test_theme_css_asset_route_serves_default_theme_asset_from_theme_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            request = SimpleNamespace(
                app={
                    "settings": SimpleNamespace(
                        WEBAPP_ENABLED=True,
                        WEBAPP_THEMES_DIR=tmpdir,
                    )
                },
                match_info={"path": "light/style.css"},
            )

            response = await subscription_webapp.theme_css_asset_route(request)

            self.assertEqual(response.content_type, "text/css")
            self.assertIn(".theme-key-light", response.text)
            self.assertTrue((Path(tmpdir) / "light" / "theme.json").exists())
            self.assertTrue((Path(tmpdir) / "light" / "style.css").exists())

    async def test_theme_css_asset_route_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            request = SimpleNamespace(
                app={
                    "settings": SimpleNamespace(
                        WEBAPP_ENABLED=True,
                        WEBAPP_THEMES_DIR=tmpdir,
                    )
                },
                match_info={"path": "../secret.css"},
            )

            with self.assertRaises(webapp_assets.web.HTTPNotFound):
                await subscription_webapp.theme_css_asset_route(request)

    async def test_theme_asset_route_serves_image_from_configured_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            themes_dir = Path(tmpdir)
            (themes_dir / "custom" / "icons").mkdir(parents=True)
            (themes_dir / "custom" / "icons" / "save.png").write_bytes(b"png-bytes")
            request = SimpleNamespace(
                app={
                    "settings": SimpleNamespace(
                        WEBAPP_ENABLED=True,
                        WEBAPP_THEMES_DIR=str(themes_dir),
                    )
                },
                match_info={"path": "custom/icons/save.png"},
            )

            response = await subscription_webapp.theme_asset_route(request)

            self.assertEqual(response.content_type, "image/png")
            self.assertEqual(response.headers["Cache-Control"], "public, max-age=3600")
            self.assertIn("ETag", response.headers)
            self.assertEqual(response.body, b"png-bytes")

    async def test_theme_asset_route_returns_not_modified_for_matching_etag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            themes_dir = Path(tmpdir)
            (themes_dir / "custom" / "icons").mkdir(parents=True)
            (themes_dir / "custom" / "icons" / "save.png").write_bytes(b"png-bytes")
            request = SimpleNamespace(
                app={
                    "settings": SimpleNamespace(
                        WEBAPP_ENABLED=True,
                        WEBAPP_THEMES_DIR=str(themes_dir),
                    )
                },
                match_info={"path": "custom/icons/save.png"},
                query={},
                headers={},
            )

            response = await subscription_webapp.theme_asset_route(request)
            etag = response.headers["ETag"]
            cached_request = SimpleNamespace(
                app=request.app,
                match_info=request.match_info,
                query={},
                headers={"If-None-Match": etag},
            )

            cached_response = await subscription_webapp.theme_asset_route(cached_request)

            self.assertEqual(cached_response.status, 304)
            self.assertEqual(cached_response.headers["ETag"], etag)
            self.assertEqual(cached_response.headers["Cache-Control"], "public, max-age=3600")

    async def test_theme_asset_route_uses_immutable_cache_for_versioned_assets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            themes_dir = Path(tmpdir)
            (themes_dir / "custom" / "icons").mkdir(parents=True)
            (themes_dir / "custom" / "icons" / "save.png").write_bytes(b"png-bytes")
            request = SimpleNamespace(
                app={
                    "settings": SimpleNamespace(
                        WEBAPP_ENABLED=True,
                        WEBAPP_THEMES_DIR=str(themes_dir),
                    )
                },
                match_info={"path": "custom/icons/save.png"},
                query={"v": "6"},
            )

            response = await subscription_webapp.theme_asset_route(request)

            self.assertEqual(
                response.headers["Cache-Control"], "public, max-age=31536000, immutable"
            )

    async def test_theme_asset_route_serves_default_theme_icon_from_theme_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            request = SimpleNamespace(
                app={
                    "settings": SimpleNamespace(
                        WEBAPP_ENABLED=True,
                        WEBAPP_THEMES_DIR=tmpdir,
                    )
                },
                match_info={"path": "windows95/icons/save.png"},
            )

            response = await subscription_webapp.theme_asset_route(request)

            self.assertEqual(response.content_type, "image/png")
            self.assertGreater(len(response.body), 0)
            self.assertTrue((Path(tmpdir) / "windows95" / "theme.json").exists())
            self.assertTrue((Path(tmpdir) / "windows95" / "icons" / "save.png").exists())

    async def test_theme_asset_route_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            request = SimpleNamespace(
                app={
                    "settings": SimpleNamespace(
                        WEBAPP_ENABLED=True,
                        WEBAPP_THEMES_DIR=tmpdir,
                    )
                },
                match_info={"path": "../secret.png"},
            )

            with self.assertRaises(webapp_assets.web.HTTPNotFound):
                await subscription_webapp.theme_asset_route(request)

    async def test_theme_asset_route_rejects_non_image_suffix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            request = SimpleNamespace(
                app={
                    "settings": SimpleNamespace(
                        WEBAPP_ENABLED=True,
                        WEBAPP_THEMES_DIR=tmpdir,
                    )
                },
                match_info={"path": "custom/icons/readme.txt"},
            )

            with self.assertRaises(webapp_assets.web.HTTPNotFound):
                await subscription_webapp.theme_asset_route(request)

    def test_webapp_logo_disk_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logo_url = "https://cdn.example.com/logo.png"
            logo = (b"png-bytes", "image/png")

            with patch.object(webapp_assets, "WEBAPP_LOGO_CACHE_DIR", Path(tmpdir)):
                subscription_webapp._write_webapp_logo_to_disk(logo_url, logo)

                self.assertEqual(subscription_webapp._read_webapp_logo_from_disk(logo_url), logo)

    async def test_warm_webapp_logo_cache_uses_disk_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logo_url = "https://cdn.example.com/logo.png"
            logo = (b"cached-logo", "image/png")
            app = {
                "settings": SimpleNamespace(WEBAPP_LOGO_URL=logo_url, WEBAPP_LOGO_USE_EMOJI=False),
                "webapp_logo_cache": None,
                "webapp_logo_cache_lock": asyncio.Lock(),
            }

            with (
                patch.object(webapp_assets, "WEBAPP_LOGO_CACHE_DIR", Path(tmpdir)),
                patch.object(
                    webapp_assets,
                    "_hostname_resolves_to_public_address",
                    return_value=True,
                ),
                patch.object(webapp_assets, "_fetch_webapp_logo") as fetch_logo,
            ):
                subscription_webapp._write_webapp_logo_to_disk(logo_url, logo)

                await subscription_webapp._warm_webapp_logo_cache(app)

            fetch_logo.assert_not_called()
            self.assertEqual(app["webapp_logo_cache"], (logo_url, logo[0], logo[1]))

    def test_webapp_animated_emoji_disk_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(webapp_assets, "WEBAPP_EMOJI_CACHE_DIR", Path(tmpdir)):
                subscription_webapp._write_webapp_animated_emoji_to_disk(
                    "1f929",
                    "gif",
                    (b"gif-bytes", "image/gif"),
                )

                self.assertEqual(
                    subscription_webapp._read_webapp_animated_emoji_from_disk("1f929", "gif"),
                    (b"gif-bytes", "image/gif"),
                )

    async def test_warm_webapp_animated_emoji_cache_uses_disk_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app = {
                "settings": SimpleNamespace(
                    WEBAPP_LOGO_USE_EMOJI=True,
                    WEBAPP_LOGO_EMOJI="🤩",
                    WEBAPP_LOGO_EMOJI_FONT="noto-color-animated",
                ),
                "webapp_emoji_cache": {},
                "webapp_emoji_cache_lock": asyncio.Lock(),
            }

            with (
                patch.object(webapp_assets, "WEBAPP_EMOJI_CACHE_DIR", Path(tmpdir)),
                patch.object(webapp_assets, "_fetch_webapp_animated_emoji") as fetch_emoji,
            ):
                subscription_webapp._write_webapp_animated_emoji_to_disk(
                    "1f929",
                    "gif",
                    (b"cached-gif", "image/gif"),
                )

                await subscription_webapp._warm_webapp_animated_emoji_cache(app)

            fetch_emoji.assert_not_called()
            self.assertEqual(app["webapp_emoji_cache"]["1f929:gif"], (b"cached-gif", "image/gif"))
