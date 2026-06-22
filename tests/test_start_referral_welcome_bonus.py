from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from bot.handlers.user.start import start_command_handler


class StartReferralWelcomeBonusTests(IsolatedAsyncioTestCase):
    async def test_start_referral_welcome_bonus_passes_default_tariff(self):
        end_date = datetime(2026, 1, 9, tzinfo=timezone.utc)
        settings = SimpleNamespace(
            DEFAULT_LANGUAGE="en",
            ADMIN_IDS=[],
            DISABLE_WELCOME_MESSAGE=False,
            REFERRAL_WELCOME_BONUS_DAYS=3,
            tariffs_config=SimpleNamespace(default_tariff="standard"),
        )
        i18n = SimpleNamespace(gettext=lambda lang, key, **kw: key)
        subscription_service = SimpleNamespace(
            extend_active_subscription_days=AsyncMock(return_value=end_date)
        )
        session = AsyncMock()
        message = SimpleNamespace(
            from_user=SimpleNamespace(
                id=42,
                username="alice",
                first_name="Alice",
                last_name="Example",
                full_name="Alice Example",
            ),
            bot=AsyncMock(),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(clear=AsyncMock())
        ref_match = Mock()
        ref_match.group.return_value = "ABC123"
        created_user = SimpleNamespace(user_id=42, referred_by_id=7)

        with (
            patch(
                "bot.handlers.user.start_flow._resolve_referrer_from_start_ref",
                AsyncMock(return_value=7),
            ),
            patch(
                "bot.handlers.user.start.user_dal.get_user_by_id",
                AsyncMock(return_value=None),
            ),
            patch(
                "bot.handlers.user.start.user_dal.create_user",
                AsyncMock(return_value=(created_user, True)),
            ),
            patch(
                "bot.handlers.user.start_flow.ensure_required_channel_subscription",
                AsyncMock(return_value=True),
            ),
            patch(
                "bot.handlers.user.start_flow.send_main_menu",
                AsyncMock(),
            ),
        ):
            await start_command_handler(
                message=message,
                state=state,
                settings=settings,
                i18n_data={"current_language": "en", "i18n_instance": i18n},
                subscription_service=subscription_service,
                referral_service=AsyncMock(),
                session=session,
                ref_match=ref_match,
            )

        subscription_service.extend_active_subscription_days.assert_awaited_once_with(
            session,
            42,
            3,
            reason="referral_welcome_bonus",
            tariff_key="standard",
        )
