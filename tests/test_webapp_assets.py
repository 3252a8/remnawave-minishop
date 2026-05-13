import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bot.app.web import subscription_webapp
from config.settings import Settings


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
        self.assertLess(html.index("/subscription_webapp.css"), html.index("WEBAPP_JS_SCRIPT"))

    def test_https_webapp_logo_uses_same_origin_proxy(self):
        settings = SimpleNamespace(WEBAPP_LOGO_URL="https://cdn.example.com/logo.png")

        self.assertRegex(
            subscription_webapp._resolve_webapp_logo_url(settings),
            r"^/webapp-logo\?v=[0-9a-f]{12}$",
        )

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
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            TARIFFS_CONFIG_PATH="missing-tariffs.json",
            CRYPTOPAY_ENABLED=False,
            FREEKASSA_ENABLED=False,
            SEVERPAY_ENABLED=False,
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

            self.assertEqual(
                response.headers["Cache-Control"], "public, max-age=31536000, immutable"
            )
            self.assertEqual(response.text, "console.log('minified');")

    def test_webapp_logo_disk_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logo_url = "https://cdn.example.com/logo.png"
            logo = (b"png-bytes", "image/png")

            with patch.object(subscription_webapp, "WEBAPP_LOGO_CACHE_DIR", Path(tmpdir)):
                subscription_webapp._write_webapp_logo_to_disk(logo_url, logo)

                self.assertEqual(subscription_webapp._read_webapp_logo_from_disk(logo_url), logo)

    async def test_warm_webapp_logo_cache_uses_disk_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logo_url = "https://cdn.example.com/logo.png"
            logo = (b"cached-logo", "image/png")
            app = {
                "settings": SimpleNamespace(WEBAPP_LOGO_URL=logo_url),
                "webapp_logo_cache": None,
                "webapp_logo_cache_lock": asyncio.Lock(),
            }

            with (
                patch.object(subscription_webapp, "WEBAPP_LOGO_CACHE_DIR", Path(tmpdir)),
                patch.object(
                    subscription_webapp,
                    "_hostname_resolves_to_public_address",
                    return_value=True,
                ),
                patch.object(subscription_webapp, "_fetch_webapp_logo") as fetch_logo,
            ):
                subscription_webapp._write_webapp_logo_to_disk(logo_url, logo)

                await subscription_webapp._warm_webapp_logo_cache(app)

            fetch_logo.assert_not_called()
            self.assertEqual(app["webapp_logo_cache"], (logo_url, logo[0], logo[1]))

    def test_webapp_animated_emoji_disk_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(subscription_webapp, "WEBAPP_EMOJI_CACHE_DIR", Path(tmpdir)):
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
                    WEBAPP_LOGO_EMOJI="🤩",
                    WEBAPP_LOGO_EMOJI_FONT="noto-color-animated",
                ),
                "webapp_emoji_cache": {},
                "webapp_emoji_cache_lock": asyncio.Lock(),
            }

            with (
                patch.object(subscription_webapp, "WEBAPP_EMOJI_CACHE_DIR", Path(tmpdir)),
                patch.object(subscription_webapp, "_fetch_webapp_animated_emoji") as fetch_emoji,
            ):
                subscription_webapp._write_webapp_animated_emoji_to_disk(
                    "1f929",
                    "gif",
                    (b"cached-gif", "image/gif"),
                )

                await subscription_webapp._warm_webapp_animated_emoji_cache(app)

            fetch_emoji.assert_not_called()
            self.assertEqual(app["webapp_emoji_cache"]["1f929:gif"], (b"cached-gif", "image/gif"))
