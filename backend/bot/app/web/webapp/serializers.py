import json
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_bot_username,
    get_optional_subscription_service,
    get_referral_service,
    get_session_factory,
    get_settings,
    get_subscription_service,
)
from bot.app.web.webapp.auth import (
    _trial_telegram_required_reason,
    _user_has_linked_telegram,
)
from bot.infra.performance import performance_phase
from bot.infra.promo_policies import (
    PromoCheckoutSuggestionContext,
    resolve_promo_checkout_suggestion,
)
from bot.services.device_topup_availability import resolve_device_topup_availability
from bot.services.partner_program_service import PartnerProgramService
from bot.services.referral_service import ReferralService
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.services.telegram_notifications import (
    TELEGRAM_NOTIFICATIONS_ENABLED,
    normalize_telegram_notification_status,
    telegram_notifications_need_prompt,
    telegram_notifications_start_link,
)
from bot.services.user_balance_service import UserBalanceService
from bot.services.user_notification_preferences import UserNotificationPreferences
from bot.utils.locale_defaults import subscription_purchase_description_text
from bot.utils.traffic_reset import format_traffic_reset_date, parse_panel_datetime
from config.menu_buttons import public_menu_buttons
from config.settings import Settings
from config.subscription_guides_config import subscription_guides_available
from config.tariffs_config import default_currency_key_for_settings, payment_currency_code
from config.webapp_themes_config import public_themes_catalog_payload
from db.dal import payment_dal, subscription_dal, support_dal, user_dal
from db.models import UserEmailAddress, UserExternalIdentity, UserPasskeyCredential

from .assets import (
    _get_cached_webapp_settings,
)
from .billing_status import refresh_payment_status_for_request
from .billing_tariff_access import request_tariff_access_code
from .common import (
    _coerce_int_or_none,
    _ensure_cached_telegram_avatar,
    _format_bytes,
    _format_remaining,
    _normalize_language,
    _telegram_avatar_url,
)
from .email_address_serializers import serialize_user_email_addresses
from .external_identity_state import external_identity_can_unlink_for_account
from .period_contracts import periods_for_client
from .referral_links import visible_referral_links
from .referral_serializers import (
    _build_webapp_referral_link,
    _serialize_referral_bonus_details,
)
from .referral_welcome_state import resolve_referral_welcome_state
from .serializers_auto_renew import resolve_auto_renew_capabilities
from .serializers_billing_options import (
    _serialize_hwid_device_packages,
    _serialize_payment_methods,
    _serialize_tariff_change_target,
    _serialize_topup_packages,
    _serialize_trial_payment_plan,
    _traffic_percent,
)
from .serializers_checkout import attach_checkout_pricing_context_to_plans
from .serializers_payments import _serialize_pending_promo_payment
from .serializers_plans import _serialize_plans
from .serializers_subscription import serialize_inactive_subscription

logger = logging.getLogger(__name__)
_MAX_PENDING_PROMO_REFRESHES = 10

__all__ = [
    "_build_user_payload",
    "_serialize_hwid_device_packages",
    "_serialize_payment_methods",
    "_serialize_pending_promo_payment",
    "_serialize_tariff_change_target",
    "_serialize_topup_packages",
    "_traffic_percent",
]


async def _suggested_checkout_promo(
    session: AsyncSession,
    *,
    user_id: int,
    pending_payment: dict[str, Any] | None,
) -> str | None:
    if pending_payment is not None:
        return None
    return await resolve_promo_checkout_suggestion(
        PromoCheckoutSuggestionContext(session=session, user_id=user_id)
    )


async def _refresh_pending_promo_payment(
    request: web.Request,
    session: AsyncSession,
    *,
    user_id: int,
) -> dict[str, Any] | None:
    """Reconcile stale resumable checkouts before exposing one to the user."""

    seen_payment_ids: set[int] = set()
    for _ in range(_MAX_PENDING_PROMO_REFRESHES):
        payment = await payment_dal.get_latest_resumable_promo_payment(
            session,
            user_id=user_id,
        )
        if payment is None:
            return None

        payment_id = int(payment.payment_id)
        if payment_id in seen_payment_ids:
            return _serialize_pending_promo_payment(payment)
        seen_payment_ids.add(payment_id)

        await refresh_payment_status_for_request(request, session, payment)
        current = await payment_dal.get_latest_resumable_promo_payment(
            session,
            user_id=user_id,
        )
        if current is None:
            return None
        if int(current.payment_id) == payment_id:
            return _serialize_pending_promo_payment(current)

    logger.warning(
        "Pending promo reconciliation reached the per-request limit for user %s",
        user_id,
    )
    payment = await payment_dal.get_latest_resumable_promo_payment(
        session,
        user_id=user_id,
    )
    return _serialize_pending_promo_payment(payment)


async def _build_user_payload(request: web.Request, user_id: int) -> dict[str, Any]:
    settings: Settings = get_settings(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    subscription_service: SubscriptionService = get_subscription_service(request)
    cached = _get_cached_webapp_settings(request)
    referral_settings = settings.referral_settings
    support_settings = settings.support_settings
    refresh_external = str(request.query.get("fresh", "")).lower() in {"1", "true", "yes", "on"}

    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            raise web.HTTPForbidden(
                text=json.dumps({"ok": False, "error": "access_denied"}),
                content_type="application/json",
            )

        with performance_phase("pending_payment"):
            if refresh_external:
                pending_promo_payment = await _refresh_pending_promo_payment(
                    request,
                    session,
                    user_id=user_id,
                )
            else:
                pending_promo_payment = _serialize_pending_promo_payment(
                    await payment_dal.get_latest_resumable_promo_payment(session, user_id=user_id)
                )
        # Provider reconciliation may roll back or commit this session while
        # making an external request. Reload the authenticated user before
        # continuing with referral or subscription writes.
        if refresh_external:
            db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            raise web.HTTPForbidden(
                text=json.dumps({"ok": False, "error": "access_denied"}),
                content_type="application/json",
            )

        with performance_phase("subscription"):
            active = await subscription_service.get_active_subscription_details(
                session, user_id, prefer_local=not refresh_external
            )
        partner_program = PartnerProgramService(settings)
        await partner_program.auto_enroll_user(session, user=db_user)
        referral_program_enabled = await partner_program.referral_program_enabled_for_user(
            session,
            user_id=user_id,
        )
        partner_client_welcome_eligible = await partner_program.client_welcome_bonus_eligible(
            session,
            user_id=user_id,
        )
        referral_code = await user_dal.ensure_referral_code(session, db_user)
        referral_service: ReferralService | None = get_referral_service(request)
        bot_username = get_bot_username(request)
        referral_link = None
        if referral_service and bot_username:
            referral_link = await referral_service.generate_referral_link(
                session,
                bot_username,
                user_id,
            )
        webapp_referral_link = _build_webapp_referral_link(
            get_settings(request).SUBSCRIPTION_MINI_APP_URL,
            referral_code,
        )
        referral_link, webapp_referral_link = visible_referral_links(
            referral_settings,
            bot_link=referral_link,
            webapp_link=webapp_referral_link,
        )
        referral_stats = (
            await referral_service.get_referral_stats(session, user_id)
            if referral_service
            else {"invited_count": 0, "purchased_count": 0}
        )
        support_unread_count = (
            await support_dal.count_user_unread(session, user_id)
            if support_settings.tickets_enabled
            else 0
        )
        balance_payload = await UserBalanceService(settings).snapshot(session, user_id=user_id)
        local_sub = (
            await subscription_dal.get_active_subscription_by_user_id(
                session,
                user_id,
                db_user.panel_user_uuid,
            )
            if db_user.panel_user_uuid
            else None
        )
        if not active and db_user.panel_user_uuid:
            local_sub = await subscription_dal.get_latest_subscription_by_user_id(
                session,
                user_id,
                db_user.panel_user_uuid,
            )
        suggested_promo_code = await _suggested_checkout_promo(
            session,
            user_id=user_id,
            pending_payment=pending_promo_payment,
        )
        install_share_token = (
            await subscription_dal.ensure_install_share_token(session, local_sub)
            if active and local_sub
            else None
        )
        trial_base_available = bool(
            settings.TRIAL_ENABLED
            and settings.TRIAL_DURATION_DAYS > 0
            and not await subscription_service.has_trial_blocking_subscription(session, user_id)
        )
        trial_telegram_required_reason = (
            _trial_telegram_required_reason(settings, db_user) if trial_base_available else None
        )
        trial_available = bool(trial_base_available and not trial_telegram_required_reason)
        lang = _normalize_language(db_user.language_code or settings.DEFAULT_LANGUAGE)
        plans_payload = _serialize_plans(
            settings,
            lang,
            subscription_options=cached["subscription_options"],
            stars_subscription_options=cached["stars_subscription_options"],
            traffic_packages=cached["traffic_packages"],
            stars_traffic_packages=cached["stars_traffic_packages"],
            assigned_tariff_key=local_sub.tariff_key if local_sub else None,
            tariff_access_code=request_tariff_access_code(request),
        )
        await _attach_hwid_renewal_quotes_to_plans(
            session,
            subscription_service,
            user_id=user_id,
            settings=settings,
            active=active,
            local_sub=local_sub,
            plans=plans_payload,
        )
        await attach_checkout_pricing_context_to_plans(
            session,
            settings,
            local_sub=local_sub,
            plans=plans_payload,
        )
        with performance_phase("avatar"):
            avatar = await _ensure_cached_telegram_avatar(
                request, session, db_user, allow_fetch=refresh_external
            )
        external_identities = (
            (
                await session.execute(
                    select(UserExternalIdentity)
                    .where(UserExternalIdentity.user_id == user_id)
                    .order_by(UserExternalIdentity.provider)
                )
            )
            .scalars()
            .all()
        )
        email_addresses = (
            (
                await session.execute(
                    select(UserEmailAddress)
                    .where(UserEmailAddress.user_id == user_id)
                    .order_by(
                        UserEmailAddress.is_primary.desc(),
                        UserEmailAddress.is_notification.desc(),
                        UserEmailAddress.created_at.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        passkey_credentials = (
            (
                await session.execute(
                    select(UserPasskeyCredential)
                    .where(UserPasskeyCredential.user_id == user_id)
                    .order_by(UserPasskeyCredential.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        try:
            await session.commit()
        except Exception:
            await session.rollback()

    admin_ids = {int(x) for x in (settings.ADMIN_IDS or [])}
    is_admin = bool(db_user.telegram_id and int(db_user.telegram_id) in admin_ids)
    telegram_linked = _user_has_linked_telegram(db_user)
    referral_welcome_days, referral_welcome_telegram_required_reason = (
        resolve_referral_welcome_state(
            settings,
            db_user,
            ordinary_referral_enabled_for_user=referral_program_enabled,
            partner_client_eligible=partner_client_welcome_eligible,
            has_active_subscription=bool(active),
        )
    )
    telegram_notifications_status = normalize_telegram_notification_status(
        getattr(db_user, "telegram_notifications_status", None)
    )
    telegram_notifications_link = telegram_notifications_start_link(get_bot_username(request))
    serialized_email_addresses, notification_email = serialize_user_email_addresses(
        db_user,
        email_addresses,
        external_identities,
    )
    return {
        "user": {
            "id": user_id,
            "username": db_user.username,
            "email": db_user.email,
            "email_verified": bool(db_user.email_verified_at),
            "notification_email": notification_email or None,
            "notification_preferences": UserNotificationPreferences.from_user(db_user).as_dict(),
            "email_addresses": serialized_email_addresses,
            "password_auth_enabled": bool(
                db_user.email and db_user.email_verified_at and db_user.password_hash
            ),
            "telegram_id": db_user.telegram_id,
            "telegram_linked": telegram_linked,
            "telegram_notifications_status": telegram_notifications_status,
            "telegram_notifications_enabled": (
                telegram_notifications_status == TELEGRAM_NOTIFICATIONS_ENABLED
            ),
            "telegram_notifications_need_prompt": telegram_notifications_need_prompt(db_user),
            "telegram_notifications_start_link": telegram_notifications_link,
            "telegram_photo_url": (
                _telegram_avatar_url(avatar)
                or ("/api/account/avatar" if db_user.telegram_id else "")
            ),
            "first_name": db_user.first_name,
            "language_code": lang,
            "is_admin": is_admin,
            "external_identities": [
                {
                    "provider": str(identity.provider),
                    "email": identity.email,
                    "email_verified": bool(identity.email_verified),
                    "display_name": identity.display_name,
                    "can_unlink": external_identity_can_unlink_for_account(
                        identity,
                        email_addresses,
                        external_identities,
                        passkey_credentials,
                        user=db_user,
                        settings=settings,
                    ),
                }
                for identity in external_identities
            ],
            "passkeys": [
                {
                    "credential_id": str(credential.credential_id),
                    "name": str(credential.name or "Passkey"),
                    "created_at": credential.created_at.isoformat()
                    if credential.created_at
                    else None,
                    "last_used_at": credential.last_used_at.isoformat()
                    if credential.last_used_at
                    else None,
                    "backed_up": bool(credential.backed_up),
                    "device_type": credential.device_type,
                    "transports": [
                        value.strip()
                        for value in str(credential.transports or "").split(",")
                        if value.strip()
                    ],
                }
                for credential in passkey_credentials
            ],
        },
        "subscription": _serialize_subscription(
            request,
            settings,
            active,
            local_sub,
            lang,
            install_share_token=install_share_token,
        ),
        "referral": {
            "code": referral_code,
            "bot_link": referral_link,
            "webapp_link": webapp_referral_link,
            "invited_count": referral_stats.get("invited_count", 0),
            "purchased_count": referral_stats.get("purchased_count", 0),
            "welcome_bonus_days": referral_welcome_days,
            "welcome_bonus_without_telegram_enabled": bool(
                referral_settings.welcome_bonus_without_telegram_enabled
            ),
            "welcome_bonus_requires_telegram": bool(
                referral_welcome_telegram_required_reason and not telegram_linked
            ),
            "welcome_bonus_block_reason": referral_welcome_telegram_required_reason,
            "one_bonus_per_referee": bool(referral_settings.one_bonus_per_referee),
            "bonus_details": _serialize_referral_bonus_details(settings, lang),
        },
        "plans": periods_for_client(request, plans_payload),
        "billing_period_unit": "day",
        "billing_period_schema_version": 2,
        "pending_payment": pending_promo_payment,
        "suggested_promo_code": suggested_promo_code,
        "payment_methods": _serialize_payment_methods(
            settings,
            request.app,
            lang,
            is_admin=is_admin,
        ),
        "themes_catalog": public_themes_catalog_payload(
            settings.webapp_themes_catalog,
            settings.WEBAPP_PRIMARY_COLOR or "#00fe7a",
            enabled_only=True,
        ),
        "support_unread_count": int(support_unread_count or 0),
        "balance": {"ok": True, **balance_payload},
        "settings": {
            "support_url": support_settings.link,
            "server_status_url": settings.server_status_external_url,
            "support_tickets_enabled": bool(support_settings.tickets_enabled),
            "support_ticket_max_body_length": int(support_settings.ticket_max_body_length or 4000),
            "support_ticket_max_subject_length": int(
                support_settings.ticket_max_subject_length or 160
            ),
            "traffic_mode": bool(settings.traffic_sale_mode),
            "my_devices_enabled": bool(settings.MY_DEVICES_SECTION_ENABLED),
            "payment_methods_display_mode": settings.PAYMENT_METHODS_DISPLAY_MODE,
            "partner_program_enabled": bool(settings.partner_settings.enabled),
            "user_balance_enabled": bool(settings.balance_settings.enabled),
            "referral_program_enabled": referral_program_enabled,
            "gifts_enabled": bool(settings.GIFTS_ENABLED),
            "subscription_reissue_enabled": bool(settings.SUBSCRIPTION_REISSUE_ENABLED),
            "user_hwid_device_limit": (
                int(settings.USER_HWID_DEVICE_LIMIT)
                if settings.USER_HWID_DEVICE_LIMIT is not None
                else None
            ),
            "trial_enabled": bool(settings.TRIAL_ENABLED),
            "trial_available": trial_available,
            "trial_payment_enabled": bool(settings.TRIAL_PAYMENT_ENABLED),
            "trial_payment_plan": _serialize_trial_payment_plan(settings),
            "trial_without_telegram_enabled": bool(settings.TRIAL_WITHOUT_TELEGRAM_ENABLED),
            "trial_requires_telegram": bool(trial_telegram_required_reason and not telegram_linked),
            "trial_block_reason": trial_telegram_required_reason,
            "trial_duration_days": int(settings.TRIAL_DURATION_DAYS or 0),
            "trial_traffic_limit_gb": float(settings.TRIAL_TRAFFIC_LIMIT_GB or 0),
            "trial_traffic_strategy": settings.TRIAL_TRAFFIC_STRATEGY,
            "subscription_purchase_description": subscription_purchase_description_text(
                settings, lang
            ),
            "subscription_guides_enabled": subscription_guides_available(settings),
            "email_auth_enabled": settings.email_auth_configured,
            "notification_preferences_enabled": bool(
                settings.USER_NOTIFICATION_PREFERENCES_ENABLED
            ),
            "email_address_change_enabled": bool(settings.EMAIL_ADDRESS_CHANGE_ENABLED),
            "auth_providers": settings.webapp_auth_providers,
            "recommended_auth_providers": settings.webapp_recommended_auth_providers,
            "menu_buttons": public_menu_buttons(
                settings.MENU_BUTTONS_JSON,
                lang,
                default_language=settings.DEFAULT_LANGUAGE,
            ),
        },
    }


def _serialize_subscription(
    request_or_settings: Any,
    settings_or_active: Any,
    active_or_local_sub: Any | None = None,
    local_sub_or_lang: Any | None = None,
    lang: str | None = None,
    *,
    install_share_token: str | None = None,
) -> dict[str, Any]:
    if lang is None:
        request = None
        settings = request_or_settings
        active = settings_or_active
        local_sub = active_or_local_sub
        lang = str(local_sub_or_lang or "ru")
    else:
        request = request_or_settings
        settings = settings_or_active
        active = active_or_local_sub
        local_sub = local_sub_or_lang

    if not active:
        return serialize_inactive_subscription(
            local_sub,
            remaining_text=_format_remaining(0, lang),
        )

    end_date = active.get("end_date")
    if end_date and end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=UTC)

    seconds_left = 0
    if end_date:
        seconds_left = max(
            0,
            int((end_date - datetime.now(UTC)).total_seconds()),
        )

    provider = str(getattr(local_sub, "provider", "") or "").strip().lower()
    local_status = (
        str(getattr(local_sub, "status_from_panel", "") or active.get("status_from_panel") or "")
        .strip()
        .upper()
    )
    is_trial = provider == "trial" or local_status == "TRIAL"
    can_topup_regular_traffic = False
    can_topup_premium_traffic = False
    can_topup_traffic = False
    topup_always_available = False
    premium_topup_always_available = False
    device_topup_availability = resolve_device_topup_availability(
        settings,
        subscription_active=True,
        tariff_key=active.get("tariff_key"),
        max_devices=active.get("max_devices"),
        subscription_is_trial=is_trial,
    )
    can_topup_devices = device_topup_availability.allowed
    if settings.tariffs_config and active.get("tariff_key"):
        try:
            tariff = settings.tariffs_config.require_configured(str(active.get("tariff_key")))
            packages = settings.tariffs_config.topup_packages_for(tariff)
            can_topup_regular_traffic = bool(packages and packages.has_any())
            can_topup_premium_traffic = bool(
                tariff.premium_squad_uuids
                and tariff.premium_topup_packages
                and tariff.premium_topup_packages.has_any()
            )
            can_topup_traffic = bool(can_topup_regular_traffic or can_topup_premium_traffic)
            topup_always_available = bool(tariff.topup_always_available)
            premium_topup_always_available = bool(tariff.premium_topup_always_available)
        except Exception:
            can_topup_regular_traffic = False
            can_topup_premium_traffic = False
            can_topup_traffic = False
            topup_always_available = False
            premium_topup_always_available = False

    panel_short_uuid = str(active.get("panel_short_uuid") or "").strip()
    share_token = str(
        install_share_token or getattr(local_sub, "install_share_token", "") or ""
    ).strip()
    extra_hwid_valid_until = active.get("extra_hwid_devices_valid_until")
    if extra_hwid_valid_until and extra_hwid_valid_until.tzinfo is None:
        extra_hwid_valid_until = extra_hwid_valid_until.replace(tzinfo=UTC)
    extra_hwid_next_valid_from = active.get("extra_hwid_devices_next_valid_from")
    if extra_hwid_next_valid_from and extra_hwid_next_valid_from.tzinfo is None:
        extra_hwid_next_valid_from = extra_hwid_next_valid_from.replace(tzinfo=UTC)
    extra_hwid_count = _coerce_int_or_none(active.get("extra_hwid_devices")) or 0
    device_topup_renewal_available = bool(
        extra_hwid_count > 0
        and extra_hwid_valid_until
        and end_date
        and extra_hwid_valid_until < end_date
    )
    auto_renew_enabled = bool(getattr(local_sub, "auto_renew_enabled", False))
    auto_renew = resolve_auto_renew_capabilities(
        provider,
        settings=settings,
        language=lang,
        subscription_service=(
            get_optional_subscription_service(request) if request is not None else None
        ),
    )
    return {
        "active": seconds_left > 0,
        "status": active.get("status_from_panel") or "UNKNOWN",
        "end_date": end_date.isoformat() if end_date else None,
        "end_date_text": end_date.strftime("%d.%m.%Y %H:%M") if end_date else "N/A",
        "duration_days": getattr(local_sub, "duration_days", None),
        "period_semantics": getattr(local_sub, "period_semantics", None),
        "days_left": seconds_left // 86400,
        "remaining_text": _format_remaining(seconds_left, lang),
        "config_link": active.get("config_link"),
        "connect_url": active.get("connect_button_url") or active.get("config_link"),
        "panel_short_uuid": panel_short_uuid or None,
        "install_share_token": subscription_dal.normalize_install_share_token(share_token) or None,
        "install_share_url": _build_install_share_link(request, settings, share_token),
        "traffic_limit": _format_bytes(active.get("traffic_limit_bytes"), zero_as_unlimited=True),
        "traffic_used": _format_bytes(active.get("traffic_used_bytes")),
        "traffic_limit_bytes": _coerce_int_or_none(active.get("traffic_limit_bytes")),
        "traffic_used_bytes": _coerce_int_or_none(active.get("traffic_used_bytes")),
        "tariff_key": active.get("tariff_key"),
        "tariff_name": active.get("tariff_name"),
        "tariff_description": active.get("tariff_description"),
        "premium_title": active.get("premium_title"),
        "billing_model": active.get("billing_model"),
        "traffic_limit_strategy": str(active.get("traffic_limit_strategy") or ""),
        "traffic_next_reset_at": _webapp_iso_datetime(active.get("traffic_next_reset_at")),
        "traffic_next_reset_text": _webapp_reset_date_text(
            active.get("traffic_next_reset_at"),
            lang,
        ),
        "tier_baseline_bytes": _coerce_int_or_none(active.get("tier_baseline_bytes")),
        "topup_balance_bytes": _coerce_int_or_none(active.get("topup_balance_bytes")),
        "premium_limit": _format_bytes(
            active.get("premium_limit_bytes"),
            zero_as_unlimited=not bool(active.get("premium_traffic_limited")),
        ),
        "premium_used": _format_bytes(active.get("premium_used_bytes")),
        "premium_limit_bytes": _coerce_int_or_none(active.get("premium_limit_bytes")),
        "premium_used_bytes": _coerce_int_or_none(active.get("premium_used_bytes")),
        "premium_baseline_bytes": _coerce_int_or_none(active.get("premium_baseline_bytes")),
        "premium_topup_balance_bytes": _coerce_int_or_none(
            active.get("premium_topup_balance_bytes")
        ),
        "premium_topup_used_bytes": _coerce_int_or_none(active.get("premium_topup_used_bytes")),
        "premium_bonus_bytes": _coerce_int_or_none(active.get("premium_bonus_bytes")) or 0,
        "regular_bonus_bytes": _coerce_int_or_none(active.get("regular_bonus_bytes")) or 0,
        "regular_unlimited_override": bool(active.get("regular_unlimited_override")),
        "premium_unlimited_override": bool(active.get("premium_unlimited_override")),
        "premium_traffic_limited": bool(active.get("premium_traffic_limited")),
        "premium_is_limited": bool(active.get("premium_is_limited")),
        "premium_traffic_limit_strategy": str(active.get("premium_traffic_limit_strategy") or ""),
        "premium_next_reset_at": _webapp_iso_datetime(active.get("premium_next_reset_at")),
        "premium_next_reset_text": _webapp_reset_date_text(
            active.get("premium_next_reset_at"),
            lang,
        ),
        "premium_squad_labels": list(active.get("premium_squad_labels") or []),
        "premium_node_labels": list(active.get("premium_node_labels") or []),
        "can_topup_traffic": can_topup_traffic,
        "can_topup_regular_traffic": can_topup_regular_traffic,
        "can_topup_premium_traffic": can_topup_premium_traffic,
        "can_topup_devices": can_topup_devices,
        "device_topup_unavailable_reason": (
            device_topup_availability.reason.value if device_topup_availability.reason else None
        ),
        "device_topup_available_currencies": list(device_topup_availability.available_currencies),
        "topup_always_available": topup_always_available,
        "premium_topup_always_available": premium_topup_always_available,
        "period_start_at": active.get("period_start_at").isoformat()
        if active.get("period_start_at")
        else None,
        "is_throttled": bool(active.get("is_throttled")),
        "max_devices": _coerce_int_or_none(active.get("max_devices")),
        "base_hwid_device_limit": _coerce_int_or_none(active.get("base_hwid_device_limit")),
        "extra_hwid_devices": extra_hwid_count,
        "extra_hwid_devices_valid_until": extra_hwid_valid_until.isoformat()
        if extra_hwid_valid_until
        else None,
        "extra_hwid_devices_valid_until_text": extra_hwid_valid_until.strftime("%d.%m.%Y %H:%M")
        if extra_hwid_valid_until
        else None,
        "extra_hwid_devices_next_valid_from": extra_hwid_next_valid_from.isoformat()
        if extra_hwid_next_valid_from
        else None,
        "device_topup_renewal_available": device_topup_renewal_available,
        "auto_renew_enabled": auto_renew_enabled,
        **auto_renew.payload_fields(enabled=auto_renew_enabled),
        "provider": getattr(local_sub, "provider", None),
    }


def _webapp_iso_datetime(value: Any | None) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=UTC)
        return normalized.isoformat()
    return str(value)


def _webapp_reset_date_text(value: Any | None, lang: str) -> str | None:
    parsed = parse_panel_datetime(value)
    if parsed is None:
        return None
    return format_traffic_reset_date(parsed, lang)


def _webapp_datetime_text(value: Any | None) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=UTC)
        return normalized.strftime("%d.%m.%Y %H:%M")
    return str(value)


async def _attach_hwid_renewal_quotes_to_plans(
    session: AsyncSession,
    subscription_service: SubscriptionService,
    *,
    user_id: int,
    settings: Settings,
    active: dict[str, Any] | None,
    local_sub: Any | None,
    plans: list[dict[str, Any]],
) -> None:
    quote_method = getattr(subscription_service, "quote_hwid_device_renewal_for_subscription", None)
    if not callable(quote_method):
        return
    if not active or not local_sub or not settings.tariffs_config:
        return
    if not active.get("end_date") or int(active.get("extra_hwid_devices") or 0) <= 0:
        return

    default_currency = default_currency_key_for_settings(settings)
    default_currency_code = payment_currency_code(default_currency)
    for plan in plans:
        if str(plan.get("sale_mode") or "subscription") != "subscription":
            continue
        target_tariff_key = str(plan.get("tariff_key") or "").strip()
        if not target_tariff_key:
            continue
        try:
            months = int(plan.get("period_key", plan.get("months")) or 0)
        except (TypeError, ValueError):
            continue
        if months <= 0:
            continue
        try:
            currency_quote = await quote_method(
                session,
                user_id=user_id,
                target_tariff_key=target_tariff_key,
                months=months,
                currency=default_currency,
            )
            stars_quote = await quote_method(
                session,
                user_id=user_id,
                target_tariff_key=target_tariff_key,
                months=months,
                currency="stars",
            )
        except Exception:
            logger.exception(
                "Failed to quote HWID renewal for plan %s/%s",
                target_tariff_key,
                months,
            )
            continue
        quote = currency_quote or stars_quote
        if not quote:
            continue
        valid_from = quote.get("valid_from")
        valid_until = quote.get("valid_until")
        active_until = quote.get("active_until")
        renewal = {
            "available": True,
            "device_count": int(quote.get("device_count") or 0),
            "price": float(currency_quote.get("price") if currency_quote else 0),
            "currency": default_currency_code,
            "valid_from": _webapp_iso_datetime(valid_from),
            "valid_from_text": _webapp_datetime_text(valid_from),
            "valid_until": _webapp_iso_datetime(valid_until),
            "valid_until_text": _webapp_datetime_text(valid_until),
            "active_until": _webapp_iso_datetime(active_until),
            "active_until_text": _webapp_datetime_text(active_until),
            "pricing_period_months": quote.get("pricing_period_months"),
            "pricing_period_days": quote.get("pricing_period_days"),
            "traffic_bonus_gb": float(quote.get("traffic_bonus_gb") or 0),
        }
        if stars_quote and int(stars_quote.get("price") or 0) > 0:
            renewal["stars_price"] = int(stars_quote["price"])
        plan["hwid_renewal"] = renewal


def _build_install_share_link(
    request: web.Request | None,
    settings: Settings,
    share_token: str,
) -> str | None:
    share_token = subscription_dal.normalize_install_share_token(share_token)
    if not share_token or request is None:
        return None
    configured_base = str(settings.SUBSCRIPTION_MINI_APP_URL or "").strip()
    if configured_base:
        parts = urlsplit(configured_base)
        if parts.scheme and parts.netloc:
            base = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        else:
            base = configured_base.rstrip("/")
    else:
        host = (
            request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or request.host
        )
        proto = request.headers.get("X-Forwarded-Proto") or request.scheme or "https"
        base = f"{proto}://{host}"
    return f"{base.rstrip('/')}/s/{quote(share_token)}"
