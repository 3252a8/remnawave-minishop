from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.services.promo_code_service import PromoCodeService


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
                "bot.services.promo_code_service.promo_code_dal.record_promo_activation",
                AsyncMock(return_value=True),
            ),
            patch(
                "bot.services.promo_code_service.promo_code_dal.increment_promo_code_usage",
                AsyncMock(return_value=True),
            ),
            patch(
                "bot.services.promo_code_service.security_dal.clear_throttle_state",
                AsyncMock(),
            ),
            patch(
                "bot.services.promo_code_service.events.emit",
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
        emit_event.assert_awaited_once_with(
            "promo_code.applied",
            {
                "user_id": 42,
                "code": "HELLO",
                "bonus_days": 7,
                "new_end_date": end_date.isoformat(),
            },
        )
