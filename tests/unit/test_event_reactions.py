from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import ANY, AsyncMock, patch

from bot.infra import events
from bot.plugins import PluginContext
from bot.services import event_reactions
from bot.services.event_reactions import register_core_reactions
from tests.support.settings_stub import settings_stub


class _SessionFactory:
    def __init__(self):
        self.session = SimpleNamespace()

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _I18n:
    def gettext(self, _language, key, **_kwargs):
        return key


class _TemplateI18n:
    def __init__(self, templates):
        self.templates = templates

    def gettext(self, _language, key, **kwargs):
        template = self.templates.get(key, key)
        return template.format(**kwargs)


def _settings():
    return settings_stub(
        DEFAULT_LANGUAGE="en",
        DEFAULT_CURRENCY="RUB",
        SUBSCRIPTION_MINI_APP_URL="https://mini.example.test",
    )


def _context(*, notification_service=None, email_auth_service=None, bot=None):
    return _context_with_i18n(
        _I18n(),
        notification_service=notification_service,
        email_auth_service=email_auth_service,
        bot=bot,
    )


def _context_with_i18n(i18n, *, notification_service=None, email_auth_service=None, bot=None):
    return PluginContext(
        settings=_settings(),
        session_factory=_SessionFactory(),
        bot=bot or SimpleNamespace(send_message=AsyncMock()),
        i18n=i18n,
        services={
            "notification_service": notification_service
            or SimpleNamespace(
                notify_trial_activation=AsyncMock(),
                notify_new_user_registration=AsyncMock(),
                notify_new_email_user_registration=AsyncMock(),
                notify_promo_activation=AsyncMock(),
                notify_account_email_linked=AsyncMock(),
                notify_account_telegram_linked=AsyncMock(),
                notify_payment_received=AsyncMock(),
                notify_account_merged=AsyncMock(),
            ),
            "email_auth_service": email_auth_service
            or SimpleNamespace(send_rendered_email=AsyncMock()),
        },
    )


class CoreEventReactionsTests(IsolatedAsyncioTestCase):
    def setUp(self):
        events.reset_subscribers()
        event_reactions._payment_log_notification_cache.clear()

    def tearDown(self):
        events.reset_subscribers()
        event_reactions._payment_log_notification_cache.clear()

    async def test_trial_activation_event_notifies_and_invalidates(self):
        end_date = datetime(2026, 1, 9, 3, 4, tzinfo=UTC)
        notification_service = SimpleNamespace(notify_trial_activation=AsyncMock())
        ctx = _context(notification_service=notification_service)
        user = SimpleNamespace(username="alice", email="alice@example.test")

        with (
            patch.object(event_reactions.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                event_reactions,
                "invalidate_webapp_user_caches",
                AsyncMock(),
            ) as invalidate,
        ):
            register_core_reactions(ctx)
            await events.emit(
                events.TRIAL_ACTIVATED,
                {"user_id": 42, "end_date": end_date.isoformat()},
            )

        notification_service.notify_trial_activation.assert_awaited_once_with(
            42,
            end_date,
            username="alice",
            email="alice@example.test",
        )
        invalidate.assert_awaited_once_with(ctx.settings, 42, include_devices=True)

    async def test_user_registered_event_routes_telegram_email_and_panel_sync(self):
        notification_service = SimpleNamespace(
            notify_new_user_registration=AsyncMock(),
            notify_new_email_user_registration=AsyncMock(),
        )
        ctx = _context(notification_service=notification_service)
        user = SimpleNamespace(email="db@example.test", username="dbuser", first_name="Db")

        with patch.object(
            event_reactions.user_dal,
            "get_user_by_id",
            AsyncMock(return_value=user),
        ):
            register_core_reactions(ctx)
            await events.emit(
                events.USER_REGISTERED,
                {
                    "user_id": 42,
                    "registered_via": "telegram",
                    "username": "alice",
                    "first_name": "Alice",
                    "email": "alice@example.test",
                    "referred_by_id": 7,
                },
            )
            await events.emit(
                events.USER_REGISTERED,
                {
                    "user_id": 43,
                    "registered_via": "email",
                    "email": "email@example.test",
                    "referred_by_id": None,
                },
            )
            await events.emit(
                events.USER_REGISTERED,
                {"user_id": 44, "registered_via": "panel_sync"},
            )

        notification_service.notify_new_user_registration.assert_awaited_once_with(
            user_id=42,
            username="alice",
            first_name="Alice",
            email="alice@example.test",
            referred_by_id=7,
        )
        notification_service.notify_new_email_user_registration.assert_awaited_once_with(
            user_id=43,
            email="email@example.test",
            referred_by_id=None,
        )

    async def test_promo_code_event_notifies_admins(self):
        notification_service = SimpleNamespace(notify_promo_activation=AsyncMock())
        ctx = _context(notification_service=notification_service)
        user = SimpleNamespace(username="alice", email="alice@example.test")

        with patch.object(
            event_reactions.user_dal,
            "get_user_by_id",
            AsyncMock(return_value=user),
        ):
            register_core_reactions(ctx)
            await events.emit(
                events.PROMO_CODE_APPLIED,
                {"user_id": 42, "code": "HELLO", "bonus_days": 7},
            )

        notification_service.notify_promo_activation.assert_awaited_once_with(
            user_id=42,
            promo_code="HELLO",
            bonus_days=7,
            username="alice",
            email="alice@example.test",
        )

    async def test_account_link_events_honor_first_link(self):
        notification_service = SimpleNamespace(
            notify_account_email_linked=AsyncMock(),
            notify_account_telegram_linked=AsyncMock(),
        )
        ctx = _context(notification_service=notification_service)
        user = SimpleNamespace(
            telegram_id=42,
            email="alice@example.test",
            username="alice",
            first_name="Alice",
        )

        with patch.object(
            event_reactions.user_dal,
            "get_user_by_id",
            AsyncMock(return_value=user),
        ):
            register_core_reactions(ctx)
            await events.emit(
                events.ACCOUNT_EMAIL_LINKED,
                {"user_id": 42, "email": "alice@example.test", "first_link": False},
            )
            await events.emit(
                events.ACCOUNT_TELEGRAM_LINKED,
                {"user_id": 42, "telegram_id": 42, "first_link": False},
            )
            await events.emit(
                events.ACCOUNT_EMAIL_LINKED,
                {"user_id": 42, "email": "alice@example.test", "first_link": True},
            )
            await events.emit(
                events.ACCOUNT_TELEGRAM_LINKED,
                {"user_id": 42, "telegram_id": 42, "first_link": True},
            )

        notification_service.notify_account_email_linked.assert_awaited_once_with(
            user_id=42,
            email="alice@example.test",
            telegram_id=42,
            username="alice",
            first_name="Alice",
        )
        notification_service.notify_account_telegram_linked.assert_awaited_once_with(
            user_id=42,
            email="alice@example.test",
            telegram_id=42,
            username="alice",
            first_name="Alice",
        )

    async def test_payment_succeeded_event_notifies_and_invalidates(self):
        notification_service = SimpleNamespace(notify_payment_received=AsyncMock())
        ctx = _context(notification_service=notification_service)
        user = SimpleNamespace(username="alice", email="alice@example.test")
        payment = SimpleNamespace(
            amount=120,
            currency="RUB",
            provider="yookassa",
            sale_mode="premium_topup@standard",
            tariff_key="standard",
        )

        with (
            patch.object(event_reactions.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                event_reactions.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                event_reactions,
                "invalidate_webapp_user_caches",
                AsyncMock(),
            ) as invalidate,
        ):
            register_core_reactions(ctx)
            await events.emit(
                events.PAYMENT_SUCCEEDED,
                {
                    "user_id": 42,
                    "payment_db_id": 5,
                    "notification_provider": "wata",
                    "amount": 120,
                    "currency": "RUB",
                    "sale_mode": "premium_topup@standard",
                    "tariff_key": "standard",
                    "traffic_gb": 10,
                },
            )

        notification_service.notify_payment_received.assert_awaited_once_with(
            user_id=42,
            amount=120.0,
            currency="RUB",
            months=0,
            traffic_gb=10.0,
            payment_provider="wata",
            username="alice",
            email="alice@example.test",
            traffic_is_premium=True,
            tariff_key="standard",
            purchased_hwid_devices=None,
            purchases=ANY,
        )
        invalidate.assert_awaited_once_with(ctx.settings, 42, include_devices=True)

    async def test_payment_succeeded_event_dedupes_log_notification_by_payment_id(self):
        notification_service = SimpleNamespace(notify_payment_received=AsyncMock())
        ctx = _context(notification_service=notification_service)
        user = SimpleNamespace(username="alice", email="alice@example.test")
        payment = SimpleNamespace(
            amount=120,
            currency="RUB",
            provider="yookassa",
            sale_mode="subscription@standard",
            tariff_key="standard",
            subscription_duration_months=1,
        )
        payload = {
            "user_id": 42,
            "payment_db_id": 5,
            "notification_provider": "yookassa",
            "amount": 120,
            "currency": "RUB",
            "sale_mode": "subscription@standard",
            "tariff_key": "standard",
            "months": 1,
        }

        with (
            patch.object(event_reactions.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                event_reactions.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                event_reactions,
                "invalidate_webapp_user_caches",
                AsyncMock(),
            ) as invalidate,
        ):
            register_core_reactions(ctx)
            await events.emit(events.PAYMENT_SUCCEEDED, payload)
            await events.emit(events.PAYMENT_SUCCEEDED, payload)

        notification_service.notify_payment_received.assert_awaited_once()
        self.assertEqual(invalidate.await_count, 2)

    async def test_payment_succeeded_event_uses_redis_dedupe_for_log_notification(self):
        notification_service = SimpleNamespace(notify_payment_received=AsyncMock())
        ctx = _context(notification_service=notification_service)
        user = SimpleNamespace(username="alice", email="alice@example.test")
        payment = SimpleNamespace(
            amount=120,
            currency="RUB",
            provider="yookassa",
            sale_mode="subscription@standard",
            tariff_key="standard",
            subscription_duration_months=1,
        )
        payload = {
            "user_id": 42,
            "payment_db_id": 5,
            "notification_provider": "yookassa",
            "amount": 120,
            "currency": "RUB",
            "sale_mode": "subscription@standard",
            "tariff_key": "standard",
            "months": 1,
        }
        redis = SimpleNamespace(set=AsyncMock(side_effect=[True, False]))

        with (
            patch.object(event_reactions, "get_redis", AsyncMock(return_value=redis)),
            patch.object(event_reactions.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                event_reactions.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(event_reactions, "invalidate_webapp_user_caches", AsyncMock()),
        ):
            register_core_reactions(ctx)
            await events.emit(events.PAYMENT_SUCCEEDED, payload)
            await events.emit(events.PAYMENT_SUCCEEDED, payload)

        notification_service.notify_payment_received.assert_awaited_once()
        self.assertEqual(redis.set.await_count, 2)

    async def test_payment_succeeded_event_falls_back_to_payment_purchase_units(self):
        notification_service = SimpleNamespace(notify_payment_received=AsyncMock())
        ctx = _context(notification_service=notification_service)
        user = SimpleNamespace(username="alice", email="alice@example.test")
        payment = SimpleNamespace(
            payment_id=5,
            amount=120.0,
            currency="RUB",
            subscription_duration_months=None,
            purchased_gb=12.5,
            purchased_hwid_devices=None,
            provider="wata",
            sale_mode="topup@standard",
            tariff_key="standard",
        )

        with (
            patch.object(event_reactions.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                event_reactions.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(event_reactions, "invalidate_webapp_user_caches", AsyncMock()),
        ):
            register_core_reactions(ctx)
            await events.emit(
                events.PAYMENT_SUCCEEDED,
                {
                    "user_id": 42,
                    "payment_db_id": 5,
                    "notification_provider": "wata",
                    "amount": 120,
                    "currency": "RUB",
                    "sale_mode": "topup@standard",
                    "tariff_key": "standard",
                },
            )

        notification_service.notify_payment_received.assert_awaited_once_with(
            user_id=42,
            amount=120.0,
            currency="RUB",
            months=0,
            traffic_gb=12.5,
            payment_provider="wata",
            username="alice",
            email="alice@example.test",
            traffic_is_premium=False,
            tariff_key="standard",
            purchased_hwid_devices=None,
            purchases=ANY,
        )

    async def test_payment_succeeded_event_passes_hwid_purchase_units_from_payment(self):
        notification_service = SimpleNamespace(notify_payment_received=AsyncMock())
        ctx = _context(notification_service=notification_service)
        user = SimpleNamespace(username="alice", email="alice@example.test")
        payment = SimpleNamespace(
            payment_id=5,
            amount=80.0,
            currency="RUB",
            subscription_duration_months=None,
            purchased_gb=None,
            purchased_hwid_devices=2,
            provider="yookassa",
            sale_mode="hwid_devices@standard",
            tariff_key="standard",
        )

        with (
            patch.object(event_reactions.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                event_reactions.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(event_reactions, "invalidate_webapp_user_caches", AsyncMock()),
        ):
            register_core_reactions(ctx)
            await events.emit(
                events.PAYMENT_SUCCEEDED,
                {
                    "user_id": 42,
                    "payment_db_id": 5,
                    "notification_provider": "yookassa",
                    "amount": 80,
                    "currency": "RUB",
                    "sale_mode": "hwid_devices@standard",
                    "tariff_key": "standard",
                },
            )

        notification_service.notify_payment_received.assert_awaited_once_with(
            user_id=42,
            amount=80.0,
            currency="RUB",
            months=0,
            traffic_gb=None,
            payment_provider="yookassa",
            username="alice",
            email="alice@example.test",
            traffic_is_premium=False,
            tariff_key="standard",
            purchased_hwid_devices=2,
            purchases=ANY,
        )

    async def test_subscription_payment_succeeded_event_includes_hwid_renewal_units(self):
        notification_service = SimpleNamespace(notify_payment_received=AsyncMock())
        ctx = _context(notification_service=notification_service)
        user = SimpleNamespace(username="alice", email="alice@example.test")
        payment = SimpleNamespace(
            payment_id=5,
            amount=180.0,
            currency="RUB",
            subscription_duration_months=1,
            purchased_gb=None,
            purchased_hwid_devices=1,
            provider="wata",
            sale_mode="subscription@standard",
            tariff_key="standard",
        )

        with (
            patch.object(event_reactions.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                event_reactions.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(event_reactions, "invalidate_webapp_user_caches", AsyncMock()),
        ):
            register_core_reactions(ctx)
            await events.emit(
                events.PAYMENT_SUCCEEDED,
                {
                    "user_id": 42,
                    "payment_db_id": 5,
                    "notification_provider": "wata",
                    "amount": 180,
                    "currency": "RUB",
                    "sale_mode": "subscription@standard",
                    "tariff_key": "standard",
                    "months": "1.0",
                },
            )

        notification_service.notify_payment_received.assert_awaited_once_with(
            user_id=42,
            amount=180.0,
            currency="RUB",
            months=1,
            traffic_gb=None,
            payment_provider="wata",
            username="alice",
            email="alice@example.test",
            traffic_is_premium=False,
            tariff_key="standard",
            purchased_hwid_devices=1,
            purchases=ANY,
        )

    async def test_payment_canceled_event_notifies_user_and_email(self):
        bot = SimpleNamespace(send_message=AsyncMock())
        email = AsyncMock()
        ctx = _context(bot=bot)
        user = SimpleNamespace(language_code="ru", email="alice@example.test")

        with (
            patch.object(event_reactions.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(event_reactions, "send_user_notification_email", email),
        ):
            register_core_reactions(ctx)
            await events.emit(
                events.PAYMENT_CANCELED,
                {"user_id": 42, "message_key": "payment_failed"},
            )

        bot.send_message.assert_awaited_once_with(42, "payment_failed")
        email.assert_awaited_once_with(
            settings=ctx.settings,
            i18n=ctx.i18n,
            user=user,
            subject_key="email_payment_failed_subject",
            message_text="payment_failed",
            dashboard_url="https://mini.example.test",
        )

    async def test_payment_canceled_event_includes_attempt_details(self):
        templates = {
            "payment_failed": "payment failed",
            "payment_failed_with_details": "{message}\n\nDetails:\n{details}",
            "payment_failed_detail_item": "- {item}",
            "payment_failed_detail_subscription_with_tariff": "{tariff} for {months} months",
            "payment_failed_detail_purchase_hwid_devices": "{count} extra devices",
            "payment_failed_detail_amount": "- Amount: {amount} {currency}",
            "payment_failed_detail_provider": "- Provider: {provider}",
            "payment_failed_detail_payment_id": "- Payment ID: {payment_id}",
        }
        bot = SimpleNamespace(send_message=AsyncMock())
        email = AsyncMock()
        ctx = _context_with_i18n(_TemplateI18n(templates), bot=bot)
        ctx.settings.tariffs_config = SimpleNamespace(
            require=lambda _key: SimpleNamespace(name=lambda _language: "Standard")
        )
        user = SimpleNamespace(language_code="en", email="alice@example.test")
        payment = SimpleNamespace(
            payment_id=42,
            user_id=42,
            status="failed",
            amount=1500.0,
            currency="RUB",
            provider="platega",
            sale_mode="subscription@standard",
            tariff_key="standard",
            subscription_duration_months=3,
            purchased_hwid_devices=2,
            created_at=datetime(2026, 1, 9, 12, 0, tzinfo=UTC),
        )

        with (
            patch.object(event_reactions.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                event_reactions.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                event_reactions.payment_dal,
                "get_user_succeeded_payments_after",
                AsyncMock(return_value=[]),
            ),
            patch.object(event_reactions, "send_user_notification_email", email),
        ):
            register_core_reactions(ctx)
            await events.emit(
                events.PAYMENT_CANCELED,
                {
                    "user_id": 42,
                    "payment_db_id": 42,
                    "provider": "platega",
                    "message_key": "payment_failed",
                },
            )

        expected = (
            "payment failed\n\n"
            "Details:\n"
            "- Standard for 3 months\n"
            "- 2 extra devices\n"
            "- Amount: 1500 RUB\n"
            "- Provider: Platega (platega)\n"
            "- Payment ID: 42"
        )
        bot.send_message.assert_awaited_once_with(42, expected)
        email.assert_awaited_once_with(
            settings=ctx.settings,
            i18n=ctx.i18n,
            user=user,
            subject_key="email_payment_failed_subject",
            message_text=expected,
            dashboard_url="https://mini.example.test",
        )

    async def test_payment_canceled_event_includes_traffic_attempt_details(self):
        templates = {
            "payment_failed": "payment failed",
            "payment_failed_with_details": "{message}\n\nDetails:\n{details}",
            "payment_failed_detail_item": "- {item}",
            "payment_failed_detail_purchase_traffic": "{gb} GB - {kind}",
            "payment_failed_traffic_kind_premium": "premium traffic",
            "payment_failed_detail_amount": "- Amount: {amount} {currency}",
            "payment_failed_detail_provider": "- Provider: {provider}",
            "payment_failed_detail_payment_id": "- Payment ID: {payment_id}",
        }
        bot = SimpleNamespace(send_message=AsyncMock())
        email = AsyncMock()
        ctx = _context_with_i18n(_TemplateI18n(templates), bot=bot)
        user = SimpleNamespace(language_code="en", email="alice@example.test")
        payment = SimpleNamespace(
            payment_id=43,
            user_id=42,
            status="failed",
            amount=250.5,
            currency="RUB",
            provider="platega",
            sale_mode="premium_topup@standard",
            tariff_key="standard",
            purchased_gb=10.0,
            created_at=datetime(2026, 1, 9, 12, 0, tzinfo=UTC),
        )

        with (
            patch.object(event_reactions.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                event_reactions.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                event_reactions.payment_dal,
                "get_user_succeeded_payments_after",
                AsyncMock(return_value=[]),
            ),
            patch.object(event_reactions, "send_user_notification_email", email),
        ):
            register_core_reactions(ctx)
            await events.emit(
                events.PAYMENT_CANCELED,
                {
                    "user_id": 42,
                    "payment_db_id": 43,
                    "provider": "platega",
                    "message_key": "payment_failed",
                },
            )

        expected = (
            "payment failed\n\n"
            "Details:\n"
            "- 10 GB - premium traffic\n"
            "- Amount: 250.5 RUB\n"
            "- Provider: Platega (platega)\n"
            "- Payment ID: 43"
        )
        bot.send_message.assert_awaited_once_with(42, expected)
        email.assert_awaited_once()

    async def test_payment_canceled_event_skips_stale_platega_failure_after_later_success(self):
        bot = SimpleNamespace(send_message=AsyncMock())
        email = AsyncMock()
        ctx = _context(bot=bot)
        created_at = datetime(2026, 1, 9, 9, 0, tzinfo=UTC)
        canceled_payment = SimpleNamespace(
            payment_id=10,
            user_id=42,
            status="canceled",
            provider="platega",
            created_at=created_at,
            updated_at=datetime(2026, 1, 9, 13, 0, tzinfo=UTC),
            sale_mode="subscription@standard",
            subscription_duration_months=1,
        )
        later_success = SimpleNamespace(
            payment_id=11,
            user_id=42,
            status="succeeded",
            provider="platega",
            created_at=datetime(2026, 1, 9, 9, 10, tzinfo=UTC),
            updated_at=datetime(2026, 1, 9, 9, 20, tzinfo=UTC),
            sale_mode="subscription@standard",
            subscription_duration_months=3,
        )

        with (
            patch.object(
                event_reactions.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=canceled_payment),
            ),
            patch.object(
                event_reactions.payment_dal,
                "get_user_succeeded_payments_after",
                AsyncMock(return_value=[later_success]),
            ),
            patch.object(event_reactions, "send_user_notification_email", email),
        ):
            register_core_reactions(ctx)
            await events.emit(
                events.PAYMENT_CANCELED,
                {
                    "user_id": 42,
                    "payment_db_id": 10,
                    "provider": "platega",
                    "status": "canceled",
                    "message_key": "payment_failed",
                },
            )

        bot.send_message.assert_not_awaited()
        email.assert_not_awaited()

    async def test_payment_canceled_event_notifies_when_success_is_older(self):
        bot = SimpleNamespace(send_message=AsyncMock())
        email = AsyncMock()
        ctx = _context(bot=bot)
        user = SimpleNamespace(language_code="ru", email="alice@example.test")
        created_at = datetime(2026, 1, 9, 12, 0, tzinfo=UTC)
        canceled_payment = SimpleNamespace(
            payment_id=20,
            user_id=42,
            status="failed",
            provider="platega",
            created_at=created_at,
            updated_at=datetime(2026, 1, 9, 13, 0, tzinfo=UTC),
        )
        older_success = SimpleNamespace(
            payment_id=19,
            user_id=42,
            status="succeeded",
            provider="platega",
            created_at=datetime(2026, 1, 8, 10, 0, tzinfo=UTC),
            updated_at=datetime(2026, 1, 8, 10, 5, tzinfo=UTC),
        )

        with (
            patch.object(event_reactions.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                event_reactions.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=canceled_payment),
            ),
            patch.object(
                event_reactions.payment_dal,
                "get_user_succeeded_payments_after",
                AsyncMock(return_value=[older_success]),
            ),
            patch.object(event_reactions, "send_user_notification_email", email),
        ):
            register_core_reactions(ctx)
            await events.emit(
                events.PAYMENT_CANCELED,
                {"user_id": 42, "payment_db_id": 20, "message_key": "payment_failed"},
            )

        bot.send_message.assert_awaited_once_with(42, "payment_failed_with_details")
        email.assert_awaited_once()

    async def test_payment_canceled_event_skips_when_payment_already_succeeded(self):
        bot = SimpleNamespace(send_message=AsyncMock())
        email = AsyncMock()
        ctx = _context(bot=bot)
        payment = SimpleNamespace(
            payment_id=30,
            user_id=42,
            status="succeeded",
            provider="platega",
            created_at=datetime(2026, 1, 9, 12, 0, tzinfo=UTC),
        )

        with (
            patch.object(
                event_reactions.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                event_reactions.payment_dal,
                "get_user_succeeded_payments_after",
                AsyncMock(side_effect=AssertionError("already succeeded must not query history")),
            ),
            patch.object(event_reactions, "send_user_notification_email", email),
        ):
            register_core_reactions(ctx)
            await events.emit(
                events.PAYMENT_CANCELED,
                {"user_id": 42, "payment_db_id": 30, "message_key": "payment_failed"},
            )

        bot.send_message.assert_not_awaited()
        email.assert_not_awaited()

    async def test_referral_bonus_event_notifies_inviter(self):
        bot = SimpleNamespace(send_message=AsyncMock())
        email = AsyncMock()
        ctx = _context(bot=bot)
        inviter = SimpleNamespace(language_code="en", email="inviter@example.test")
        end_date = datetime(2026, 1, 9, tzinfo=UTC)

        with (
            patch.object(
                event_reactions.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=inviter),
            ),
            patch.object(event_reactions, "send_user_notification_email", email),
        ):
            register_core_reactions(ctx)
            await events.emit(
                events.REFERRAL_BONUS_GRANTED,
                {
                    "referee_user_id": 43,
                    "referee_name": "Bob",
                    "inviter_bonus_applied": True,
                    "inviter_user_id": 42,
                    "inviter_bonus_days": 7,
                    "inviter_bonus_end_date": end_date.isoformat(),
                    "inviter_bonus_kind": "new_sub",
                },
            )

        bot.send_message.assert_awaited_once_with(
            42,
            "referral_bonus_inviter_notification_new_sub",
        )
        email.assert_awaited_once_with(
            settings=ctx.settings,
            i18n=ctx.i18n,
            user=inviter,
            subject_key="email_referral_bonus_subject",
            message_text="referral_bonus_inviter_notification_new_sub",
            dashboard_url="https://mini.example.test",
        )

    async def test_account_merged_event_notifies_admin_and_optional_email(self):
        final_end_date = datetime(2026, 1, 9, 3, 4, tzinfo=UTC)
        notification_service = SimpleNamespace(notify_account_merged=AsyncMock())
        email_service = SimpleNamespace(send_rendered_email=AsyncMock())
        ctx = _context(
            notification_service=notification_service,
            email_auth_service=email_service,
        )

        with patch.object(
            event_reactions,
            "render_account_merged",
            return_value=SimpleNamespace(subject="subject", html="html", text="text"),
        ):
            register_core_reactions(ctx)
            await events.emit(
                events.ACCOUNT_MERGED,
                {
                    "source_user_id": -100,
                    "target_user_id": 42,
                    "reason": "panel_sync",
                },
            )
            await events.emit(
                events.ACCOUNT_MERGED,
                {
                    "source_user_id": -100,
                    "target_user_id": 42,
                    "reason": "telegram_link",
                    "send_user_email": True,
                    "email": "alice@example.test",
                    "telegram_id": 42,
                    "username": "alice",
                    "first_name": "Alice",
                    "source_panel_user_uuid": "source-panel",
                    "target_panel_user_uuid": "target-panel",
                    "language": "en",
                    "final_end_date": final_end_date.isoformat(),
                },
            )

        notification_service.notify_account_merged.assert_awaited_once_with(
            primary_user_id=42,
            removed_user_id=-100,
            email="alice@example.test",
            telegram_id=42,
            username="alice",
            first_name="Alice",
            final_end_date_text="09.01.2026 03:04",
            primary_panel_user_uuid="target-panel",
            removed_panel_user_uuid="source-panel",
        )
        email_service.send_rendered_email.assert_awaited_once()
