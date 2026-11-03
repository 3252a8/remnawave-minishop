import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.middlewares.i18n import JsonI18n
from bot.services.birthday_activation_worker import BirthdayActivationWorker
from config.settings import Settings
from db.models import PromoCode, User


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

        with self.assertRaises(TimeoutError):
            await worker._process_user(1, 100, now, 5)
        await worker._process_user(1, 100, now, 5)
        await worker._process_user(1, 100, now, 5)
        await worker._process_user(2, 200, now, 5)
        bot.get_chat.return_value = SimpleNamespace(birthdate=None)
        await worker._process_user(3, 300, now, 5)

        async with sessions() as session:
            promo = (await session.scalars(select(PromoCode))).one()
            user = await session.get(User, 1)
            assert user is not None
            self.assertEqual(promo.user_id, 1)
            self.assertEqual(promo.max_activations, 1)
            self.assertEqual(promo.bonus_days, 5)
            self.assertEqual(user.telegram_birthday_sent_year, 2026)
        self.assertEqual(bot.send_message.await_count, 2)
        self.assertEqual(
            [call.args for call in bot.send_message.await_args_list], [(100, promo.code)] * 2
        )
