import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.services import config_health_service as health


def _settings(**overrides):
    base = {
        "BACKUP_DIR": "data/backups",
        "TARIFFS_CONFIG_PATH": "data/tariffs.json",
        "SUBSCRIPTION_MINI_APP_URL": "https://shop.example.com/app",
        "REDIS_URL": "redis://redis:6379/0",
        "SMTP_USERNAME": None,
        "SMTP_PASSWORD": None,
        "SMTP_FROM_EMAIL": None,
        "email_auth_configured": False,
        "WEBHOOK_BASE_URL": "https://shop.example.com",
        "telegram_webhook_path": "/tg/webhook",
        "PANEL_API_URL": "https://panel.example.com/api",
        "PANEL_API_KEY": "panel-key",
        "trusted_proxies": ["127.0.0.1", "172.16.0.0/12"],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _alert_ids(alerts):
    return [alert.id for alert in alerts]


class DataDirAlertsTests(unittest.TestCase):
    def test_missing_data_dir_reported_as_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            alerts = health.data_dir_alerts(_settings(), app_root=Path(tmpdir))

        self.assertEqual(_alert_ids(alerts), ["data_dir_missing"])
        self.assertEqual(alerts[0].severity, "error")
        self.assertIn("backups", alerts[0].sections)

    def test_writable_data_dir_produces_no_alerts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "data").mkdir()
            alerts = health.data_dir_alerts(_settings(), app_root=Path(tmpdir))

        self.assertEqual(alerts, [])

    def test_unwritable_data_dir_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "data").mkdir()
            with patch.object(health, "_dir_is_writable", return_value=False):
                alerts = health.data_dir_alerts(_settings(), app_root=Path(tmpdir))

        self.assertIn("data_dir_not_writable", _alert_ids(alerts))


class ConfigFileAlertsTests(unittest.TestCase):
    def test_invalid_tariffs_config_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tariffs_path = Path(tmpdir) / "tariffs.json"
            tariffs_path.write_text("{not json", encoding="utf-8")
            settings = _settings(TARIFFS_CONFIG_PATH=str(tariffs_path))
            with patch.object(health, "APP_ROOT", Path(tmpdir)):
                alerts = health.config_file_alerts(settings)

        self.assertIn("tariffs_config_invalid", _alert_ids(alerts))

    def test_invalid_locale_overrides_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            (data_dir / "locales-overrides.json").write_text("{oops", encoding="utf-8")
            settings = _settings(TARIFFS_CONFIG_PATH=str(Path(tmpdir) / "absent.json"))
            with patch.object(health, "APP_ROOT", Path(tmpdir)):
                alerts = health.config_file_alerts(settings)

        self.assertIn("locale_overrides_invalid", _alert_ids(alerts))

    def test_valid_files_produce_no_alerts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            (data_dir / "locales-overrides.json").write_text("{}", encoding="utf-8")
            settings = _settings(TARIFFS_CONFIG_PATH=str(Path(tmpdir) / "absent.json"))
            with patch.object(health, "APP_ROOT", Path(tmpdir)):
                alerts = health.config_file_alerts(settings)

        self.assertNotIn("tariffs_config_invalid", _alert_ids(alerts))
        self.assertNotIn("locale_overrides_invalid", _alert_ids(alerts))


class PaymentProviderAlertsTests(unittest.TestCase):
    @staticmethod
    def _spec(
        spec_id,
        *,
        enabled=True,
        configured=True,
        webhook_requires_base_url=False,
        service_key=None,
    ):
        return SimpleNamespace(
            id=spec_id,
            label=spec_id.title(),
            service_key=service_key or f"{spec_id}_service",
            webhook_requires_base_url=webhook_requires_base_url,
            is_effectively_enabled=lambda settings: enabled,
            is_service_configured=lambda app: configured,
        )

    def test_enabled_but_unconfigured_provider_reported(self):
        specs = [self._spec("wata", configured=False)]
        with patch("bot.payment_providers.iter_provider_specs", return_value=specs):
            alerts = health.payment_provider_alerts(_settings(), app={})

        self.assertEqual(_alert_ids(alerts), ["provider_not_configured:wata"])
        self.assertEqual(alerts[0].message_key, "provider_not_configured")
        self.assertEqual(alerts[0].params["provider"], "Wata")

    def test_webhook_provider_without_base_url_reported(self):
        specs = [self._spec("yookassa", webhook_requires_base_url=True)]
        settings = _settings(WEBHOOK_BASE_URL=None)
        with patch("bot.payment_providers.iter_provider_specs", return_value=specs):
            alerts = health.payment_provider_alerts(settings, app={})

        self.assertIn("provider_webhook_needs_base_url:yookassa", _alert_ids(alerts))

    def test_no_enabled_providers_reported_as_warning(self):
        specs = [self._spec("wata", enabled=False)]
        with patch("bot.payment_providers.iter_provider_specs", return_value=specs):
            alerts = health.payment_provider_alerts(_settings(), app={})

        self.assertEqual(_alert_ids(alerts), ["no_payment_methods"])
        self.assertEqual(alerts[0].severity, "warning")

    def test_configured_enabled_provider_produces_no_alerts(self):
        specs = [self._spec("wata")]
        with patch("bot.payment_providers.iter_provider_specs", return_value=specs):
            alerts = health.payment_provider_alerts(_settings(), app={})

        self.assertEqual(alerts, [])

    def test_shared_service_reported_once(self):
        specs = [
            self._spec("platega", configured=False, service_key="platega_service"),
            self._spec("platega_crypto", configured=False, service_key="platega_service"),
        ]
        with patch("bot.payment_providers.iter_provider_specs", return_value=specs):
            alerts = health.payment_provider_alerts(_settings(), app={})

        self.assertEqual(_alert_ids(alerts), ["provider_not_configured:platega"])


class SettingsAlertsTests(unittest.TestCase):
    def test_clean_settings_produce_no_alerts(self):
        self.assertEqual(health.settings_alerts(_settings()), [])

    def test_missing_mini_app_url_reported(self):
        alerts = health.settings_alerts(_settings(SUBSCRIPTION_MINI_APP_URL=None))
        self.assertIn("mini_app_url_missing", _alert_ids(alerts))

    def test_http_mini_app_url_reported_as_error(self):
        alerts = health.settings_alerts(
            _settings(SUBSCRIPTION_MINI_APP_URL="http://shop.example.com")
        )
        ids = _alert_ids(alerts)
        self.assertIn("mini_app_url_not_https", ids)
        self.assertEqual(alerts[ids.index("mini_app_url_not_https")].severity, "error")

    def test_missing_redis_reported(self):
        alerts = health.settings_alerts(_settings(REDIS_URL=None))
        self.assertIn("redis_not_configured", _alert_ids(alerts))

    def test_partial_smtp_reported(self):
        alerts = health.settings_alerts(_settings(SMTP_USERNAME="mailer"))
        self.assertIn("smtp_incomplete", _alert_ids(alerts))

    def test_complete_smtp_not_reported(self):
        alerts = health.settings_alerts(
            _settings(SMTP_USERNAME="mailer", email_auth_configured=True)
        )
        self.assertNotIn("smtp_incomplete", _alert_ids(alerts))


class ProxyAlertsTests(unittest.TestCase):
    def test_untrusted_proxy_reported(self):
        request = SimpleNamespace(
            remote="203.0.113.50",
            headers={"X-Forwarded-For": "198.51.100.7"},
        )
        alerts = health.proxy_alerts(request, _settings())
        self.assertEqual(_alert_ids(alerts), ["proxy_not_trusted"])

    def test_trusted_proxy_not_reported(self):
        request = SimpleNamespace(
            remote="172.18.0.5",
            headers={"X-Forwarded-For": "198.51.100.7"},
        )
        self.assertEqual(health.proxy_alerts(request, _settings()), [])

    def test_direct_request_not_reported(self):
        request = SimpleNamespace(remote="203.0.113.50", headers={})
        self.assertEqual(health.proxy_alerts(request, _settings()), [])


class TelegramAlertsTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _webhook_info(**overrides):
        base = {
            "url": "https://shop.example.com/tg/webhook",
            "last_error_date": None,
            "last_error_message": None,
            "pending_update_count": 0,
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    async def test_healthy_webhook_produces_no_alerts(self):
        bot = SimpleNamespace(get_webhook_info=AsyncMock(return_value=self._webhook_info()))
        self.assertEqual(await health.telegram_alerts(bot, _settings()), [])

    async def test_missing_webhook_reported_as_error(self):
        bot = SimpleNamespace(get_webhook_info=AsyncMock(return_value=self._webhook_info(url="")))
        alerts = await health.telegram_alerts(bot, _settings())
        self.assertEqual(_alert_ids(alerts), ["telegram_webhook_missing"])
        self.assertEqual(alerts[0].severity, "error")

    async def test_webhook_mismatch_reported(self):
        bot = SimpleNamespace(
            get_webhook_info=AsyncMock(
                return_value=self._webhook_info(url="https://other.example.com/tg/webhook")
            )
        )
        alerts = await health.telegram_alerts(bot, _settings())
        self.assertEqual(_alert_ids(alerts), ["telegram_webhook_mismatch"])

    async def test_recent_delivery_error_with_pending_update_reported(self):
        info = self._webhook_info(
            last_error_date=datetime.now(timezone.utc),
            last_error_message="SSL error",
            pending_update_count=1,
        )
        bot = SimpleNamespace(get_webhook_info=AsyncMock(return_value=info))
        alerts = await health.telegram_alerts(bot, _settings())
        self.assertEqual(_alert_ids(alerts), ["telegram_webhook_error"])
        self.assertEqual(alerts[0].params["error"], "SSL error")

    async def test_recent_delivery_error_without_pending_update_not_reported(self):
        info = self._webhook_info(
            last_error_date=datetime.now(timezone.utc),
            last_error_message="Connection refused",
            pending_update_count=0,
        )
        bot = SimpleNamespace(get_webhook_info=AsyncMock(return_value=info))
        self.assertEqual(await health.telegram_alerts(bot, _settings()), [])

    async def test_stale_delivery_error_not_reported(self):
        info = self._webhook_info(last_error_date=time.time() - 7200)
        bot = SimpleNamespace(get_webhook_info=AsyncMock(return_value=info))
        self.assertEqual(await health.telegram_alerts(bot, _settings()), [])

    async def test_pending_updates_reported(self):
        info = self._webhook_info(pending_update_count=500)
        bot = SimpleNamespace(get_webhook_info=AsyncMock(return_value=info))
        alerts = await health.telegram_alerts(bot, _settings())
        self.assertEqual(_alert_ids(alerts), ["telegram_webhook_pending"])

    async def test_unauthorized_token_reported_as_error(self):
        class TelegramUnauthorizedError(Exception):
            pass

        bot = SimpleNamespace(
            get_webhook_info=AsyncMock(side_effect=TelegramUnauthorizedError("401"))
        )
        alerts = await health.telegram_alerts(bot, _settings())
        self.assertEqual(_alert_ids(alerts), ["bot_token_invalid"])

    async def test_generic_api_error_reported_as_warning(self):
        bot = SimpleNamespace(get_webhook_info=AsyncMock(side_effect=OSError("boom")))
        alerts = await health.telegram_alerts(bot, _settings())
        self.assertEqual(_alert_ids(alerts), ["telegram_api_error"])
        self.assertEqual(alerts[0].severity, "warning")


class PanelAlertsTests(unittest.IsolatedAsyncioTestCase):
    async def test_unconfigured_panel_reported(self):
        settings = _settings(PANEL_API_URL=None, PANEL_API_KEY=None)
        alerts = await health.panel_alerts(None, settings)
        self.assertEqual(_alert_ids(alerts), ["panel_api_not_configured"])

    async def test_unreachable_panel_reported(self):
        panel_service = SimpleNamespace(get_system_stats=AsyncMock(return_value=None))
        alerts = await health.panel_alerts(panel_service, _settings())
        self.assertEqual(_alert_ids(alerts), ["panel_api_unreachable"])

    async def test_healthy_panel_produces_no_alerts(self):
        panel_service = SimpleNamespace(get_system_stats=AsyncMock(return_value={"cpu": 1}))
        self.assertEqual(await health.panel_alerts(panel_service, _settings()), [])


class CollectAlertsTests(unittest.IsolatedAsyncioTestCase):
    async def test_collect_sorts_errors_first_and_serializes(self):
        settings = _settings()
        request = SimpleNamespace(app={"settings": settings}, headers={}, remote="127.0.0.1")
        warning = health.ConfigAlert(id="warn_alert", severity="warning", sections=("settings",))
        error = health.ConfigAlert(id="error_alert", severity="error", sections=("backups",))

        with (
            patch.object(health, "local_alerts", return_value=[warning, error]),
            patch.object(health, "network_alerts", AsyncMock(return_value=[])),
        ):
            payload = await health.collect_config_alerts(request)

        self.assertEqual([item["id"] for item in payload], ["error_alert", "warn_alert"])
        self.assertEqual(payload[0]["message_key"], "error_alert")
        self.assertEqual(payload[0]["sections"], ["backups"])

    async def test_network_alerts_cached_between_calls(self):
        settings = _settings()
        app = {"settings": settings, "bot": None, "panel_service": None}
        health._network_cache.clear()

        with patch.object(health, "panel_alerts", AsyncMock(return_value=[])) as panel_mock:
            await health.network_alerts(app, settings)
            await health.network_alerts(app, settings)
            self.assertEqual(panel_mock.await_count, 1)
            await health.network_alerts(app, settings, refresh=True)
            self.assertEqual(panel_mock.await_count, 2)
        health._network_cache.clear()


class HealthLocaleKeysTests(unittest.TestCase):
    def test_every_message_key_has_locale_entries(self):
        root = Path(__file__).resolve().parents[2]
        for language in ("ru", "en"):
            messages = json.loads(
                (root / "locales" / f"{language}.json").read_text(encoding="utf-8")
            )
            for suffix in ("title", "refresh", *health.ALL_MESSAGE_KEYS):
                self.assertIn(
                    f"admin_health_{suffix}",
                    messages,
                    f"locales/{language}.json is missing admin_health_{suffix}",
                )

    def test_alert_ids_used_by_checks_are_known_message_keys(self):
        known = set(health.ALL_MESSAGE_KEYS)
        with tempfile.TemporaryDirectory() as tmpdir:
            local = health.data_dir_alerts(_settings(), app_root=Path(tmpdir))
        local += health.settings_alerts(_settings(SUBSCRIPTION_MINI_APP_URL=None, REDIS_URL=None))
        for alert in local:
            self.assertIn(alert.message_key or alert.id, known)


if __name__ == "__main__":
    unittest.main()
