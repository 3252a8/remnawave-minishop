from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from aiogram import Bot
from sqlalchemy.orm import sessionmaker

from bot.infra import events
from bot.middlewares.i18n import JsonI18n
from bot.services.email_auth_service import EmailAuthService
from bot.services.notification_service import NotificationService
from config.settings import Settings
from db.dal import message_log_dal, subscription_dal, support_dal, user_dal
from db.models import SupportTicket, SupportTicketMessage, User

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdminNotificationDecision:
    send_telegram: bool
    send_email: bool


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _notification_due(
    last_sent_at: Optional[datetime],
    *,
    now: datetime,
    cooldown_seconds: int,
) -> bool:
    last_sent_at = _as_utc(last_sent_at)
    if last_sent_at is None:
        return True
    cooldown = max(0, int(cooldown_seconds or 0))
    if cooldown <= 0:
        return True
    return (now - last_sent_at).total_seconds() >= cooldown


def _support_admin_notification_decision(
    ticket: SupportTicket,
    settings: Settings,
    *,
    now: Optional[datetime] = None,
    admin_email_notifications_enabled: Optional[bool] = None,
) -> AdminNotificationDecision:
    now = _as_utc(now) or datetime.now(timezone.utc)
    unread_count = max(0, int(getattr(ticket, "unread_admin_count", 0) or 0))
    if unread_count <= 0:
        return AdminNotificationDecision(send_telegram=False, send_email=False)

    first_unread = unread_count <= 1
    send_telegram = first_unread or _notification_due(
        getattr(ticket, "admin_last_notified_at", None),
        now=now,
        cooldown_seconds=getattr(settings, "SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS", 300),
    )
    if admin_email_notifications_enabled is None:
        admin_email_notifications_enabled = bool(
            getattr(settings, "SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED", False)
        )
    send_email = bool(admin_email_notifications_enabled) and (
        first_unread
        or _notification_due(
            getattr(ticket, "admin_last_emailed_at", None),
            now=now,
            cooldown_seconds=getattr(settings, "SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS", 1800),
        )
    )
    return AdminNotificationDecision(send_telegram=send_telegram, send_email=send_email)


def _format_support_remaining(seconds: int, lang: str) -> str:
    if seconds <= 0:
        return "Subscription inactive" if lang == "en" else "Подписка не активна"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if lang == "en":
        if days > 0:
            return f"{days} d. {hours} h."
        if hours > 0:
            return f"{hours} h. {minutes} min."
        return f"{max(1, minutes)} min."
    if days > 0:
        return f"{days} д. {hours} ч."
    if hours > 0:
        return f"{hours} ч. {minutes} мин."
    return f"{max(1, minutes)} мин."


class TicketForbidden(PermissionError):
    pass


class TicketRateLimited(RuntimeError):
    pass


class TicketNotFound(LookupError):
    pass


class SupportService:
    def __init__(
        self,
        session_factory: sessionmaker,
        settings: Settings,
        bot: Bot,
        i18n: Optional[JsonI18n],
        notification_service: Optional[NotificationService] = None,
        email_auth_service: Optional[EmailAuthService] = None,
    ):
        self.session_factory = session_factory
        self.settings = settings
        self.bot = bot
        self.i18n = i18n
        self.email_auth_service = email_auth_service or EmailAuthService(settings, i18n)
        self.notification_service = notification_service or NotificationService(
            bot,
            settings,
            i18n,
            session_factory=session_factory,
            email_auth_service=self.email_auth_service,
        )

    @staticmethod
    def _schedule_notification(coro, error_message: str, *error_args: Any) -> None:
        async def _runner():
            try:
                await coro
            except Exception:
                logger.exception(error_message, *error_args)

        asyncio.create_task(_runner(), name="support-notification")

    async def _ensure_user_allowed(self, session, user_id: int) -> User:
        user = await user_dal.get_user_by_id(session, user_id)
        if not user or user.is_banned or not self.settings.SUPPORT_TICKETS_ENABLED:
            raise TicketForbidden("ticket_forbidden")
        return user

    async def create_ticket(
        self,
        user_id: int,
        subject: str,
        category: str,
        priority: str,
        first_message_body: str,
    ) -> SupportTicket:
        async with self.session_factory() as session:
            user = await self._ensure_user_allowed(session, user_id)
            limit = max(0, int(self.settings.SUPPORT_TICKET_RATE_LIMIT_PER_HOUR or 0))
            if limit:
                recent = await support_dal.count_recent_tickets_for_user(session, user_id, 3600)
                if recent >= limit:
                    raise TicketRateLimited("ticket_rate_limited")
            ticket = await support_dal.create_ticket(
                session,
                user_id,
                subject[: self.settings.SUPPORT_TICKET_MAX_SUBJECT_LENGTH],
                category,
                priority,
                first_message_body[: self.settings.SUPPORT_TICKET_MAX_BODY_LENGTH],
            )
            snapshot = await self.build_user_snapshot(user, session=session)
            await session.commit()

        await events.emit(
            events.SUPPORT_TICKET_CREATED,
            {
                "user_id": user_id,
                "ticket_id": ticket.ticket_id,
                "category": category,
                "priority": priority,
            },
        )

        try:
            await self.notification_service.notify_new_support_ticket(
                ticket,
                user,
                first_message_body,
                snapshot,
            )
        except Exception:
            logger.exception("Failed to notify about support ticket %s", ticket.ticket_id)
        return ticket

    async def reply_as_user(
        self,
        user_id: int,
        ticket_id: int,
        body: str,
    ) -> tuple[SupportTicket, SupportTicketMessage]:
        async with self.session_factory() as session:
            user = await self._ensure_user_allowed(session, user_id)
            ticket, _messages = await support_dal.get_ticket(session, ticket_id)
            if not ticket or ticket.user_id != user_id:
                raise TicketNotFound("not_found")
            message = await support_dal.add_message(
                session,
                ticket_id,
                "user",
                user_id,
                body[: self.settings.SUPPORT_TICKET_MAX_BODY_LENGTH],
            )
            if message is None:
                raise TicketNotFound("not_found")
            await session.refresh(ticket)
            notification_at = datetime.now(timezone.utc)
            admin_email_notifications_enabled = (
                await self.notification_service.support_admin_email_notifications_enabled()
            )
            notification_decision = _support_admin_notification_decision(
                ticket,
                self.settings,
                now=notification_at,
                admin_email_notifications_enabled=admin_email_notifications_enabled,
            )
            await support_dal.record_admin_notification(
                session,
                ticket_id,
                notified_at=notification_at if notification_decision.send_telegram else None,
                emailed_at=notification_at if notification_decision.send_email else None,
            )
            snapshot = await self.build_user_snapshot(user, session=session)
            await session.commit()

        if notification_decision.send_telegram or notification_decision.send_email:
            self._schedule_notification(
                self.notification_service.notify_support_user_reply(
                    ticket,
                    message,
                    user,
                    snapshot,
                    unread_count=int(ticket.unread_admin_count or 0),
                    send_telegram=notification_decision.send_telegram,
                    send_email=notification_decision.send_email,
                ),
                "Failed to notify about support user reply %s",
                ticket_id,
            )
        return ticket, message

    async def reply_as_admin(
        self,
        admin_id: int,
        ticket_id: int,
        body: str,
        *,
        is_internal_note: bool = False,
    ) -> tuple[SupportTicket, SupportTicketMessage]:
        async with self.session_factory() as session:
            ticket, _messages = await support_dal.get_ticket(
                session,
                ticket_id,
                include_internal=True,
            )
            if not ticket:
                raise TicketNotFound("not_found")
            user = await user_dal.get_user_by_id(session, ticket.user_id)
            message = await support_dal.add_message(
                session,
                ticket_id,
                "admin",
                admin_id,
                body[: self.settings.SUPPORT_TICKET_MAX_BODY_LENGTH],
                is_internal_note=is_internal_note,
            )
            if message is None:
                raise TicketNotFound("not_found")
            await support_dal.mark_read(session, ticket_id, "admin")
            if not is_internal_note:
                await message_log_dal.create_message_log_no_commit(
                    session,
                    {
                        "user_id": admin_id,
                        "event_type": "support_admin_reply",
                        "content": f"Support ticket #{ticket_id} reply",
                        "is_admin_event": True,
                        "target_user_id": ticket.user_id,
                    },
                )
            await session.refresh(ticket)
            await session.commit()

        if user and not is_internal_note:
            self._schedule_notification(
                self.notification_service.notify_support_admin_reply(ticket, message, user),
                "Failed to notify user about support admin reply %s",
                ticket_id,
            )
        return ticket, message

    async def change_status(self, admin_id: int, ticket_id: int, status: str) -> SupportTicket:
        return await self._update_and_audit(admin_id, ticket_id, status=status)

    async def change_priority(self, admin_id: int, ticket_id: int, priority: str) -> SupportTicket:
        return await self._update_and_audit(admin_id, ticket_id, priority=priority)

    async def change_category(self, admin_id: int, ticket_id: int, category: str) -> SupportTicket:
        return await self._update_and_audit(admin_id, ticket_id, category=category)

    async def assign_admin(
        self,
        admin_id: int,
        ticket_id: int,
        assigned_admin_id: Optional[int],
    ) -> SupportTicket:
        return await self._update_and_audit(
            admin_id,
            ticket_id,
            assigned_admin_id=assigned_admin_id,
        )

    async def close_ticket(self, admin_id: int, ticket_id: int) -> SupportTicket:
        ticket = await self._update_and_audit(
            admin_id,
            ticket_id,
            status="closed",
            closed_by_admin_id=admin_id,
        )
        async with self.session_factory() as session:
            user = await user_dal.get_user_by_id(session, ticket.user_id)
        if user:
            try:
                await self.notification_service.notify_support_ticket_closed(ticket, user, admin_id)
            except Exception:
                logger.exception("Failed to notify user about support close %s", ticket_id)
        return ticket

    async def _update_and_audit(
        self,
        admin_id: int,
        ticket_id: int,
        **updates: Any,
    ) -> SupportTicket:
        async with self.session_factory() as session:
            ticket = await support_dal.update_ticket(session, ticket_id, **updates)
            if not ticket:
                raise TicketNotFound("not_found")
            await message_log_dal.create_message_log_no_commit(
                session,
                {
                    "user_id": admin_id,
                    "event_type": "support_ticket_update",
                    "content": f"Support ticket #{ticket_id}: {updates}",
                    "is_admin_event": True,
                    "target_user_id": ticket.user_id,
                },
            )
            await session.commit()
            return ticket

    async def mark_read_as_user(self, user_id: int, ticket_id: int) -> None:
        async with self.session_factory() as session:
            ticket, _messages = await support_dal.get_ticket(session, ticket_id)
            if not ticket or ticket.user_id != user_id:
                raise TicketNotFound("not_found")
            await support_dal.mark_read(session, ticket_id, "user")
            await session.commit()

    async def mark_read_as_admin(self, ticket_id: int) -> None:
        async with self.session_factory() as session:
            await support_dal.mark_read(session, ticket_id, "admin")
            await session.commit()

    async def build_user_snapshot(self, user: User, *, session=None) -> dict:
        owns_session = session is None
        if owns_session:
            session = self.session_factory()
            await session.__aenter__()
        try:
            sub = None
            if getattr(user, "panel_user_uuid", None):
                sub = await subscription_dal.get_active_subscription_by_user_id(
                    session,
                    int(user.user_id),
                    user.panel_user_uuid,
                )
            lang = (
                getattr(user, "language_code", None) or self.settings.DEFAULT_LANGUAGE or "ru"
            ).split("-")[0]
            tariff_name = ""
            if sub and getattr(sub, "tariff_key", None) and self.settings.tariffs_config:
                try:
                    tariff = self.settings.tariffs_config.require(str(sub.tariff_key))
                    tariff_name = tariff.name(lang)
                except Exception:
                    tariff_name = str(sub.tariff_key or "")
            end_date = getattr(sub, "end_date", None)
            seconds_left = (
                max(0, int((end_date - datetime.now(timezone.utc)).total_seconds()))
                if end_date
                else 0
            )
            return {
                "user_id": int(user.user_id),
                "name": " ".join(
                    part for part in [user.first_name, getattr(user, "last_name", None)] if part
                )
                or user.username
                or str(user.user_id),
                "username": user.username,
                "email": user.email,
                "telegram_id": user.telegram_id,
                "language": lang,
                "registration_date": (
                    user.registration_date.isoformat() if user.registration_date else None
                ),
                "email_login": bool(user.email and user.email_verified_at),
                "subscription_active": bool(sub),
                "panel_status": getattr(sub, "status_from_panel", None) if sub else None,
                "end_date": end_date.isoformat() if end_date else None,
                "remaining": _format_support_remaining(seconds_left, lang),
                "tariff": tariff_name or (getattr(sub, "tariff_key", None) if sub else ""),
                "traffic_regular": self._traffic_snapshot(
                    getattr(sub, "traffic_used_bytes", 0) if sub else 0,
                    self._regular_limit(sub),
                ),
                "traffic_premium": self._traffic_snapshot(
                    getattr(sub, "premium_used_bytes", 0) if sub else 0,
                    self._premium_limit(sub),
                ),
                "is_throttled": bool(getattr(sub, "is_throttled", False)) if sub else False,
                "topup_balance_bytes": int(getattr(sub, "topup_balance_bytes", 0) or 0)
                if sub
                else 0,
                "premium_topup_balance_bytes": int(
                    getattr(sub, "premium_topup_balance_bytes", 0) or 0
                )
                if sub
                else 0,
                "lifetime_used_traffic_bytes": int(user.lifetime_used_traffic_bytes or 0),
            }
        finally:
            if owns_session:
                await session.__aexit__(None, None, None)

    @staticmethod
    def _regular_limit(sub) -> int:
        if not sub:
            return 0
        if getattr(sub, "regular_unlimited_override", False):
            return 0
        return int(
            (sub.traffic_limit_bytes or 0)
            + (sub.topup_balance_bytes or 0)
            + (getattr(sub, "regular_bonus_bytes", 0) or 0)
        )

    @staticmethod
    def _premium_limit(sub) -> int:
        if not sub:
            return 0
        if getattr(sub, "premium_unlimited_override", False):
            return 0
        return int(
            (sub.premium_baseline_bytes or 0)
            + (sub.premium_topup_balance_bytes or 0)
            + (getattr(sub, "premium_topup_used_bytes", 0) or 0)
            + (getattr(sub, "premium_bonus_bytes", 0) or 0)
        )

    @staticmethod
    def _traffic_snapshot(used: Any, limit: Any) -> dict:
        used_value = max(0, int(used or 0))
        limit_value = max(0, int(limit or 0))
        percent = round((used_value / limit_value) * 100, 2) if limit_value else 0
        left = max(0, limit_value - used_value) if limit_value else 0
        return {
            "used_bytes": used_value,
            "limit_bytes": limit_value,
            "percent": percent,
            "left_bytes": left,
        }
