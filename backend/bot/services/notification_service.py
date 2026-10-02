import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.text_decorations import html_decoration as hd
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from bot.infra.payment_events import (
    PaymentPurchase,
    payment_purchases_from_legacy_fields,
    sale_mode_base,
)
from bot.middlewares.i18n import JsonI18n
from bot.services.email_auth_service import EmailAuthService
from bot.services.notification_partner import NotificationPartnerMixin
from bot.services.notification_support import NotificationSupportMixin
from bot.utils.message_queue import get_queue_manager
from bot.utils.subscription_periods import format_duration_days
from bot.utils.telegram_markup import (
    is_profile_link_error,
    remove_profile_link_buttons,
)
from config.settings import Settings
from db.auth_models import AccountRole
from db.models import User

logger = logging.getLogger(__name__)


class NotificationService(NotificationPartnerMixin, NotificationSupportMixin):
    """Enhanced notification service for sending messages to admins and log channels"""

    def __init__(
        self,
        bot: Bot | None,
        settings: Settings,
        i18n: JsonI18n | None = None,
        *,
        session_factory: sessionmaker | None = None,
        email_auth_service: EmailAuthService | None = None,
        bot_username: str | None = None,
    ) -> None:
        self.bot = bot
        self.settings = settings
        self.i18n = i18n
        self.session_factory = session_factory
        self.email_auth_service = email_auth_service
        self.bot_username = bot_username or ""

    @staticmethod
    def _external_auth_provider_label(translate: Callable[..., str], provider: str | None) -> str:
        key = {
            "google": "log_auth_provider_google",
            "yandex": "log_auth_provider_yandex",
        }.get(str(provider or "").lower())
        return hd.quote(translate(key) if key else str(provider or ""))

    async def _send_to_log_channel(
        self,
        message: str,
        thread_id: int | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        """Send message to configured log channel/group using message queue"""
        if not self.settings.LOG_CHAT_ID or self.bot is None:
            return

        queue_manager = get_queue_manager()
        if not queue_manager:
            logger.warning("Message queue manager not available, falling back to direct send")
            final_thread_id = thread_id or self.settings.LOG_THREAD_ID

            def _build_kwargs(markup: InlineKeyboardMarkup | None) -> dict[str, Any]:
                kwargs: dict[str, Any] = {
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
                    logger.warning(
                        "Telegram rejected profile buttons for log chat %s: %s. "
                        "Retrying without tg:// links.",
                        self.settings.LOG_CHAT_ID,
                        getattr(exc, "message", "") or str(exc),
                    )
                    try:
                        await self.bot.send_message(**_build_kwargs(fallback_markup))
                    except Exception as retry_exc:
                        logger.error(
                            "Failed to send notification without profile buttons to log channel "
                            "%s: %s",
                            self.settings.LOG_CHAT_ID,
                            retry_exc,
                        )
                    return
                logger.error(
                    "Failed to send notification to log channel %s: %s",
                    self.settings.LOG_CHAT_ID,
                    exc,
                )
            except Exception:
                logger.exception(
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
            logger.exception(
                "Failed to queue notification to log channel %s.", self.settings.LOG_CHAT_ID
            )

    async def _admin_telegram_ids(self) -> list[int]:
        if self.session_factory is None:
            return []
        async with self.session_factory() as session:
            result = await session.execute(
                select(User.telegram_id)
                .join(AccountRole, AccountRole.user_id == User.user_id)
                .where(
                    AccountRole.role.in_(("owner", "admin")),
                    AccountRole.revoked_at.is_(None),
                    User.telegram_id.is_not(None),
                    User.is_banned.is_(False),
                )
                .distinct()
            )
            return [int(chat_id) for chat_id in result.scalars().all()]

    async def _send_to_admins(
        self,
        message: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        """Send message to all admin users using message queue"""
        if self.bot is None:
            return

        admin_telegram_ids = await self._admin_telegram_ids()
        if not admin_telegram_ids:
            return

        queue_manager = get_queue_manager()
        if not queue_manager:
            logger.warning("Message queue manager not available, falling back to direct send")
            for admin_id in admin_telegram_ids:
                try:
                    await self.bot.send_message(
                        chat_id=admin_id,
                        text=message,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                        reply_markup=reply_markup,
                    )
                except Exception:
                    logger.exception("Failed to send notification to admin %s.", admin_id)
            return

        for admin_id in admin_telegram_ids:
            try:
                await queue_manager.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=reply_markup,
                )
            except Exception:
                logger.exception("Failed to queue notification to admin %s.", admin_id)

    async def notify_new_user_registration(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        email: str | None = None,
        referred_by_id: int | None = None,
        partner_user_id: int | None = None,
        telegram_id: int | None = None,
        minishop_id: str | None = None,
    ) -> None:
        """Send notification about new user registration"""
        if not self.settings.LOG_NEW_USERS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        public_id = await self._public_user_id(user_id, minishop_id)
        user_display, profile_keyboard = await self._user_log_context(
            _,
            user_id,
            minishop_id=public_id,
            username=username,
            first_name=first_name,
            email=email,
            telegram_id=telegram_id,
        )

        referral_text, profile_keyboard = await self._registration_inviter_context(
            _,
            referred_by_id=referred_by_id,
            partner_user_id=partner_user_id,
            profile_keyboard=profile_keyboard,
        )

        message = _(
            "log_new_user_registration",
            user_id=hd.quote(public_id),
            user_display=user_display,
            referral_text=referral_text,
            timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Send to log channel
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def notify_new_email_user_registration(
        self,
        user_id: int,
        email: str,
        referred_by_id: int | None = None,
        partner_user_id: int | None = None,
        minishop_id: str | None = None,
    ) -> None:
        """Send notification about new user registration via email (Web App)."""
        if not self.settings.LOG_NEW_USERS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k
        public_id = await self._public_user_id(user_id, minishop_id)

        user_display, profile_keyboard = await self._user_log_context(
            _, user_id, minishop_id=public_id, email=email
        )
        referral_text, profile_keyboard = await self._registration_inviter_context(
            _,
            referred_by_id=referred_by_id,
            partner_user_id=partner_user_id,
            profile_keyboard=profile_keyboard,
        )

        message = _(
            "log_new_email_user_registration",
            user_id=hd.quote(public_id),
            user_display=user_display,
            email=hd.quote(email),
            referral_text=referral_text,
            timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )

        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def notify_new_external_user_registration(
        self,
        *,
        user_id: int,
        provider: str,
        email: str,
        referred_by_id: int | None = None,
        partner_user_id: int | None = None,
        minishop_id: str | None = None,
    ) -> None:
        """Send a provider-aware notification for an external OAuth registration."""
        if not self.settings.LOG_NEW_USERS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k
        public_id = await self._public_user_id(user_id, minishop_id)

        user_display, profile_keyboard = await self._user_log_context(
            _, user_id, minishop_id=public_id, email=email
        )
        referral_text, profile_keyboard = await self._registration_inviter_context(
            _,
            referred_by_id=referred_by_id,
            partner_user_id=partner_user_id,
            profile_keyboard=profile_keyboard,
        )

        message = _(
            "log_new_external_user_registration",
            user_id=hd.quote(public_id),
            user_display=user_display,
            provider=self._external_auth_provider_label(_, provider),
            email=hd.quote(email),
            referral_text=referral_text,
            timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def notify_account_email_linked(
        self,
        user_id: int,
        email: str,
        telegram_id: int | None = None,
        username: str | None = None,
        first_name: str | None = None,
    ) -> None:
        """Send notification when an email is linked to a Telegram-created account."""
        if not self.settings.LOG_NEW_USERS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k
        public_id = await self._public_user_id(user_id)

        user_display, profile_keyboard = await self._user_log_context(
            _,
            user_id,
            minishop_id=public_id,
            username=username,
            first_name=first_name,
            email=email,
            telegram_id=telegram_id,
        )

        message = _(
            "log_account_email_linked",
            user_id=hd.quote(public_id),
            telegram_id=telegram_id or "—",
            user_display=user_display,
            email=hd.quote(email),
            timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )

        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def notify_account_telegram_linked(
        self,
        user_id: int,
        email: str | None,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> None:
        """Send notification when Telegram is linked to an email-created account."""
        if not self.settings.LOG_NEW_USERS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k
        public_id = await self._public_user_id(user_id)

        user_display, profile_keyboard = await self._user_log_context(
            _,
            user_id,
            minishop_id=public_id,
            username=username,
            first_name=first_name,
            email=email,
            telegram_id=telegram_id,
        )

        message = _(
            "log_account_telegram_linked",
            user_id=hd.quote(public_id),
            telegram_id=telegram_id,
            user_display=user_display,
            email=hd.quote(email or ""),
            timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )

        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def notify_account_external_identity_linked(
        self,
        *,
        user_id: int,
        provider: str,
        link_source: str,
        email: str | None,
        telegram_id: int | None,
        username: str | None = None,
        first_name: str | None = None,
    ) -> None:
        """Send a provider-aware notification when an external identity is linked."""
        if not self.settings.LOG_NEW_USERS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k
        source_key = {
            "settings": "log_external_link_source_settings",
            "email_confirmation": "log_external_link_source_email_confirmation",
            "provider_verified_email": "log_external_link_source_provider_verified_email",
        }.get(link_source, "log_external_link_source_settings")
        display_user_id = await self._public_user_id(user_id)
        user_display, profile_keyboard = await self._user_log_context(
            _,
            user_id,
            minishop_id=display_user_id,
            username=username,
            first_name=first_name,
            email=email,
            telegram_id=telegram_id,
        )
        message = _(
            "log_account_external_identity_linked",
            user_id=hd.quote(display_user_id),
            provider=self._external_auth_provider_label(_, provider),
            link_source=hd.quote(_(source_key)),
            user_display=user_display,
            email=hd.quote(email or ""),
            timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def notify_account_merged(
        self,
        *,
        primary_user_id: int,
        removed_user_id: int,
        email: str | None,
        telegram_id: int | None,
        username: str | None = None,
        first_name: str | None = None,
        final_end_date_text: str | None = None,
        primary_panel_user_uuid: str | None = None,
        source_panel_user_uuid: str | None = None,
        reason: str | None = None,
        provider: str | None = None,
        primary_minishop_id: str | None = None,
        removed_minishop_id: str | None = None,
    ) -> None:
        """Send notification when duplicate email/Telegram accounts are merged."""
        if not self.settings.LOG_NEW_USERS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        display_user_id = await self._public_user_id(primary_user_id, primary_minishop_id)
        removed_display_id = await self._public_user_id(removed_user_id, removed_minishop_id)
        user_display, profile_keyboard = await self._user_log_context(
            _,
            primary_user_id,
            minishop_id=display_user_id,
            username=username,
            first_name=first_name,
            email=email,
            telegram_id=telegram_id,
        )
        merge_source = ""
        if provider:
            merge_source = self._external_auth_provider_label(_, provider)
        else:
            source_key = {
                "email_link": "log_account_merge_source_email",
                "telegram_link": "log_account_merge_source_telegram",
                "login": "log_account_merge_source_login",
            }.get(str(reason or ""))
            if source_key:
                merge_source = hd.quote(_(source_key))

        primary_panel_uuid = str(primary_panel_user_uuid or "").strip()
        source_panel_uuid = str(source_panel_user_uuid or "").strip()
        if primary_panel_uuid and source_panel_uuid == primary_panel_uuid:
            panel_operation = _(
                "log_account_merge_panel_unchanged",
                panel_user_uuid=hd.quote(primary_panel_uuid),
            )
        elif primary_panel_uuid and source_panel_uuid:
            panel_operation = _(
                "log_account_merge_panel_distinct",
                primary_panel_user_uuid=hd.quote(primary_panel_uuid),
                source_panel_user_uuid=hd.quote(source_panel_uuid),
            )
        elif primary_panel_uuid:
            panel_operation = _(
                "log_account_merge_panel_current",
                panel_user_uuid=hd.quote(primary_panel_uuid),
            )
        else:
            panel_operation = ""

        message = _(
            "log_account_merged",
            primary_user_id=hd.quote(display_user_id),
            removed_user_id=hd.quote(removed_display_id),
            telegram_id=telegram_id or "",
            user_display=user_display,
            email=hd.quote(email or ""),
            final_end_date=hd.quote(final_end_date_text or ""),
            panel_operation=panel_operation,
            merge_source=merge_source,
            timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )

        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    def _format_traffic_gb_admin(self, traffic_gb: float) -> str:
        value = float(traffic_gb)
        if value.is_integer():
            return str(int(value))
        return f"{value:g}"

    def _tariff_display_for_log(self, tariff_key: str | None) -> str:
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
        username: str | None = None,
        email: str | None = None,
        traffic_gb: float | None = None,
        *,
        traffic_is_premium: bool = False,
        tariff_key: str | None = None,
        purchased_hwid_devices: int | None = None,
        purchases: tuple[PaymentPurchase, ...] | None = None,
        sale_mode: str | None = None,
        payment_id: int | None = None,
        duration_days: int | None = None,
        promo_code: str | None = None,
        discount_amount: float | None = None,
        minishop_id: str | None = None,
        telegram_id: int | None = None,
    ) -> None:
        """Send notification about successful payment"""
        if not self.settings.LOG_PAYMENTS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        user_display, profile_keyboard = await self._user_log_context(
            _,
            user_id,
            minishop_id=await self._public_user_id(user_id, minishop_id),
            username=username,
            email=email,
            telegram_id=telegram_id,
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

        if sale_mode_base(sale_mode) == "balance_topup":
            message = _(
                "log_balance_topup_received",
                provider_emoji=provider_emoji,
                user_display=user_display,
                amount=amount,
                currency=currency,
                payment_provider=payment_provider,
                payment_id=payment_id if payment_id is not None else "—",
                timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            )
        elif sale_mode_base(sale_mode) == "tariff_upgrade":
            tariff_name = self._tariff_display_for_log(tariff_key)
            message = _(
                "log_payment_tariff_upgrade_received",
                provider_emoji=provider_emoji,
                user_display=user_display,
                amount=amount,
                currency=currency,
                tariff_line=_("log_payment_tariff_line", name=hd.quote(tariff_name))
                if tariff_name
                else "",
                purchase_summary_line=_(
                    "log_payment_purchase_summary_line", summary=purchase_summary
                )
                if purchase_summary
                else "",
                payment_provider=payment_provider,
                payment_id=payment_id if payment_id is not None else "—",
                timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            )
        elif has_traffic_purchase:
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
                timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            )
        elif effective_purchases:
            tariff_name = self._tariff_display_for_log(tariff_key)
            tariff_line = (
                _("log_payment_tariff_line", name=hd.quote(tariff_name)) if tariff_name else ""
            )
            period_line = (
                _(
                    "log_payment_period_days_line",
                    period=format_duration_days(duration_days, _, admin_lang),
                )
                if duration_days
                else _("log_payment_period_line", months=months)
                if months
                else ""
            )
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
                timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            )
        else:
            message = _(
                "log_payment_received_days" if duration_days else "log_payment_received",
                provider_emoji=provider_emoji,
                user_display=user_display,
                amount=amount,
                currency=currency,
                months=months,
                period=format_duration_days(duration_days, _, admin_lang) if duration_days else "",
                payment_provider=payment_provider,
                timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            )

        payment_detail_lines: list[str] = []
        if promo_code:
            payment_detail_lines.append(
                _("log_payment_promo_code_line", promo_code=hd.quote(promo_code))
            )
        if discount_amount is not None and discount_amount > 0:
            payment_detail_lines.append(
                _(
                    "log_payment_discount_line",
                    discount_amount=self._format_traffic_gb_admin(discount_amount),
                    currency=hd.quote(currency),
                )
            )
        if payment_detail_lines:
            message = f"{message}\n" + "\n".join(payment_detail_lines)

        # Send to log channel
        if "gift" in str(sale_mode or "").split("|"):
            message = (
                _(
                    "log_gift_created_by_admin"
                    if payment_provider == "admin_gift"
                    else "log_gift_purchase",
                    payment_id=payment_id or "—",
                )
                + "\n\n"
                + message
            )
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
        regular_traffic_gb: float = 0,
        premium_traffic_gb: float = 0,
        username: str | None = None,
        email: str | None = None,
    ) -> None:
        """Send notification about promo code activation"""
        if not self.settings.LOG_PROMO_ACTIVATIONS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        user_display, profile_keyboard = await self._user_log_context(
            _,
            user_id,
            minishop_id=await self._public_user_id(user_id),
            username=username,
            email=email,
        )

        bonus_parts: list[str] = []
        if bonus_days > 0:
            bonus_parts.append(_("promo_bonus_days_short", days=bonus_days))
        if regular_traffic_gb > 0:
            bonus_parts.append(
                _(
                    "promo_bonus_regular_traffic_short",
                    gb=self._format_traffic_gb_admin(regular_traffic_gb),
                )
            )
        if premium_traffic_gb > 0:
            bonus_parts.append(
                _(
                    "promo_bonus_premium_traffic_short",
                    gb=self._format_traffic_gb_admin(premium_traffic_gb),
                )
            )
        message = _(
            "log_promo_activation",
            user_display=user_display,
            promo_code=promo_code,
            bonus=", ".join(bonus_parts) or "-",
            timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Send to log channel
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def notify_trial_activation(
        self,
        user_id: int,
        end_date: datetime,
        username: str | None = None,
        email: str | None = None,
    ) -> None:
        """Send notification about trial activation"""
        if not self.settings.LOG_TRIAL_ACTIVATIONS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        user_display, profile_keyboard = await self._user_log_context(
            _,
            user_id,
            minishop_id=await self._public_user_id(user_id),
            username=username,
            email=email,
        )

        message = _(
            "log_trial_activation",
            user_display=user_display,
            end_date=end_date.strftime("%Y-%m-%d %H:%M"),
            timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Send to log channel
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def notify_panel_sync(
        self,
        status: str,
        details: str,
        users_processed: int,
        subs_synced: int,
        username: str | None = None,
    ) -> None:
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
            timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S %Z"),
            details=details,
        )

        # Send to log channel
        await self._send_to_log_channel(message)

    async def notify_suspicious_promo_attempt(
        self,
        user_id: int,
        suspicious_input: str,
        username: str | None = None,
        first_name: str | None = None,
        email: str | None = None,
        minishop_id: str | None = None,
    ) -> None:
        """Send notification about a suspicious promo code attempt."""
        if not self.settings.LOG_SUSPICIOUS_ACTIVITY:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        public_id = await self._public_user_id(user_id, minishop_id)
        user_display, profile_keyboard = await self._user_log_context(
            _, user_id, minishop_id=public_id, username=username, first_name=first_name, email=email
        )

        message = _(
            "log_suspicious_promo",
            user_display=user_display,
            user_id=hd.quote(public_id),
            suspicious_input=hd.quote(suspicious_input),
            timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S %Z"),
        )

        # Send to log channel
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def send_custom_notification(
        self,
        message: str,
        to_admins: bool = False,
        to_log_channel: bool = True,
        thread_id: int | None = None,
    ) -> None:
        """Send custom notification message"""
        if to_log_channel:
            await self._send_to_log_channel(message, thread_id)
        if to_admins:
            await self._send_to_admins(message)


# Removed legacy helper functions that duplicated NotificationService API
