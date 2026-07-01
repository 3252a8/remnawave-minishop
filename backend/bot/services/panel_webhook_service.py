import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiohttp import web
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, sessionmaker

from bot.infra import events
from bot.infra.event_payloads import PanelWebhookReceivedPayload
from bot.infra.webhook_queue import enqueue_webhook_event
from bot.keyboards.inline.user_keyboards import (
    get_autorenew_cancel_keyboard,
    get_subscribe_only_markup,
)
from bot.middlewares.i18n import JsonI18n
from bot.services.subscription_lifecycle_notifications import (
    SubscriptionLifecycleNotificationService,
    SubscriptionNotificationStage,
)
from config.settings import Settings
from db.dal import subscription_dal, tariff_dal, user_dal
from db.models import Subscription, User

from .panel_api_service import PanelApiService

if TYPE_CHECKING:
    from bot.services.subscription_service_impl.core import SubscriptionService

EXPIRATION_EVENT = "user.expiration"
EXPIRED_EVENT = "user.expired"
EXPIRED_24H_AFTER_EVENT = "user.expired_24_hours_ago"

EVENT_MAP = {
    "user.expires_in_72_hours": SubscriptionNotificationStage(
        key="before_3d",
        message_key="subscription_72h_notification",
        days_left=3,
    ),
    "user.expires_in_48_hours": SubscriptionNotificationStage(
        key="before_2d",
        message_key="subscription_48h_notification",
        days_left=2,
    ),
    "user.expires_in_24_hours": SubscriptionNotificationStage(
        key="before_1d",
        message_key="subscription_24h_notification",
        days_left=1,
    ),
}
ACTIONABLE_EVENTS = frozenset(
    {
        *EVENT_MAP.keys(),
        EXPIRATION_EVENT,
        EXPIRED_EVENT,
        EXPIRED_24H_AFTER_EVENT,
    }
)
_LEGACY_EXPIRATION_HOURS_TO_EVENT = {
    -72: "user.expires_in_72_hours",
    -48: "user.expires_in_48_hours",
    -24: "user.expires_in_24_hours",
}


class PanelWebhookService:
    # Cap parallel background event handlers so an expiry burst from the panel
    # cannot exhaust the DB pool or the YooKassa client.
    _MAX_CONCURRENT_EVENTS = 50

    def __init__(
        self,
        bot: Bot,
        settings: Settings,
        i18n: JsonI18n,
        async_session_factory: sessionmaker,
        panel_service: PanelApiService,
    ) -> None:
        self.bot = bot
        self.settings = settings
        self.i18n = i18n
        self.async_session_factory = async_session_factory
        self.panel_service = panel_service
        self.lifecycle_notifications = SubscriptionLifecycleNotificationService(
            settings,
            bot,
            i18n,
        )
        self.subscription_service: SubscriptionService | None = None
        self._event_semaphore = asyncio.Semaphore(self._MAX_CONCURRENT_EVENTS)
        if not self.settings.PANEL_WEBHOOK_SECRET:
            logging.error(
                "PANEL_WEBHOOK_SECRET is not configured. Panel webhooks will be rejected."
            )

    async def _send_message(
        self,
        user_id: int,
        lang: str,
        message_key: str,
        reply_markup: InlineKeyboardMarkup | None = None,
        **kwargs: object,
    ) -> None:
        _ = lambda k, **kw: self.i18n.gettext(lang, k, **kw)
        extra_text = str(kwargs.pop("extra_text", "") or "").strip()
        try:
            text = _(message_key, **kwargs)
            if extra_text:
                text = f"{text}\n\n{extra_text}"
            await self.bot.send_message(user_id, text, reply_markup=reply_markup)
        except Exception:
            logging.exception("Failed to send notification to %s", user_id)

    async def _hwid_renewal_note(self, internal_user_id: int, lang: str) -> str:
        try:
            from db.dal import subscription_dal

            async with self.async_session_factory() as session:
                sub = await subscription_dal.get_active_subscription_by_user_id(
                    session, internal_user_id
                )
                if not sub:
                    return ""
                summary = await tariff_dal.get_hwid_device_entitlement_summary(
                    session,
                    subscription_id=sub.subscription_id,
                )
                count = int(summary.get("active_devices") or sub.extra_hwid_devices or 0)
                if count <= 0:
                    return ""
                active_until = summary.get("active_until") or sub.end_date
                date_text = active_until.strftime("%Y-%m-%d") if active_until else ""
        except Exception:
            logging.exception("Failed to build HWID renewal note for user %s", internal_user_id)
            return ""
        return str(
            self.i18n.gettext(
                lang,
                "subscription_hwid_renewal_reminder",
                count=count,
                date=date_text,
            )
        )

    async def handle_event(
        self,
        event_name: str,
        user_payload: dict[str, Any],
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        await events.emit_model(
            PanelWebhookReceivedPayload(
                event=event_name,
                panel_user_uuid=user_payload.get("uuid"),
                telegram_id=user_payload.get("telegramId"),
            )
        )

        if not self.settings.SUBSCRIPTION_NOTIFICATIONS_ENABLED:
            return

        if event_name not in ACTIONABLE_EVENTS:
            logging.info(
                "Panel webhook event %s ignored: event is not used for subscription "
                "notifications; %s",
                event_name,
                self._payload_log_context(user_payload),
            )
            return

        stage = self._stage_for_event(event_name, user_payload, meta)
        if stage is None:
            logging.warning(
                "Panel webhook event %s ignored: expiration metadata is missing or invalid; %s",
                event_name,
                self._payload_log_context(user_payload),
            )
            return

        async with self.async_session_factory() as session:
            db_user = await self._user_for_payload(session, user_payload)
            sub = await self._subscription_for_payload(session, user_payload, db_user)
            telegram_id = self._payload_telegram_id(user_payload)
            internal_user_id = (
                int(db_user.user_id)
                if db_user
                else int(getattr(sub, "user_id", 0) or telegram_id or 0)
            )
            lang = (
                db_user.language_code
                if db_user and db_user.language_code
                else self.settings.DEFAULT_LANGUAGE
            )
            if not sub:
                if not telegram_id:
                    local_user_id = getattr(db_user, "user_id", None) if db_user else None
                    logging.warning(
                        "Panel webhook event %s cannot be matched to a local subscription; "
                        "notification skipped. %s local_user_id=%s. Possible causes: "
                        "panel user was created outside the bot, subscription was deleted "
                        "or not synced, panel identifiers changed, or skip_notifications "
                        "is enabled for the local subscription.",
                        event_name,
                        self._payload_log_context(user_payload),
                        local_user_id or "N/A",
                    )
                    return
                await self._send_legacy_without_dedupe(
                    event_name,
                    user_payload,
                    int(telegram_id),
                    lang,
                    db_user,
                    meta=meta,
                )
                return

            markup = get_subscribe_only_markup(
                lang,
                self.i18n,
                self.settings,
                tariff_key=self.lifecycle_notifications._renewal_tariff_key(sub),
            )
            end_date_text = self._payload_expire_date(user_payload)

            # The panel may target a stale, expired subscription row while the
            # user has already renewed into a newer active subscription. Sending
            # expiry/expiring notices in that case is wrong (e.g. "your sub ended
            # yesterday" right after a successful renewal), so skip them.
            if await self._superseded_by_newer_subscription(session, sub):
                logging.info(
                    "Panel webhook event %s skipped: subscription %s is superseded by a "
                    "newer active subscription for user %s.",
                    event_name,
                    getattr(sub, "subscription_id", None),
                    internal_user_id,
                )
                return

            if self._is_before_expiration_stage(stage):
                days_left = int(stage.days_left or 0)
                hwid_renewal_note = await self._hwid_renewal_note(internal_user_id, lang)
                if self._is_autorenew_charge_stage(stage) and await self._try_autorenew_charge(
                    internal_user_id,
                    stage.key,
                ):
                    return
                if self._should_send_before_expiration_stage(stage):
                    # For 48h, auto-renew users get a cancel button instead.
                    if days_left == 2:
                        active_sub = await subscription_dal.get_active_subscription_by_user_id(
                            session,
                            internal_user_id,
                        )
                        logging.info(
                            "48h webhook check: user_id=%s sub_found=%s auto_renew=%s provider=%s",
                            internal_user_id,
                            bool(active_sub),
                            getattr(active_sub, "auto_renew_enabled", None) if active_sub else None,
                            getattr(active_sub, "provider", None) if active_sub else None,
                        )
                        if (
                            active_sub
                            and active_sub.auto_renew_enabled
                            and active_sub.provider == "yookassa"
                        ):
                            cancel_kb = get_autorenew_cancel_keyboard(lang, self.i18n)
                            await self.lifecycle_notifications.send_stage(
                                session,
                                sub,
                                SubscriptionNotificationStage(
                                    key="before_2d_autorenew",
                                    message_key="autorenew_48h_charge_tomorrow_notice",
                                    days_left=2,
                                ),
                                user=db_user,
                                telegram_markup=cancel_kb,
                                extra_text=hwid_renewal_note,
                                end_date_text=end_date_text,
                            )
                            await session.commit()
                            return
                    await self.lifecycle_notifications.send_stage(
                        session,
                        sub,
                        stage,
                        user=db_user,
                        telegram_markup=markup,
                        extra_text=hwid_renewal_note,
                        end_date_text=end_date_text,
                    )
                    await session.commit()
            elif stage.key == "expired":
                if self.settings.SUBSCRIPTION_NOTIFY_ON_EXPIRE:
                    await self.lifecycle_notifications.send_stage(
                        session,
                        sub,
                        stage,
                        user=db_user,
                        telegram_markup=markup,
                        end_date_text=end_date_text,
                    )
                    await session.commit()
            elif (
                self._is_after_expiration_stage(stage)
                and self.settings.SUBSCRIPTION_NOTIFY_AFTER_EXPIRE
            ):
                await self.lifecycle_notifications.send_stage(
                    session,
                    sub,
                    stage,
                    user=db_user,
                    telegram_markup=markup,
                    end_date_text=end_date_text,
                )
                await session.commit()

    async def _send_legacy_without_dedupe(
        self,
        event_name: str,
        user_payload: dict,
        user_id: int,
        lang: str,
        db_user: Optional[User],
        *,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        first_name = getattr(db_user, "first_name", None) or f"User {user_id}"
        markup = get_subscribe_only_markup(lang, self.i18n, self.settings)
        stage = self._stage_for_event(event_name, user_payload, meta)
        if stage is None:
            return

        kwargs: dict[str, object] = {
            "user_name": first_name,
            "end_date": self._payload_expire_date(user_payload),
        }
        if stage.hours_before is not None:
            kwargs["hours"] = stage.hours_before
        elif stage.hours_after is not None:
            kwargs["hours"] = stage.hours_after

        if self._is_before_expiration_stage(stage):
            if not self._should_send_before_expiration_stage(stage):
                return
            await self._send_message(
                user_id,
                lang,
                stage.message_key,
                reply_markup=markup,
                **kwargs,
            )
        elif stage.key == "expired" and self.settings.SUBSCRIPTION_NOTIFY_ON_EXPIRE:
            await self._send_message(
                user_id,
                lang,
                stage.message_key,
                reply_markup=markup,
                **kwargs,
            )
        elif (
            self._is_after_expiration_stage(stage)
            and self.settings.SUBSCRIPTION_NOTIFY_AFTER_EXPIRE
        ):
            await self._send_message(
                user_id,
                lang,
                stage.message_key,
                reply_markup=markup,
                **kwargs,
            )

    @classmethod
    def _stage_for_event(
        cls,
        event_name: str,
        user_payload: dict[str, Any],
        meta: Optional[dict[str, Any]] = None,
    ) -> Optional[SubscriptionNotificationStage]:
        if event_name in EVENT_MAP:
            return EVENT_MAP[event_name]
        if event_name == EXPIRED_EVENT:
            return SubscriptionNotificationStage(
                key="expired",
                message_key="subscription_expired_notification",
                days_left=0,
            )
        if event_name == EXPIRED_24H_AFTER_EVENT:
            return cls._expired_after_stage(24)
        if event_name != EXPIRATION_EVENT:
            return None

        expiration_hours = cls._expiration_hours(meta, user_payload)
        if expiration_hours is None or expiration_hours == 0:
            return None
        legacy_event = _LEGACY_EXPIRATION_HOURS_TO_EVENT.get(expiration_hours)
        if legacy_event:
            return EVENT_MAP[legacy_event]
        if expiration_hours == 24:
            return cls._expired_after_stage(24)
        if expiration_hours < 0:
            hours_before = abs(expiration_hours)
            return SubscriptionNotificationStage(
                key=f"before_{hours_before}h",
                message_key="subscription_hours_notification",
                hours_before=hours_before,
            )
        return cls._expired_after_stage(expiration_hours)

    @staticmethod
    def _expired_after_stage(hours_after: int) -> SubscriptionNotificationStage:
        if hours_after == 24:
            return SubscriptionNotificationStage(
                key="expired_24h_after",
                message_key="subscription_expired_yesterday_notification",
                days_left=0,
                hours_after=24,
            )
        return SubscriptionNotificationStage(
            key=f"expired_{hours_after}h_after",
            message_key="subscription_expired_hours_ago_notification",
            days_left=0,
            hours_after=hours_after,
        )

    @staticmethod
    def _is_before_expiration_stage(stage: SubscriptionNotificationStage) -> bool:
        return bool(stage.hours_before is not None or int(stage.days_left or 0) > 0)

    @staticmethod
    def _is_after_expiration_stage(stage: SubscriptionNotificationStage) -> bool:
        return stage.key.startswith("expired_") and stage.key != "expired"

    @staticmethod
    def _is_autorenew_charge_stage(stage: SubscriptionNotificationStage) -> bool:
        if int(stage.days_left or 0) == 1:
            return True
        return bool(stage.hours_before is not None and 0 < stage.hours_before <= 24)

    def _should_send_before_expiration_stage(
        self,
        stage: SubscriptionNotificationStage,
    ) -> bool:
        if stage.hours_before is not None:
            return True
        return int(stage.days_left or 0) <= self.settings.SUBSCRIPTION_NOTIFY_DAYS_BEFORE

    async def _try_autorenew_charge(self, internal_user_id: int, stage_key: str) -> bool:
        # SubscriptionService is wired by the factory after both services are built.
        try:
            subscription_service = getattr(self, "subscription_service", None)
            if not subscription_service:
                return False
            async with self.async_session_factory() as renewal_session:
                active_sub = await subscription_dal.get_active_subscription_by_user_id(
                    renewal_session,
                    internal_user_id,
                )
                if not (
                    active_sub
                    and active_sub.auto_renew_enabled
                    and active_sub.provider == "yookassa"
                ):
                    return False
                try:
                    ok = await subscription_service.charge_subscription_renewal(
                        renewal_session,
                        active_sub,
                    )
                    if ok:
                        await renewal_session.commit()
                        return True
                    await renewal_session.rollback()
                except Exception:
                    await renewal_session.rollback()
                    logging.exception("Auto-renew attempt (%s) failed", stage_key)
        except Exception:
            logging.exception("Auto-renew trigger (%s) failed pre-check", stage_key)
        return False

    @classmethod
    def _expiration_hours(
        cls,
        meta: Optional[dict[str, Any]],
        user_payload: dict[str, Any],
    ) -> Optional[int]:
        for source in (meta, user_payload):
            if not isinstance(source, dict):
                continue
            for key in ("expiration", "expirationHours", "hours"):
                value = cls._coerce_int(source.get(key))
                if value is not None:
                    return value
        return None

    @staticmethod
    def _coerce_int(value: object) -> Optional[int]:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value) if value.is_integer() else None
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return int(text)
            except ValueError:
                try:
                    parsed = float(text)
                except ValueError:
                    return None
                return int(parsed) if parsed.is_integer() else None
        return None

    async def _user_for_payload(
        self,
        session: AsyncSession,
        user_payload: dict,
    ) -> Optional[User]:
        telegram_id = self._payload_telegram_id(user_payload)
        if telegram_id:
            user = await user_dal.get_user_by_telegram_id(session, telegram_id)
            if user:
                return user
            user = await user_dal.get_user_by_id(session, telegram_id)
            if user:
                return user

        panel_uuid = self._payload_panel_uuid(user_payload)
        if panel_uuid:
            user = await user_dal.get_user_by_panel_uuid(session, panel_uuid)
            if user:
                return user

        email = str(user_payload.get("email") or "").strip()
        if email:
            return await user_dal.get_user_by_email(session, email)
        return None

    async def _superseded_by_newer_subscription(
        self,
        session: AsyncSession,
        sub: Optional[Subscription],
    ) -> bool:
        if sub is None:
            return False
        user_id = getattr(sub, "user_id", None)
        if user_id is None:
            return False
        now = datetime.now(timezone.utc)
        sub_end = getattr(sub, "end_date", None)
        if sub_end is not None and sub_end.tzinfo is None:
            sub_end = sub_end.replace(tzinfo=timezone.utc)
        after = max(now, sub_end) if sub_end is not None else now
        return bool(
            await subscription_dal.user_has_active_subscription_after(
                session,
                user_id,
                after,
                exclude_subscription_id=getattr(sub, "subscription_id", None),
            )
        )

    async def _subscription_for_payload(
        self,
        session: AsyncSession,
        user_payload: dict,
        db_user: Optional[User],
    ) -> Optional[Subscription]:
        conditions = []
        if db_user:
            conditions.append(Subscription.user_id == db_user.user_id)
        panel_uuid = self._payload_panel_uuid(user_payload)
        if panel_uuid:
            conditions.append(Subscription.panel_user_uuid == panel_uuid)
        if not conditions:
            return None
        base_stmt = (
            select(Subscription)
            .where(
                Subscription.skip_notifications == False,
                or_(*conditions),
            )
            .options(selectinload(Subscription.user))
        )

        expire_at = self._payload_expire_datetime(user_payload)
        if expire_at is not None:
            window_stmt = (
                base_stmt.where(
                    Subscription.end_date >= expire_at - timedelta(days=1),
                    Subscription.end_date <= expire_at + timedelta(days=1),
                )
                .order_by(Subscription.end_date.desc())
                .limit(1)
            )
            result = await session.execute(window_stmt)
            found = result.scalars().first()
            if found:
                return found

        stmt = base_stmt.order_by(Subscription.end_date.desc()).limit(1)
        result = await session.execute(stmt)
        return result.scalars().first()

    @staticmethod
    def _payload_telegram_id(user_payload: dict) -> Optional[int]:
        raw = user_payload.get("telegramId")
        try:
            value = int(raw or 0)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    @staticmethod
    def _payload_panel_uuid(user_payload: dict) -> str:
        return str(
            user_payload.get("uuid")
            or user_payload.get("userUuid")
            or user_payload.get("shortUuid")
            or ""
        ).strip()

    @staticmethod
    def _payload_expire_date(user_payload: dict) -> str:
        return str(user_payload.get("expireAt") or "")[:10]

    @staticmethod
    def _payload_log_context(user_payload: dict) -> str:
        telegram_id = PanelWebhookService._payload_telegram_id(user_payload)
        panel_uuid = PanelWebhookService._payload_panel_uuid(user_payload)
        email = PanelWebhookService._mask_email(str(user_payload.get("email") or "").strip())
        expire_at = str(user_payload.get("expireAt") or "").strip()
        payload_keys = ",".join(sorted(str(key) for key in user_payload.keys())) or "none"
        return (
            f"telegramId={telegram_id or 'N/A'} "
            f"panel_uuid={panel_uuid or 'N/A'} "
            f"email={email or 'N/A'} "
            f"expireAt={expire_at or 'N/A'} "
            f"payload_keys={payload_keys}"
        )

    @staticmethod
    def _mask_email(email: str) -> str:
        if not email:
            return ""
        local_part, separator, domain = email.partition("@")
        if not separator or not domain:
            return "present"
        visible = local_part[:2] if len(local_part) > 2 else local_part[:1]
        return f"{visible}***@{domain}"

    @staticmethod
    def _payload_expire_datetime(user_payload: dict) -> Optional[datetime]:
        raw = str(user_payload.get("expireAt") or "").strip()
        if not raw:
            return None
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                value = datetime.fromisoformat(raw[:10])
            except ValueError:
                return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    async def handle_webhook(
        self, raw_body: bytes, signature_header: Optional[str]
    ) -> web.Response:
        if not self.settings.PANEL_WEBHOOK_SECRET:
            return web.Response(status=401, text="unauthorized")

        if not signature_header:
            return web.Response(status=401, text="unauthorized")

        expected_sig = hmac.new(
            self.settings.PANEL_WEBHOOK_SECRET.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, signature_header):
            return web.Response(status=401, text="unauthorized")

        try:
            payload = json.loads(raw_body.decode())
        except Exception:
            return web.Response(status=400, text="bad_request")
        if not isinstance(payload, dict):
            return web.Response(status=400, text="bad_request")

        event_name = payload.get("name") or payload.get("event")
        event_data = payload.get("payload") or payload.get("data", {})
        event_data_dict = event_data if isinstance(event_data, dict) else {}
        meta = self._webhook_meta(payload, event_data_dict)
        user_data = event_data_dict
        if "user" in event_data_dict:
            nested_user = event_data_dict.get("user")
            user_data = nested_user if isinstance(nested_user, dict) else event_data_dict

        telegram_id = user_data.get("telegramId") if isinstance(user_data, dict) else None

        if not event_name:
            return web.Response(status=200, text="ok_no_event")

        logging.info(
            "Panel webhook event received: %s; telegramId=%s",
            event_name,
            telegram_id if telegram_id is not None else "N/A",
        )

        queued_payload: dict[str, object] = {"event": event_name, "user": user_data}
        if meta:
            queued_payload["meta"] = meta
        queued = await enqueue_webhook_event(
            self.settings,
            "panel",
            queued_payload,
            event_id=self._webhook_event_id(str(event_name), user_data, meta),
        )
        if not queued:
            asyncio.create_task(
                self._run_event_in_background(str(event_name), user_data, meta),
                name=f"panel_event_{event_name}",
            )
        return web.Response(status=200, text="ok")

    @classmethod
    def _webhook_meta(
        cls,
        payload: dict[str, Any],
        event_data: dict[str, Any],
    ) -> dict[str, Any]:
        meta: dict[str, Any] = {}
        for source in (payload, event_data):
            for key in ("meta", "_meta"):
                raw = source.get(key)
                if isinstance(raw, dict):
                    meta.update(raw)
        return meta

    @classmethod
    def _webhook_event_id(
        cls,
        event_name: str,
        user_payload: dict[str, Any],
        meta: Optional[dict[str, Any]] = None,
    ) -> str:
        subject = (
            cls._payload_telegram_id(user_payload)
            or user_payload.get("uuid")
            or user_payload.get("userUuid")
            or user_payload.get("shortUuid")
            or "unknown"
        )
        event_id = f"{event_name}:{subject}"
        if event_name == EXPIRATION_EVENT:
            expiration_hours = cls._expiration_hours(meta, user_payload)
            if expiration_hours is not None:
                event_id = f"{event_id}:expiration:{expiration_hours}"
        return event_id

    async def _run_event_in_background(
        self,
        event_name: str,
        user_payload: dict[str, Any],
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        async with self._event_semaphore:
            try:
                await self.handle_event(event_name, user_payload, meta=meta)
            except Exception:
                logging.exception(
                    "Panel webhook background handler failed for event %s", event_name
                )


async def panel_webhook_route(request: web.Request) -> web.Response:
    from bot.app.web.context import get_panel_webhook_service

    service: PanelWebhookService = get_panel_webhook_service(request)
    raw = await request.read()
    signature_header = request.headers.get("X-Remnawave-Signature")
    return await service.handle_webhook(raw, signature_header)
