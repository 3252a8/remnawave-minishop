import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import get_subscribe_only_markup
from bot.middlewares.i18n import JsonI18n
from bot.services.email_auth_service import EmailAuthService
from bot.services.email_templates import render_subscription_lifecycle_notification
from config.settings import Settings
from db.dal import subscription_dal
from db.models import Subscription, User


@dataclass(frozen=True)
class SubscriptionNotificationStage:
    key: str
    message_key: str
    days_left: Optional[int] = None
    hours_before: Optional[int] = None


@dataclass(frozen=True)
class SubscriptionNotificationDelivery:
    telegram_sent: bool = False
    email_sent: bool = False

    @property
    def any_sent(self) -> bool:
        return self.telegram_sent or self.email_sent


class SubscriptionLifecycleNotificationService:
    def __init__(
        self,
        settings: Settings,
        bot: Bot,
        i18n: JsonI18n,
        *,
        email_service: Optional[EmailAuthService] = None,
    ) -> None:
        self.settings = settings
        self.bot = bot
        self.i18n = i18n
        self.email_service = email_service

    async def send_stage(
        self,
        session: AsyncSession,
        sub: Subscription,
        stage: SubscriptionNotificationStage,
        *,
        user: Optional[User] = None,
        telegram_markup: Optional[InlineKeyboardMarkup] = None,
        extra_text: str = "",
        end_date_text: Optional[str] = None,
        sent_at: Optional[datetime] = None,
    ) -> SubscriptionNotificationDelivery:
        if sent_at is None:
            sent_at = datetime.now(timezone.utc)

        resolved_user = user or getattr(sub, "user", None)
        lang = getattr(resolved_user, "language_code", None) or self.settings.DEFAULT_LANGUAGE
        user_id = int(getattr(sub, "user_id", 0) or 0)
        user_name = getattr(resolved_user, "first_name", None) or f"User {user_id}"
        final_end_date_text = end_date_text
        if final_end_date_text is None:
            end_date = self._as_utc(getattr(sub, "end_date", None))
            final_end_date_text = end_date.strftime("%Y-%m-%d") if end_date else ""

        kwargs = {"user_name": user_name, "end_date": final_end_date_text}
        if stage.hours_before is not None:
            kwargs["hours"] = stage.hours_before

        message_text = self.i18n.gettext(lang, stage.message_key, **kwargs)
        final_extra_text = str(extra_text or "").strip()
        if final_extra_text:
            message_text = f"{message_text}\n\n{final_extra_text}"

        telegram_sent = await self._send_telegram(
            session,
            sub,
            stage,
            resolved_user,
            lang=lang,
            message_text=message_text,
            markup=telegram_markup or get_subscribe_only_markup(lang, self.i18n),
            sent_at=sent_at,
        )
        email_sent = await self._send_email(
            session,
            sub,
            stage,
            resolved_user,
            lang=lang,
            message_text=message_text,
            end_date_text=final_end_date_text,
            sent_at=sent_at,
        )
        return SubscriptionNotificationDelivery(
            telegram_sent=telegram_sent,
            email_sent=email_sent,
        )

    async def _send_telegram(
        self,
        session: AsyncSession,
        sub: Subscription,
        stage: SubscriptionNotificationStage,
        user: Optional[User],
        *,
        lang: str,
        message_text: str,
        markup: Optional[InlineKeyboardMarkup],
        sent_at: datetime,
    ) -> bool:
        chat_id = self._telegram_chat_id(user, getattr(sub, "user_id", None))
        if chat_id is None:
            return False
        if await self._already_sent(session, sub.subscription_id, stage.key, "telegram"):
            return False
        try:
            await self.bot.send_message(chat_id, message_text, reply_markup=markup)
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            if self._is_terminal_telegram_delivery_error(exc):
                logging.warning(
                    "Skipping subscription notification %s for unreachable Telegram user %s: %s",
                    stage.key,
                    chat_id,
                    exc,
                )
                try:
                    await subscription_dal.record_subscription_notification(
                        session,
                        sub.subscription_id,
                        self._channel_key(stage.key, "telegram"),
                        sent_at=sent_at,
                    )
                except Exception:
                    logging.exception(
                        "Failed to record skipped subscription notification %s "
                        "for Telegram user %s",
                        stage.key,
                        chat_id,
                    )
                return False
            logging.exception(
                "Failed to send subscription notification %s to Telegram user %s",
                stage.key,
                chat_id,
            )
            return False
        except Exception:
            logging.exception(
                "Failed to send subscription notification %s to Telegram user %s",
                stage.key,
                chat_id,
            )
            return False
        await subscription_dal.record_subscription_notification(
            session,
            sub.subscription_id,
            self._channel_key(stage.key, "telegram"),
            sent_at=sent_at,
        )
        return True

    async def _send_email(
        self,
        session: AsyncSession,
        sub: Subscription,
        stage: SubscriptionNotificationStage,
        user: Optional[User],
        *,
        lang: str,
        message_text: str,
        end_date_text: str,
        sent_at: datetime,
    ) -> bool:
        if not getattr(self.settings, "SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED", True):
            return False
        if not getattr(self.settings, "email_auth_configured", False):
            return False
        recipient = str(getattr(user, "email", "") or "").strip() if user else ""
        if not recipient:
            return False
        if await self._already_sent(session, sub.subscription_id, stage.key, "email"):
            return False

        try:
            content = render_subscription_lifecycle_notification(
                self.settings,
                language_code=lang,
                notification_key=stage.key,
                message_text=message_text,
                end_date_text=end_date_text,
                dashboard_url=(self.settings.SUBSCRIPTION_MINI_APP_URL or "").strip() or None,
                days_left=stage.days_left,
                hours_before=stage.hours_before,
                i18n=self.i18n,
            )
            email_service = self.email_service or EmailAuthService(self.settings, self.i18n)
            await email_service.send_rendered_email(email=recipient, content=content)
        except Exception:
            logging.exception(
                "Failed to send subscription notification %s to email %s",
                stage.key,
                recipient,
            )
            return False
        await subscription_dal.record_subscription_notification(
            session,
            sub.subscription_id,
            self._channel_key(stage.key, "email"),
            sent_at=sent_at,
        )
        return True

    async def _already_sent(
        self,
        session: AsyncSession,
        subscription_id: int,
        stage_key: str,
        channel: str,
    ) -> bool:
        channel_key = self._channel_key(stage_key, channel)
        if await subscription_dal.has_subscription_notification(
            session,
            subscription_id,
            channel_key,
        ):
            return True

        # Legacy rows were stored without a channel. Treat them as Telegram-only
        # history so existing installs do not re-send old bot messages, while
        # still allowing the newly introduced email channel to catch up.
        return channel == "telegram" and await subscription_dal.has_subscription_notification(
            session,
            subscription_id,
            stage_key,
        )

    @staticmethod
    def _channel_key(stage_key: str, channel: str) -> str:
        return f"{stage_key}:{channel}"

    @staticmethod
    def _telegram_chat_id(user: Optional[User], fallback_user_id: Optional[int]) -> Optional[int]:
        for candidate in (getattr(user, "telegram_id", None), fallback_user_id):
            try:
                chat_id = int(candidate or 0)
            except (TypeError, ValueError):
                continue
            if chat_id > 0:
                return chat_id
        return None

    @staticmethod
    def _is_terminal_telegram_delivery_error(
        exc: TelegramBadRequest | TelegramForbiddenError,
    ) -> bool:
        if isinstance(exc, TelegramForbiddenError):
            return True
        message = str(exc).lower()
        return any(
            token in message
            for token in (
                "chat not found",
                "bot was blocked",
                "bot can't initiate conversation",
                "user is deactivated",
            )
        )

    @staticmethod
    def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
