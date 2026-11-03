"""Read Telegram birthdays in bounded batches and deliver personal codes."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import Select, case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.services.birthday_activation_config import (
    BirthdayActivationConfig,
    load_birthday_activation_config,
)
from bot.services.promo_code_service import PromoCodeService
from config.settings import Settings
from db.models import PromoCode, User

logger = logging.getLogger(__name__)


class BirthdayActivationWorker:
    def __init__(
        self,
        settings: Settings,
        sessions: async_sessionmaker[AsyncSession],
        bot: Bot,
        i18n: JsonI18n,
    ) -> None:
        self.settings = settings
        self.sessions = sessions
        self.bot = bot
        self.i18n = i18n

    def _eligible_users(self) -> Select[tuple[User]]:
        query = select(User).where(
            User.telegram_id.is_not(None),
            User.is_banned.is_not(True),
            User.telegram_notifications_status.not_in(("blocked", "needs_start")),
        )
        if self.settings.USER_NOTIFICATION_PREFERENCES_ENABLED:
            query = query.where(User.marketing_notifications_telegram_enabled.is_(True))
        return query

    async def _tick(self, now: datetime, config: BirthdayActivationConfig) -> None:
        today = now.month * 100 + now.day
        due = (User.telegram_birthday_month_day == today) & (
            User.telegram_birthday_sent_year.is_distinct_from(now.year)
        )
        async with self.sessions() as session:
            result = await session.execute(
                self._eligible_users()
                .where(
                    or_(
                        due,
                        User.telegram_birthday_checked_for.is_distinct_from(User.telegram_id),
                        User.telegram_birthday_checked_at.is_(None),
                        User.telegram_birthday_checked_at < now - timedelta(days=30),
                    )
                )
                .order_by(
                    case((due, 0), else_=1),
                    User.telegram_birthday_checked_at.asc().nulls_first(),
                    User.user_id,
                )
                .limit(30)
            )
            candidates = [(int(user.user_id), int(user.telegram_id)) for user in result.scalars()]
        for user_id, telegram_id in candidates:
            try:
                await self._process_user(user_id, telegram_id, now, config)
            except TelegramRetryAfter:
                raise
            except Exception:
                logger.exception("Birthday activation delivery failed for user %s", user_id)
            await asyncio.sleep(1)

    async def _process_user(
        self, user_id: int, telegram_id: int, now: datetime, config: BirthdayActivationConfig
    ) -> None:
        try:
            chat = await self.bot.get_chat(telegram_id)
            birthdate = chat.birthdate
        except (TelegramBadRequest, TelegramForbiddenError):
            birthdate = None
        month_day = birthdate.month * 100 + birthdate.day if birthdate else None
        origin = f"birthday-{now.year}"
        user_query = (
            self._eligible_users()
            .where(User.user_id == user_id, User.telegram_id == telegram_id)
            .with_for_update()
        )
        async with self.sessions.begin() as session:
            user = await session.scalar(user_query)
            if user is None:
                return
            user.telegram_birthday_month_day = month_day
            user.telegram_birthday_checked_at = now
            user.telegram_birthday_checked_for = telegram_id
            if month_day != now.month * 100 + now.day:
                return
            if user.telegram_birthday_sent_year == now.year:
                return
            promo = await session.scalar(
                select(PromoCode).where(PromoCode.user_id == user_id, PromoCode.origin == origin)
            )
            if promo is None:
                promo = await PromoCodeService.issue_code(
                    session,
                    effects=config.effects,
                    code=None,
                    max_activations=1,
                    valid_until=now + timedelta(days=config.valid_days),
                    origin=origin,
                    created_by_admin_id=None,
                    user_id=user_id,
                    max_duration_multiplier=float(self.settings.PROMO_DURATION_MULTIPLIER_MAX),
                    max_traffic_multiplier=float(self.settings.PROMO_TRAFFIC_MULTIPLIER_MAX),
                )
            if promo.archived_at or not promo.is_active:
                return
            code = str(promo.code)
            expires = promo.valid_until.strftime("%Y-%m-%d %H:%M")

        # Commit issuance before sending so a failed delivery can reuse the same code.
        async with self.sessions.begin() as session:
            user = await session.scalar(user_query)
            if user is None or user.telegram_birthday_sent_year == now.year:
                return
            message = self.i18n.gettext(
                user.language_code or self.settings.DEFAULT_LANGUAGE,
                "birthday_activation_code_message",
                code=code,
                expires=expires,
            )
            try:
                await self.bot.send_message(telegram_id, message, parse_mode=None)
            except (TelegramBadRequest, TelegramForbiddenError):
                user.telegram_birthday_month_day = None
                return
            user.telegram_birthday_sent_year = now.year

    async def run(self) -> None:
        while True:
            delay = 30
            try:
                async with self.sessions() as session:
                    config = await load_birthday_activation_config(session, self.settings)
                if config.enabled:
                    await self._tick(datetime.now(UTC), config)
            except TelegramRetryAfter as exc:
                delay = max(delay, exc.retry_after)
            except Exception:
                logger.exception("Birthday activation worker tick failed")
            await asyncio.sleep(delay)
