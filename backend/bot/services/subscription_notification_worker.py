import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from aiogram import Bot
from aiogram.utils.text_decorations import html_decoration as hd
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, sessionmaker

from bot.infra.redis import redis_lock
from bot.keyboards.inline.user_keyboards import get_subscribe_only_markup
from bot.middlewares.i18n import JsonI18n
from bot.services.message_audit import log_user_message_delivery
from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_lifecycle_notifications import (
    SubscriptionLifecycleNotificationService,
    SubscriptionNotificationStage,
)
from bot.services.subscription_service import SubscriptionService
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
from db.advisory_locks import acquire_subscription_background_sync_lock
from db.dal import subscription_dal
from db.models import Subscription

SUBSCRIPTION_NOTIFICATION_LOCK = "subscription-notification-worker"
DEFAULT_SUBSCRIPTION_NOTIFICATION_TICK_SECONDS = 300
EXPIRED_NOTIFICATION_WINDOW = timedelta(hours=24)
EXPIRED_AFTER_NOTIFICATION_WINDOW = timedelta(hours=48)


class SubscriptionNotificationWorker:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker,
        bot: Bot,
        i18n: JsonI18n,
        panel_service: PanelApiService,
        subscription_service: SubscriptionService,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.bot = bot
        self.i18n = i18n
        self.panel_service = panel_service
        self.subscription_service = subscription_service
        self.lifecycle_notifications = SubscriptionLifecycleNotificationService(
            settings,
            bot,
            i18n,
        )
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                async with redis_lock(
                    self.settings,
                    SUBSCRIPTION_NOTIFICATION_LOCK,
                    ttl_seconds=max(60, self._tick_seconds() - 10),
                ) as acquired:
                    if not acquired:
                        logging.info(
                            "SubscriptionNotificationWorker tick skipped: Redis lock is held"
                        )
                    else:
                        started = time.monotonic()
                        async with self.session_factory() as session:
                            await acquire_subscription_background_sync_lock(session)
                            await self.expiry_tick(session)
                            await self.trial_traffic_tick(session)
                            await session.commit()
                        logging.info(
                            "metric worker_tick_duration_seconds=%.3f "
                            "worker=subscription_notification",
                            time.monotonic() - started,
                        )
            except Exception:
                logging.exception("SubscriptionNotificationWorker tick failed")
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self._tick_seconds())
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self._stopped.set()

    def _tick_seconds(self) -> int:
        return int(
            getattr(
                self.settings,
                "SUBSCRIPTION_NOTIFICATION_WORKER_TICK_SECONDS",
                DEFAULT_SUBSCRIPTION_NOTIFICATION_TICK_SECONDS,
            )
            or DEFAULT_SUBSCRIPTION_NOTIFICATION_TICK_SECONDS
        )

    async def expiry_tick(self, session: AsyncSession) -> None:
        if not getattr(self.settings, "SUBSCRIPTION_NOTIFICATIONS_ENABLED", True):
            return
        now = datetime.now(timezone.utc)
        lower = now - EXPIRED_AFTER_NOTIFICATION_WINDOW
        upper = now + self._max_before_window()
        result = await session.execute(
            select(Subscription)
            .where(
                Subscription.skip_notifications == False,
                Subscription.end_date >= lower,
                Subscription.end_date <= upper,
            )
            .options(selectinload(Subscription.user))
            .order_by(Subscription.end_date.asc())
        )
        for sub in result.scalars().all():
            stage = self.stage_for_subscription(sub, now)
            if stage is None:
                continue
            await self.lifecycle_notifications.send_stage(
                session,
                sub,
                stage,
                sent_at=now,
            )

    def stage_for_subscription(
        self,
        sub: Subscription,
        now: datetime,
    ) -> Optional[SubscriptionNotificationStage]:
        end_date = self._as_utc(getattr(sub, "end_date", None))
        if end_date is None:
            return None

        seconds_left = (end_date - now).total_seconds()
        if seconds_left > 0:
            hours_before = int(getattr(self.settings, "SUBSCRIPTION_NOTIFY_HOURS_BEFORE", 0) or 0)
            if 0 < hours_before <= 23 and seconds_left <= hours_before * 3600:
                return SubscriptionNotificationStage(
                    key=f"before_{hours_before}h",
                    message_key="subscription_hours_notification",
                    hours_before=hours_before,
                )

            # Trial and registration/referral-bonus subscriptions last only a
            # few days, so a multi-day "ending soon" reminder would fire almost
            # the moment they are granted and needlessly alarm newcomers. Skip
            # the day-before stages for them — they still get the hours-before
            # reminder above and the expiry/after-expiry notices below. Paying
            # for a real subscription clears the flag and restores all stages.
            if bool(getattr(sub, "suppress_early_expiry_notifications", False)):
                return None

            days_before_limit = max(
                0,
                int(getattr(self.settings, "SUBSCRIPTION_NOTIFY_DAYS_BEFORE", 0) or 0),
            )
            day_stages = (
                (1, "subscription_24h_notification"),
                (2, "subscription_48h_notification"),
                (3, "subscription_72h_notification"),
            )
            for days_before, message_key in day_stages:
                if days_before > days_before_limit:
                    continue
                if seconds_left <= days_before * 24 * 3600:
                    return SubscriptionNotificationStage(
                        key=f"before_{days_before}d",
                        message_key=message_key,
                        days_left=days_before,
                    )
            return None

        expired_for = now - end_date
        if (
            getattr(self.settings, "SUBSCRIPTION_NOTIFY_ON_EXPIRE", True)
            and expired_for <= EXPIRED_NOTIFICATION_WINDOW
        ):
            return SubscriptionNotificationStage(
                key="expired",
                message_key="subscription_expired_notification",
                days_left=0,
            )
        if (
            getattr(self.settings, "SUBSCRIPTION_NOTIFY_AFTER_EXPIRE", True)
            and EXPIRED_NOTIFICATION_WINDOW < expired_for <= EXPIRED_AFTER_NOTIFICATION_WINDOW
        ):
            return SubscriptionNotificationStage(
                key="expired_24h_after",
                message_key="subscription_expired_yesterday_notification",
                days_left=0,
            )
        return None

    async def trial_traffic_tick(self, session: AsyncSession) -> None:
        if not getattr(self.settings, "SUBSCRIPTION_NOTIFICATIONS_ENABLED", True):
            return
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(Subscription)
            .where(
                Subscription.skip_notifications == False,
                Subscription.is_active == True,
                Subscription.end_date > now,
                Subscription.traffic_limit_bytes.is_not(None),
                Subscription.traffic_limit_bytes > 0,
                or_(
                    Subscription.provider == "trial",
                    Subscription.status_from_panel == "TRIAL",
                    Subscription.duration_months == 0,
                ),
            )
            .options(selectinload(Subscription.user))
            .order_by(Subscription.end_date.asc())
        )
        for sub in result.scalars().all():
            legacy_sent = await subscription_dal.has_subscription_notification(
                session,
                sub.subscription_id,
                "trial_traffic_depleted",
            )
            telegram_done = legacy_sent or await subscription_dal.has_subscription_notification(
                session,
                sub.subscription_id,
                "trial_traffic_depleted:telegram",
            )
            email_done = await subscription_dal.has_subscription_notification(
                session,
                sub.subscription_id,
                "trial_traffic_depleted:email",
            )
            if telegram_done and email_done:
                continue

            used = int(getattr(sub, "traffic_used_bytes", 0) or 0)
            limit = int(getattr(sub, "traffic_limit_bytes", 0) or 0)
            panel_data = await self._panel_user(sub)
            if panel_data:
                panel_used, panel_limit, _ = (
                    self.subscription_service._extract_panel_traffic_details(panel_data)
                )
                if panel_used is not None:
                    used = int(panel_used)
                    sub.traffic_used_bytes = used
                if panel_limit is not None:
                    limit = int(panel_limit)
                    sub.traffic_limit_bytes = limit
                panel_status = str(panel_data.get("status") or "").upper()
                if panel_status:
                    sub.status_from_panel = panel_status

            if limit <= 0 or used < limit:
                continue
            delivery = await self._send_trial_traffic_depleted(
                session,
                sub,
                used=used,
                limit=limit,
                send_telegram=not telegram_done,
                send_email=not email_done,
            )
            if not delivery["telegram"] and not delivery["email"]:
                continue
            if delivery["telegram"]:
                await subscription_dal.record_subscription_notification(
                    session,
                    sub.subscription_id,
                    "trial_traffic_depleted:telegram",
                    sent_at=now,
                )
            if delivery["email"]:
                await subscription_dal.record_subscription_notification(
                    session,
                    sub.subscription_id,
                    "trial_traffic_depleted:email",
                    sent_at=now,
                )

    async def _panel_user(self, sub: Subscription) -> Optional[dict]:
        panel_uuid = str(getattr(sub, "panel_user_uuid", "") or "").strip()
        if not panel_uuid:
            return None
        try:
            data = await self.panel_service.get_user_by_uuid(panel_uuid, log_response=False)
        except Exception:
            logging.exception(
                "SubscriptionNotificationWorker: failed to fetch panel user %s",
                panel_uuid,
            )
            return None
        return data if isinstance(data, dict) else None

    async def _send_trial_traffic_depleted(
        self,
        session: AsyncSession,
        sub: Subscription,
        *,
        used: int,
        limit: int,
        send_telegram: bool = True,
        send_email: bool = True,
    ) -> dict[str, bool]:
        user_id = int(getattr(sub, "user_id", 0) or 0)
        user = getattr(sub, "user", None)
        lang = getattr(user, "language_code", None) or self.settings.DEFAULT_LANGUAGE
        translate = lambda k, **kw: self.i18n.gettext(lang, k, **kw)
        remaining = max(0, limit - used)
        message_text = translate(
            "trial_traffic_depleted_notification",
            used=hd.quote(self._fmt_bytes(used)),
            remaining=hd.quote(self._fmt_bytes(remaining)),
            limit_total=hd.quote(self._fmt_bytes(limit)),
        )
        telegram_sent = False
        email_sent = False
        telegram_chat_id = int(getattr(user, "telegram_id", 0) or user_id or 0)
        telegram_status = normalize_telegram_notification_status(
            getattr(user, "telegram_notifications_status", None)
        )
        can_try_telegram = telegram_status not in {
            TELEGRAM_NOTIFICATIONS_NEEDS_START,
            TELEGRAM_NOTIFICATIONS_BLOCKED,
        }
        if send_telegram and telegram_chat_id > 0 and can_try_telegram:
            try:
                await self.bot.send_message(
                    telegram_chat_id,
                    message_text,
                    reply_markup=get_subscribe_only_markup(lang, self.i18n),
                    parse_mode="HTML",
                )
                telegram_sent = True
                await log_user_message_delivery(
                    session,
                    target_user_id=user_id,
                    event_type="telegram_traffic_warning_sent",
                    channel="telegram",
                    recipient=str(telegram_chat_id),
                    content=(
                        "kind=trial warning_key=trial_traffic_depleted "
                        f"used_bytes={used} limit_bytes={limit}"
                    ),
                )
            except Exception as exc:
                status = telegram_notification_status_from_error(exc)
                if status and user and user_id:
                    await mark_telegram_notifications_status(session, user_id, status)
                logging.exception(
                    "Failed to send trial traffic depleted warning to user %s",
                    telegram_chat_id,
                )
            else:
                if user and telegram_status != TELEGRAM_NOTIFICATIONS_ENABLED and user_id:
                    await mark_telegram_notifications_status(
                        session,
                        user_id,
                        TELEGRAM_NOTIFICATIONS_ENABLED,
                        telegram_id=telegram_chat_id,
                    )
        if send_email and user:
            email_sent = await send_user_notification_email(
                settings=self.settings,
                i18n=self.i18n,
                user=user,
                subject_key="email_trial_traffic_depleted_subject",
                message_text=message_text,
                dashboard_url=(getattr(self.settings, "SUBSCRIPTION_MINI_APP_URL", "") or None),
                session=session,
                audit_event_type="email_traffic_warning_sent",
                audit_content=(
                    "kind=trial warning_key=trial_traffic_depleted "
                    f"used_bytes={used} limit_bytes={limit}"
                ),
            )
        return {"telegram": telegram_sent, "email": email_sent}

    def _max_before_window(self) -> timedelta:
        days_before = max(0, int(getattr(self.settings, "SUBSCRIPTION_NOTIFY_DAYS_BEFORE", 0) or 0))
        hours_before = max(
            0,
            int(getattr(self.settings, "SUBSCRIPTION_NOTIFY_HOURS_BEFORE", 0) or 0),
        )
        return max(timedelta(days=min(days_before, 3)), timedelta(hours=hours_before))

    @staticmethod
    def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _fmt_bytes(value: int) -> str:
        size = float(max(0, int(value or 0)))
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024 or unit == "TB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024
        return f"{size:.1f} TB"
