import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import ANY, AsyncMock, patch

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp import billing as billing_module
from bot.app.web.webapp import billing_subscription
from bot.app.web.webapp.auth_common import (
    _referral_welcome_telegram_required_reason,
    _trial_oauth_required_reason,
    _trial_oauth_required_reason_for_user,
)
from config.settings_defaults import DEFAULT_DISPOSABLE_EMAIL_DOMAINS
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
    async def test_paid_trial_rejects_direct_free_activation(self):
        settings = settings_stub(
            TRIAL_ENABLED=True,
            TRIAL_DURATION_DAYS=7,
            TRIAL_PAYMENT_ENABLED=True,
        )
        subscription_service = SimpleNamespace(activate_trial_subscription=AsyncMock())
        request = SimpleNamespace(
            app={
                "settings": settings,
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
        ):
            response = await billing_module.activate_trial_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 402)
        self.assertEqual(payload["error"], "trial_payment_required")
        subscription_service.activate_trial_subscription.assert_not_awaited()

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

    async def test_email_only_trial_activation_requires_oauth_when_disabled(self):
        session = _Session()
        settings = settings_stub(
            TRIAL_ENABLED=True,
            TRIAL_DURATION_DAYS=7,
            TRIAL_TRAFFIC_LIMIT_GB=10,
            TRIAL_WITHOUT_OAUTH_ENABLED=False,
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
            patch.object(
                billing_module.user_dal,
                "has_external_oauth_identity",
                AsyncMock(return_value=False),
            ),
        ):
            response = await billing_module.activate_trial_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 400)
        self.assertEqual(payload["error"], "trial_oauth_required")
        self.assertEqual(payload["message"], "oauth_required")
        subscription_service.activate_trial_subscription.assert_not_awaited()

    async def test_disposable_email_trial_activation_requires_telegram(self):
        session = _Session()
        settings = settings_stub(
            TRIAL_ENABLED=True,
            TRIAL_DURATION_DAYS=7,
            TRIAL_TRAFFIC_LIMIT_GB=10,
            TRIAL_WITHOUT_OAUTH_ENABLED=True,
            DISPOSABLE_EMAIL_DOMAINS=DEFAULT_DISPOSABLE_EMAIL_DOMAINS,
            LOG_TRIAL_ACTIVATIONS=False,
        )
        db_user = SimpleNamespace(
            user_id=42,
            telegram_id=None,
            is_banned=False,
            email="person@prorises.com",
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

    def test_linked_telegram_allows_disposable_email_trial_activation(self):
        settings = settings_stub(
            TRIAL_WITHOUT_OAUTH_ENABLED=True,
            DISPOSABLE_EMAIL_DOMAINS=DEFAULT_DISPOSABLE_EMAIL_DOMAINS,
        )
        db_user = SimpleNamespace(
            telegram_id=123456,
            email="person@ogzmail.com",
        )

        self.assertIsNone(_trial_oauth_required_reason(settings, db_user))

    def test_trial_and_referral_without_telegram_switches_are_independent(self):
        settings = settings_stub(
            TRIAL_WITHOUT_OAUTH_ENABLED=True,
            REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED=False,
            DISPOSABLE_EMAIL_DOMAINS=DEFAULT_DISPOSABLE_EMAIL_DOMAINS,
        )
        db_user = SimpleNamespace(
            telegram_id=None,
            email="person@example.com",
        )

        self.assertIsNone(_trial_oauth_required_reason(settings, db_user))
        self.assertEqual(
            _referral_welcome_telegram_required_reason(settings, db_user),
            "telegram_required",
        )

    async def test_linked_external_oauth_satisfies_trial_requirement(self):
        settings = settings_stub(
            TRIAL_WITHOUT_OAUTH_ENABLED=False,
            DISPOSABLE_EMAIL_DOMAINS="",
        )
        db_user = SimpleNamespace(
            user_id=42,
            telegram_id=None,
            email="oauth@example.com",
        )

        with patch.object(
            billing_module.user_dal,
            "has_external_oauth_identity",
            AsyncMock(return_value=True),
        ) as has_external_identity:
            self.assertIsNone(
                await _trial_oauth_required_reason_for_user(
                    SimpleNamespace(),
                    settings,
                    db_user,
                )
            )

        has_external_identity.assert_awaited_once_with(ANY, 42)

    async def test_trial_oauth_requirement_rejects_account_without_identity(self):
        settings = settings_stub(
            TRIAL_WITHOUT_OAUTH_ENABLED=False,
            DISPOSABLE_EMAIL_DOMAINS="",
        )
        db_user = SimpleNamespace(
            user_id=42,
            telegram_id=None,
            email="email-only@example.com",
        )

        with patch.object(
            billing_module.user_dal,
            "has_external_oauth_identity",
            AsyncMock(return_value=False),
        ):
            self.assertEqual(
                await _trial_oauth_required_reason_for_user(
                    SimpleNamespace(),
                    settings,
                    db_user,
                ),
                "oauth_required",
            )

    async def test_external_oauth_does_not_bypass_disposable_email_block(self):
        settings = settings_stub(
            TRIAL_WITHOUT_OAUTH_ENABLED=False,
            DISPOSABLE_EMAIL_DOMAINS=DEFAULT_DISPOSABLE_EMAIL_DOMAINS,
        )
        db_user = SimpleNamespace(
            user_id=42,
            telegram_id=None,
            email="person@prorises.com",
        )

        has_external_identity = AsyncMock(return_value=True)
        with patch.object(
            billing_module.user_dal,
            "has_external_oauth_identity",
            has_external_identity,
        ):
            self.assertEqual(
                await _trial_oauth_required_reason_for_user(
                    SimpleNamespace(),
                    settings,
                    db_user,
                ),
                "disposable_email",
            )

        has_external_identity.assert_not_awaited()

    async def test_trial_activation_failure_returns_localized_panel_hint(self):
        session = _Session()
        settings = settings_stub(
            DEFAULT_LANGUAGE="ru",
            TRIAL_ENABLED=True,
            TRIAL_DURATION_DAYS=7,
            TRIAL_TRAFFIC_LIMIT_GB=10,
            TRIAL_WITHOUT_OAUTH_ENABLED=True,
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
