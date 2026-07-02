import logging
import secrets
import string
from dataclasses import dataclass
from datetime import datetime
from html import escape as html_escape

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra import events
from bot.infra.event_payloads import PromoCodeAppliedPayload
from bot.middlewares.i18n import JsonI18n
from bot.services.promo_effects import PromoEffects, summarize_effects, validate_effects
from config.settings import Settings
from db.dal import promo_code_dal, security_dal
from db.models import PromoCode

from .subscription_service import SubscriptionService


@dataclass(frozen=True)
class PromoCheckoutRequired:
    code: str
    effect_summary: str
    applies_to: str
    min_subscription_months: int | None = None
    min_traffic_gb: float | None = None


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

    @staticmethod
    def _normalize_code(value: str) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _generate_code() -> str:
        alphabet = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(10))

    @staticmethod
    async def issue_code(
        session: AsyncSession,
        *,
        effects: PromoEffects,
        code: str | None,
        max_activations: int,
        valid_until: datetime | None,
        origin: str,
        created_by_admin_id: int | None,
        max_duration_multiplier: float = 12.0,
        max_traffic_multiplier: float = 12.0,
    ) -> PromoCode:
        validate_effects(
            effects,
            max_duration_multiplier=max_duration_multiplier,
            max_traffic_multiplier=max_traffic_multiplier,
        )
        normalized_origin = str(origin or "admin").strip()[:32] or "admin"
        normalized_code = PromoCodeService._normalize_code(code or "")
        if normalized_code:
            existing = await promo_code_dal.get_promo_code_by_code(session, normalized_code)
            if existing is not None:
                raise ValueError("duplicate_code")
        else:
            for _ in range(32):
                candidate = PromoCodeService._generate_code()
                existing = await promo_code_dal.get_promo_code_by_code(session, candidate)
                if existing is None:
                    normalized_code = candidate
                    break
            if not normalized_code:
                raise ValueError("code_generation_failed")

        return await promo_code_dal.create_promo_code(
            session,
            {
                "code": normalized_code,
                "bonus_days": effects.bonus_days,
                "discount_percent": effects.discount_percent,
                "duration_multiplier": (
                    effects.duration_multiplier if effects.duration_multiplier != 1.0 else None
                ),
                "traffic_multiplier": (
                    effects.traffic_multiplier if effects.traffic_multiplier != 1.0 else None
                ),
                "bonus_requires_payment": bool(
                    effects.bonus_requires_payment and effects.bonus_days > 0
                ),
                "applies_to": effects.applies_to,
                "min_subscription_months": effects.min_subscription_months,
                "min_traffic_gb": effects.min_traffic_gb,
                "origin": normalized_origin,
                "max_activations": int(max_activations),
                "valid_until": valid_until,
                "created_by_admin_id": created_by_admin_id,
                "is_active": True,
            },
        )

    async def apply_promo_code(
        self,
        session: AsyncSession,
        user_id: int,
        code_input: str,
        user_lang: str,
    ) -> tuple[bool, datetime | str | PromoCheckoutRequired]:
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

        effects = PromoEffects.from_model(promo_data)
        if not effects.can_apply_standalone:
            await security_dal.clear_throttle_state(
                session,
                scope=security_dal.PROMO_CODE_APPLY_SCOPE,
                identifier=throttle_identifier,
            )
            return True, PromoCheckoutRequired(
                code=applied_code,
                effect_summary=summarize_effects(effects),
                applies_to=effects.applies_to,
                min_subscription_months=effects.min_subscription_months,
                min_traffic_gb=effects.min_traffic_gb,
            )

        bonus_days = promo_data.bonus_days
        default_tariff_key = None
        tariffs_config = getattr(self.settings, "tariffs_config", None)
        if tariffs_config:
            default_tariff_key = getattr(tariffs_config, "default_tariff", None)

        activation = await promo_code_dal.consume_promo_activation(
            session,
            promo_data.promo_code_id,
            user_id,
            payment_id=None,
            enforce_limit=True,
            effect_summary=summarize_effects(effects),
            bonus_days=effects.bonus_days,
            discount_percent=effects.discount_percent,
            duration_multiplier=(
                effects.duration_multiplier if effects.duration_multiplier != 1.0 else None
            ),
            traffic_multiplier=(
                effects.traffic_multiplier if effects.traffic_multiplier != 1.0 else None
            ),
            applies_to=effects.applies_to,
            granted_days=bonus_days,
        )
        if activation is None:
            logging.warning(
                "Failed to consume code %s for standalone activation by user %s",
                promo_data.code,
                user_id,
            )
            return False, _("error_applying_promo_bonus")

        new_end_date = await self.subscription_service.extend_active_subscription_days(
            session=session,
            user_id=user_id,
            bonus_days=bonus_days,
            reason=f"promo code {applied_code}",
            tariff_key=default_tariff_key,
        )

        if not new_end_date:
            await promo_code_dal.release_promo_activation(
                session,
                promo_data.promo_code_id,
                user_id,
                payment_id=None,
            )
            return False, _("error_applying_promo_bonus")

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
