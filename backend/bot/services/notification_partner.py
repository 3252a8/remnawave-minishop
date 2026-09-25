from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.text_decorations import html_decoration as hd

from bot.services.partner_common import minor_to_decimal_string
from bot.services.telegram_notifications import (
    TELEGRAM_NOTIFICATIONS_BLOCKED,
    TELEGRAM_NOTIFICATIONS_NEEDS_START,
    mark_telegram_notifications_status,
    normalize_telegram_notification_status,
    telegram_notification_status_from_error,
)
from bot.utils import MessageContent, send_message_via_queue
from bot.utils.message_queue import get_queue_manager
from db.models import User

if TYPE_CHECKING:
    from aiogram import Bot

    from bot.middlewares.i18n import JsonI18n
    from config.settings import Settings

logger = logging.getLogger(__name__)


class NotificationPartnerMixin:
    if TYPE_CHECKING:
        bot: Bot
        settings: Settings
        i18n: JsonI18n | None
        session_factory: Any

        @staticmethod
        def _format_user_display(
            user_id: str,
            username: str | None = None,
            first_name: str | None = None,
            email: str | None = None,
        ) -> str: ...

        @staticmethod
        def _build_profile_keyboard(
            translate: Any,
            telegram_id: int | None,
            referrer_telegram_id: int | None = None,
        ) -> InlineKeyboardMarkup | None: ...

        async def _send_to_log_channel(
            self,
            message: str,
            thread_id: int | None = None,
            reply_markup: InlineKeyboardMarkup | None = None,
        ) -> None: ...

    def _partner_text(
        self,
        language: str | None,
        key: str,
        fallback: str,
        **kwargs: object,
    ) -> str:
        if self.i18n:
            translated = self.i18n.gettext(
                language or self.settings.DEFAULT_LANGUAGE,
                key,
                **kwargs,
            )
            if translated and translated != key:
                return translated
        return fallback.format(**kwargs)

    @staticmethod
    def _partner_user_chat_id(user: User) -> int | None:
        telegram_id = getattr(user, "telegram_id", None)
        if telegram_id and int(telegram_id) > 0:
            return int(telegram_id)
        return None

    @staticmethod
    def _partner_amount(amount_minor: int, currency_scale: int) -> str:
        return minor_to_decimal_string(int(amount_minor), scale=int(currency_scale))

    def _partner_admin_context(self, user: User) -> tuple[str, InlineKeyboardMarkup | None]:
        language = self.settings.DEFAULT_LANGUAGE
        translate = lambda key, **kwargs: self._partner_text(
            language,
            key,
            key,
            **kwargs,
        )
        user_display = self._format_user_display(
            user_id=str(getattr(user, "minishop_id", None) or "—"),
            username=getattr(user, "username", None),
            first_name=getattr(user, "first_name", None),
            email=getattr(user, "email", None),
        )
        chat_id = self._partner_user_chat_id(user)
        keyboard = self._build_profile_keyboard(translate, chat_id) if chat_id else None
        return user_display, keyboard

    async def _mark_partner_delivery_status(self, user: User, status: str) -> None:
        if self.session_factory is None:
            return
        try:
            async with self.session_factory() as session:
                await mark_telegram_notifications_status(session, int(user.user_id), status)
                await session.commit()
        except Exception:
            logger.exception(
                "Failed to persist partner notification status for user %s.",
                user.user_id,
            )

    async def _send_partner_user_notification(self, user: User, message: str) -> bool:
        chat_id = self._partner_user_chat_id(user)
        if chat_id is None:
            return False
        status = normalize_telegram_notification_status(
            getattr(user, "telegram_notifications_status", None)
        )
        if status in {TELEGRAM_NOTIFICATIONS_NEEDS_START, TELEGRAM_NOTIFICATIONS_BLOCKED}:
            return False

        queue_manager = get_queue_manager()
        try:
            if queue_manager is not None:
                await send_message_via_queue(
                    queue_manager,
                    chat_id,
                    MessageContent(content_type="text", text=message),
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            else:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            delivery_status = telegram_notification_status_from_error(exc)
            if delivery_status:
                await self._mark_partner_delivery_status(user, delivery_status)
                logger.warning(
                    "Partner notification could not reach Telegram user %s: %s",
                    chat_id,
                    exc,
                )
                return False
            logger.exception("Failed to send partner notification to user %s.", chat_id)
            return False
        except Exception:
            logger.exception("Failed to send partner notification to user %s.", chat_id)
            return False
        return True

    async def notify_partner_application_submitted(
        self,
        *,
        application_id: int,
        user: User,
        submitted_at: datetime,
    ) -> None:
        user_display, keyboard = self._partner_admin_context(user)
        message = self._partner_text(
            self.settings.DEFAULT_LANGUAGE,
            "log_partner_application_submitted",
            (
                "🤝 <b>New partner application</b>\n\n"
                "👤 User: {user_display}\n"
                "📝 Application: <code>#{application_id}</code>\n"
                "🕐 Time: {timestamp}"
            ),
            user_display=user_display,
            application_id=application_id,
            timestamp=submitted_at.strftime("%Y-%m-%d %H:%M:%S"),
        )
        await self._send_to_log_channel(message, reply_markup=keyboard)

    async def notify_partner_application_decided(
        self,
        *,
        application_id: int,
        user: User,
        status: str,
        decided_at: datetime,
    ) -> None:
        normalized = str(status or "").strip().lower()
        if normalized == "approved":
            user_display, keyboard = self._partner_admin_context(user)
            admin_message = self._partner_text(
                self.settings.DEFAULT_LANGUAGE,
                "log_partner_application_approved",
                (
                    "✅ <b>Partner access activated</b>\n\n"
                    "👤 User: {user_display}\n"
                    "📝 Application: <code>#{application_id}</code>\n"
                    "🕐 Time: {timestamp}"
                ),
                user_display=user_display,
                application_id=application_id,
                timestamp=decided_at.strftime("%Y-%m-%d %H:%M:%S"),
            )
            await self._send_to_log_channel(admin_message, reply_markup=keyboard)
            key = "partner_application_approved_notification"
            fallback = (
                "✅ <b>Your partner application was approved</b>\n\n"
                "Your partner profile is active. Open the Partner section to get your links."
            )
        elif normalized == "rejected":
            key = "partner_application_rejected_notification"
            fallback = (
                "❌ <b>Your partner application was declined</b>\n\n"
                "Open the Partner section to review the administrator's decision."
            )
        else:
            return
        message = self._partner_text(getattr(user, "language_code", None), key, fallback)
        await self._send_partner_user_notification(user, message)

    async def notify_partner_profile_status_changed(
        self,
        *,
        partner_id: int,
        user: User,
        old_status: str,
        status: str,
        changed_at: datetime,
    ) -> None:
        normalized = str(status or "").strip().lower()
        old_normalized = str(old_status or "").strip().lower()
        if normalized == "active" and old_normalized == "none":
            user_display, keyboard = self._partner_admin_context(user)
            admin_message = self._partner_text(
                self.settings.DEFAULT_LANGUAGE,
                "log_partner_profile_activated",
                (
                    "✅ <b>Partner profile activated</b>\n\n"
                    "👤 User: {user_display}\n"
                    "🤝 Partner: <code>#{partner_id}</code>\n"
                    "🕐 Time: {timestamp}"
                ),
                user_display=user_display,
                partner_id=partner_id,
                timestamp=changed_at.strftime("%Y-%m-%d %H:%M:%S"),
            )
            await self._send_to_log_channel(admin_message, reply_markup=keyboard)
            key = "partner_profile_activated_notification"
            fallback = (
                "✅ <b>Your partner profile is active</b>\n\n"
                "Open the Partner section to get your links."
            )
        elif normalized == "active":
            key = "partner_profile_resumed_notification"
            fallback = "✅ <b>Your partner profile is active again</b>"
        elif normalized == "paused":
            key = "partner_profile_paused_notification"
            fallback = (
                "⏸ <b>Your partner profile was paused</b>\n\n"
                "Open the Partner section for the current status."
            )
        elif normalized == "closed":
            key = "partner_profile_closed_notification"
            fallback = "⛔ <b>Your partner profile was closed</b>"
        else:
            return
        message = self._partner_text(getattr(user, "language_code", None), key, fallback)
        await self._send_partner_user_notification(user, message)

    async def notify_partner_withdrawal_requested(
        self,
        *,
        withdrawal_id: int,
        user: User,
        amount_minor: int,
        currency: str,
        currency_scale: int,
        requested_at: datetime,
    ) -> None:
        user_display, keyboard = self._partner_admin_context(user)
        message = self._partner_text(
            self.settings.DEFAULT_LANGUAGE,
            "log_partner_withdrawal_requested",
            (
                "💸 <b>New partner withdrawal request</b>\n\n"
                "👤 User: {user_display}\n"
                "💰 Amount: <b>{amount} {currency}</b>\n"
                "🧾 Request: <code>#{withdrawal_id}</code>\n"
                "🕐 Time: {timestamp}"
            ),
            user_display=user_display,
            amount=hd.quote(self._partner_amount(amount_minor, currency_scale)),
            currency=hd.quote(str(currency).upper()),
            withdrawal_id=withdrawal_id,
            timestamp=requested_at.strftime("%Y-%m-%d %H:%M:%S"),
        )
        await self._send_to_log_channel(message, reply_markup=keyboard)

    async def notify_partner_withdrawal_status_changed(
        self,
        *,
        withdrawal_id: int,
        user: User,
        status: str,
        amount_minor: int,
        currency: str,
        currency_scale: int,
        settlement_amount: str | None = None,
        external_reference: str | None = None,
    ) -> None:
        normalized = str(status or "").strip().lower()
        messages = {
            "processing": (
                "partner_withdrawal_processing_notification",
                (
                    "🕐 <b>Withdrawal request #{withdrawal_id} was approved and is being "
                    "processed</b>\n\nAmount: {amount} {currency}"
                ),
            ),
            "paid": (
                "partner_withdrawal_paid_notification",
                (
                    "✅ <b>Withdrawal request #{withdrawal_id} was paid</b>\n\n"
                    "Amount: {amount} {currency}"
                ),
            ),
            "rejected": (
                "partner_withdrawal_rejected_notification",
                (
                    "❌ <b>Withdrawal request #{withdrawal_id} was declined</b>\n\n"
                    "The reserved {amount} {currency} was returned to your partner balance."
                ),
            ),
            "failed": (
                "partner_withdrawal_failed_notification",
                (
                    "⚠️ <b>Withdrawal request #{withdrawal_id} could not be completed</b>\n\n"
                    "The {amount} {currency} remains reserved while the administrator retries "
                    "or declines the request."
                ),
            ),
            "canceled": (
                "partner_withdrawal_canceled_notification",
                (
                    "↩️ <b>Withdrawal request #{withdrawal_id} was canceled</b>\n\n"
                    "The reserved {amount} {currency} was returned to your partner balance."
                ),
            ),
        }
        selected = messages.get(normalized)
        if selected is None:
            return
        key, fallback = selected
        message = self._partner_text(
            getattr(user, "language_code", None),
            key,
            fallback,
            withdrawal_id=withdrawal_id,
            amount=hd.quote(self._partner_amount(amount_minor, currency_scale)),
            currency=hd.quote(str(currency).upper()),
        )
        normalized_settlement = str(settlement_amount or "").strip()
        if normalized == "paid" and normalized_settlement:
            language = getattr(user, "language_code", None)
            details = [
                self._partner_text(
                    language,
                    "partner_withdrawal_paid_settlement_amount",
                    "Final cryptocurrency amount: <b>{settlement_amount}</b>",
                    settlement_amount=hd.quote(normalized_settlement),
                )
            ]
            reference = str(external_reference or "").strip()
            if reference:
                try:
                    parsed_reference = urlsplit(reference)
                    reference_is_link = parsed_reference.scheme.lower() in {
                        "http",
                        "https",
                    } and bool(parsed_reference.netloc)
                except ValueError:
                    reference_is_link = False
                if reference_is_link:
                    details.append(
                        self._partner_text(
                            language,
                            "partner_withdrawal_paid_transaction_link",
                            'Transaction: <a href="{transaction_url}">open in explorer</a>',
                            transaction_url=hd.quote(reference),
                        )
                    )
                else:
                    details.append(
                        self._partner_text(
                            language,
                            "partner_withdrawal_paid_transaction_reference",
                            "Transaction hash: <code>{transaction_reference}</code>",
                            transaction_reference=hd.quote(reference),
                        )
                    )
            message = f"{message}\n\n" + "\n".join(details)
        await self._send_partner_user_notification(user, message)
