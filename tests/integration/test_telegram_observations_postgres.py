"""Ordered Telegram observations exercise real concurrent transactions."""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.types import Chat, ChatMemberBanned, ChatMemberMember, ChatMemberUpdated, Update
from aiogram.types import User as TelegramUser
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.app.controllers.dispatcher_controller import build_dispatcher
from bot.handlers.telegram_membership import build_telegram_membership_router
from bot.middlewares.i18n import JsonI18n
from db.dal.telegram_state_dal import record_channel_membership, record_delivery_state
from db.migrator.chain_0108_telegram_observations import CHAIN_0108_TELEGRAM_OBSERVATIONS
from db.models import Base, User
from tests.support.settings_stub import settings_stub

DATABASE_URL = os.environ.get("CORE_PERFORMANCE_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="Disposable PostgreSQL URL is required")


def test_atomic_ordering_identity_and_dispatcher(monkeypatch):
    async def run():
        schema = "telegram_observations_" + uuid.uuid4().hex
        admin = create_async_engine(DATABASE_URL)
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(
            DATABASE_URL, connect_args={"server_settings": {"search_path": schema}}
        )
        bot = Bot("123456:TEST_TOKEN")
        send = AsyncMock()
        monkeypatch.setattr(bot, "send_message", send)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(
                    lambda connection: Base.metadata.create_all(connection, tables=[User.__table__])
                )
                await connection.execute(
                    text(
                        "ALTER TABLE users DROP COLUMN telegram_notifications_observation_order, "
                        "DROP COLUMN channel_subscription_observation_order"
                    )
                )
                for _ in range(2):
                    await connection.run_sync(CHAIN_0108_TELEGRAM_OBSERVATIONS[0].upgrade)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            now = datetime.now(UTC).replace(microsecond=0)
            async with factory.begin() as session:
                session.add_all(
                    [
                        User(user_id=7, telegram_id=42, is_banned=True, username="original"),
                        User(user_id=42, telegram_id=99),
                        User(user_id=900, telegram_id=900, username="unchanged_actor"),
                    ]
                )
            async with factory.begin() as session:
                assert await record_delivery_state(
                    session, 7, "blocked", now, telegram_id=42, update_id=20
                )
                assert (
                    await record_delivery_state(
                        session, 7, "blocked", now, telegram_id=42, update_id=20
                    )
                    is None
                )
                assert (
                    await record_delivery_state(
                        session, 7, "enabled", now, telegram_id=42, update_id=19
                    )
                    is None
                )
                assert (
                    await record_delivery_state(
                        session, 7, "enabled", now, telegram_id=99, update_id=30
                    )
                    is None
                )

            locked = asyncio.Event()
            release = asyncio.Event()

            async def newer_transaction():
                async with factory.begin() as session:
                    await record_delivery_state(
                        session,
                        7,
                        "enabled",
                        now + timedelta(seconds=2),
                        telegram_id=42,
                        update_id=1,
                    )
                    locked.set()
                    await release.wait()

            async def delayed_failure():
                await locked.wait()
                async with factory.begin() as session:
                    release.set()
                    assert (
                        await record_delivery_state(
                            session, 7, "blocked", now + timedelta(seconds=1), telegram_id=42
                        )
                        is None
                    )

            await asyncio.gather(newer_transaction(), delayed_failure())
            async with factory.begin() as session:
                await record_channel_membership(
                    session, 7, 42, -1001234567890, True, now + timedelta(seconds=4)
                )
                assert (
                    await record_channel_membership(
                        session, 7, 42, -1001234567890, False, now, update_id=999
                    )
                    is None
                )

            settings = settings_stub(
                REQUIRED_CHANNEL_ID=-1001234567890,
                REDIS_URL=None,
                MAINTENANCE_MODE_ENABLED=True,
                REGISTRATION_INVITE_ONLY_ENABLED=True,
            )
            dp = build_dispatcher(
                settings, factory, bot=bot, i18n_instance=JsonI18n("locales", "en")
            )
            dp.include_router(build_telegram_membership_router())
            actor = TelegramUser(id=900, is_bot=False, first_name="Actor")
            bot_user = TelegramUser(id=bot.id, is_bot=True, first_name="Bot")
            event = ChatMemberUpdated(
                chat=Chat(id=42, type="private"),
                from_user=actor,
                date=now + timedelta(seconds=5),
                old_chat_member=ChatMemberMember(user=bot_user),
                new_chat_member=ChatMemberBanned(user=bot_user, until_date=0),
            )
            await dp.feed_update(bot, Update(update_id=30, my_chat_member=event))
            await dp.feed_update(bot, Update(update_id=30, my_chat_member=event))
            # The affected member, never the initiating administrator, owns the row.
            member = TelegramUser(id=42, is_bot=False, first_name="Member")
            channel_event = ChatMemberUpdated(
                chat=Chat(id=-1001234567890, type="channel", title="Required"),
                from_user=actor,
                date=now + timedelta(seconds=6),
                old_chat_member=ChatMemberMember(user=member),
                new_chat_member=ChatMemberBanned(user=member, until_date=0),
            )
            await dp.feed_update(bot, Update(update_id=31, chat_member=channel_event))
            async with factory() as session:
                user = await session.get(User, 7)
                other = await session.get(User, 42)
                assert user and other
                assert user.telegram_notifications_status == "blocked"
                assert user.telegram_notifications_blocked_at == event.date
                assert user.channel_subscription_verified is False
                assert user.is_banned is True and user.username == "original"
                assert other.telegram_notifications_status == "unknown"
                assert other.channel_subscription_verified is None
                initiator = await session.get(User, 900)
                assert initiator and initiator.username == "unchanged_actor"
            # Unknown accounts are ignored, as are events about another bot/channel.
            unknown = event.model_copy(update={"chat": Chat(id=999, type="private")})
            await dp.feed_update(bot, Update(update_id=32, my_chat_member=unknown))
            async with factory() as session:
                assert await session.get(User, 999) is None
            settings.REQUIRED_CHANNEL_ID = -1001234567891
            await dp.feed_update(
                bot,
                Update(
                    update_id=33,
                    chat_member=channel_event.model_copy(
                        update={
                            "date": now + timedelta(seconds=7),
                            "new_chat_member": ChatMemberMember(user=member),
                        }
                    ),
                ),
            )
            async with factory() as session:
                user = await session.get(User, 7)
                assert user and user.channel_subscription_verified is False
            await dp.feed_update(
                bot,
                Update(
                    update_id=34,
                    chat_member=channel_event.model_copy(
                        update={
                            "date": now + timedelta(seconds=8),
                            "chat": Chat(
                                id=settings.REQUIRED_CHANNEL_ID, type="channel", title="New"
                            ),
                            "new_chat_member": ChatMemberMember(user=member),
                        }
                    ),
                ),
            )
            async with factory() as session:
                user = await session.get(User, 7)
                assert user and user.channel_subscription_verified is True
                assert user.channel_subscription_verified_for == settings.REQUIRED_CHANNEL_ID
            send.assert_not_awaited()
            await dp.storage.close()
        finally:
            await bot.session.close()
            await engine.dispose()
            async with admin.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin.dispose()

    asyncio.run(run())
