"""User notifications driven by Remnawave HWID device webhooks."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.text_decorations import html_decoration as hd
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra import events
from bot.infra.event_payloads import DeviceConnectedPayload, DeviceLimitReachedPayload
from bot.middlewares.i18n import JsonI18n
from bot.services.device_topup_availability import resolve_device_topup_availability
from bot.services.message_audit import log_user_message_delivery
from bot.services.message_composition import mini_app_section_link
from bot.services.panel_api_service import PanelApiService
from bot.services.telegram_notifications import (
    TELEGRAM_NOTIFICATIONS_ENABLED,
    mark_telegram_notifications_status,
    normalize_telegram_notification_status,
    telegram_notification_status_from_error,
)
from bot.services.user_email_notifications import send_user_notification_email
from bot.services.user_notification_policy import (
    UserNotificationCategory,
    telegram_recipient,
    user_notification_delivery_plan,
)
from config.settings import Settings
from db.dal import subscription_dal
from db.models import Subscription, User

logger = logging.getLogger(__name__)

HWID_DEVICE_NOTIFICATION_RUNTIME_SETTING_KEYS = {
    "MY_DEVICES_SECTION_ENABLED",
    "SUBSCRIPTION_MINI_APP_URL",
    "USER_HWID_DEVICE_LIMIT",
    "USER_NOTIFICATION_DEVICE_ACTIVITY_EMAIL_ENABLED",
    "USER_NOTIFICATION_DEVICE_ACTIVITY_TELEGRAM_ENABLED",
    "USER_NOTIFICATION_DEVICE_LIMIT_EMAIL_ENABLED",
    "USER_NOTIFICATION_DEVICE_LIMIT_TELEGRAM_ENABLED",
    "USER_NOTIFICATION_SINGLE_CHANNEL_FALLBACK_ENABLED",
}


@dataclass(frozen=True)
class HwidDeviceNotificationResult:
    retry_channels: tuple[str, ...] = ()

    @property
    def needs_retry(self) -> bool:
        return bool(self.retry_channels)


class HwidDeviceNotificationRetryError(RuntimeError):
    def __init__(self, channels: tuple[str, ...]) -> None:
        self.channels = channels
        super().__init__("Transient HWID device notification failure: " + ", ".join(channels))


class HwidDeviceNotificationService:
    def __init__(
        self,
        settings: Settings,
        bot: Bot | None,
        i18n: JsonI18n,
        panel_service: PanelApiService,
    ) -> None:
        self.settings = settings
        self.bot = bot
        self.i18n = i18n
        self.panel_service = panel_service

    async def handle_added(
        self,
        session: AsyncSession,
        *,
        user: User,
        subscription: Subscription,
        user_payload: dict[str, Any],
        context: dict[str, Any],
    ) -> HwidDeviceNotificationResult:
        fingerprint = str(context.get("fingerprint") or "").strip().lower()
        if not fingerprint:
            logger.warning(
                "HWID device event for subscription %s has no safe fingerprint; skipped",
                subscription.subscription_id,
            )
            return HwidDeviceNotificationResult()

        now = datetime.now(UTC)
        panel_reference = str(
            user_payload.get("uuid") or user_payload.get("id") or subscription.panel_user_uuid or ""
        ).strip()
        current_devices = await self._current_device_count(panel_reference)
        device_limit = self._device_limit(user_payload, subscription)
        limit_reached = bool(
            current_devices is not None
            and device_limit is not None
            and device_limit > 0
            and current_devices >= device_limit
        )
        topup_available = self._topup_available(
            subscription,
            device_limit=device_limit,
            now=now,
        )
        device_label = self._device_label(context, user.language_code)
        occurred_at = self._event_datetime(context.get("created_at")) or now

        await self._emit_domain_events_once(
            session,
            user=user,
            subscription=subscription,
            fingerprint=fingerprint,
            panel_reference=panel_reference,
            device_label=device_label,
            context=context,
            current_devices=current_devices,
            device_limit=device_limit,
            limit_reached=limit_reached,
            topup_available=topup_available,
            occurred_at=occurred_at,
        )

        lang = user.language_code or self.settings.DEFAULT_LANGUAGE
        messages = {
            "connected": self.i18n.gettext(
                lang,
                "device_connected_notification",
                device=hd.quote(device_label),
            ),
        }
        if limit_reached and current_devices is not None and device_limit is not None:
            messages["limit"] = self.i18n.gettext(
                lang,
                (
                    "device_limit_reached_notification_topup"
                    if topup_available
                    else "device_limit_reached_notification_manage"
                ),
                current=current_devices,
                limit=device_limit,
            )

        plans = {
            "connected": user_notification_delivery_plan(
                self.settings,
                UserNotificationCategory.DEVICE_ACTIVITY,
                user,
            ),
            "limit": user_notification_delivery_plan(
                self.settings,
                UserNotificationCategory.DEVICE_LIMIT,
                user,
            ),
        }
        pending: dict[str, list[str]] = {"telegram": [], "email": []}
        for kind in messages:
            plan = plans[kind]
            for channel in ("telegram", "email"):
                if not bool(getattr(plan, channel)):
                    continue
                key = self._delivery_key(kind, fingerprint, channel)
                if not await subscription_dal.has_subscription_notification(
                    session,
                    subscription.subscription_id,
                    key,
                ):
                    pending[channel].append(kind)

        dashboard_url = self._devices_url()
        retry_channels: list[str] = []
        if pending["telegram"]:
            sent, retry = await self._send_telegram(
                session,
                user=user,
                subscription=subscription,
                fingerprint=fingerprint,
                kinds=pending["telegram"],
                messages=messages,
                dashboard_url=dashboard_url,
                topup_available=topup_available,
                lang=lang,
            )
            if sent:
                await self._record_deliveries(
                    session,
                    subscription.subscription_id,
                    fingerprint,
                    pending["telegram"],
                    "telegram",
                    now,
                )
            if retry:
                retry_channels.append("telegram")

        if pending["email"]:
            sent = await self._send_email(
                session,
                user=user,
                subscription=subscription,
                kinds=pending["email"],
                messages=messages,
                dashboard_url=dashboard_url,
                topup_available=topup_available,
            )
            if sent:
                await self._record_deliveries(
                    session,
                    subscription.subscription_id,
                    fingerprint,
                    pending["email"],
                    "email",
                    now,
                )
            else:
                retry_channels.append("email")

        return HwidDeviceNotificationResult(tuple(retry_channels))

    async def _current_device_count(self, panel_reference: str) -> int | None:
        if not panel_reference:
            return None
        try:
            devices = await self.panel_service.get_user_devices(
                panel_reference,
                force_refresh=True,
            )
        except Exception:
            logger.exception(
                "Failed to refresh HWID devices after device-added webhook for user %s",
                panel_reference,
            )
            return None
        return len(devices) if devices is not None else None

    def _device_limit(
        self,
        user_payload: dict[str, Any],
        subscription: Subscription,
    ) -> int | None:
        raw_limit = user_payload.get("hwidDeviceLimit")
        if raw_limit in (None, ""):
            raw_limit = subscription.hwid_device_limit
            if raw_limit in (None, ""):
                raw_limit = self.settings.USER_HWID_DEVICE_LIMIT
            try:
                base_limit = int(str(raw_limit)) if raw_limit not in (None, "") else None
            except (TypeError, ValueError):
                return None
            if base_limit is None or base_limit <= 0:
                return max(0, base_limit or 0) if base_limit is not None else None
            return base_limit + max(0, int(subscription.extra_hwid_devices or 0))
        try:
            return max(0, int(str(raw_limit)))
        except (TypeError, ValueError):
            return None

    def _topup_available(
        self,
        subscription: Subscription,
        *,
        device_limit: int | None,
        now: datetime,
    ) -> bool:
        end_date = self._event_datetime(subscription.end_date)
        active = bool(subscription.is_active and end_date and end_date > now)
        provider = str(subscription.provider or "").strip().lower()
        status = str(subscription.status_from_panel or "").strip().upper()
        return resolve_device_topup_availability(
            self.settings,
            subscription_active=active,
            tariff_key=subscription.tariff_key,
            max_devices=device_limit,
            subscription_is_trial=provider == "trial" or status == "TRIAL",
        ).allowed

    async def _emit_domain_events_once(
        self,
        session: AsyncSession,
        *,
        user: User,
        subscription: Subscription,
        fingerprint: str,
        panel_reference: str,
        device_label: str,
        context: dict[str, Any],
        current_devices: int | None,
        device_limit: int | None,
        limit_reached: bool,
        topup_available: bool,
        occurred_at: datetime,
    ) -> None:
        connected_key = self._delivery_key("connected", fingerprint, "event")
        if not await subscription_dal.has_subscription_notification(
            session,
            subscription.subscription_id,
            connected_key,
        ):
            await events.emit_model(
                DeviceConnectedPayload(
                    user_id=int(user.user_id),
                    subscription_id=int(subscription.subscription_id),
                    panel_user_uuid=panel_reference or None,
                    device_label=device_label,
                    platform=str(context.get("platform") or "") or None,
                    os_version=str(context.get("os_version") or "") or None,
                    current_devices=current_devices,
                    device_limit=device_limit,
                    occurred_at=occurred_at,
                )
            )
            await subscription_dal.record_subscription_notification(
                session,
                subscription.subscription_id,
                connected_key,
                sent_at=occurred_at,
            )

        if not limit_reached or current_devices is None or device_limit is None:
            return
        limit_key = self._delivery_key("limit", fingerprint, "event")
        if await subscription_dal.has_subscription_notification(
            session,
            subscription.subscription_id,
            limit_key,
        ):
            return
        await events.emit_model(
            DeviceLimitReachedPayload(
                user_id=int(user.user_id),
                subscription_id=int(subscription.subscription_id),
                tariff_key=subscription.tariff_key,
                current_devices=current_devices,
                device_limit=device_limit,
                device_topup_available=topup_available,
                occurred_at=occurred_at,
            )
        )
        await subscription_dal.record_subscription_notification(
            session,
            subscription.subscription_id,
            limit_key,
            sent_at=occurred_at,
        )

    async def _send_telegram(
        self,
        session: AsyncSession,
        *,
        user: User,
        subscription: Subscription,
        fingerprint: str,
        kinds: list[str],
        messages: dict[str, str],
        dashboard_url: str | None,
        topup_available: bool,
        lang: str,
    ) -> tuple[bool, bool]:
        if self.bot is None:
            return False, False
        chat_id = telegram_recipient(user, subscription.user_id)
        if chat_id is None:
            return False, False
        try:
            await self.bot.send_message(
                chat_id,
                "\n\n".join(messages[kind] for kind in kinds),
                parse_mode="HTML",
                reply_markup=self._telegram_markup(
                    lang,
                    dashboard_url,
                    topup_available=topup_available and "limit" in kinds,
                ),
            )
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            status = telegram_notification_status_from_error(exc)
            if status:
                await mark_telegram_notifications_status(session, int(user.user_id), status)
                logger.warning(
                    "Skipping unreachable Telegram recipient for HWID device notification: %s",
                    chat_id,
                )
                return False, False
            logger.exception("Failed to send HWID device notification to Telegram user %s", chat_id)
            return False, True
        except Exception:
            logger.exception("Failed to send HWID device notification to Telegram user %s", chat_id)
            return False, True

        await log_user_message_delivery(
            session,
            target_user_id=user.user_id,
            event_type="telegram_device_notification_sent",
            channel="telegram",
            recipient=str(chat_id),
            content=(
                f"kinds={','.join(kinds)} subscription_id={subscription.subscription_id} "
                f"event_ref={fingerprint}"
            ),
        )
        if normalize_telegram_notification_status(
            getattr(user, "telegram_notifications_status", None)
        ) != (TELEGRAM_NOTIFICATIONS_ENABLED):
            await mark_telegram_notifications_status(
                session,
                int(user.user_id),
                TELEGRAM_NOTIFICATIONS_ENABLED,
                telegram_id=chat_id,
            )
        return True, False

    async def _send_email(
        self,
        session: AsyncSession,
        *,
        user: User,
        subscription: Subscription,
        kinds: list[str],
        messages: dict[str, str],
        dashboard_url: str | None,
        topup_available: bool,
    ) -> bool:
        has_limit = "limit" in kinds
        try:
            return await send_user_notification_email(
                settings=self.settings,
                i18n=self.i18n,
                user=user,
                subject_key=(
                    "email_device_limit_reached_subject"
                    if has_limit
                    else "email_device_connected_subject"
                ),
                message_text="\n\n".join(messages[kind] for kind in kinds),
                dashboard_url=dashboard_url,
                cta_label_key=(
                    "device_limit_notification_cta_topup"
                    if has_limit and topup_available
                    else "device_notification_cta_manage"
                ),
                session=session,
                audit_event_type="email_device_notification_sent",
                audit_content=(
                    f"kinds={','.join(kinds)} subscription_id={subscription.subscription_id}"
                ),
                raise_on_error=True,
            )
        except Exception:
            logger.exception("Failed to send HWID device notification email")
            return False

    async def _record_deliveries(
        self,
        session: AsyncSession,
        subscription_id: int,
        fingerprint: str,
        kinds: list[str],
        channel: str,
        sent_at: datetime,
    ) -> None:
        for kind in kinds:
            await subscription_dal.record_subscription_notification(
                session,
                subscription_id,
                self._delivery_key(kind, fingerprint, channel),
                sent_at=sent_at,
            )

    def _telegram_markup(
        self,
        lang: str,
        dashboard_url: str | None,
        *,
        topup_available: bool,
    ) -> InlineKeyboardMarkup | None:
        if not dashboard_url or urlsplit(dashboard_url).scheme != "https":
            return None
        label_key = (
            "device_limit_notification_cta_topup"
            if topup_available
            else "device_notification_cta_manage"
        )
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=self.i18n.gettext(lang, label_key),
                        web_app=WebAppInfo(url=dashboard_url),
                    )
                ]
            ]
        )

    def _devices_url(self) -> str | None:
        if not self.settings.MY_DEVICES_SECTION_ENABLED:
            return None
        return mini_app_section_link(self.settings.SUBSCRIPTION_MINI_APP_URL, "devices")

    def _device_label(self, context: dict[str, Any], language_code: str | None) -> str:
        model = str(context.get("device_model") or "").strip()
        platform = str(context.get("platform") or "").strip()
        os_version = str(context.get("os_version") or "").strip()
        platform_label = " ".join(part for part in (platform, os_version) if part)
        if model and platform_label and platform_label.casefold() not in model.casefold():
            return f"{model} · {platform_label}"
        if model or platform_label:
            return model or platform_label
        lang = language_code or self.settings.DEFAULT_LANGUAGE
        return str(self.i18n.gettext(lang, "device_notification_unknown_device"))

    @staticmethod
    def _event_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            parsed = value
        else:
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

    @staticmethod
    def _delivery_key(kind: str, fingerprint: str, channel: str) -> str:
        return f"device_{kind}:{fingerprint}:{channel}"


__all__ = [
    "HWID_DEVICE_NOTIFICATION_RUNTIME_SETTING_KEYS",
    "HwidDeviceNotificationResult",
    "HwidDeviceNotificationRetryError",
    "HwidDeviceNotificationService",
]
