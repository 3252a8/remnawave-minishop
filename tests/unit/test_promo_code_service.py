from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.services.promo_code_service import (
    PROMO_STATUS_ALREADY_USED,
    PROMO_STATUS_NOT_FOUND,
    PROMO_STATUS_REQUIRES_CHECKOUT,
    PROMO_STATUS_STANDALONE,
    PROMO_STATUS_THROTTLED,
    PromoCheckoutRequired,
    PromoCodeService,
)


def _status_settings():
    return SimpleNamespace(
        MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED=False,
        BRUTE_FORCE_LOCK_SECONDS=60,
        BRUTE_FORCE_MAX_FAILURES=5,
        BRUTE_FORCE_WINDOW_SECONDS=300,
    )


def _status_gettext(lang, key, **kw):
    suffix = ",".join(f"{k}={v}" for k, v in kw.items())
    return f"{key}|{suffix}" if suffix else key


def _status_service():
    i18n = SimpleNamespace(gettext=_status_gettext)
    subscription_service = SimpleNamespace(extend_active_subscription_days=AsyncMock())
    return PromoCodeService(_status_settings(), subscription_service, AsyncMock(), i18n)


class PromoCodeServiceTests(IsolatedAsyncioTestCase):
    async def test_apply_promo_passes_default_tariff_for_new_bonus_subscription(self):
        end_date = datetime(2026, 1, 8, tzinfo=UTC)
        settings = SimpleNamespace(
            MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED=False,
            BRUTE_FORCE_LOCK_SECONDS=60,
            BRUTE_FORCE_MAX_FAILURES=5,
            BRUTE_FORCE_WINDOW_SECONDS=300,
            tariffs_config=SimpleNamespace(default_tariff="standard"),
        )
        subscription_service = SimpleNamespace(
            extend_active_subscription_days=AsyncMock(return_value=end_date)
        )
        i18n = SimpleNamespace(gettext=lambda lang, key, **kw: key)
        service = PromoCodeService(settings, subscription_service, AsyncMock(), i18n)
        session = AsyncMock()
        promo = SimpleNamespace(
            promo_code_id=5,
            code="HELLO",
            bonus_days=7,
            applies_to="subscription",
        )
        activation = SimpleNamespace(activation_id=10)

        with (
            patch(
                "bot.services.promo_code_service.security_dal.check_throttle",
                AsyncMock(return_value=SimpleNamespace(locked=False, retry_after=None)),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.get_active_promo_code_by_code_str",
                AsyncMock(return_value=promo),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.get_user_activation_for_promo",
                AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.consume_promo_activation",
                AsyncMock(return_value=activation),
            ) as consume_activation,
            patch(
                "bot.services.promo_code_service.security_dal.clear_throttle_state",
                AsyncMock(),
            ),
            patch(
                "bot.services.promo_code_service.events.emit_model",
                AsyncMock(),
            ) as emit_event,
        ):
            success, result = await service.apply_promo_code(
                session=session,
                user_id=42,
                code_input="hello",
                user_lang="en",
            )

        self.assertTrue(success)
        self.assertEqual(result, end_date)
        subscription_service.extend_active_subscription_days.assert_awaited_once_with(
            session=session,
            user_id=42,
            bonus_days=7,
            reason="promo code HELLO",
            tariff_key="standard",
        )
        consume_activation.assert_awaited_once()
        consume_kwargs = consume_activation.await_args.kwargs
        self.assertIsNone(consume_kwargs["payment_id"])
        self.assertTrue(consume_kwargs["enforce_limit"])
        self.assertEqual(consume_kwargs["bonus_days"], 7)
        self.assertEqual(consume_kwargs["granted_days"], 7)
        self.assertEqual(consume_kwargs["applies_to"], "subscription")
        emitted_payload = emit_event.await_args.args[0]
        self.assertEqual(emitted_payload.user_id, 42)
        self.assertEqual(emitted_payload.code, "HELLO")
        self.assertEqual(emitted_payload.bonus_days, 7)
        self.assertEqual(emitted_payload.new_end_date, end_date)

    async def test_apply_promo_releases_activation_when_extension_fails(self):
        settings = SimpleNamespace(
            MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED=False,
            BRUTE_FORCE_LOCK_SECONDS=60,
            BRUTE_FORCE_MAX_FAILURES=5,
            BRUTE_FORCE_WINDOW_SECONDS=300,
            tariffs_config=SimpleNamespace(default_tariff="standard"),
        )
        subscription_service = SimpleNamespace(
            extend_active_subscription_days=AsyncMock(return_value=None)
        )
        i18n = SimpleNamespace(gettext=lambda lang, key, **kw: key)
        service = PromoCodeService(settings, subscription_service, AsyncMock(), i18n)
        session = AsyncMock()
        promo = SimpleNamespace(
            promo_code_id=5,
            code="HELLO",
            bonus_days=7,
            applies_to="subscription",
        )

        with (
            patch(
                "bot.services.promo_code_service.security_dal.check_throttle",
                AsyncMock(return_value=SimpleNamespace(locked=False, retry_after=None)),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.get_active_promo_code_by_code_str",
                AsyncMock(return_value=promo),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.get_user_activation_for_promo",
                AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.consume_promo_activation",
                AsyncMock(return_value=SimpleNamespace(activation_id=10)),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.release_promo_activation",
                AsyncMock(return_value=True),
            ) as release_activation,
            patch(
                "bot.services.promo_code_service.security_dal.clear_throttle_state",
                AsyncMock(),
            ) as clear_throttle,
            patch(
                "bot.services.promo_code_service.events.emit_model",
                AsyncMock(),
            ) as emit_event,
        ):
            success, result = await service.apply_promo_code(
                session=session,
                user_id=42,
                code_input="hello",
                user_lang="en",
            )

        self.assertFalse(success)
        self.assertEqual(result, "error_applying_promo_bonus")
        release_activation.assert_awaited_once_with(session, 5, 42, payment_id=None)
        clear_throttle.assert_not_awaited()
        emit_event.assert_not_awaited()

    async def test_apply_bonus_code_requires_checkout_when_payment_mode_enabled(self):
        settings = SimpleNamespace(
            MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED=False,
            BRUTE_FORCE_LOCK_SECONDS=60,
            BRUTE_FORCE_MAX_FAILURES=5,
            BRUTE_FORCE_WINDOW_SECONDS=300,
        )
        subscription_service = SimpleNamespace(extend_active_subscription_days=AsyncMock())
        i18n = SimpleNamespace(gettext=lambda lang, key, **kw: key)
        service = PromoCodeService(settings, subscription_service, AsyncMock(), i18n)
        session = AsyncMock()
        promo = SimpleNamespace(
            promo_code_id=5,
            code="HELLO",
            bonus_days=7,
            bonus_requires_payment=True,
            applies_to="subscription",
        )

        with (
            patch(
                "bot.services.promo_code_service.security_dal.check_throttle",
                AsyncMock(return_value=SimpleNamespace(locked=False, retry_after=None)),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.get_active_promo_code_by_code_str",
                AsyncMock(return_value=promo),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.get_user_activation_for_promo",
                AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.consume_promo_activation",
                AsyncMock(),
            ) as consume_activation,
            patch(
                "bot.services.promo_code_service.security_dal.clear_throttle_state",
                AsyncMock(),
            ) as clear_throttle,
        ):
            success, result = await service.apply_promo_code(
                session=session,
                user_id=42,
                code_input="hello",
                user_lang="en",
            )

        self.assertTrue(success)
        self.assertIsInstance(result, PromoCheckoutRequired)
        assert isinstance(result, PromoCheckoutRequired)
        self.assertEqual(result.code, "HELLO")
        self.assertEqual(result.effect_summary, "+7 days")
        subscription_service.extend_active_subscription_days.assert_not_awaited()
        consume_activation.assert_not_awaited()
        clear_throttle.assert_awaited_once()


class PromoCodeStatusTests(IsolatedAsyncioTestCase):
    async def test_status_standalone_for_unused_bonus_code(self):
        service = _status_service()
        promo = SimpleNamespace(
            promo_code_id=5,
            code="HELLO",
            bonus_days=7,
            applies_to="subscription",
        )
        with (
            patch(
                "bot.services.promo_code_service.security_dal.check_throttle",
                AsyncMock(return_value=SimpleNamespace(locked=False, retry_after=None)),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.get_active_promo_code_by_code_str",
                AsyncMock(return_value=promo),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.get_user_activation_for_promo",
                AsyncMock(return_value=None),
            ),
        ):
            status = await service.get_promo_code_status(AsyncMock(), 42, "hello", "en")

        self.assertEqual(status.status, PROMO_STATUS_STANDALONE)
        self.assertEqual(status.code, "HELLO")
        self.assertEqual(status.bonus_days, 7)
        self.assertEqual(status.effect_summary, "+7 days")

    async def test_status_requires_checkout_for_discount_code(self):
        service = _status_service()
        promo = SimpleNamespace(
            promo_code_id=5,
            code="SALE20",
            bonus_days=0,
            discount_percent=20,
            applies_to="subscription",
            min_subscription_months=3,
        )
        with (
            patch(
                "bot.services.promo_code_service.security_dal.check_throttle",
                AsyncMock(return_value=SimpleNamespace(locked=False, retry_after=None)),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.get_active_promo_code_by_code_str",
                AsyncMock(return_value=promo),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.get_user_activation_for_promo",
                AsyncMock(return_value=None),
            ),
        ):
            status = await service.get_promo_code_status(AsyncMock(), 42, "sale20", "en")

        self.assertEqual(status.status, PROMO_STATUS_REQUIRES_CHECKOUT)
        self.assertEqual(status.code, "SALE20")
        self.assertEqual(status.min_subscription_months, 3)

    async def test_status_already_used_includes_dates(self):
        service = _status_service()
        promo = SimpleNamespace(
            promo_code_id=5,
            code="HELLO",
            bonus_days=7,
            applies_to="subscription",
        )
        activation = SimpleNamespace(activated_at=datetime(2026, 6, 1, tzinfo=UTC))
        active_subscription = SimpleNamespace(end_date=datetime(2026, 8, 1, tzinfo=UTC))
        with (
            patch(
                "bot.services.promo_code_service.security_dal.check_throttle",
                AsyncMock(return_value=SimpleNamespace(locked=False, retry_after=None)),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.get_active_promo_code_by_code_str",
                AsyncMock(return_value=promo),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.get_user_activation_for_promo",
                AsyncMock(return_value=activation),
            ),
            patch(
                "bot.services.promo_code_service.subscription_dal.get_active_subscription_by_user_id",
                AsyncMock(return_value=active_subscription),
            ),
        ):
            status = await service.get_promo_code_status(AsyncMock(), 42, "hello", "en")

        self.assertEqual(status.status, PROMO_STATUS_ALREADY_USED)
        self.assertIn("promo_code_already_used_details", status.message)
        self.assertIn("date=01.06.2026", status.message)
        self.assertIn("promo_code_already_used_subscription_until", status.message)
        self.assertIn("end_date=01.08.2026", status.message)
        self.assertEqual(status.subscription_end_date, active_subscription.end_date)

    async def test_status_not_found_records_throttle_failure(self):
        service = _status_service()
        record_failure = AsyncMock(return_value=SimpleNamespace(locked=False, retry_after=None))
        with (
            patch(
                "bot.services.promo_code_service.security_dal.check_throttle",
                AsyncMock(return_value=SimpleNamespace(locked=False, retry_after=None)),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.get_active_promo_code_by_code_str",
                AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.promo_code_service.security_dal.record_throttle_failure",
                record_failure,
            ),
        ):
            status = await service.get_promo_code_status(AsyncMock(), 42, "nope", "en")

        self.assertEqual(status.status, PROMO_STATUS_NOT_FOUND)
        self.assertIn("promo_code_not_found", status.message)
        record_failure.assert_awaited_once()

    async def test_status_throttled_when_locked(self):
        service = _status_service()
        with patch(
            "bot.services.promo_code_service.security_dal.check_throttle",
            AsyncMock(return_value=SimpleNamespace(locked=True, retry_after=30)),
        ):
            status = await service.get_promo_code_status(AsyncMock(), 42, "hello", "en")

        self.assertEqual(status.status, PROMO_STATUS_THROTTLED)
        self.assertIn("seconds=30", status.message)

    async def test_apply_already_used_message_includes_activation_date(self):
        service = _status_service()
        promo = SimpleNamespace(
            promo_code_id=5,
            code="HELLO",
            bonus_days=7,
            applies_to="subscription",
        )
        activation = SimpleNamespace(activated_at=datetime(2026, 6, 1, tzinfo=UTC))
        with (
            patch(
                "bot.services.promo_code_service.security_dal.check_throttle",
                AsyncMock(return_value=SimpleNamespace(locked=False, retry_after=None)),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.get_active_promo_code_by_code_str",
                AsyncMock(return_value=promo),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.get_user_activation_for_promo",
                AsyncMock(return_value=activation),
            ),
            patch(
                "bot.services.promo_code_service.subscription_dal.get_active_subscription_by_user_id",
                AsyncMock(return_value=None),
            ),
        ):
            success, result = await service.apply_promo_code(
                session=AsyncMock(),
                user_id=42,
                code_input="hello",
                user_lang="en",
            )

        self.assertFalse(success)
        self.assertIn("promo_code_already_used_details", str(result))
        self.assertIn("date=01.06.2026", str(result))
