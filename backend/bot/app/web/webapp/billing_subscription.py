import logging
from datetime import datetime, timezone

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_promo_code_service,
    get_session_factory,
    get_settings,
    get_subscription_service,
)
from bot.app.web.webapp.assets import _enforce_webapp_rate_limit
from bot.app.web.webapp.auth import _require_user_id, _trial_telegram_required_reason
from bot.app.web.webapp.common import (
    _invalidate_webapp_user_caches,
    _json_error,
    _normalize_language,
    _parse_model_payload,
)
from bot.app.web.webapp.payloads import (
    WebAppAutoRenewPayload,
    WebAppPromoApplyPayload,
)
from bot.services.promo_code_service import PromoCheckoutRequired, PromoCodeService
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.utils.config_link import prepare_config_links
from config.settings import Settings
from db.dal import message_log_dal, subscription_dal, user_dal

from .billing_common import (
    _TRIAL_ACTIVATION_FAILURE_STATUSES,
    _localized_webapp_message,
    _plain_text_message,
)
from .common import (
    _format_webapp_datetime,
)
from .response_helpers import json_response

logger = logging.getLogger(__name__)


async def apply_promo_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    promo_payload = await _parse_model_payload(request, WebAppPromoApplyPayload)
    code = str(promo_payload.code or "").strip()
    if not code:
        return _json_error(400, "empty_code", "Promo code is empty")

    settings: Settings = get_settings(request)
    promo_code_service: PromoCodeService = get_promo_code_service(request)
    if not promo_code_service:
        return _json_error(503, "service_unavailable", "Promo service unavailable")

    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        try:
            db_user = await user_dal.get_user_by_id(session, user_id)
            if not db_user or db_user.is_banned:
                await session.rollback()
                return _json_error(403, "access_denied", "Access denied")
            lang = _normalize_language(db_user.language_code or settings.DEFAULT_LANGUAGE)
            success, result = await promo_code_service.apply_promo_code(
                session,
                user_id,
                code,
                lang,
            )
            if not success:
                await session.commit()
                return _json_error(400, "promo_apply_failed", _plain_text_message(result))
            await session.commit()
            if isinstance(result, PromoCheckoutRequired):
                return json_response(
                    {
                        "ok": True,
                        "requires_checkout": True,
                        "code": result.code,
                        "effect_summary": result.effect_summary,
                        "applies_to": result.applies_to,
                        "min_subscription_months": result.min_subscription_months,
                        "min_traffic_gb": result.min_traffic_gb,
                    }
                )
            end_date = result if isinstance(result, datetime) else None
            return json_response(
                {
                    "ok": True,
                    "end_date": end_date.isoformat() if end_date else None,
                    "end_date_text": end_date.strftime("%d.%m.%Y %H:%M") if end_date else None,
                }
            )
        except Exception:
            await session.rollback()
            logger.exception("WebApp promo apply failed")
            return _json_error(500, "promo_apply_failed", "Promo apply failed")


async def subscription_auto_renew_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    auto_renew_payload = await _parse_model_payload(request, WebAppAutoRenewPayload)

    enabled = bool(auto_renew_payload.enabled)
    settings: Settings = get_settings(request)
    subscription_service: SubscriptionService = get_subscription_service(request)
    async_session_factory: sessionmaker = get_session_factory(request)

    async with async_session_factory() as session:
        try:
            db_user = await user_dal.get_user_by_id(session, user_id)
            if not db_user or db_user.is_banned:
                await session.rollback()
                return _json_error(403, "access_denied", "Access denied")
            sub = await subscription_dal.get_active_subscription_by_user_id(
                session,
                user_id,
                db_user.panel_user_uuid,
            )
            if not sub:
                await session.rollback()
                return _json_error(
                    400,
                    "subscription_required",
                    "Active subscription is required",
                )

            provider = str(getattr(sub, "provider", "") or "").strip().lower()
            from bot.payment_providers import provider_label_map, provider_supports_recurring
            from bot.payment_providers.shared import service_supports_recurring
            from db.dal import user_billing_dal

            if not provider_supports_recurring(provider):
                await session.rollback()
                return _json_error(
                    400,
                    "auto_renew_unavailable",
                    "Auto-renew is not available for this payment provider",
                )

            if enabled:
                recurring_service_for = getattr(subscription_service, "recurring_service_for", None)
                recurring_service = (
                    recurring_service_for(provider) if callable(recurring_service_for) else None
                )
                if not service_supports_recurring(recurring_service):
                    await session.rollback()
                    return _json_error(
                        400,
                        "auto_renew_unavailable",
                        "Auto-renew is not available for this payment provider",
                    )
                has_saved_method = await user_billing_dal.user_has_saved_payment_method(
                    session,
                    user_id,
                    provider=provider,
                )
                if not has_saved_method:
                    await session.rollback()
                    return _json_error(
                        400,
                        "auto_renew_requires_saved_method",
                        "A saved payment method is required",
                    )

            await subscription_dal.update_subscription(
                session,
                sub.subscription_id,
                {"auto_renew_enabled": enabled},
            )
            await session.commit()
            await _invalidate_webapp_user_caches(settings, user_id)

            lang = _normalize_language(db_user.language_code or settings.DEFAULT_LANGUAGE)
            provider_label = provider_label_map(settings, language=lang).get(provider, provider)
            return json_response(
                {
                    "ok": True,
                    "auto_renew_enabled": enabled,
                    "provider": provider,
                    "provider_label": provider_label,
                }
            )
        except Exception:
            await session.rollback()
            logger.exception("WebApp auto-renew update failed for user %s", user_id)
            return _json_error(500, "auto_renew_update_failed", "Auto-renew update failed")


async def activate_trial_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    rate_limit_response = await _enforce_webapp_rate_limit(
        request,
        user_id=user_id,
        action="trial_activate",
    )
    if rate_limit_response:
        return rate_limit_response

    settings: Settings = get_settings(request)
    if not settings.TRIAL_ENABLED or settings.TRIAL_DURATION_DAYS <= 0:
        return _json_error(400, "trial_unavailable", "Trial is not available")

    async_session_factory: sessionmaker = get_session_factory(request)
    subscription_service: SubscriptionService = get_subscription_service(request)
    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        lang = _normalize_language(
            getattr(db_user, "language_code", None) or settings.DEFAULT_LANGUAGE
        )
        telegram_required_reason = _trial_telegram_required_reason(settings, db_user)
        if telegram_required_reason:
            return _json_error(
                400,
                "trial_telegram_required",
                telegram_required_reason,
            )

        activation_result = await subscription_service.activate_trial_subscription(session, user_id)
        if not activation_result or not activation_result.get("activated"):
            await session.rollback()
            message_key = (
                activation_result.get("message_key", "trial_activation_failed")
                if activation_result
                else "trial_activation_failed"
            )
            status = _TRIAL_ACTIVATION_FAILURE_STATUSES.get(message_key, 400)
            message = _localized_webapp_message(request, lang, message_key)
            return _json_error(status, message_key, message)

        end_date = activation_result.get("end_date")
        config_link, connect_url = await prepare_config_links(
            settings,
            activation_result.get("subscription_url"),
        )

        try:
            await message_log_dal.create_message_log_no_commit(
                session,
                {
                    "user_id": user_id,
                    "telegram_username": getattr(db_user, "username", None),
                    "telegram_first_name": getattr(db_user, "first_name", None),
                    "event_type": "webapp_trial_activate",
                    "content": (
                        f"Trial activated via WebApp for user_id={user_id}; "
                        f"email={getattr(db_user, 'email', None) or 'N/A'}"
                    ),
                    "is_admin_event": False,
                    "target_user_id": user_id,
                    "timestamp": datetime.now(timezone.utc),
                },
            )
        except Exception:
            logger.exception("Failed to add WebApp trial activation audit log")

        await session.commit()

        try:
            from db.dal import ad_dal as _ad_dal

            await _ad_dal.mark_trial_activated(session, user_id)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Failed to mark WebApp trial activation for ad attribution")

        return json_response(
            {
                "ok": True,
                "activated": True,
                "days": activation_result.get("days", settings.TRIAL_DURATION_DAYS),
                "end_date": end_date.isoformat() if isinstance(end_date, datetime) else None,
                "end_date_text": _format_webapp_datetime(end_date)
                if isinstance(end_date, datetime)
                else None,
                "traffic_gb": activation_result.get("traffic_gb", settings.TRIAL_TRAFFIC_LIMIT_GB),
                "config_link": config_link,
                "connect_url": connect_url or config_link,
            }
        )
