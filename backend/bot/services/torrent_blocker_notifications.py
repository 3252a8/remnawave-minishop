from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.services.message_audit import log_user_message_delivery
from bot.services.telegram_notifications import (
    TELEGRAM_NOTIFICATIONS_BLOCKED,
    TELEGRAM_NOTIFICATIONS_ENABLED,
    TELEGRAM_NOTIFICATIONS_NEEDS_START,
    mark_telegram_notifications_status,
    normalize_telegram_notification_status,
    telegram_notification_status_from_error,
)
from bot.services.user_email_notifications import send_user_notification_email
from config.settings import Settings
from db.dal import message_log_dal, user_dal
from db.models import User

logger = logging.getLogger(__name__)

TORRENT_BLOCKER_EVENT = "torrent_blocker.report"
TELEGRAM_TORRENT_NOTIFICATION_EVENT = "telegram_torrent_blocker_notification_sent"
EMAIL_TORRENT_NOTIFICATION_EVENT = "email_torrent_blocker_notification_sent"


def _parse_datetime(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _non_negative_int(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    if not isinstance(value, (int, float, str, bytes, bytearray)):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, parsed)


def _validated_ip(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return ""


def torrent_blocker_event_fingerprint(context: dict[str, Any]) -> str:
    normalized = json.dumps(context, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode()).hexdigest()[:24]


@dataclass(frozen=True, slots=True)
class TorrentBlockerReport:
    blocked: bool
    ip: str
    block_duration_seconds: int
    processed_at: datetime | None
    will_unblock_at: datetime | None
    fingerprint: str

    @classmethod
    def from_context(cls, context: dict[str, Any]) -> TorrentBlockerReport:
        duration = _non_negative_int(context.get("block_duration"))
        processed_at = _parse_datetime(
            context.get("processed_at") or context.get("event_timestamp")
        )
        will_unblock_at = _parse_datetime(context.get("will_unblock_at"))
        if will_unblock_at is None and processed_at is not None and duration:
            will_unblock_at = processed_at + timedelta(seconds=duration)
        return cls(
            blocked=context.get("blocked") is True,
            ip=_validated_ip(context.get("ip")),
            block_duration_seconds=duration,
            processed_at=processed_at,
            will_unblock_at=will_unblock_at,
            fingerprint=torrent_blocker_event_fingerprint(context),
        )


@dataclass(frozen=True, slots=True)
class TorrentBlockerNotificationDelivery:
    telegram_sent: bool = False
    email_sent: bool = False


class TorrentBlockerNotificationService:
    def __init__(
        self,
        settings: Settings,
        bot: Bot,
        i18n: JsonI18n,
        async_session_factory: sessionmaker,
    ) -> None:
        self.settings = settings
        self.bot = bot
        self.i18n = i18n
        self.async_session_factory = async_session_factory

    async def handle(
        self,
        user_payload: dict[str, Any],
        context: dict[str, Any],
    ) -> TorrentBlockerNotificationDelivery:
        if not getattr(self.settings, "TORRENT_BLOCKER_NOTIFICATIONS_ENABLED", False):
            return TorrentBlockerNotificationDelivery()

        report = TorrentBlockerReport.from_context(context)
        if not report.blocked:
            logger.info(
                "Torrent blocker report ignored because no IP block was applied; panel_uuid=%s",
                self._panel_uuid(user_payload) or "N/A",
            )
            return TorrentBlockerNotificationDelivery()

        async with self.async_session_factory() as session:
            user = await self._resolve_user(session, user_payload)
            if user is None:
                logger.warning(
                    "Torrent blocker report cannot be matched to a local user; panel_uuid=%s",
                    self._panel_uuid(user_payload) or "N/A",
                )
                return TorrentBlockerNotificationDelivery()

            locked_user = await user_dal.lock_user_by_id(session, int(user.user_id))
            if locked_user is None:
                return TorrentBlockerNotificationDelivery()
            user = locked_user

            now = datetime.now(UTC)
            language = str(user.language_code or self.settings.DEFAULT_LANGUAGE or "ru")
            message_text = self._message_text(language, report)
            telegram_sent = await self._send_telegram(
                session,
                user,
                user_payload=user_payload,
                report=report,
                message_text=message_text,
                sent_at=now,
            )
            email_sent = await self._send_email(
                session,
                user,
                report=report,
                message_text=message_text,
                sent_at=now,
            )
            await session.commit()
            return TorrentBlockerNotificationDelivery(
                telegram_sent=telegram_sent,
                email_sent=email_sent,
            )

    async def _resolve_user(
        self,
        session: AsyncSession,
        user_payload: dict[str, Any],
    ) -> User | None:
        panel_uuid = self._panel_uuid(user_payload)
        if panel_uuid:
            user = await user_dal.get_user_by_panel_uuid(session, panel_uuid)
            if user is not None:
                return user

        telegram_id = self._positive_int(user_payload.get("telegramId"))
        if telegram_id:
            user = await user_dal.get_user_by_telegram_id(session, telegram_id)
            if user is not None:
                return user
            user = await user_dal.get_user_by_id(session, telegram_id)
            if user is not None:
                return user

        email = str(user_payload.get("email") or "").strip()
        if email:
            return await user_dal.get_user_by_email(session, email)
        return None

    def _message_text(self, language: str, report: TorrentBlockerReport) -> str:
        if report.will_unblock_at is not None:
            message = self.i18n.gettext(
                language,
                "torrent_blocker_notification",
                unblock_at=report.will_unblock_at.strftime("%Y-%m-%d %H:%M UTC"),
            )
        else:
            message = self.i18n.gettext(
                language,
                "torrent_blocker_notification_without_time",
            )

        if getattr(self.settings, "TORRENT_BLOCKER_NOTIFICATION_INCLUDE_IP", False) and report.ip:
            ip_line = self.i18n.gettext(
                language,
                "torrent_blocker_notification_ip",
                ip=report.ip,
            )
            message = f"{message}\n\n{ip_line}"
        return str(message)

    async def _send_telegram(
        self,
        session: AsyncSession,
        user: User,
        *,
        user_payload: dict[str, Any],
        report: TorrentBlockerReport,
        message_text: str,
        sent_at: datetime,
    ) -> bool:
        if not getattr(self.settings, "TORRENT_BLOCKER_TELEGRAM_NOTIFICATIONS_ENABLED", True):
            return False
        chat_id = self._telegram_chat_id(user, user_payload)
        if chat_id is None:
            return False

        status = normalize_telegram_notification_status(user.telegram_notifications_status)
        if status in {TELEGRAM_NOTIFICATIONS_NEEDS_START, TELEGRAM_NOTIFICATIONS_BLOCKED}:
            return False
        if await self._channel_is_suppressed(
            session,
            user_id=int(user.user_id),
            event_type=TELEGRAM_TORRENT_NOTIFICATION_EVENT,
            fingerprint=report.fingerprint,
            now=sent_at,
        ):
            return False

        try:
            await self.bot.send_message(chat_id, message_text)
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            delivery_status = telegram_notification_status_from_error(exc)
            if delivery_status:
                await mark_telegram_notifications_status(
                    session,
                    int(user.user_id),
                    delivery_status,
                )
                return False
            logger.exception("Failed to send torrent blocker notification to Telegram")
            return False
        except Exception:
            logger.exception("Failed to send torrent blocker notification to Telegram")
            return False

        await log_user_message_delivery(
            session,
            target_user_id=int(user.user_id),
            event_type=TELEGRAM_TORRENT_NOTIFICATION_EVENT,
            channel="telegram",
            recipient=str(chat_id),
            content=f"fingerprint={report.fingerprint} message_key=torrent_blocker_notification",
            timestamp=sent_at,
        )
        if status != TELEGRAM_NOTIFICATIONS_ENABLED:
            await mark_telegram_notifications_status(
                session,
                int(user.user_id),
                TELEGRAM_NOTIFICATIONS_ENABLED,
                telegram_id=chat_id,
                checked_at=sent_at,
            )
        return True

    async def _send_email(
        self,
        session: AsyncSession,
        user: User,
        *,
        report: TorrentBlockerReport,
        message_text: str,
        sent_at: datetime,
    ) -> bool:
        if not getattr(self.settings, "TORRENT_BLOCKER_EMAIL_NOTIFICATIONS_ENABLED", False):
            return False
        if await self._channel_is_suppressed(
            session,
            user_id=int(user.user_id),
            event_type=EMAIL_TORRENT_NOTIFICATION_EVENT,
            fingerprint=report.fingerprint,
            now=sent_at,
        ):
            return False

        dashboard_url = str(self.settings.SUBSCRIPTION_MINI_APP_URL or "").strip() or None
        return await send_user_notification_email(
            settings=self.settings,
            i18n=self.i18n,
            user=user,
            subject_key="torrent_blocker_email_subject",
            heading_key="torrent_blocker_email_heading",
            intro_key="torrent_blocker_email_intro",
            message_text=message_text,
            dashboard_url=dashboard_url,
            session=session,
            audit_event_type=EMAIL_TORRENT_NOTIFICATION_EVENT,
            audit_content=(
                f"fingerprint={report.fingerprint} message_key=torrent_blocker_notification"
            ),
        )

    async def _channel_is_suppressed(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        event_type: str,
        fingerprint: str,
        now: datetime,
    ) -> bool:
        if await message_log_dal.has_target_event_content(
            session,
            target_user_id=user_id,
            event_type=event_type,
            content_fragment=f"fingerprint={fingerprint}",
        ):
            return True

        cooldown_seconds = _non_negative_int(
            getattr(self.settings, "TORRENT_BLOCKER_NOTIFICATION_COOLDOWN_SECONDS", 3600)
        )
        if cooldown_seconds == 0:
            return False
        return await message_log_dal.has_recent_target_event(
            session,
            target_user_id=user_id,
            event_type=event_type,
            since=now - timedelta(seconds=cooldown_seconds),
        )

    @staticmethod
    def _panel_uuid(user_payload: dict[str, Any]) -> str:
        return str(
            user_payload.get("uuid")
            or user_payload.get("userUuid")
            or user_payload.get("shortUuid")
            or ""
        ).strip()

    @classmethod
    def _telegram_chat_id(
        cls,
        user: User,
        user_payload: dict[str, Any],
    ) -> int | None:
        for candidate in (
            user.telegram_id,
            user_payload.get("telegramId"),
            user.user_id,
        ):
            chat_id = cls._positive_int(candidate)
            if chat_id:
                return chat_id
        return None

    @staticmethod
    def _positive_int(value: object) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        if not isinstance(value, (int, float, str, bytes, bytearray)):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return parsed if parsed > 0 else None
