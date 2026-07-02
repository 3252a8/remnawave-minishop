import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp import billing as billing_module
from bot.app.web.webapp import billing_subscription
from tests.support.settings_stub import settings_stub


class _Session:
    def __init__(self):
        self.commit_count = 0
        self.rollback_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


class _SessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self.session


class WebAppTrialActivationTests(IsolatedAsyncioTestCase):
    async def test_email_only_trial_activation_is_written_to_admin_logs(self):
        session = _Session()
        end_date = datetime(2026, 1, 9, 3, 4, tzinfo=UTC)
        settings = settings_stub(
            TRIAL_ENABLED=True,
            TRIAL_DURATION_DAYS=7,
            TRIAL_TRAFFIC_LIMIT_GB=10,
            LOG_TRIAL_ACTIVATIONS=False,
        )
        db_user = SimpleNamespace(
            user_id=42,
            is_banned=False,
            username=None,
            first_name=None,
            email="email-only@example.com",
        )
        subscription_service = SimpleNamespace(
            activate_trial_subscription=AsyncMock(
                return_value={
                    "activated": True,
                    "days": 7,
                    "end_date": end_date,
                    "traffic_gb": 10,
                    "subscription_url": "https://panel.example/sub",
                }
            )
        )
        request = SimpleNamespace(
            app={
                "settings": settings,
                "async_session_factory": _SessionFactory(session),
                "subscription_service": subscription_service,
            }
        )

        with (
            patch.object(billing_subscription, "_require_user_id", return_value=42),
            patch.object(
                billing_subscription,
                "_enforce_webapp_rate_limit",
                AsyncMock(return_value=None),
            ),
            patch.object(
                billing_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=db_user),
            ),
            patch.object(
                billing_subscription,
                "prepare_config_links",
                AsyncMock(return_value=("https://panel.example/sub", "https://connect.example")),
            ),
            patch.object(
                billing_module.message_log_dal,
                "create_message_log_no_commit",
                AsyncMock(),
            ) as create_log,
            patch("db.dal.ad_dal.mark_trial_activated", AsyncMock()) as mark_trial_activated,
        ):
            response = await billing_module.activate_trial_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["activated"])
        subscription_service.activate_trial_subscription.assert_awaited_once_with(session, 42)
        create_log.assert_awaited_once()
        log_payload = create_log.await_args.args[1]
        self.assertEqual(log_payload["user_id"], 42)
        self.assertEqual(log_payload["target_user_id"], 42)
        self.assertEqual(log_payload["event_type"], "webapp_trial_activate")
        self.assertFalse(log_payload["is_admin_event"])
        self.assertIn("email-only@example.com", log_payload["content"])
        mark_trial_activated.assert_awaited_once_with(session, 42)
        self.assertEqual(session.commit_count, 2)
        self.assertEqual(session.rollback_count, 0)

    async def test_email_only_trial_activation_requires_telegram_when_disabled(self):
        session = _Session()
        settings = settings_stub(
            TRIAL_ENABLED=True,
            TRIAL_DURATION_DAYS=7,
            TRIAL_TRAFFIC_LIMIT_GB=10,
            TRIAL_WITHOUT_TELEGRAM_ENABLED=False,
            DISPOSABLE_EMAIL_DOMAINS="",
            LOG_TRIAL_ACTIVATIONS=False,
        )
        db_user = SimpleNamespace(
            user_id=42,
            telegram_id=None,
            is_banned=False,
            email="email-only@example.com",
        )
        subscription_service = SimpleNamespace(activate_trial_subscription=AsyncMock())
        request = SimpleNamespace(
            app={
                "settings": settings,
                "async_session_factory": _SessionFactory(session),
                "subscription_service": subscription_service,
            }
        )

        with (
            patch.object(billing_subscription, "_require_user_id", return_value=42),
            patch.object(
                billing_subscription,
                "_enforce_webapp_rate_limit",
                AsyncMock(return_value=None),
            ),
            patch.object(
                billing_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=db_user),
            ),
        ):
            response = await billing_module.activate_trial_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 400)
        self.assertEqual(payload["error"], "trial_telegram_required")
        self.assertEqual(payload["message"], "telegram_required")
        subscription_service.activate_trial_subscription.assert_not_awaited()

    async def test_disposable_email_trial_activation_requires_telegram(self):
        session = _Session()
        settings = settings_stub(
            TRIAL_ENABLED=True,
            TRIAL_DURATION_DAYS=7,
            TRIAL_TRAFFIC_LIMIT_GB=10,
            TRIAL_WITHOUT_TELEGRAM_ENABLED=True,
            DISPOSABLE_EMAIL_DOMAINS="mailinator.com,temp-mail.org",
            LOG_TRIAL_ACTIVATIONS=False,
        )
        db_user = SimpleNamespace(
            user_id=42,
            telegram_id=None,
            is_banned=False,
            email="person@mailinator.com",
        )
        subscription_service = SimpleNamespace(activate_trial_subscription=AsyncMock())
        request = SimpleNamespace(
            app={
                "settings": settings,
                "async_session_factory": _SessionFactory(session),
                "subscription_service": subscription_service,
            }
        )

        with (
            patch.object(billing_subscription, "_require_user_id", return_value=42),
            patch.object(
                billing_subscription,
                "_enforce_webapp_rate_limit",
                AsyncMock(return_value=None),
            ),
            patch.object(
                billing_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=db_user),
            ),
        ):
            response = await billing_module.activate_trial_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 400)
        self.assertEqual(payload["error"], "trial_telegram_required")
        self.assertEqual(payload["message"], "disposable_email")
        subscription_service.activate_trial_subscription.assert_not_awaited()

    async def test_trial_activation_failure_returns_localized_panel_hint(self):
        session = _Session()
        settings = settings_stub(
            DEFAULT_LANGUAGE="ru",
            TRIAL_ENABLED=True,
            TRIAL_DURATION_DAYS=7,
            TRIAL_TRAFFIC_LIMIT_GB=10,
            TRIAL_WITHOUT_TELEGRAM_ENABLED=True,
            DISPOSABLE_EMAIL_DOMAINS="",
            LOG_TRIAL_ACTIVATIONS=False,
        )
        db_user = SimpleNamespace(
            user_id=42,
            telegram_id=None,
            is_banned=False,
            email="email-only@example.com",
            language_code="ru",
        )
        subscription_service = SimpleNamespace(
            activate_trial_subscription=AsyncMock(
                return_value={
                    "activated": False,
                    "message_key": "trial_activation_failed_panel_link",
                }
            )
        )
        i18n = SimpleNamespace(
            gettext=lambda lang, key: (
                "<b>Не удалось активировать пробный период.</b>\n"
                "Проверьте PANEL_API_URL и PANEL_API_KEY."
                if lang == "ru" and key == "trial_activation_failed_panel_link"
                else key
            )
        )
        request = SimpleNamespace(
            app={
                "settings": settings,
                "async_session_factory": _SessionFactory(session),
                "subscription_service": subscription_service,
                "i18n": i18n,
            }
        )

        with (
            patch.object(billing_subscription, "_require_user_id", return_value=42),
            patch.object(
                billing_subscription,
                "_enforce_webapp_rate_limit",
                AsyncMock(return_value=None),
            ),
            patch.object(
                billing_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=db_user),
            ),
        ):
            response = await billing_module.activate_trial_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 502)
        self.assertEqual(payload["error"], "trial_activation_failed_panel_link")
        self.assertEqual(
            payload["message"],
            "Не удалось активировать пробный период.\nПроверьте PANEL_API_URL и PANEL_API_KEY.",
        )
        subscription_service.activate_trial_subscription.assert_awaited_once_with(session, 42)
        self.assertEqual(session.rollback_count, 1)
