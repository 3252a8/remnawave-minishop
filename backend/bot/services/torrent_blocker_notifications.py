from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
from collections.abc import Awaitable, Callable
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

TELEGRAM_TORRENT_NOTIFICATION_EVENT = "telegram_torrent_blocker_notification_sent"
EMAIL_TORRENT_NOTIFICATION_EVENT = "email_torrent_blocker_notification_sent"
_FINGERPRINT_DOMAIN = b"minishop:torrent-blocker-report:v1\0"


def _utc_now() -> datetime:
    return datetime.now(UTC)


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


def torrent_blocker_event_fingerprint(
    context: dict[str, Any],
    *,
    secret: str,
) -> str:
    fingerprint_key = secret.strip().encode()
    if not fingerprint_key:
        raise ValueError("Torrent blocker fingerprint secret is not configured")
    normalized = json.dumps(context, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hmac.new(
        fingerprint_key,
        _FINGERPRINT_DOMAIN + normalized.encode(),
        hashlib.sha256,
    ).hexdigest()[:24]


@dataclass(frozen=True, slots=True)
class TorrentBlockerReport:
    blocked: bool
    ip: str
    block_duration_seconds: int
    processed_at: datetime | None
    will_unblock_at: datetime | None
    fingerprint: str

    @classmethod
    def from_context(
        cls,
        context: dict[str, Any],
        *,
        fingerprint_secret: str,
    ) -> TorrentBlockerReport:
        duration = _non_negative_int(context.get("block_duration"))
        processed_at = _parse_datetime(
            context.get("processed_at") or context.get("event_timestamp")
        )
        will_unblock_at = _parse_datetime(context.get("will_unblock_at"))
        if will_unblock_at is None and processed_at is not None and duration:
            try:
                will_unblock_at = processed_at + timedelta(seconds=duration)
            except OverflowError:
                will_unblock_at = None
        return cls(
            blocked=context.get("blocked") is True,
            ip=_validated_ip(context.get("ip")),
            block_duration_seconds=duration,
            processed_at=processed_at,
            will_unblock_at=will_unblock_at,
            fingerprint=torrent_blocker_event_fingerprint(
                context,
                secret=fingerprint_secret,
            ),
        )

    def is_stale(self, *, now: datetime) -> bool:
        return self.will_unblock_at is not None and self.will_unblock_at <= now


@dataclass(frozen=True, slots=True)
class TorrentBlockerNotificationDelivery:
    telegram_sent: bool = False
    email_sent: bool = False


class TorrentBlockerDeliveryError(RuntimeError):
    def __init__(self, channels: list[str]) -> None:
        self.channels = tuple(channels)
        super().__init__(
            "Transient torrent blocker notification failure: " + ", ".join(self.channels)
        )


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
        if not self.settings.TORRENT_BLOCKER_NOTIFICATIONS_ENABLED:
            self._log_outcome(outcome="disabled")
            return TorrentBlockerNotificationDelivery()

        report = TorrentBlockerReport.from_context(
            context,
            fingerprint_secret=str(self.settings.PANEL_WEBHOOK_SECRET or ""),
        )
        now = _utc_now()
        if not report.blocked:
            logger.info(
                "Torrent blocker report ignored because no IP block was applied; panel_uuid=%s",
                self._panel_uuid(user_payload) or "N/A",
            )
            self._log_outcome(outcome="not_blocked", fingerprint=report.fingerprint)
            return TorrentBlockerNotificationDelivery()
        if report.is_stale(now=now):
            logger.info(
                "Stale torrent blocker report ignored; panel_uuid=%s fingerprint=%s",
                self._panel_uuid(user_payload) or "N/A",
                report.fingerprint,
            )
            self._log_outcome(outcome="stale", fingerprint=report.fingerprint)
            return TorrentBlockerNotificationDelivery()

        async with self.async_session_factory() as session:
            user = await self._resolve_user(session, user_payload)
            if user is None:
                logger.warning(
                    "Torrent blocker report cannot be matched to a local user; panel_uuid=%s",
                    self._panel_uuid(user_payload) or "N/A",
                )
                self._log_outcome(outcome="user_not_found", fingerprint=report.fingerprint)
                return TorrentBlockerNotificationDelivery()

            user_id = int(user.user_id)
            language = str(user.language_code or self.settings.DEFAULT_LANGUAGE or "ru")
            message_text = self._message_text(language, report)
            failures: list[tuple[str, Exception]] = []
            telegram_sent, telegram_error = await self._deliver_channel(
                session,
                user_id=user_id,
                channel="telegram",
                enabled=self.settings.TORRENT_BLOCKER_TELEGRAM_NOTIFICATIONS_ENABLED,
                fingerprint=report.fingerprint,
                deliver=lambda locked_session, locked_user: self._send_telegram(
                    locked_session,
                    locked_user,
                    user_payload=user_payload,
                    report=report,
                    message_text=message_text,
                    sent_at=now,
                ),
            )
            if telegram_error is not None:
                failures.append(("telegram", telegram_error))

            email_sent, email_error = await self._deliver_channel(
                session,
                user_id=user_id,
                channel="email",
                enabled=self.settings.TORRENT_BLOCKER_EMAIL_NOTIFICATIONS_ENABLED,
                fingerprint=report.fingerprint,
                deliver=lambda locked_session, locked_user: self._send_email(
                    locked_session,
                    locked_user,
                    report=report,
                    message_text=message_text,
                    sent_at=now,
                ),
            )
            if email_error is not None:
                failures.append(("email", email_error))

            if failures:
                error = TorrentBlockerDeliveryError([channel for channel, _exc in failures])
                raise error from failures[0][1]
            return TorrentBlockerNotificationDelivery(
                telegram_sent=telegram_sent,
                email_sent=email_sent,
            )

    async def _deliver_channel(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        channel: str,
        enabled: bool,
        fingerprint: str,
        deliver: Callable[[AsyncSession, User], Awaitable[bool]],
    ) -> tuple[bool, Exception | None]:
        if not enabled:
            self._log_outcome(
                outcome="channel_disabled",
                channel=channel,
                user_id=user_id,
                fingerprint=fingerprint,
            )
            return False, None

        locked_user = await user_dal.lock_user_by_id(session, user_id)
        if locked_user is None:
            self._log_outcome(
                outcome="user_deleted",
                channel=channel,
                user_id=user_id,
                fingerprint=fingerprint,
            )
            return False, None

        try:
            sent = await deliver(session, locked_user)
            await session.commit()
            return sent, None
        except Exception as exc:
            await session.rollback()
            logger.exception(
                "Transient torrent blocker notification failure; channel=%s user_id=%s",
                channel,
                user_id,
            )
            self._log_outcome(
                outcome="transient_failure",
                channel=channel,
                user_id=user_id,
                fingerprint=fingerprint,
            )
            return False, exc

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

        if self.settings.TORRENT_BLOCKER_NOTIFICATION_INCLUDE_IP and report.ip:
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
        chat_id = self._telegram_chat_id(user, user_payload)
        if chat_id is None:
            self._log_outcome(
                outcome="no_recipient",
                channel="telegram",
                user_id=int(user.user_id),
                fingerprint=report.fingerprint,
            )
            return False

        status = normalize_telegram_notification_status(user.telegram_notifications_status)
        if status in {TELEGRAM_NOTIFICATIONS_NEEDS_START, TELEGRAM_NOTIFICATIONS_BLOCKED}:
            self._log_outcome(
                outcome="recipient_unavailable",
                channel="telegram",
                user_id=int(user.user_id),
                fingerprint=report.fingerprint,
            )
            return False
        suppression_reason = await self._channel_suppression_reason(
            session,
            user_id=int(user.user_id),
            event_type=TELEGRAM_TORRENT_NOTIFICATION_EVENT,
            fingerprint=report.fingerprint,
            now=sent_at,
        )
        if suppression_reason is not None:
            self._log_outcome(
                outcome=suppression_reason,
                channel="telegram",
                user_id=int(user.user_id),
                fingerprint=report.fingerprint,
            )
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
                self._log_outcome(
                    outcome="recipient_unavailable",
                    channel="telegram",
                    user_id=int(user.user_id),
                    fingerprint=report.fingerprint,
                )
                return False
            logger.exception("Failed to send torrent blocker notification to Telegram")
            self._log_outcome(
                outcome="permanent_failure",
                channel="telegram",
                user_id=int(user.user_id),
                fingerprint=report.fingerprint,
            )
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
        self._log_outcome(
            outcome="sent",
            channel="telegram",
            user_id=int(user.user_id),
            fingerprint=report.fingerprint,
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
        if not self.settings.email_auth_configured:
            self._log_outcome(
                outcome="channel_unavailable",
                channel="email",
                user_id=int(user.user_id),
                fingerprint=report.fingerprint,
            )
            return False
        if not str(user.email or "").strip():
            self._log_outcome(
                outcome="no_recipient",
                channel="email",
                user_id=int(user.user_id),
                fingerprint=report.fingerprint,
            )
            return False
        suppression_reason = await self._channel_suppression_reason(
            session,
            user_id=int(user.user_id),
            event_type=EMAIL_TORRENT_NOTIFICATION_EVENT,
            fingerprint=report.fingerprint,
            now=sent_at,
        )
        if suppression_reason is not None:
            self._log_outcome(
                outcome=suppression_reason,
                channel="email",
                user_id=int(user.user_id),
                fingerprint=report.fingerprint,
            )
            return False

        dashboard_url = str(self.settings.SUBSCRIPTION_MINI_APP_URL or "").strip() or None
        sent = await send_user_notification_email(
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
            raise_on_error=True,
        )
        self._log_outcome(
            outcome="sent" if sent else "channel_unavailable",
            channel="email",
            user_id=int(user.user_id),
            fingerprint=report.fingerprint,
        )
        return sent

    async def _channel_suppression_reason(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        event_type: str,
        fingerprint: str,
        now: datetime,
    ) -> str | None:
        if await message_log_dal.has_target_event_content(
            session,
            target_user_id=user_id,
            event_type=event_type,
            content_fragment=f"fingerprint={fingerprint}",
        ):
            return "duplicate"

        cooldown_seconds = self.settings.TORRENT_BLOCKER_NOTIFICATION_COOLDOWN_SECONDS
        if cooldown_seconds == 0:
            return None
        recent = await message_log_dal.has_recent_target_event(
            session,
            target_user_id=user_id,
            event_type=event_type,
            since=now - timedelta(seconds=cooldown_seconds),
        )
        return "cooldown" if recent else None

    @staticmethod
    def _log_outcome(
        *,
        outcome: str,
        channel: str = "event",
        user_id: int | None = None,
        fingerprint: str = "",
    ) -> None:
        logger.info(
            "metric torrent_blocker_notification_total=1 outcome=%s channel=%s "
            "user_id=%s fingerprint=%s",
            outcome,
            channel,
            user_id if user_id is not None else "N/A",
            fingerprint or "N/A",
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
