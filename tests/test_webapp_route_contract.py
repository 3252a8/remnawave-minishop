import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from bot.app.web import admin_api, subscription_webapp
from bot.app.web.admin_api_impl import auth as admin_auth_routes
from bot.app.web.webapp_auth import create_webapp_session_token

REPO_ROOT = Path(__file__).resolve().parents[1]


class _Request(dict):
    def __init__(self, *, path="/", app=None, headers=None, cookies=None):
        super().__init__()
        self.path = path
        self.app = app or {}
        self.headers = headers or {}
        self.cookies = cookies or {}


class _AsyncSessionFactory:
    def __call__(self):
        return self

    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _I18n:
    locales_data = {
        "en": {
            "wa_app_launch_title": "Localized launch",
            "wa_app_launch_opening_hint": "Localized opening hint",
            "wa_app_launch_hint": "Localized manual hint",
            "wa_app_launch_button": "Localized open",
            "wa_app_launch_retry_button": "Localized retry",
            "wa_app_launch_done_title": "Localized done",
            "wa_app_launch_done_hint": "Localized done hint",
            "wa_app_launch_close_button": "Localized close",
            "wa_app_launch_unavailable_title": "Localized unavailable",
            "wa_app_launch_unavailable_hint": "Localized unavailable hint",
        }
    }

    def gettext(self, lang_code, key, **kwargs):
        return self.locales_data.get(lang_code, {}).get(key, key)


def _route_map(app: web.Application) -> dict[tuple[str, str], str]:
    return {
        (route.method, route.resource.canonical): route.handler.__name__
        for route in app.router.routes()
        if route.method != "HEAD"
    }


class WebAppRouteContractTests(unittest.TestCase):
    def test_subscription_webapp_registers_public_and_api_routes(self):
        app = web.Application()

        subscription_webapp.setup_subscription_webapp_routes(app)

        routes = _route_map(app)
        expected = {
            ("GET", "/"): "index_route",
            ("GET", "/login/password"): "index_route",
            ("GET", "/home"): "index_route",
            ("GET", "/install"): "index_route",
            ("GET", "/trial"): "index_route",
            ("GET", "/open-app"): "app_deeplink_route",
            ("GET", "/s/{share_token}"): "index_route",
            ("GET", "/invite"): "index_route",
            ("GET", "/devices"): "index_route",
            ("GET", "/settings"): "index_route",
            ("GET", "/admin"): "index_route",
            ("GET", "/admin/{section}"): "index_route",
            ("GET", "/admin/users/{user_id}"): "index_route",
            ("GET", "/auth/telegram/start"): "telegram_oauth_start_route",
            ("GET", "/auth/telegram/callback"): "telegram_oauth_callback_route",
            ("GET", "/health"): "health_route",
            ("GET", "/robots.txt"): "robots_txt_route",
            ("GET", "/webapp-logo"): "webapp_logo_route",
            ("GET", "/webapp-uploaded-logo/{filename}"): "webapp_uploaded_logo_route",
            ("GET", "/webapp-emoji/{codepoints}/512.{ext}"): "webapp_animated_emoji_route",
            ("GET", "/subscription_webapp.css"): "css_asset_route",
            ("GET", "/subscription_webapp_admin.css"): "admin_css_asset_route",
            ("GET", "/webapp-theme-css/{path}"): "theme_css_asset_route",
            ("GET", "/subscription_webapp.min.{asset_hash}.js"): "js_asset_route",
            ("GET", "/subscription_webapp.js"): "js_asset_route",
            ("GET", "/subscription_webapp_admin.min.{asset_hash}.js"): "admin_js_asset_route",
            ("GET", "/subscription_webapp_admin.js"): "admin_js_asset_route",
            ("POST", "/api/auth/telegram/nonce"): "telegram_oauth_nonce_route",
            ("POST", "/api/auth/token"): "auth_token_route",
            ("POST", "/api/auth/email/request"): "email_auth_request_route",
            ("POST", "/api/auth/email/verify"): "email_auth_verify_route",
            ("POST", "/api/auth/email/magic"): "email_auth_magic_route",
            ("POST", "/api/auth/email/password"): "email_password_auth_route",
            ("POST", "/api/auth/logout"): "logout_route",
            ("GET", "/api/me"): "me_route",
            ("GET", "/api/subscription-guides"): "subscription_guides_route",
            (
                "GET",
                "/api/subscription-guides/public/{share_token}",
            ): "public_subscription_guides_route",
            ("GET", "/api/account/avatar"): "account_avatar_route",
            ("POST", "/api/account/language"): "account_language_route",
            ("POST", "/api/account/email/request"): "account_email_request_route",
            ("POST", "/api/account/email/verify"): "account_email_verify_route",
            ("POST", "/api/account/password/request"): "account_password_request_route",
            ("POST", "/api/account/password/confirm"): "account_password_confirm_route",
            ("POST", "/api/account/telegram/link"): "account_telegram_link_route",
            ("POST", "/api/promo/apply"): "apply_promo_route",
            ("POST", "/api/trial/activate"): "activate_trial_route",
            ("GET", "/api/devices"): "devices_route",
            ("POST", "/api/devices/disconnect"): "disconnect_device_route",
            ("GET", "/api/devices/topup-options"): "device_topup_options_route",
            ("GET", "/api/tariffs/topup-options"): "tariff_topup_options_route",
            ("GET", "/api/tariffs/change-options"): "tariff_change_options_route",
            ("POST", "/api/tariffs/change"): "tariff_change_route",
            ("POST", "/api/tariffs/change-payment"): "tariff_change_payment_route",
            ("POST", "/api/payments"): "create_payment_route",
            ("GET", "/api/payments/{payment_id}"): "payment_status_route",
        }

        for key, handler_name in expected.items():
            self.assertEqual(routes.get(key), handler_name, key)

    def test_robots_txt_disallows_crawling_webapp(self):
        response = asyncio.run(subscription_webapp.robots_txt_route(_Request()))

        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "text/plain")
        self.assertEqual(response.headers["Cache-Control"], "public, max-age=3600")
        self.assertIn("User-agent: *", response.text)
        self.assertIn("User-agent: OAI-SearchBot", response.text)
        self.assertIn("User-agent: GPTBot", response.text)
        self.assertIn("Disallow: /", response.text)

    def test_admin_api_registers_expected_routes(self):
        app = web.Application()

        admin_api.setup_admin_routes(app)

        routes = _route_map(app)
        expected = {
            ("GET", "/api/admin/me"): "admin_me_route",
            ("GET", "/api/admin/stats"): "admin_stats_route",
            ("GET", "/api/admin/users"): "admin_users_list_route",
            ("GET", "/api/admin/users/{user_id}"): "admin_user_detail_route",
            ("GET", "/api/admin/users/{user_id}/referrals"): "admin_user_referrals_route",
            ("GET", "/api/admin/users/{user_id}/avatar"): "admin_user_avatar_route",
            ("POST", "/api/admin/users/{user_id}/ban"): "admin_user_ban_route",
            ("POST", "/api/admin/users/{user_id}/message"): "admin_user_message_route",
            (
                "POST",
                "/api/admin/users/{user_id}/message/preview",
            ): "admin_user_message_preview_route",
            ("POST", "/api/admin/users/{user_id}/reset-trial"): "admin_user_reset_trial_route",
            ("POST", "/api/admin/users/{user_id}/extend"): "admin_user_extend_route",
            (
                "POST",
                "/api/admin/users/{user_id}/premium-override",
            ): "admin_user_premium_override_route",
            (
                "POST",
                "/api/admin/users/{user_id}/regular-traffic-override",
            ): "admin_user_regular_traffic_override_route",
            ("POST", "/api/admin/users/{user_id}/traffic-grant"): "admin_user_traffic_grant_route",
            ("DELETE", "/api/admin/users/{user_id}"): "admin_user_delete_route",
            ("GET", "/api/admin/payments"): "admin_payments_list_route",
            ("GET", "/api/admin/payments/export.csv"): "admin_payments_export_route",
            ("GET", "/api/admin/promos"): "admin_promos_list_route",
            ("POST", "/api/admin/promos"): "admin_promo_create_route",
            ("PATCH", "/api/admin/promos/{promo_id}"): "admin_promo_update_route",
            ("DELETE", "/api/admin/promos/{promo_id}"): "admin_promo_delete_route",
            ("GET", "/api/admin/logs"): "admin_logs_route",
            ("POST", "/api/admin/broadcast"): "admin_broadcast_route",
            ("POST", "/api/admin/sync"): "admin_sync_route",
            ("GET", "/api/admin/ads"): "admin_ads_list_route",
            ("POST", "/api/admin/ads"): "admin_ad_create_route",
            ("POST", "/api/admin/ads/{campaign_id}/toggle"): "admin_ad_toggle_route",
            ("DELETE", "/api/admin/ads/{campaign_id}"): "admin_ad_delete_route",
            ("GET", "/api/admin/settings"): "admin_settings_get_route",
            ("PATCH", "/api/admin/settings"): "admin_settings_patch_route",
            ("GET", "/api/admin/translations"): "admin_translations_get_route",
            ("PATCH", "/api/admin/translations"): "admin_translations_patch_route",
            ("GET", "/api/admin/tariffs"): "admin_tariffs_get_route",
            ("PUT", "/api/admin/tariffs"): "admin_tariffs_save_route",
            ("GET", "/api/admin/themes"): "admin_themes_get_route",
            ("PUT", "/api/admin/themes"): "admin_themes_save_route",
            ("POST", "/api/admin/appearance/logo"): "admin_appearance_logo_upload_route",
            ("POST", "/api/admin/appearance/favicon"): "admin_appearance_favicon_upload_route",
            ("GET", "/api/admin/backups"): "admin_backups_list_route",
            ("POST", "/api/admin/backups/create"): "admin_backups_create_route",
            ("POST", "/api/admin/backups/upload"): "admin_backups_upload_route",
            ("POST", "/api/admin/backups/restore"): "admin_backups_restore_route",
            ("GET", "/api/admin/panel/internal-squads"): "admin_panel_internal_squads_route",
        }

        for key, handler_name in expected.items():
            self.assertEqual(routes.get(key), handler_name, key)

    def test_admin_themes_page_route_is_not_registered(self):
        app = web.Application()
        subscription_webapp.setup_subscription_webapp_routes(app)

        request = make_mocked_request("GET", "/admin/themes", app=app)
        match_info = asyncio.run(app.router.resolve(request))

        self.assertEqual(match_info.http_exception.status, 404)

    def test_admin_appearance_page_route_is_registered(self):
        app = web.Application()
        subscription_webapp.setup_subscription_webapp_routes(app)

        request = make_mocked_request("GET", "/admin/appearance", app=app)
        match_info = asyncio.run(app.router.resolve(request))

        self.assertEqual(match_info.handler.__name__, "index_route")

    def test_admin_translations_page_route_is_registered(self):
        app = web.Application()
        subscription_webapp.setup_subscription_webapp_routes(app)

        request = make_mocked_request("GET", "/admin/translations", app=app)
        match_info = asyncio.run(app.router.resolve(request))

        self.assertEqual(match_info.handler.__name__, "index_route")

    def test_admin_backups_page_route_is_registered(self):
        app = web.Application()
        subscription_webapp.setup_subscription_webapp_routes(app)

        request = make_mocked_request("GET", "/admin/backups", app=app)
        match_info = asyncio.run(app.router.resolve(request))

        self.assertEqual(match_info.handler.__name__, "index_route")

    def test_webapp_favicon_asset_route_is_registered(self):
        app = web.Application()
        subscription_webapp.setup_subscription_webapp_routes(app)

        request = make_mocked_request(
            "GET",
            "/webapp-favicon/abcdef1234567890/icon-180.png",
            app=app,
        )
        match_info = asyncio.run(app.router.resolve(request))

        self.assertEqual(match_info.handler.__name__, "webapp_favicon_route")

    def test_webapp_root_icon_alias_routes_are_registered(self):
        app = web.Application()
        subscription_webapp.setup_subscription_webapp_routes(app)

        for path in (
            "/favicon.ico",
            "/apple-touch-icon.png",
            "/apple-touch-icon-precomposed.png",
            "/icon-192.png",
            "/icon-512.png",
        ):
            request = make_mocked_request("GET", path, app=app)
            match_info = asyncio.run(app.router.resolve(request))

            self.assertEqual(match_info.handler.__name__, "webapp_current_favicon_route")

    def test_app_deeplink_gateway_keeps_target_in_fragment(self):
        request = _Request(
            app={
                "settings": SimpleNamespace(
                    WEBAPP_ENABLED=True,
                    WEBAPP_TITLE="/minishop",
                    DEFAULT_LANGUAGE="en",
                )
            }
        )
        request["csp_nonce"] = "nonce-value"

        response = asyncio.run(subscription_webapp.app_deeplink_route(request))

        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn('nonce="nonce-value"', response.text)
        self.assertNotIn("__MESSAGES_JSON__", response.text)
        self.assertIn("window.location.hash", response.text)
        self.assertIn("URLSearchParams", response.text)
        self.assertIn("Settings added", response.text)
        self.assertIn("window.close()", response.text)
        self.assertNotIn('window.addEventListener("blur", notePageLeft)', response.text)
        self.assertNotIn("window.setTimeout(tryCloseWindow, 120)", response.text)
        self.assertIn("const CLOSE_ATTEMPT_DELAY_MS = 2500", response.text)
        self.assertIn("if (pageLeft || document.hidden) tryCloseWindow();", response.text)
        self.assertIn(r"/^(?:javascript|data|vbscript|https?):/i", response.text)

    def test_app_deeplink_gateway_uses_i18n_template(self):
        request = _Request(
            app={
                "settings": SimpleNamespace(
                    WEBAPP_ENABLED=True,
                    WEBAPP_TITLE="/minishop",
                    DEFAULT_LANGUAGE="en",
                ),
                "i18n": _I18n(),
            }
        )
        request["csp_nonce"] = "nonce-value"

        response = asyncio.run(subscription_webapp.app_deeplink_route(request))

        self.assertEqual(response.status, 200)
        self.assertIn("Localized launch", response.text)
        self.assertIn("Localized done hint", response.text)
        self.assertIn("<title>/minishop - Localized launch</title>", response.text)
        self.assertTrue(
            (REPO_ROOT / "backend/bot/app/web/templates/open_app_gateway.html").is_file()
        )

    def test_app_launch_i18n_keys_are_available_to_webapp_bootstrap(self):
        required_keys = {
            "wa_app_launch_title",
            "wa_app_launch_opening_hint",
            "wa_app_launch_hint",
            "wa_app_launch_button",
            "wa_app_launch_retry_button",
            "wa_app_launch_done_title",
            "wa_app_launch_done_hint",
            "wa_app_launch_close_button",
            "wa_app_launch_unavailable_title",
            "wa_app_launch_unavailable_hint",
        }
        for locale in ("en", "ru"):
            messages = json.loads((REPO_ROOT / f"locales/{locale}.json").read_text("utf-8"))
            self.assertLessEqual(required_keys, set(messages))


class AdminApiAuthContractTests(unittest.IsolatedAsyncioTestCase):
    def _settings(self):
        return SimpleNamespace(
            ADMIN_IDS=[999],
            WEBAPP_SESSION_SECRET="session-secret",
            WEBAPP_SESSION_TTL_SECONDS=3600,
        )

    async def test_admin_auth_middleware_resolves_telegram_id_from_webapp_session(self):
        settings = self._settings()
        token = create_webapp_session_token(settings, 42)
        request = _Request(
            path="/api/admin/me",
            app={
                "settings": settings,
                "async_session_factory": _AsyncSessionFactory(),
            },
            headers={},
            cookies={"rw_webapp_session": token},
        )
        handler = AsyncMock(return_value=web.json_response({"ok": True}))
        db_user = SimpleNamespace(user_id=42, telegram_id=999)

        with patch.object(
            admin_auth_routes.user_dal,
            "get_user_by_id",
            AsyncMock(return_value=db_user),
        ):
            response = await admin_api.admin_auth_middleware(request, handler)

        self.assertEqual(response.status, 200)
        self.assertEqual(request["admin_telegram_id"], 999)
        handler.assert_awaited_once_with(request)

    async def test_admin_route_rejects_authenticated_non_admin(self):
        settings = self._settings()
        token = create_webapp_session_token(settings, 42)
        request = _Request(
            path="/api/admin/me",
            app={"settings": settings},
            headers={},
            cookies={"rw_webapp_session": token},
        )
        request["admin_telegram_id"] = 123

        with self.assertRaises(web.HTTPForbidden) as raised:
            await admin_api.admin_me_route(request)

        self.assertEqual(raised.exception.status, 403)
