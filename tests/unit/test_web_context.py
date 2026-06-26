import asyncio
import unittest

from aiohttp import web

from bot.app.web.context import (
    EMAIL_AUTH_SERVICE,
    SUBSCRIPTION_GUIDES_CONFIG_CACHE,
    SUBSCRIPTION_GUIDES_CONFIG_LOCK,
    SUBSCRIPTION_SERVICE,
    WEBAPP_LOGO_CACHE,
    WEBAPP_SETTINGS_CACHE,
    get_app_required_subscription_service,
    get_app_webapp_settings_cache,
    get_or_create_subscription_guides_config_cache,
    get_or_create_subscription_guides_config_lock,
    get_webapp_logo_cache,
    initialize_webapp_runtime_context,
    set_service_context,
    set_webapp_logo_cache,
)


class WebContextTests(unittest.TestCase):
    def test_webapp_runtime_context_sets_appkeys_and_compat_string_keys(self):
        app = web.Application()

        initialize_webapp_runtime_context(app)

        self.assertIs(app[WEBAPP_SETTINGS_CACHE], app["webapp_settings_cache"])
        self.assertIs(get_app_webapp_settings_cache(app), app["webapp_settings_cache"])
        self.assertIsNone(app[WEBAPP_LOGO_CACHE])
        self.assertIsNone(app["webapp_logo_cache"])
        self.assertIs(
            app[SUBSCRIPTION_GUIDES_CONFIG_CACHE],
            app["subscription_guides_config_cache"],
        )
        self.assertIsInstance(app[SUBSCRIPTION_GUIDES_CONFIG_LOCK], asyncio.Lock)
        self.assertIs(app[SUBSCRIPTION_GUIDES_CONFIG_LOCK], app["subscription_guides_config_lock"])

    def test_compat_string_cache_is_promoted_to_appkey_on_first_typed_access(self):
        app = web.Application()
        app["subscription_guides_config_cache"] = {"fingerprint": ("stale",), "status": None}
        app["subscription_guides_config_lock"] = asyncio.Lock()

        cache = get_or_create_subscription_guides_config_cache(app)
        lock = get_or_create_subscription_guides_config_lock(app)

        self.assertIs(cache, app["subscription_guides_config_cache"])
        self.assertIs(cache, app[SUBSCRIPTION_GUIDES_CONFIG_CACHE])
        self.assertIs(lock, app["subscription_guides_config_lock"])
        self.assertIs(lock, app[SUBSCRIPTION_GUIDES_CONFIG_LOCK])

    def test_setters_keep_appkey_and_compat_string_values_in_sync(self):
        app = web.Application()
        logo = ("https://cdn.example.test/logo.png", b"png", "image/png")

        set_webapp_logo_cache(app, logo)

        self.assertIs(app[WEBAPP_LOGO_CACHE], app["webapp_logo_cache"])
        self.assertEqual(get_webapp_logo_cache(app), logo)

    def test_service_context_sets_typed_service_keys(self):
        app = web.Application()
        subscription_service = object()
        email_service = object()

        set_service_context(app, "subscription_service", subscription_service)
        set_service_context(app, "email_auth_service", email_service)

        self.assertIs(app["subscription_service"], subscription_service)
        self.assertIs(app[SUBSCRIPTION_SERVICE], subscription_service)
        self.assertIs(get_app_required_subscription_service(app), subscription_service)
        self.assertIs(app["email_auth_service"], email_service)
        self.assertIs(app[EMAIL_AUTH_SERVICE], email_service)


if __name__ == "__main__":
    unittest.main()
