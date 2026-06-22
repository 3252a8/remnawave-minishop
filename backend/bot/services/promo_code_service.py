import logging
from datetime import datetime
from html import escape as html_escape
from typing import Tuple

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra import events
from bot.infra.event_payloads import PromoCodeAppliedPayload
from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from db.dal import promo_code_dal, security_dal

from .subscription_service import SubscriptionService


class PromoCodeService:
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

    def _throttle_identifier(self, user_id: int) -> str:
        return f"user:{int(user_id)}"

    async def apply_promo_code(
        self,
        session: AsyncSession,
        user_id: int,
        code_input: str,
        user_lang: str,
    ) -> Tuple[bool, datetime | str]:
        _ = lambda k, **kw: self.i18n.gettext(user_lang, k, **kw)
        preserve_case = bool(
            getattr(self.settings, "MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED", False)
        )
        code_input_clean = (code_input or "").strip()[:100]
        lookup_code = code_input_clean if preserve_case else code_input_clean.upper()
        code_display = html_escape(lookup_code[:100], quote=False)
        throttle_identifier = self._throttle_identifier(user_id)

        throttle = await security_dal.check_throttle(
            session,
            scope=security_dal.PROMO_CODE_APPLY_SCOPE,
            identifier=throttle_identifier,
        )
        if throttle.locked:
            return False, _(
                "promo_code_too_many_attempts",
                seconds=throttle.retry_after or max(1, int(self.settings.BRUTE_FORCE_LOCK_SECONDS)),
            )

        promo_data = await promo_code_dal.get_active_promo_code_by_code_str(
            session, lookup_code, preserve_case=preserve_case
        )

        if not promo_data:
            throttle_result = await security_dal.record_throttle_failure(
                session,
                scope=security_dal.PROMO_CODE_APPLY_SCOPE,
                identifier=throttle_identifier,
                max_failures=self.settings.BRUTE_FORCE_MAX_FAILURES,
                window_seconds=self.settings.BRUTE_FORCE_WINDOW_SECONDS,
                lock_seconds=self.settings.BRUTE_FORCE_LOCK_SECONDS,
            )
            if throttle_result.locked:
                return False, _(
                    "promo_code_too_many_attempts",
                    seconds=throttle_result.retry_after
                    or max(1, int(self.settings.BRUTE_FORCE_LOCK_SECONDS)),
                )
            return False, _("promo_code_not_found", code=code_display)

        applied_code = str(promo_data.code or lookup_code)
        code_display = html_escape(applied_code[:100], quote=False)
        existing_activation = await promo_code_dal.get_user_activation_for_promo(
            session, promo_data.promo_code_id, user_id
        )
        if existing_activation:
            return False, _("promo_code_already_used_by_user", code=code_display)

        bonus_days = promo_data.bonus_days
        default_tariff_key = None
        tariffs_config = getattr(self.settings, "tariffs_config", None)
        if tariffs_config:
            default_tariff_key = getattr(tariffs_config, "default_tariff", None)

        new_end_date = await self.subscription_service.extend_active_subscription_days(
            session=session,
            user_id=user_id,
            bonus_days=bonus_days,
            reason=f"promo code {applied_code}",
            tariff_key=default_tariff_key,
        )

        if new_end_date:
            activation_recorded = await promo_code_dal.record_promo_activation(
                session, promo_data.promo_code_id, user_id, payment_id=None
            )
            promo_incremented = await promo_code_dal.increment_promo_code_usage(
                session, promo_data.promo_code_id
            )

            if activation_recorded and promo_incremented:
                await security_dal.clear_throttle_state(
                    session,
                    scope=security_dal.PROMO_CODE_APPLY_SCOPE,
                    identifier=throttle_identifier,
                )
                await events.emit_model(
                    PromoCodeAppliedPayload(
                        user_id=user_id,
                        code=applied_code,
                        bonus_days=bonus_days,
                        new_end_date=new_end_date,
                    )
                )

                return True, new_end_date
            else:
                logging.error(
                    f"Failed to record activation or increment usage for promo {promo_data.code} by user {user_id}"  # noqa: E501
                )
                return False, _("error_applying_promo_bonus")
        else:
            return False, _("error_applying_promo_bonus")
