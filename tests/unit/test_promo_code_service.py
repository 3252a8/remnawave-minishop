from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.services.promo_code_service import PromoCheckoutRequired, PromoCodeService


class PromoCodeServiceTests(IsolatedAsyncioTestCase):
    async def test_apply_promo_passes_default_tariff_for_new_bonus_subscription(self):
        end_date = datetime(2026, 1, 8, tzinfo=timezone.utc)
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
