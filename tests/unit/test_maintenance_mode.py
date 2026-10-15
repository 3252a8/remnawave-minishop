import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import Update
from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from sqlalchemy.orm import sessionmaker

from bot.app.controllers.dispatcher_controller import build_dispatcher
from bot.app.web.admin_settings_manifest import coerce_value, get_field_by_key
from bot.app.web.context import SETTINGS
from bot.app.web.webapp.maintenance import maintenance_middleware
from bot.middlewares.db_session import DBSessionMiddleware
from bot.middlewares.i18n import JsonI18n
from bot.middlewares.maintenance import MaintenanceMiddleware
from bot.middlewares.telegram_menu_settings import TelegramMenuSettingsMiddleware
from bot.middlewares.update_antiflood import UpdateAntiFloodMiddleware
from bot.services.settings_override_service import apply_overrides
from config.settings import Settings
from tests.support.settings_stub import settings_stub

_ROOT = Path(__file__).resolve().parents[2]


def _session_factory() -> tuple[sessionmaker, AsyncMock]:
    session = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    return cast(sessionmaker, MagicMock(return_value=context)), session


def _update(kind: str = "message", *, payment: str | None = None) -> Update:
    actor = SimpleNamespace(id=42, language_code="en")
    chat = SimpleNamespace(type="private")
    message = SimpleNamespace(
        from_user=actor,
        chat=chat,
        successful_payment=object() if payment == "successful" else None,
        refunded_payment=object() if payment == "refunded" else None,
        answer=AsyncMock(),
    )
    callback = SimpleNamespace(from_user=actor, message=message, answer=AsyncMock())
    inline = SimpleNamespace(from_user=actor, answer=AsyncMock())
    return cast(
        Update,
        SimpleNamespace(
            message=message if kind == "message" else None,
            edited_message=message if kind == "edited_message" else None,
            callback_query=callback if kind == "callback" else None,
            inline_query=inline if kind == "inline" else None,
        ),
    )


class TelegramMaintenanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = settings_stub(MAINTENANCE_MODE_ENABLED=True)
        self.factory, self.session = _session_factory()
        self.i18n = JsonI18n(str(_ROOT / "locales"), default="ru")
        self.middleware = MaintenanceMiddleware(self.settings, self.factory, self.i18n)
        self.handler = AsyncMock(return_value="handled")

    async def test_message_uses_stored_language_without_running_user_actions(self):
        update = _update()
        user = SimpleNamespace(user_id=7, language_code="ru", is_banned=False)
        with (
            patch(
                "bot.middlewares.maintenance.user_dal.get_user_by_telegram_id",
                AsyncMock(return_value=user),
            ),
            patch("bot.middlewares.maintenance.is_admin", AsyncMock(return_value=False)),
        ):
            data = {}
            self.assertIsNone(await self.middleware(self.handler, update, data))
        assert update.message is not None
        cast(AsyncMock, update.message.answer).assert_awaited_once_with(
            text=self.i18n.gettext("ru", "maintenance_mode_message")
        )
        self.handler.assert_not_awaited()
        self.assertTrue(data["skip_action_log"])

    async def test_new_user_gets_telegram_language_without_registration(self):
        update = _update()
        with patch(
            "bot.middlewares.maintenance.user_dal.get_user_by_telegram_id",
            AsyncMock(return_value=None),
        ):
            await self.middleware(self.handler, update, {})
        assert update.message is not None
        cast(AsyncMock, update.message.answer).assert_awaited_once_with(
            text=self.i18n.gettext("en", "maintenance_mode_message")
        )
        self.handler.assert_not_awaited()

    async def test_callback_is_answered_with_maintenance_alert(self):
        update = _update("callback")
        with patch(
            "bot.middlewares.maintenance.user_dal.get_user_by_telegram_id",
            AsyncMock(return_value=None),
        ):
            await self.middleware(self.handler, update, {})
        assert update.callback_query is not None
        cast(AsyncMock, update.callback_query.answer).assert_awaited_once_with(
            text=self.i18n.gettext("en", "maintenance_mode_message"), show_alert=True
        )
        self.handler.assert_not_awaited()

    async def test_inline_query_is_answered_without_running_profile_sync(self):
        update = _update("inline")
        with patch(
            "bot.middlewares.maintenance.user_dal.get_user_by_telegram_id",
            AsyncMock(return_value=None),
        ):
            await self.middleware(self.handler, update, {})
        assert update.inline_query is not None
        cast(AsyncMock, update.inline_query.answer).assert_awaited_once_with(
            results=[], cache_time=0, is_personal=True
        )
        self.handler.assert_not_awaited()

    async def test_group_messages_do_not_reach_panel_when_group_updates_are_enabled(self):
        update = _update()
        assert update.message is not None
        cast(SimpleNamespace, update.message.chat).type = "group"
        with patch(
            "bot.middlewares.maintenance.user_dal.get_user_by_telegram_id",
            AsyncMock(return_value=None),
        ):
            await self.middleware(self.handler, update, {})
        self.handler.assert_not_awaited()
        cast(AsyncMock, update.message.answer).assert_not_awaited()

    async def test_edited_message_is_blocked_before_profile_sync(self):
        update = _update("edited_message")
        with patch(
            "bot.middlewares.maintenance.user_dal.get_user_by_telegram_id",
            AsyncMock(return_value=None),
        ):
            await self.middleware(self.handler, update, {})
        self.handler.assert_not_awaited()
        assert update.edited_message is not None
        cast(AsyncMock, update.edited_message.answer).assert_awaited_once_with(
            text=self.i18n.gettext("en", "maintenance_mode_message")
        )

    async def test_admin_bypass_does_not_swallow_downstream_errors(self):
        user = SimpleNamespace(user_id=7, language_code="ru", is_banned=False)
        self.handler.side_effect = RuntimeError("downstream")
        with (
            patch(
                "bot.middlewares.maintenance.user_dal.get_user_by_telegram_id",
                AsyncMock(return_value=user),
            ),
            patch("bot.middlewares.maintenance.is_admin", AsyncMock(return_value=True)),
            self.assertRaisesRegex(RuntimeError, "downstream"),
        ):
            await self.middleware(self.handler, _update(), {})
        self.handler.assert_awaited_once()

    async def test_disabled_mode_passes_without_role_query(self):
        self.settings.MAINTENANCE_MODE_ENABLED = False
        self.assertEqual(await self.middleware(self.handler, _update(), {}), "handled")
        cast(MagicMock, self.factory).assert_not_called()

    async def test_payment_and_checkout_lifecycle_updates_are_not_dropped(self):
        for event in (
            _update(payment="successful"),
            _update(payment="refunded"),
            _update("checkout"),
        ):
            self.assertEqual(await self.middleware(self.handler, event, {}), "handled")
        self.assertEqual(self.handler.await_count, 3)
        cast(MagicMock, self.factory).assert_not_called()

    async def test_worker_refresh_includes_mode_before_maintenance_gate(self):
        dispatcher = build_dispatcher(
            self.settings, self.factory, bot=None, i18n_instance=self.i18n
        )
        middleware_types = [type(item) for item in dispatcher.update.outer_middleware]
        self.assertLess(
            middleware_types.index(UpdateAntiFloodMiddleware),
            middleware_types.index(TelegramMenuSettingsMiddleware),
        )
        self.assertLess(
            middleware_types.index(TelegramMenuSettingsMiddleware),
            middleware_types.index(MaintenanceMiddleware),
        )
        self.assertLess(
            middleware_types.index(MaintenanceMiddleware),
            middleware_types.index(DBSessionMiddleware),
        )
        with patch(
            "bot.middlewares.telegram_menu_settings.refresh_overrides_from_db", AsyncMock()
        ) as refresh:
            await TelegramMenuSettingsMiddleware(self.settings, self.factory)(
                self.handler, _update(), {}
            )
        self.assertIn("MAINTENANCE_MODE_ENABLED", refresh.await_args.kwargs["keys"])


class WebappMaintenanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = settings_stub(MAINTENANCE_MODE_ENABLED=True)
        self.app = web.Application()
        self.app[SETTINGS] = self.settings
        self.handler = AsyncMock(return_value=web.Response(text="handled"))

    def request(self, path="/api/me", method="GET"):
        return make_mocked_request(method, path, app=self.app)

    async def test_user_action_is_rejected_before_downstream_side_effects(self):
        with patch(
            "bot.app.web.webapp.maintenance.extract_authenticated_user_id", return_value=None
        ):
            response = await maintenance_middleware(
                self.request("/api/payments", "POST"), self.handler
            )
        self.assertEqual(response.status, 503)
        self.assertIsInstance(response, web.Response)
        self.assertEqual(
            json.loads(cast(web.Response, response).text or ""),
            {"ok": False, "error": "maintenance_mode"},
        )
        self.assertEqual(response.headers["Retry-After"], "60")
        self.handler.assert_not_awaited()

    async def test_authenticated_nonadmin_cannot_reach_me_or_device_actions(self):
        factory, _ = _session_factory()
        user = SimpleNamespace(is_banned=False)
        for path in ("/api/me", "/api/devices", "/api/subscription/quote"):
            with (
                patch(
                    "bot.app.web.webapp.maintenance.extract_authenticated_user_id", return_value=7
                ),
                patch("bot.app.web.webapp.maintenance.get_session_factory", return_value=factory),
                patch(
                    "bot.app.web.webapp.maintenance.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
                patch("bot.app.web.webapp.maintenance.is_admin", AsyncMock(return_value=False)),
            ):
                response = await maintenance_middleware(self.request(path), self.handler)
            self.assertEqual(response.status, 503)
        self.handler.assert_not_awaited()

    async def test_account_admin_can_use_user_actions(self):
        factory, _ = _session_factory()
        with (
            patch("bot.app.web.webapp.maintenance.extract_authenticated_user_id", return_value=7),
            patch("bot.app.web.webapp.maintenance.get_session_factory", return_value=factory),
            patch(
                "bot.app.web.webapp.maintenance.user_dal.get_user_by_id",
                AsyncMock(return_value=SimpleNamespace(is_banned=False)),
            ),
            patch("bot.app.web.webapp.maintenance.is_admin", AsyncMock(return_value=True)),
        ):
            response = await maintenance_middleware(self.request(), self.handler)
        self.assertEqual(response.status, 200)
        self.handler.assert_awaited_once()

    async def test_auth_assets_recovery_and_existing_payments_remain_available(self):
        for path, method in (
            ("/api/bootstrap", "GET"),
            ("/api/i18n", "GET"),
            ("/api/auth/session", "GET"),
            ("/api/auth/token", "POST"),
            ("/api/admin/settings", "PATCH"),
            ("/health", "GET"),
            ("/s/" + "a" * 32, "GET"),
            ("/api/payments/17", "GET"),
            ("/api/payments/17/cancel", "POST"),
        ):
            response = await maintenance_middleware(self.request(path, method), self.handler)
            self.assertEqual(response.status, 200)

    async def test_disabling_mode_resumes_user_actions_immediately(self):
        self.settings.MAINTENANCE_MODE_ENABLED = False
        response = await maintenance_middleware(self.request(), self.handler)
        self.assertEqual(response.status, 200)
        self.handler.assert_awaited_once()


class MaintenanceSettingsTests(unittest.TestCase):
    def test_setting_defaults_off_and_supports_runtime_override(self):
        self.assertFalse(Settings.model_fields["MAINTENANCE_MODE_ENABLED"].default)
        field = get_field_by_key("MAINTENANCE_MODE_ENABLED")
        assert field is not None
        self.assertEqual((field.type, field.section), ("bool", "general"))
        self.assertTrue(coerce_value(field, True))
        settings = settings_stub()
        self.assertEqual(apply_overrides(settings, {"MAINTENANCE_MODE_ENABLED": True}), 1)
        self.assertTrue(settings.MAINTENANCE_MODE_ENABLED)
        self.assertEqual(apply_overrides(settings, {"MAINTENANCE_MODE_ENABLED": False}), 1)
        self.assertFalse(settings.MAINTENANCE_MODE_ENABLED)
