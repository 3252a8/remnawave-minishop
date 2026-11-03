import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.middlewares.i18n import JsonI18n
from bot.services.birthday_activation_config import (
    BIRTHDAY_CAMPAIGN_KEY,
    LEGACY_BIRTHDAY_DAYS_KEY,
    BirthdayActivationConfig,
    load_birthday_activation_config,
)
from bot.services.birthday_activation_worker import BirthdayActivationWorker
from bot.services.promo_effects import PromoEffects
from config.settings import Settings
from db.dal import app_settings_dal
from db.models import AppSettingOverride, PromoCode, User


class BirthdayActivationWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_delivery_failure_reuses_personal_code_and_success_sends_once(self):
        engine = create_async_engine("sqlite+aiosqlite://")
        self.addAsyncCleanup(engine.dispose)
        async with engine.begin() as connection:
            await connection.run_sync(User.__table__.create)
            await connection.run_sync(PromoCode.__table__.create)

        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions.begin() as session:
            session.add(User(user_id=1, telegram_id=100, language_code="en"))
            session.add(
                User(user_id=2, telegram_id=200, marketing_notifications_telegram_enabled=False)
            )
            session.add(User(user_id=3, telegram_id=300))

        bot = AsyncMock()
        bot.get_chat.return_value = SimpleNamespace(birthdate=SimpleNamespace(month=11, day=3))
        bot.send_message.side_effect = [TimeoutError, None]
        settings = Settings(
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            BIRTHDAY_ACTIVATION_CODE_DAYS=5,
        )
        i18n = Mock(spec=JsonI18n)
        i18n.gettext.side_effect = lambda lang, key, **params: str(params["code"])
        worker = BirthdayActivationWorker(settings, sessions, bot, i18n)
        now = datetime(2026, 11, 3, tzinfo=UTC)
        config = BirthdayActivationConfig(
            enabled=True, valid_days=13, effects=PromoEffects(bonus_days=5, discount_percent=10)
        )

        with self.assertRaises(TimeoutError):
            await worker._process_user(1, 100, now, config)
        await worker._process_user(1, 100, now, config.model_copy(update={"valid_days": 2}))
        await worker._process_user(1, 100, now, config)
        await worker._process_user(2, 200, now, config)
        bot.get_chat.return_value = SimpleNamespace(birthdate=None)
        await worker._process_user(3, 300, now, config)

        async with sessions() as session:
            promo = (await session.scalars(select(PromoCode))).one()
            user = await session.get(User, 1)
            assert user is not None
            self.assertEqual(promo.user_id, 1)
            self.assertEqual(promo.max_activations, 1)
            self.assertEqual(promo.bonus_days, 5)
            self.assertEqual(promo.discount_percent, 10)
            self.assertEqual(promo.valid_until.replace(tzinfo=UTC), now + timedelta(days=13))
            self.assertEqual(user.telegram_birthday_sent_year, 2026)
        self.assertEqual(bot.send_message.await_count, 2)
        self.assertEqual(
            [call.args for call in bot.send_message.await_args_list], [(100, promo.code)] * 2
        )

    async def test_saved_disabled_campaign_overrides_legacy_configuration(self) -> None:
        engine = create_async_engine("sqlite+aiosqlite://")
        self.addAsyncCleanup(engine.dispose)
        async with engine.begin() as connection:
            await connection.run_sync(AppSettingOverride.__table__.create)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        settings = Settings(
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            BIRTHDAY_ACTIVATION_CODE_DAYS=5,
        )
        async with sessions.begin() as session:
            env = await load_birthday_activation_config(session, settings)
            self.assertTrue(env.enabled)
            self.assertEqual(env.effects.bonus_days, 5)
            await app_settings_dal.upsert_override(
                session, key=LEGACY_BIRTHDAY_DAYS_KEY, value=10, updated_by=1
            )
            legacy = await load_birthday_activation_config(session, settings)
            self.assertEqual(legacy.effects.bonus_days, 10)
            await app_settings_dal.upsert_override(
                session,
                key=BIRTHDAY_CAMPAIGN_KEY,
                value=legacy.model_copy(update={"enabled": False}).model_dump(mode="json"),
                updated_by=1,
            )
            saved = await load_birthday_activation_config(session, settings)
            self.assertFalse(saved.enabled)
            self.assertEqual(saved.effects.bonus_days, 10)
