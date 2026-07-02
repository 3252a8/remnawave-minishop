import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.email_auth_service import EmailAuthService
from bot.services.email_templates import render_payment_success
from config.tariffs_config import default_payment_currency_code_for_settings
from db.dal import payment_dal, subscription_dal, user_dal
from db.models import User

from ._typing import SubscriptionServiceMixinContract


class PaymentContextMixin(SubscriptionServiceMixinContract):
    # Human-readable provider names rendered in payment-success emails.
    # Keys are the lowercased value persisted in ``subscriptions.provider``
    # (see the call sites in lifecycle.py / traffic.py); missing keys produce
    # no row in the email rather than raising.
    _PROVIDER_LABELS = {
        "yookassa": "YooKassa",
        "freekassa": "FreeKassa",
        "platega": "Platega",
        "severpay": "SeverPay",
        "wata": "Wata",
        "lava": "LAVA",
        "pally": "Pally",
        "cryptopay": "Crypto Pay",
        "paykilla": "PayKilla",
        "cloudpayments": "CloudPayments",
        "telegram_stars": "Telegram Stars",
    }

    async def _record_payment_context(
        self,
        session: AsyncSession,
        payment_db_id: int,
        *,
        sale_mode: str,
        tariff_key: str | None,
        purchased_gb: float | None = None,
        purchased_hwid_devices: int | None = None,
        hwid_valid_from: datetime | None = None,
        hwid_valid_until: datetime | None = None,
        hwid_pricing_period_months: int | None = None,
        hwid_proration_ratio: float | None = None,
        hwid_full_price: float | None = None,
    ) -> None:
        payment = await payment_dal.get_payment_by_db_id(session, payment_db_id)
        if not payment:
            return
        payment.sale_mode = sale_mode
        payment.tariff_key = tariff_key
        payment.purchased_gb = purchased_gb
        if purchased_hwid_devices is not None:
            payment.purchased_hwid_devices = purchased_hwid_devices
        if hwid_valid_from is not None:
            payment.hwid_valid_from = hwid_valid_from
        if hwid_valid_until is not None:
            payment.hwid_valid_until = hwid_valid_until
        if hwid_pricing_period_months is not None:
            payment.hwid_pricing_period_months = hwid_pricing_period_months
        if hwid_proration_ratio is not None:
            payment.hwid_proration_ratio = hwid_proration_ratio
        if hwid_full_price is not None:
            payment.hwid_full_price = hwid_full_price
        await session.flush()

    async def get_user_language(self, session: AsyncSession, user_id: int) -> str:
        user_record = await user_dal.get_user_by_id(session, user_id)
        return str(
            user_record.language_code
            if user_record and user_record.language_code
            else self.settings.DEFAULT_LANGUAGE
        )

    async def has_had_any_subscription(self, session: AsyncSession, user_id: int) -> bool:
        return bool(await subscription_dal.has_any_subscription_for_user(session, user_id))

    async def has_trial_blocking_subscription(self, session: AsyncSession, user_id: int) -> bool:
        return bool(
            await subscription_dal.has_trial_blocking_subscription_for_user(session, user_id)
        )

    async def has_active_subscription(self, session: AsyncSession, user_id: int) -> bool:
        """Return True if user currently has an active subscription (end_date in future)."""
        try:
            user_record = await user_dal.get_user_by_id(session, user_id)
            if not user_record or not user_record.panel_user_uuid:
                return False
            active_sub = await subscription_dal.get_active_subscription_by_user_id(
                session, user_id, user_record.panel_user_uuid
            )
            if not active_sub or not active_sub.end_date:
                return False
            from datetime import datetime

            return bool(active_sub.is_active and active_sub.end_date > datetime.now(UTC))
        except Exception:
            return False

    async def _send_payment_success_email(
        self,
        *,
        db_user: User,
        sale_mode: str,
        months: int,
        traffic_gb: float | None,
        payment_amount: float,
        end_date: datetime | None,
        provider: str,
    ) -> None:
        """Best-effort branded email confirming the payment. No-op if SMTP or
        the user's email aren't set. Failures are logged and swallowed so the
        payment flow is never blocked by mail delivery."""
        if not getattr(
            self.settings,
            "smtp_delivery_configured",
            getattr(self.settings, "email_auth_configured", False),
        ):
            return
        recipient = (db_user.email or "").strip() if db_user else ""
        if not recipient:
            return

        end_date_text = end_date.strftime("%Y-%m-%d") if end_date else ""
        try:
            from bot.payment_providers import provider_label_map

            provider_label = provider_label_map(
                self.settings,
                db_user.language_code or self.settings.DEFAULT_LANGUAGE,
            ).get((provider or "").lower())
        except Exception:
            provider_label = self._PROVIDER_LABELS.get((provider or "").lower())
        dashboard_url = (self.settings.SUBSCRIPTION_MINI_APP_URL or "").strip() or None
        i18n = getattr(self, "i18n", None)

        try:
            content = render_payment_success(
                self.settings,
                language_code=db_user.language_code or self.settings.DEFAULT_LANGUAGE,
                sale_mode=sale_mode,
                months=int(months or 0),
                traffic_gb=traffic_gb,
                amount=float(payment_amount or 0),
                currency=default_payment_currency_code_for_settings(self.settings),
                end_date_text=end_date_text,
                dashboard_url=dashboard_url,
                provider_label=provider_label,
                i18n=i18n,
            )
            email_service = EmailAuthService(self.settings, i18n)
            await email_service.send_rendered_email(email=recipient, content=content)
        except Exception:
            logging.exception("Failed to send payment success email to user %s", db_user.user_id)

    async def update_last_notification_sent(
        self, session: AsyncSession, user_id: int, subscription_end_date: datetime
    ) -> None:
        sub_to_update = await subscription_dal.find_subscription_for_notification_update(
            session, user_id, subscription_end_date
        )
        if sub_to_update:
            await subscription_dal.update_subscription_notification_time(
                session, sub_to_update.subscription_id, datetime.now(UTC)
            )
            logging.info(
                f"Updated last_notification_sent for user {user_id}, sub_id {sub_to_update.subscription_id}"  # noqa: E501
            )
        else:
            logging.warning(
                f"Could not find subscription for user {user_id} ending at {subscription_end_date.isoformat()} to update notification time."  # noqa: E501
            )
