import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from aiogram import Bot
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra import events
from bot.middlewares.i18n import JsonI18n
from bot.services.user_email_notifications import send_user_notification_email
from config.settings import Settings
from db.dal import payment_dal, subscription_dal, user_dal

from .subscription_service import SubscriptionService


class ReferralService:
    def __init__(
        self,
        settings: Settings,
        subscription_service: SubscriptionService,
        bot: Bot,
        i18n: JsonI18n,
    ):
        self.settings = settings
        self.subscription_service = subscription_service
        self.bot = bot
        self.i18n = i18n

    async def apply_referral_bonuses_for_payment(
        self,
        session: AsyncSession,
        referee_user_id: int,
        purchased_subscription_months: int,
        current_payment_db_id: Optional[int] = None,
        skip_if_active_before_payment: bool = True,
        tariff_key: Optional[str] = None,
    ) -> Dict[str, Any]:

        referee_final_end_date: Optional[datetime] = None
        referee_bonus_applied_days: Optional[int] = None
        inviter_bonus_successfully_applied = False

        try:
            referee_user_model = await user_dal.get_user_by_id(session, referee_user_id)
            if not referee_user_model or referee_user_model.referred_by_id is None:
                logging.debug(
                    f"User {referee_user_id} not referred or inviter ID missing. No referral bonuses."  # noqa: E501
                )
                return {"referee_bonus_applied_days": None, "referee_new_end_date": None}

            # If configured to apply referral bonuses only once per invited user,
            # check if the referee already has succeeded payments.
            # Use getattr with a safe default (True) to avoid AttributeError if
            # running with an older settings schema.
            if getattr(self.settings, "REFERRAL_ONE_BONUS_PER_REFEREE", True):
                try:
                    succeeded_count = await payment_dal.count_user_succeeded_payments(
                        session, referee_user_id, exclude_payment_id=current_payment_db_id
                    )
                    if succeeded_count and succeeded_count > 0:
                        logging.info(
                            f"Referral bonuses skipped for user {referee_user_id}: already has {succeeded_count} succeeded payments."  # noqa: E501
                        )
                        return {"referee_bonus_applied_days": None, "referee_new_end_date": None}
                except Exception as e_cnt:
                    logging.error(
                        f"Failed counting succeeded payments for user {referee_user_id}: {e_cnt}"
                    )

            # Additionally, do not award referral bonuses if the user was active at payment time
            # (has an active subscription now). This avoids giving bonuses to already active users.
            if skip_if_active_before_payment:
                try:
                    if await self.subscription_service.has_active_subscription(
                        session, referee_user_id
                    ):
                        logging.info(
                            f"Referral bonuses skipped for user {referee_user_id}: user currently has an active subscription."  # noqa: E501
                        )
                        return {"referee_bonus_applied_days": None, "referee_new_end_date": None}
                except Exception as e_sub:
                    logging.error(
                        f"Failed to check active subscription for {referee_user_id}: {e_sub}"
                    )

            inviter_user_id = referee_user_model.referred_by_id
            inviter_user_model = await user_dal.get_user_by_id(session, inviter_user_id)

            referee_name_for_msg = referee_user_model.first_name or f"User {referee_user_id}"

            default_lang_for_placeholder = self.settings.DEFAULT_LANGUAGE
            inviter_name_for_referee_msg = (
                inviter_user_model.first_name
                if inviter_user_model and inviter_user_model.first_name
                else self.i18n.gettext(default_lang_for_placeholder, "friend_placeholder")
            )

            inviter_bonus_days, referee_bonus_days = self._referral_bonus_days_for_payment(
                purchased_subscription_months,
                tariff_key=tariff_key,
            )

            if inviter_bonus_days and inviter_bonus_days > 0:
                if not inviter_user_model:
                    logging.warning(
                        f"Inviter user {inviter_user_id} not found in local DB. Cannot apply inviter bonus."  # noqa: E501
                    )
                else:
                    (
                        inviter_panel_uuid,
                        inviter_panel_sub_link_id,
                        _,
                        _,
                    ) = await self.subscription_service._get_or_create_panel_user_link_details(
                        session, inviter_user_id, inviter_user_model
                    )

                    if not inviter_panel_uuid:
                        logging.warning(
                            f"Failed to get/create panel link for inviter {inviter_user_id}. Cannot apply inviter bonus directly to panel."  # noqa: E501
                        )

                    else:
                        new_end_date_inviter = (
                            await self.subscription_service.extend_active_subscription_days(
                                session=session,
                                user_id=inviter_user_id,
                                bonus_days=inviter_bonus_days,
                                reason=f"referral bonus from {referee_name_for_msg}",
                            )
                        )

                        if new_end_date_inviter:
                            inviter_bonus_successfully_applied = True
                            logging.info(
                                f"Bonus of {inviter_bonus_days} days successfully applied/extended for inviter {inviter_user_id}."  # noqa: E501
                            )

                            try:
                                inviter_lang = (
                                    inviter_user_model.language_code or default_lang_for_placeholder
                                )
                                _i = lambda k, **kw: self.i18n.gettext(inviter_lang, k, **kw)
                                message_text = _i(
                                    "referral_bonus_inviter_notification_extended",
                                    days=inviter_bonus_days,
                                    referee_name=referee_name_for_msg,
                                    new_end_date=new_end_date_inviter.strftime("%Y-%m-%d"),
                                )
                                try:
                                    await self.bot.send_message(inviter_user_id, message_text)
                                except Exception as e_notify_inviter:
                                    logging.error(
                                        f"Failed to send bonus notification to inviter {inviter_user_id}: {e_notify_inviter}"  # noqa: E501
                                    )
                                await send_user_notification_email(
                                    settings=self.settings,
                                    i18n=self.i18n,
                                    user=inviter_user_model,
                                    subject_key="email_referral_bonus_subject",
                                    message_text=message_text,
                                    dashboard_url=(
                                        getattr(
                                            self.settings,
                                            "SUBSCRIPTION_MINI_APP_URL",
                                            "",
                                        )
                                        or None
                                    ),
                                )
                            except Exception as e_notify_inviter:
                                logging.error(
                                    f"Failed to prepare bonus notification for inviter {inviter_user_id}: {e_notify_inviter}"  # noqa: E501
                                )
                        else:
                            logging.info(
                                f"Inviter {inviter_user_id} has no active sub to extend. Creating new bonus subscription for {inviter_bonus_days} days."  # noqa: E501
                            )

                            bonus_start_date = datetime.now(timezone.utc)
                            bonus_end_date = bonus_start_date + timedelta(days=inviter_bonus_days)

                            if not inviter_panel_sub_link_id:
                                logging.error(
                                    f"Cannot create bonus subscription for inviter {inviter_user_id}: panel_sub_link_id is missing even after link detail fetch."  # noqa: E501
                                )
                            else:
                                bonus_sub_payload = {
                                    "user_id": inviter_user_id,
                                    "panel_user_uuid": inviter_panel_uuid,
                                    "panel_subscription_uuid": inviter_panel_sub_link_id,
                                    "start_date": bonus_start_date,
                                    "end_date": bonus_end_date,
                                    "duration_months": 0,
                                    "is_active": True,
                                    "status_from_panel": "ACTIVE_BONUS",
                                    "traffic_limit_bytes": self.settings.user_traffic_limit_bytes,
                                    "auto_renew_enabled": False,
                                    # Short bonus grant: warn only hours before it
                                    # ends, not days ahead. A real payment clears this.
                                    "suppress_early_expiry_notifications": True,
                                }
                                try:
                                    await subscription_dal.deactivate_other_active_subscriptions(
                                        session, inviter_panel_uuid, inviter_panel_sub_link_id
                                    )
                                    bonus_sub = await subscription_dal.upsert_subscription(
                                        session, bonus_sub_payload
                                    )

                                    panel_update_success = await self.subscription_service.panel_service.update_user_details_on_panel(  # noqa: E501
                                        inviter_panel_uuid,
                                        {
                                            "expireAt": bonus_end_date.isoformat(
                                                timespec="milliseconds"
                                            ).replace("+00:00", "Z"),
                                            "status": "ACTIVE",
                                        },
                                    )
                                    if panel_update_success:
                                        inviter_bonus_successfully_applied = True
                                        logging.info(
                                            f"New bonus subscription for {inviter_bonus_days} days created for inviter {inviter_user_id}."  # noqa: E501
                                        )

                                        inviter_lang = (
                                            inviter_user_model.language_code
                                            or default_lang_for_placeholder
                                        )
                                        _i = lambda k, **kw: self.i18n.gettext(
                                            inviter_lang, k, **kw
                                        )
                                        message_text = _i(
                                            "referral_bonus_inviter_notification_new_sub",
                                            days=inviter_bonus_days,
                                            referee_name=referee_name_for_msg,
                                            new_end_date=bonus_end_date.strftime("%Y-%m-%d"),
                                        )
                                        try:
                                            await self.bot.send_message(
                                                inviter_user_id,
                                                message_text,
                                            )
                                        except Exception as e_notify_inviter:
                                            logging.error(
                                                f"Failed to send bonus notification to inviter {inviter_user_id}: {e_notify_inviter}"  # noqa: E501
                                            )
                                        await send_user_notification_email(
                                            settings=self.settings,
                                            i18n=self.i18n,
                                            user=inviter_user_model,
                                            subject_key="email_referral_bonus_subject",
                                            message_text=message_text,
                                            dashboard_url=(
                                                getattr(
                                                    self.settings,
                                                    "SUBSCRIPTION_MINI_APP_URL",
                                                    "",
                                                )
                                                or None
                                            ),
                                        )
                                    else:
                                        logging.warning(
                                            f"Failed to update panel for new bonus subscription for inviter {inviter_user_id}. Local bonus sub created (ID: {bonus_sub.subscription_id}) but may not be active on panel."  # noqa: E501
                                        )

                                except Exception as e_create_bonus_sub:
                                    logging.error(
                                        f"Failed to create new bonus subscription for inviter {inviter_user_id}: {e_create_bonus_sub}",  # noqa: E501
                                        exc_info=True,
                                    )

            if referee_bonus_days and referee_bonus_days > 0:
                new_end_date_referee = (
                    await self.subscription_service.extend_active_subscription_days(
                        session=session,
                        user_id=referee_user_id,
                        bonus_days=referee_bonus_days,
                        reason=f"referee bonus (invited by {inviter_name_for_referee_msg})",
                    )
                )
                if new_end_date_referee:
                    referee_final_end_date = new_end_date_referee
                    referee_bonus_applied_days = referee_bonus_days
                    logging.info(
                        f"Bonus of {referee_bonus_days} days successfully applied to referee {referee_user_id}."  # noqa: E501
                    )
                else:
                    logging.warning(
                        f"Failed to apply referee bonus for {referee_user_id} (could not extend their new subscription)."  # noqa: E501
                    )

            if referee_bonus_applied_days or inviter_bonus_successfully_applied:
                await events.emit(
                    events.REFERRAL_BONUS_GRANTED,
                    {
                        "referee_user_id": referee_user_id,
                        "referee_bonus_days": referee_bonus_applied_days,
                        "referee_new_end_date": events.iso(referee_final_end_date),
                        "inviter_bonus_applied": inviter_bonus_successfully_applied,
                        "payment_db_id": current_payment_db_id,
                    },
                )

            return {
                "referee_bonus_applied_days": referee_bonus_applied_days,
                "referee_new_end_date": referee_final_end_date,
                "inviter_bonus_applied_flag": inviter_bonus_successfully_applied,
            }
        except Exception as e:
            logging.error(
                f"Error in apply_referral_bonuses_for_payment for referee {referee_user_id}: {e}",
                exc_info=True,
            )

            raise

    def _referral_bonus_days_for_payment(
        self,
        purchased_subscription_months: int,
        *,
        tariff_key: Optional[str] = None,
    ) -> tuple[Optional[int], Optional[int]]:
        months = int(purchased_subscription_months)
        tariffs_config = getattr(self.settings, "tariffs_config", None)
        if tariff_key and tariffs_config:
            try:
                tariff = tariffs_config.require(str(tariff_key))
            except Exception:
                logging.warning(
                    "Referral bonuses skipped: tariff %s was not found.",
                    tariff_key,
                )
                return None, None
            if tariff.billing_model != "period":
                return None, None
            return (
                tariff.referral_inviter_bonus_days(months),
                tariff.referral_referee_bonus_days(months),
            )

        return (
            self.settings.referral_bonus_inviter.get(months),
            self.settings.referral_bonus_referee.get(months),
        )

    async def generate_referral_link(
        self, session: AsyncSession, bot_username: str, inviter_user_id: int
    ) -> Optional[str]:
        try:
            user = await user_dal.get_user_by_id(session, inviter_user_id)
            if not user:
                logging.warning(
                    "Unable to generate referral link: user %s not found.",
                    inviter_user_id,
                )
                return None

            referral_code = await user_dal.ensure_referral_code(session, user)
            if not referral_code:
                logging.warning(
                    "User %s has no referral code even after regeneration attempt.",
                    inviter_user_id,
                )
                return None

            return f"https://t.me/{bot_username}?start=ref_u{referral_code}"
        except Exception as exc:
            logging.error(
                "Failed to generate referral link for user %s: %s",
                inviter_user_id,
                exc,
                exc_info=True,
            )
            return None

    async def get_referral_stats(self, session: AsyncSession, user_id: int) -> dict:
        """Get referral statistics for a user"""

        try:
            # Count total invited users (referrals)
            invited_count_result = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE referred_by_id = :user_id"),
                {"user_id": user_id},
            )
            invited_count = invited_count_result.scalar() or 0

            # Count users who made successful payments (purchased subscription)
            purchased_count_result = await session.execute(
                text("""
                    SELECT COUNT(DISTINCT u.user_id) 
                    FROM users u 
                    JOIN payments p ON u.user_id = p.user_id 
                    WHERE u.referred_by_id = :user_id 
                    AND p.status = 'succeeded'
                """),
                {"user_id": user_id},
            )
            purchased_count = purchased_count_result.scalar() or 0

            return {"invited_count": invited_count, "purchased_count": purchased_count}
        except Exception as e:
            logging.error(f"Error getting referral stats for user {user_id}: {e}")
            return {"invited_count": 0, "purchased_count": 0}
