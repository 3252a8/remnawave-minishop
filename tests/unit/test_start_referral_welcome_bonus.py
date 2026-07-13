from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from bot.handlers.user.start import start_command_handler
from config.settings_models import ReferralSettings


class StartReferralWelcomeBonusTests(IsolatedAsyncioTestCase):
    def _settings(self, **overrides):
        values = {
            "DEFAULT_LANGUAGE": "en",
            "ADMIN_IDS": [],
            "DISABLE_WELCOME_MESSAGE": False,
            "REGISTRATION_INVITE_ONLY_ENABLED": False,
            "LEGACY_REFS": True,
            "compatibility_settings": SimpleNamespace(remnashop_referral_code_compat_enabled=False),
            "referral_settings": ReferralSettings(
                bonus_days_inviter_1_month=7,
                bonus_days_inviter_3_months=7,
                bonus_days_inviter_6_months=7,
                bonus_days_inviter_12_months=7,
                bonus_days_referee_1_month=3,
                bonus_days_referee_3_months=3,
                bonus_days_referee_6_months=3,
                bonus_days_referee_12_months=3,
                one_bonus_per_referee=False,
                welcome_bonus_days=0,
                welcome_bonus_without_telegram_enabled=True,
                legacy_refs_enabled=True,
            ),
            "tariffs_config": None,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def _message(self):
        return SimpleNamespace(
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

    async def test_start_invite_only_without_ref_does_not_create_user(self):
        settings = self._settings(REGISTRATION_INVITE_ONLY_ENABLED=True)
        i18n = SimpleNamespace(gettext=lambda lang, key, **kw: key)
        session = AsyncMock()
        state = SimpleNamespace(clear=AsyncMock())
        message = self._message()
        create_user = AsyncMock()

        with (
            patch(
                "bot.handlers.user.start.user_dal.get_user_by_id",
                AsyncMock(return_value=None),
            ),
            patch("bot.handlers.user.start.user_dal.create_user", create_user),
            patch(
                "bot.handlers.user.start_flow.ensure_required_channel_subscription",
                AsyncMock(return_value=True),
            ) as ensure_channel,
        ):
            await start_command_handler(
                message=message,
                state=state,
                settings=settings,
                i18n_data={"current_language": "en", "i18n_instance": i18n},
                subscription_service=SimpleNamespace(),
                referral_service=AsyncMock(),
                session=session,
            )

        create_user.assert_not_awaited()
        ensure_channel.assert_not_awaited()
        message.answer.assert_awaited_once_with("registration_invite_required")

    async def test_start_invite_only_with_invalid_ref_does_not_create_user(self):
        settings = self._settings(REGISTRATION_INVITE_ONLY_ENABLED=True)
        i18n = SimpleNamespace(gettext=lambda lang, key, **kw: key)
        session = AsyncMock()
        state = SimpleNamespace(clear=AsyncMock())
        message = self._message()
        create_user = AsyncMock()
        ref_match = Mock()
        ref_match.group.return_value = "ABC123"

        with (
            patch(
                "bot.handlers.user.start.user_dal.get_user_by_id",
                AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.registration_invite_gate.user_dal.get_user_by_referral_code",
                AsyncMock(return_value=None),
            ),
            patch("bot.handlers.user.start.user_dal.create_user", create_user),
            patch(
                "bot.handlers.user.start_flow.ensure_required_channel_subscription",
                AsyncMock(return_value=True),
            ) as ensure_channel,
        ):
            await start_command_handler(
                message=message,
                state=state,
                settings=settings,
                i18n_data={"current_language": "en", "i18n_instance": i18n},
                subscription_service=SimpleNamespace(),
                referral_service=AsyncMock(),
                session=session,
                ref_match=ref_match,
            )

        create_user.assert_not_awaited()
        ensure_channel.assert_not_awaited()
        message.answer.assert_awaited_once_with("registration_invite_required")

    async def test_start_invite_only_with_self_ref_does_not_create_user(self):
        settings = self._settings(REGISTRATION_INVITE_ONLY_ENABLED=True)
        i18n = SimpleNamespace(gettext=lambda lang, key, **kw: key)
        session = AsyncMock()
        state = SimpleNamespace(clear=AsyncMock())
        message = self._message()
        create_user = AsyncMock()
        ref_match = Mock()
        ref_match.group.return_value = "42"

        with (
            patch(
                "bot.handlers.user.start.user_dal.get_user_by_id",
                AsyncMock(side_effect=[None, SimpleNamespace(user_id=42)]),
            ),
            patch(
                "bot.services.registration_invite_gate.user_dal.get_user_by_referral_code",
                AsyncMock(return_value=None),
            ),
            patch("bot.handlers.user.start.user_dal.create_user", create_user),
            patch(
                "bot.handlers.user.start_flow.ensure_required_channel_subscription",
                AsyncMock(return_value=True),
            ) as ensure_channel,
        ):
            await start_command_handler(
                message=message,
                state=state,
                settings=settings,
                i18n_data={"current_language": "en", "i18n_instance": i18n},
                subscription_service=SimpleNamespace(),
                referral_service=AsyncMock(),
                session=session,
                ref_match=ref_match,
            )

        create_user.assert_not_awaited()
        ensure_channel.assert_not_awaited()
        message.answer.assert_awaited_once_with("registration_invite_required")

    async def test_start_referral_welcome_bonus_passes_default_tariff(self):
        end_date = datetime(2026, 1, 9, tzinfo=UTC)
        settings = self._settings(
            REFERRAL_WELCOME_BONUS_DAYS=3,
            referral_settings=ReferralSettings(
                bonus_days_inviter_1_month=7,
                bonus_days_inviter_3_months=7,
                bonus_days_inviter_6_months=7,
                bonus_days_inviter_12_months=7,
                bonus_days_referee_1_month=3,
                bonus_days_referee_3_months=3,
                bonus_days_referee_6_months=3,
                bonus_days_referee_12_months=3,
                one_bonus_per_referee=False,
                welcome_bonus_days=3,
                welcome_bonus_without_telegram_enabled=True,
                legacy_refs_enabled=True,
            ),
            tariffs_config=SimpleNamespace(default_tariff="standard"),
        )
        i18n = SimpleNamespace(gettext=lambda lang, key, **kw: key)
        subscription_service = SimpleNamespace(
            extend_active_subscription_days=AsyncMock(return_value=end_date)
        )
        session = AsyncMock()
        message = self._message()
        state = SimpleNamespace(clear=AsyncMock())
        ref_match = Mock()
        ref_match.group.return_value = "ABC123"
        created_user = SimpleNamespace(
            user_id=42,
            referred_by_id=7,
            referral_welcome_bonus_claimed_at=None,
        )
        referrer = SimpleNamespace(user_id=7)

        with (
            patch(
                "bot.services.registration_invite_gate.user_dal.get_user_by_referral_code",
                AsyncMock(return_value=referrer),
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
                "bot.handlers.user.start_flow.user_dal.lock_user_by_id",
                AsyncMock(return_value=created_user),
            ),
            patch(
                "bot.handlers.user.start_flow.subscription_dal.has_any_subscription_for_user",
                AsyncMock(return_value=False),
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
