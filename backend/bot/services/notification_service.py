import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.text_decorations import html_decoration as hd

from bot.infra.payment_events import PaymentPurchase, payment_purchases_from_legacy_fields
from bot.middlewares.i18n import JsonI18n
from bot.services.email_auth_service import EmailAuthService
from bot.services.notification_support import NotificationSupportMixin
from bot.utils.message_queue import get_queue_manager
from bot.utils.telegram_markup import (
    is_profile_link_error,
    remove_profile_link_buttons,
)
from bot.utils.text_sanitizer import (
    display_name_or_fallback,
    username_for_display,
)
from config.settings import Settings


class NotificationService(NotificationSupportMixin):
    """Enhanced notification service for sending messages to admins and log channels"""

    def __init__(
        self,
        bot: Bot,
        settings: Settings,
        i18n: Optional[JsonI18n] = None,
        *,
        session_factory=None,
        email_auth_service: Optional[EmailAuthService] = None,
        bot_username: Optional[str] = None,
    ):
        self.bot = bot
        self.settings = settings
        self.i18n = i18n
        self.session_factory = session_factory
        self.email_auth_service = email_auth_service
        self.bot_username = bot_username or ""

    @staticmethod
    def _format_user_display(
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> str:
        base_display = display_name_or_fallback(first_name, f"ID {user_id}")
        if username:
            base_display = f"{base_display} ({username_for_display(username)})"
        safe_display = hd.quote(base_display)
        clean_email = str(email or "").strip()
        if clean_email:
            safe_display = f"{safe_display} · <code>{hd.quote(clean_email)}</code>"
        return safe_display

    @staticmethod
    def _build_profile_keyboard(
        translate: Callable[..., str],
        user_id: int,
        referrer_id: Optional[int] = None,
    ) -> Optional[InlineKeyboardMarkup]:
        """Create inline keyboard with links to user (and referrer) profiles.

        Email-only users have a synthetic negative ``user_id`` with no
        Telegram profile, so we skip the tg:// button for them.
        """
        buttons = []
        if user_id and user_id > 0:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=translate("log_open_profile_link"),
                        url=f"tg://user?id={user_id}",
                    )
                ]
            )

        if referrer_id and referrer_id > 0:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=translate("log_open_referrer_profile_button"),
                        url=f"tg://user?id={referrer_id}",
                    )
                ]
            )

        return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

    async def _send_to_log_channel(
        self,
        message: str,
        thread_id: Optional[int] = None,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ):
        """Send message to configured log channel/group using message queue"""
        if not self.settings.LOG_CHAT_ID:
            return

        queue_manager = get_queue_manager()
        if not queue_manager:
            logging.warning("Message queue manager not available, falling back to direct send")
            final_thread_id = thread_id or self.settings.LOG_THREAD_ID

            def _build_kwargs(markup: Optional[InlineKeyboardMarkup]) -> Dict[str, Any]:
                kwargs: Dict[str, Any] = {
                    "chat_id": self.settings.LOG_CHAT_ID,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                }
                if markup:
                    kwargs["reply_markup"] = markup
                if final_thread_id:
                    kwargs["message_thread_id"] = final_thread_id
                return kwargs

            try:
                await self.bot.send_message(**_build_kwargs(reply_markup))
            except TelegramBadRequest as exc:
                if is_profile_link_error(exc):
                    fallback_markup = remove_profile_link_buttons(reply_markup)
                    logging.warning(
                        "Telegram rejected profile buttons for log chat %s: %s. "
                        "Retrying without tg:// links.",
                        self.settings.LOG_CHAT_ID,
                        getattr(exc, "message", "") or str(exc),
                    )
                    try:
                        await self.bot.send_message(**_build_kwargs(fallback_markup))
                    except Exception as retry_exc:
                        logging.error(
                            "Failed to send notification without profile buttons to log "
                            f"channel {self.settings.LOG_CHAT_ID}: {retry_exc}"
                        )
                    return
                logging.error(
                    f"Failed to send notification to log channel {self.settings.LOG_CHAT_ID}: {exc}"
                )
            except Exception:
                logging.exception(
                    "Failed to send notification to log channel %s.", self.settings.LOG_CHAT_ID
                )
            return

        try:
            # Use thread_id if provided, otherwise use from settings
            final_thread_id = thread_id or self.settings.LOG_THREAD_ID

            kwargs = {"text": message, "parse_mode": "HTML", "disable_web_page_preview": True}
            if reply_markup:
                kwargs["reply_markup"] = reply_markup

            # Add thread ID for supergroups if specified
            if final_thread_id:
                kwargs["message_thread_id"] = final_thread_id

            # Queue message for sending (groups are rate limited to 15/minute)
            await queue_manager.send_message(self.settings.LOG_CHAT_ID, **kwargs)

        except Exception:
            logging.exception(
                "Failed to queue notification to log channel %s.", self.settings.LOG_CHAT_ID
            )

    async def _send_to_admins(
        self,
        message: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ):
        """Send message to all admin users using message queue"""
        if not self.settings.ADMIN_IDS:
            return

        queue_manager = get_queue_manager()
        if not queue_manager:
            logging.warning("Message queue manager not available, falling back to direct send")
            for admin_id in self.settings.ADMIN_IDS:
                try:
                    await self.bot.send_message(
                        chat_id=admin_id,
                        text=message,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                        reply_markup=reply_markup,
                    )
                except Exception:
                    logging.exception("Failed to send notification to admin %s.", admin_id)
            return

        for admin_id in self.settings.ADMIN_IDS:
            try:
                await queue_manager.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=reply_markup,
                )
            except Exception:
                logging.exception("Failed to queue notification to admin %s.", admin_id)

    async def notify_new_user_registration(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        email: Optional[str] = None,
        referred_by_id: Optional[int] = None,
    ):
        """Send notification about new user registration"""
        if not self.settings.LOG_NEW_USERS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        user_display = self._format_user_display(
            user_id=user_id,
            username=username,
            first_name=first_name,
            email=email,
        )

        referral_text = ""
        if referred_by_id:
            referrer_link = hd.link(str(referred_by_id), f"tg://user?id={referred_by_id}")
            referral_text = _(
                "log_referral_suffix",
                referrer_link=referrer_link,
            )

        message = _(
            "log_new_user_registration",
            user_id=user_id,
            user_display=user_display,
            referral_text=referral_text,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Send to log channel
        profile_keyboard = self._build_profile_keyboard(_, user_id, referred_by_id)
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def notify_new_email_user_registration(
        self,
        user_id: int,
        email: str,
        referred_by_id: Optional[int] = None,
    ):
        """Send notification about new user registration via email (Web App)."""
        if not self.settings.LOG_NEW_USERS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        referral_text = ""
        if referred_by_id:
            referrer_link = hd.link(str(referred_by_id), f"tg://user?id={referred_by_id}")
            referral_text = _(
                "log_referral_suffix",
                referrer_link=referrer_link,
            )

        message = _(
            "log_new_email_user_registration",
            user_id=user_id,
            email=hd.quote(email),
            referral_text=referral_text,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Email users have a synthetic (negative) user_id with no Telegram profile,
        # so we only attach the referrer button when a real referrer is present.
        reply_markup: Optional[InlineKeyboardMarkup] = None
        if referred_by_id and referred_by_id > 0:
            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=_("log_open_referrer_profile_button"),
                            url=f"tg://user?id={referred_by_id}",
                        )
                    ]
                ]
            )

        await self._send_to_log_channel(message, reply_markup=reply_markup)

    async def notify_account_email_linked(
        self,
        user_id: int,
        email: str,
        telegram_id: Optional[int] = None,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ):
        """Send notification when an email is linked to a Telegram-created account."""
        if not self.settings.LOG_NEW_USERS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        user_display = self._format_user_display(
            user_id=telegram_id or user_id,
            username=username,
            first_name=first_name,
            email=email,
        )

        message = _(
            "log_account_email_linked",
            user_id=user_id,
            telegram_id=telegram_id or user_id,
            user_display=user_display,
            email=hd.quote(email),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        reply_markup: Optional[InlineKeyboardMarkup] = None
        if telegram_id and telegram_id > 0:
            reply_markup = self._build_profile_keyboard(_, telegram_id)

        await self._send_to_log_channel(message, reply_markup=reply_markup)

    async def notify_account_telegram_linked(
        self,
        user_id: int,
        email: Optional[str],
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ):
        """Send notification when Telegram is linked to an email-created account."""
        if not self.settings.LOG_NEW_USERS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        user_display = self._format_user_display(
            user_id=telegram_id,
            username=username,
            first_name=first_name,
            email=email,
        )

        message = _(
            "log_account_telegram_linked",
            user_id=user_id,
            telegram_id=telegram_id,
            user_display=user_display,
            email=hd.quote(email or ""),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        profile_keyboard = self._build_profile_keyboard(_, telegram_id)
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def notify_account_merged(
        self,
        *,
        primary_user_id: int,
        removed_user_id: int,
        email: Optional[str],
        telegram_id: Optional[int],
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        final_end_date_text: Optional[str] = None,
        primary_panel_user_uuid: Optional[str] = None,
        removed_panel_user_uuid: Optional[str] = None,
    ):
        """Send notification when duplicate email/Telegram accounts are merged."""
        if not self.settings.LOG_NEW_USERS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        display_user_id = int(telegram_id or primary_user_id)
        user_display = self._format_user_display(
            user_id=display_user_id,
            username=username,
            first_name=first_name,
            email=email,
        )

        message = _(
            "log_account_merged",
            primary_user_id=primary_user_id,
            removed_user_id=removed_user_id,
            telegram_id=telegram_id or "",
            user_display=user_display,
            email=hd.quote(email or ""),
            final_end_date=hd.quote(final_end_date_text or ""),
            primary_panel_user_uuid=hd.quote(primary_panel_user_uuid or ""),
            removed_panel_user_uuid=hd.quote(removed_panel_user_uuid or ""),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        profile_keyboard = (
            self._build_profile_keyboard(_, int(telegram_id)) if telegram_id else None
        )
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    def _format_traffic_gb_admin(self, traffic_gb: float) -> str:
        value = float(traffic_gb)
        if value.is_integer():
            return str(int(value))
        return f"{value:g}"

    def _tariff_display_for_log(self, tariff_key: Optional[str]) -> str:
        if not tariff_key:
            return ""
        cfg = getattr(self.settings, "tariffs_config", None)
        if not cfg:
            return str(tariff_key)
        try:
            tariff = cfg.require(str(tariff_key))
            return str(tariff.name(self.settings.DEFAULT_LANGUAGE))
        except Exception:
            return str(tariff_key)

    async def notify_payment_received(
        self,
        user_id: int,
        amount: float,
        currency: str,
        months: int,
        payment_provider: str,
        username: Optional[str] = None,
        email: Optional[str] = None,
        traffic_gb: Optional[float] = None,
        *,
        traffic_is_premium: bool = False,
        tariff_key: Optional[str] = None,
        purchased_hwid_devices: Optional[int] = None,
        purchases: Optional[tuple[PaymentPurchase, ...]] = None,
    ):
        """Send notification about successful payment"""
        if not self.settings.LOG_PAYMENTS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        user_display = self._format_user_display(
            user_id=user_id,
            username=username,
            email=email,
        )

        try:
            from bot.payment_providers import provider_emoji_map

            provider_emoji = provider_emoji_map(self.settings).get(payment_provider.lower(), "💰")
        except Exception:
            provider_emoji = "💰"

        effective_purchases = (
            purchases
            if purchases is not None
            else payment_purchases_from_legacy_fields(
                traffic_gb=traffic_gb,
                traffic_is_premium=traffic_is_premium,
                purchased_hwid_devices=purchased_hwid_devices,
            )
        )
        purchase_summary_parts = [
            self._format_payment_purchase_line(_, purchase) for purchase in effective_purchases
        ]
        purchase_summary = "\n".join(line for line in purchase_summary_parts if line)
        has_traffic_purchase = any(purchase.kind == "traffic" for purchase in effective_purchases)

        if has_traffic_purchase:
            traffic_purchase = next(
                purchase for purchase in effective_purchases if purchase.kind == "traffic"
            )
            traffic_kind = _(
                "log_payment_traffic_kind_premium"
                if traffic_purchase.scope == "premium"
                else "log_payment_traffic_kind_regular",
            )
            purchase_summary = purchase_summary or _(
                "log_payment_traffic_purchase_line",
                gb=self._format_traffic_gb_admin(float(traffic_purchase.amount)),
                kind=traffic_kind,
            )

            tariff_name = self._tariff_display_for_log(tariff_key)
            tariff_line = (
                _("log_payment_tariff_line", name=hd.quote(tariff_name)) if tariff_name else ""
            )
            message = _(
                "log_payment_received_traffic",
                provider_emoji=provider_emoji,
                user_display=user_display,
                amount=amount,
                currency=currency,
                traffic_summary=purchase_summary,
                tariff_line=tariff_line,
                payment_provider=payment_provider,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        elif effective_purchases:
            tariff_name = self._tariff_display_for_log(tariff_key)
            tariff_line = (
                _("log_payment_tariff_line", name=hd.quote(tariff_name)) if tariff_name else ""
            )
            period_line = _("log_payment_period_line", months=months) if months else ""
            purchase_summary_line = _(
                "log_payment_purchase_summary_line",
                summary=purchase_summary,
            )
            message = _(
                "log_payment_received_with_purchases",
                provider_emoji=provider_emoji,
                user_display=user_display,
                amount=amount,
                currency=currency,
                period_line=period_line,
                purchase_summary_line=purchase_summary_line,
                tariff_line=tariff_line,
                payment_provider=payment_provider,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        else:
            message = _(
                "log_payment_received",
                provider_emoji=provider_emoji,
                user_display=user_display,
                amount=amount,
                currency=currency,
                months=months,
                payment_provider=payment_provider,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

        # Send to log channel
        profile_keyboard = self._build_profile_keyboard(_, user_id)
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    def _format_payment_purchase_line(
        self,
        translate: Callable[..., str],
        purchase: PaymentPurchase,
    ) -> str:
        if purchase.kind == "traffic":
            traffic_kind = translate(
                "log_payment_traffic_kind_premium"
                if purchase.scope == "premium"
                else "log_payment_traffic_kind_regular"
            )
            return translate(
                "log_payment_traffic_purchase_line",
                gb=self._format_traffic_gb_admin(float(purchase.amount)),
                kind=traffic_kind,
            )
        if purchase.kind == "hwid_devices":
            return translate(
                "log_payment_hwid_devices_purchase_line",
                count=int(float(purchase.amount)),
            )
        amount_label = self._format_traffic_gb_admin(float(purchase.amount))
        label_kwargs = {
            "amount": amount_label,
            "unit": purchase.unit,
            "kind": purchase.kind,
            "scope": purchase.scope or "",
            **dict(purchase.label_kwargs),
        }
        if purchase.label_key:
            return translate(purchase.label_key, **label_kwargs)
        return translate("log_payment_generic_purchase_line", **label_kwargs)

    async def notify_promo_activation(
        self,
        user_id: int,
        promo_code: str,
        bonus_days: int,
        username: Optional[str] = None,
        email: Optional[str] = None,
    ):
        """Send notification about promo code activation"""
        if not self.settings.LOG_PROMO_ACTIVATIONS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        user_display = self._format_user_display(
            user_id=user_id,
            username=username,
            email=email,
        )

        message = _(
            "log_promo_activation",
            user_display=user_display,
            promo_code=promo_code,
            bonus_days=bonus_days,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Send to log channel
        profile_keyboard = self._build_profile_keyboard(_, user_id)
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def notify_trial_activation(
        self,
        user_id: int,
        end_date: datetime,
        username: Optional[str] = None,
        email: Optional[str] = None,
    ):
        """Send notification about trial activation"""
        if not self.settings.LOG_TRIAL_ACTIVATIONS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        user_display = self._format_user_display(
            user_id=user_id,
            username=username,
            email=email,
        )

        message = _(
            "log_trial_activation",
            user_display=user_display,
            end_date=end_date.strftime("%Y-%m-%d %H:%M"),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Send to log channel
        profile_keyboard = self._build_profile_keyboard(_, user_id)
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def notify_panel_sync(
        self,
        status: str,
        details: str,
        users_processed: int,
        subs_synced: int,
        username: Optional[str] = None,
    ):
        """Send notification about panel synchronization"""
        if not getattr(self.settings, "LOG_PANEL_SYNC", True):
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        # Status emoji based on sync result
        status_emoji = {"completed": "✅", "completed_with_errors": "⚠️", "failed": "❌"}.get(
            status, "🔄"
        )

        message = _(
            "log_panel_sync",
            status_emoji=status_emoji,
            status=status,
            users_processed=users_processed,
            subs_synced=subs_synced,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z"),
            details=details,
        )

        # Send to log channel
        await self._send_to_log_channel(message)

    async def notify_suspicious_promo_attempt(
        self,
        user_id: int,
        suspicious_input: str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        email: Optional[str] = None,
    ):
        """Send notification about a suspicious promo code attempt."""
        if not self.settings.LOG_SUSPICIOUS_ACTIVITY:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        user_display = self._format_user_display(
            user_id=user_id,
            username=username,
            first_name=first_name,
            email=email,
        )

        message = _(
            "log_suspicious_promo",
            user_display=user_display,
            user_id=user_id,
            suspicious_input=hd.quote(suspicious_input),
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z"),
        )

        # Send to log channel
        profile_keyboard = self._build_profile_keyboard(_, user_id)
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def send_custom_notification(
        self,
        message: str,
        to_admins: bool = False,
        to_log_channel: bool = True,
        thread_id: Optional[int] = None,
    ):
        """Send custom notification message"""
        if to_log_channel:
            await self._send_to_log_channel(message, thread_id)
        if to_admins:
            await self._send_to_admins(message)


# Removed legacy helper functions that duplicated NotificationService API
