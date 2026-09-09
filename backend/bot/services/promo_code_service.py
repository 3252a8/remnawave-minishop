import logging
import secrets
import string
from collections.abc import Callable
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
from db.dal import promo_code_dal, security_dal, subscription_dal
from db.models import PromoCode

from .subscription_service import SubscriptionService

logger = logging.getLogger(__name__)

PROMO_STATUS_NOT_FOUND = "not_found"
PROMO_STATUS_ALREADY_USED = "already_used"
PROMO_STATUS_REQUIRES_CHECKOUT = "requires_checkout"
PROMO_STATUS_STANDALONE = "standalone"
PROMO_STATUS_THROTTLED = "throttled"


@dataclass(frozen=True)
class PromoCheckoutRequired:
    code: str
    effect_summary: str
    applies_to: str
    bonus_days: int = 0
    regular_traffic_gb: float = 0
    premium_traffic_gb: float = 0
    discount_percent: float | None = None
    duration_multiplier: float | None = None
    traffic_multiplier: float | None = None
    min_subscription_months: int | None = None
    min_subscription_days: int | None = None
    min_traffic_gb: float | None = None


@dataclass(frozen=True)
class PromoCodeStatus:
    """Read-only verdict on how a promo code relates to a specific user.

    ``message`` carries the localized human explanation for terminal states
    (already used / not found / throttled) so both the bot and the web app can
    show it verbatim.
    """

    status: str
    code: str = ""
    message: str = ""
    effect_summary: str = ""
    applies_to: str = "all"
    min_subscription_months: int | None = None
    min_subscription_days: int | None = None
    min_traffic_gb: float | None = None
    bonus_days: int = 0
    regular_traffic_gb: float = 0
    premium_traffic_gb: float = 0
    discount_percent: float | None = None
    duration_multiplier: float | None = None
    traffic_multiplier: float | None = None
    activated_at: datetime | None = None
    subscription_end_date: datetime | None = None


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
        user_id: int | None = None,
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
            if existing is not None and getattr(existing, "archived_at", None) is not None:
                await promo_code_dal.release_archived_promo_code(session, existing)
                existing = await promo_code_dal.get_promo_code_by_code(session, normalized_code)
            if existing is not None:
                raise ValueError("duplicate_code")
        else:
            for _ in range(32):
                candidate = PromoCodeService._generate_code()
                existing = await promo_code_dal.get_promo_code_by_code(session, candidate)
                if existing is not None and getattr(existing, "archived_at", None) is not None:
                    await promo_code_dal.release_archived_promo_code(session, existing)
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
                "regular_traffic_gb": effects.regular_traffic_gb or None,
                "premium_traffic_gb": effects.premium_traffic_gb or None,
                "discount_percent": effects.discount_percent,
                "duration_multiplier": (
                    effects.duration_multiplier if effects.duration_multiplier != 1.0 else None
                ),
                "traffic_multiplier": (
                    effects.traffic_multiplier if effects.traffic_multiplier != 1.0 else None
                ),
                "bonus_requires_payment": bool(
                    effects.bonus_requires_payment and effects.has_fixed_grant
                ),
                "applies_to": effects.applies_to,
                "min_subscription_months": effects.min_subscription_months,
                "min_subscription_days": effects.min_subscription_days,
                "min_traffic_gb": effects.min_traffic_gb,
                "origin": normalized_origin,
                "max_activations": int(max_activations),
                "valid_until": valid_until,
                "created_by_admin_id": created_by_admin_id,
                # Naming a customer is what makes the code personal.
                "user_id": int(user_id) if user_id else None,
                "is_active": True,
            },
        )

    async def _already_used_message(
        self,
        session: AsyncSession,
        user_id: int,
        code_display: str,
        activated_at: datetime | None,
        translate: Callable[..., str],
    ) -> tuple[str, datetime | None]:
        """Build the localized "you already used this code" explanation.

        Includes the activation date when known and the active subscription end
        date when the user still has one, so the user understands why the code
        no longer applies and what they currently have.
        """
        if activated_at is not None:
            message = translate(
                "promo_code_already_used_details",
                code=code_display,
                date=activated_at.strftime("%d.%m.%Y"),
            )
        else:
            message = translate("promo_code_already_used_by_user", code=code_display)

        subscription_end: datetime | None = None
        try:
            active = await subscription_dal.get_active_subscription_by_user_id(session, user_id)
            subscription_end = getattr(active, "end_date", None) if active else None
        except Exception:
            logger.debug("Active subscription lookup failed for user %s.", user_id, exc_info=True)
        if subscription_end is not None:
            message = (
                f"{message} "
                + translate(
                    "promo_code_already_used_subscription_until",
                    end_date=subscription_end.strftime("%d.%m.%Y"),
                )
            ).strip()
        return message, subscription_end

    async def get_promo_code_status(
        self,
        session: AsyncSession,
        user_id: int,
        code_input: str,
        user_lang: str,
    ) -> PromoCodeStatus:
        """Read-only classification of a code for a user (deeplink pre-check).

        Mirrors ``apply_promo_code`` validation without consuming anything.
        Unknown codes still count towards the apply throttle so this endpoint
        cannot be used to enumerate codes faster than apply itself.
        """
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
            return PromoCodeStatus(
                status=PROMO_STATUS_THROTTLED,
                code=lookup_code,
                message=_(
                    "promo_code_too_many_attempts",
                    seconds=throttle.retry_after
                    or max(1, int(self.settings.BRUTE_FORCE_LOCK_SECONDS)),
                ),
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
                return PromoCodeStatus(
                    status=PROMO_STATUS_THROTTLED,
                    code=lookup_code,
                    message=_(
                        "promo_code_too_many_attempts",
                        seconds=throttle_result.retry_after
                        or max(1, int(self.settings.BRUTE_FORCE_LOCK_SECONDS)),
                    ),
                )
            return PromoCodeStatus(
                status=PROMO_STATUS_NOT_FOUND,
                code=lookup_code,
                message=_("promo_code_not_found", code=code_display),
            )

        applied_code = str(promo_data.code or lookup_code)
        code_display = html_escape(applied_code[:100], quote=False)
        existing_activation = await promo_code_dal.get_user_activation_for_promo(
            session, promo_data.promo_code_id, user_id
        )
        if existing_activation:
            activated_at = getattr(existing_activation, "activated_at", None)
            message, subscription_end = await self._already_used_message(
                session, user_id, code_display, activated_at, _
            )
            return PromoCodeStatus(
                status=PROMO_STATUS_ALREADY_USED,
                code=applied_code,
                message=message,
                activated_at=activated_at,
                subscription_end_date=subscription_end,
            )

        effects = PromoEffects.from_model(promo_data)
        summary = summarize_effects(effects)
        if not effects.can_apply_standalone:
            return PromoCodeStatus(
                status=PROMO_STATUS_REQUIRES_CHECKOUT,
                code=applied_code,
                effect_summary=summary,
                applies_to=effects.applies_to,
                bonus_days=effects.bonus_days,
                regular_traffic_gb=effects.regular_traffic_gb,
                premium_traffic_gb=effects.premium_traffic_gb,
                discount_percent=effects.discount_percent,
                duration_multiplier=(
                    effects.duration_multiplier if effects.duration_multiplier != 1.0 else None
                ),
                traffic_multiplier=(
                    effects.traffic_multiplier if effects.traffic_multiplier != 1.0 else None
                ),
                min_subscription_months=effects.min_subscription_months,
                min_subscription_days=effects.min_subscription_days,
                min_traffic_gb=effects.min_traffic_gb,
            )
        return PromoCodeStatus(
            status=PROMO_STATUS_STANDALONE,
            code=applied_code,
            effect_summary=summary,
            applies_to=effects.applies_to,
            bonus_days=int(effects.bonus_days or 0),
            regular_traffic_gb=effects.regular_traffic_gb,
            premium_traffic_gb=effects.premium_traffic_gb,
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
            message, _end = await self._already_used_message(
                session,
                user_id,
                code_display,
                getattr(existing_activation, "activated_at", None),
                _,
            )
            return False, message

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
                bonus_days=effects.bonus_days,
                regular_traffic_gb=effects.regular_traffic_gb,
                premium_traffic_gb=effects.premium_traffic_gb,
                discount_percent=effects.discount_percent,
                duration_multiplier=(
                    effects.duration_multiplier if effects.duration_multiplier != 1.0 else None
                ),
                traffic_multiplier=(
                    effects.traffic_multiplier if effects.traffic_multiplier != 1.0 else None
                ),
                min_subscription_months=effects.min_subscription_months,
                min_subscription_days=effects.min_subscription_days,
                min_traffic_gb=effects.min_traffic_gb,
            )

        bonus_days = effects.bonus_days
        default_tariff_key = None
        tariffs_config = getattr(self.settings, "tariffs_config", None)
        if tariffs_config:
            default_tariff_key = getattr(tariffs_config, "default_tariff", None)

        if effects.has_traffic_grant:
            active_sub = await subscription_dal.get_active_subscription_by_user_id(session, user_id)
            if not active_sub:
                return False, _("promo_code_active_subscription_required")
            if effects.premium_traffic_gb > 0:
                try:
                    active_tariff = (
                        tariffs_config.require_configured(active_sub.tariff_key)
                        if tariffs_config and active_sub.tariff_key
                        else None
                    )
                except (KeyError, ValueError):
                    active_tariff = None
                if active_tariff is None or not active_tariff.premium_squad_uuids:
                    return False, _("promo_code_premium_traffic_unavailable")

        activation = await promo_code_dal.consume_promo_activation(
            session,
            promo_data.promo_code_id,
            user_id,
            payment_id=None,
            enforce_limit=True,
            effect_summary=summarize_effects(effects),
            bonus_days=effects.bonus_days,
            regular_traffic_gb=effects.regular_traffic_gb or None,
            premium_traffic_gb=effects.premium_traffic_gb or None,
            discount_percent=effects.discount_percent,
            duration_multiplier=(
                effects.duration_multiplier if effects.duration_multiplier != 1.0 else None
            ),
            traffic_multiplier=(
                effects.traffic_multiplier if effects.traffic_multiplier != 1.0 else None
            ),
            applies_to=effects.applies_to,
            granted_days=bonus_days,
            granted_regular_traffic_gb=effects.regular_traffic_gb or None,
            granted_premium_traffic_gb=effects.premium_traffic_gb or None,
        )
        if activation is None:
            logger.warning(
                "Failed to consume code %s for standalone activation by user %s",
                promo_data.code,
                user_id,
            )
            return False, _("error_applying_promo_bonus")

        if effects.has_traffic_grant:
            grant_result = await self.subscription_service.grant_promo_entitlements(
                session=session,
                user_id=user_id,
                bonus_days=bonus_days,
                regular_traffic_gb=effects.regular_traffic_gb,
                premium_traffic_gb=effects.premium_traffic_gb,
            )
            new_end_date = grant_result.get("end_date") if grant_result else None
        else:
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
                regular_traffic_gb=effects.regular_traffic_gb,
                premium_traffic_gb=effects.premium_traffic_gb,
                new_end_date=new_end_date,
            )
        )

        return True, new_end_date
