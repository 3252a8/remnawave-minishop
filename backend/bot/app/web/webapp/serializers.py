import json
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession
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
    _referral_welcome_telegram_required_reason,
    _trial_telegram_required_reason,
    _user_has_linked_telegram,
)
from bot.services.referral_service import ReferralService
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.services.telegram_notifications import (
    TELEGRAM_NOTIFICATIONS_ENABLED,
    normalize_telegram_notification_status,
    telegram_notifications_need_prompt,
    telegram_notifications_start_link,
)
from bot.utils.locale_defaults import subscription_purchase_description_text
from bot.utils.traffic_reset import format_traffic_reset_date, parse_panel_datetime
from config.settings import Settings
from config.subscription_guides_config import subscription_guides_available
from config.tariffs_config import default_currency_key_for_settings, payment_currency_code
from config.webapp_themes_config import public_themes_catalog_payload
from db.dal import subscription_dal, support_dal, user_dal

from .assets import (
    _get_cached_webapp_settings,
)
from .common import (
    _coerce_int_or_none,
    _ensure_cached_telegram_avatar,
    _format_bytes,
    _format_months_title,
    _format_number_for_payload,
    _format_remaining,
    _format_traffic_title,
    _normalize_language,
    _telegram_avatar_url,
)
from .serializers_billing_options import (
    _serialize_hwid_device_packages,
    _serialize_payment_methods,
    _serialize_tariff_change_target,
    _serialize_topup_packages,
    _traffic_percent,
)

logger = logging.getLogger(__name__)

__all__ = [
    "_build_user_payload",
    "_serialize_hwid_device_packages",
    "_serialize_payment_methods",
    "_serialize_tariff_change_target",
    "_serialize_topup_packages",
    "_traffic_percent",
]


async def _build_user_payload(request: web.Request, user_id: int) -> dict[str, Any]:
    settings: Settings = get_settings(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    subscription_service: SubscriptionService = get_subscription_service(request)
    cached = _get_cached_webapp_settings(request)
    referral_settings = settings.referral_settings
    support_settings = settings.support_settings

    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            raise web.HTTPForbidden(
                text=json.dumps({"ok": False, "error": "access_denied"}),
                content_type="application/json",
            )

        active = await subscription_service.get_active_subscription_details(session, user_id)
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
        local_sub = (
            await subscription_dal.get_active_subscription_by_user_id(
                session,
                user_id,
                db_user.panel_user_uuid,
            )
            if db_user.panel_user_uuid
            else None
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
        avatar = await _ensure_cached_telegram_avatar(request, session, db_user)
        try:
            await session.commit()
        except Exception:
            await session.rollback()

    admin_ids = {int(x) for x in (settings.ADMIN_IDS or [])}
    is_admin = bool(db_user.telegram_id and int(db_user.telegram_id) in admin_ids)
    telegram_linked = _user_has_linked_telegram(db_user)
    referral_welcome_days = max(0, int(referral_settings.welcome_bonus_days or 0))
    referral_welcome_telegram_required_reason = (
        _referral_welcome_telegram_required_reason(settings, db_user)
        if db_user.referred_by_id and not active and referral_welcome_days > 0
        else None
    )
    telegram_notifications_status = normalize_telegram_notification_status(
        getattr(db_user, "telegram_notifications_status", None)
    )
    telegram_notifications_link = telegram_notifications_start_link(get_bot_username(request))
    return {
        "user": {
            "id": user_id,
            "username": db_user.username,
            "email": db_user.email,
            "email_verified": bool(db_user.email_verified_at),
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
            "telegram_photo_url": _telegram_avatar_url(avatar),
            "first_name": db_user.first_name,
            "language_code": lang,
            "is_admin": is_admin,
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
        "plans": plans_payload,
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
        "settings": {
            "support_url": support_settings.link,
            "server_status_url": settings.SERVER_STATUS_URL,
            "support_tickets_enabled": bool(support_settings.tickets_enabled),
            "support_ticket_max_body_length": int(support_settings.ticket_max_body_length or 4000),
            "support_ticket_max_subject_length": int(
                support_settings.ticket_max_subject_length or 160
            ),
            "traffic_mode": bool(settings.traffic_sale_mode),
            "my_devices_enabled": bool(settings.MY_DEVICES_SECTION_ENABLED),
            "user_hwid_device_limit": (
                int(settings.USER_HWID_DEVICE_LIMIT)
                if settings.USER_HWID_DEVICE_LIMIT is not None
                else None
            ),
            "trial_enabled": bool(settings.TRIAL_ENABLED),
            "trial_available": trial_available,
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
        },
    }


def _legacy_referral_bonus_periods(settings: Settings) -> list[int]:
    if settings.traffic_sale_mode:
        return []

    return sorted(int(months) for months in settings.subscription_options)


def _serialize_tariff_period_referral_bonus_details(tariff: Any, lang: str) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for months in sorted(int(month) for month in tariff.enabled_periods):
        inviter_days = tariff.referral_inviter_bonus_days(months)
        friend_days = tariff.referral_referee_bonus_days(months)
        if inviter_days is None and friend_days is None:
            continue
        details.append(
            {
                "id": f"{tariff.key}:{months}",
                "tariff_key": tariff.key,
                "tariff_name": tariff.name(lang),
                "months": int(months),
                "title": _format_months_title(int(months), lang),
                "inviter_days": int(inviter_days or 0),
                "friend_days": int(friend_days or 0),
            }
        )
    return details


def _serialize_tariff_referral_bonus_details(settings: Settings, lang: str) -> list[dict[str, Any]]:
    tariffs_config = settings.tariffs_config
    if not tariffs_config:
        return []

    period_tariffs = [
        tariff for tariff in tariffs_config.enabled_tariffs if tariff.billing_model == "period"
    ]
    if len(period_tariffs) <= 1:
        return (
            _serialize_tariff_period_referral_bonus_details(period_tariffs[0], lang)
            if period_tariffs
            else []
        )

    summaries: list[dict[str, Any]] = []
    for tariff in period_tariffs:
        details = _serialize_tariff_period_referral_bonus_details(tariff, lang)
        if not details:
            continue
        inviter_values = [int(item["inviter_days"]) for item in details]
        friend_values = [int(item["friend_days"]) for item in details]
        summaries.append(
            {
                "id": f"tariff:{tariff.key}",
                "type": "tariff_summary",
                "tariff_key": tariff.key,
                "tariff_name": tariff.name(lang),
                "title": tariff.name(lang),
                "inviter_min_days": min(inviter_values),
                "inviter_max_days": max(inviter_values),
                "friend_min_days": min(friend_values),
                "friend_max_days": max(friend_values),
                "details": details,
            }
        )
    return summaries


def _serialize_referral_bonus_details(settings: Settings, lang: str) -> list[dict[str, Any]]:
    if settings.tariffs_config:
        return _serialize_tariff_referral_bonus_details(settings, lang)

    details: list[dict[str, Any]] = []
    for months in _legacy_referral_bonus_periods(settings):
        inviter_days = settings.referral_bonus_inviter.get(months)
        friend_days = settings.referral_bonus_referee.get(months)
        if inviter_days is None and friend_days is None:
            continue
        details.append(
            {
                "months": int(months),
                "title": _format_months_title(int(months), lang),
                "inviter_days": int(inviter_days or 0),
                "friend_days": int(friend_days or 0),
            }
        )
    return details


def _build_webapp_referral_link(
    base_url: str | None,
    referral_code: str | None,
) -> str | None:
    if not base_url or not referral_code:
        return None
    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["ref"] = f"u{referral_code}"
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path or "/",
            urlencode(query),
            parts.fragment,
        )
    )


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
        return {
            "active": False,
            "status": "INACTIVE",
            "remaining_text": _format_remaining(0, lang),
            "days_left": 0,
            "config_link": None,
            "connect_url": None,
            "panel_short_uuid": None,
            "install_share_token": None,
            "install_share_url": None,
        }

    end_date = active.get("end_date")
    if end_date and end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=UTC)

    seconds_left = 0
    if end_date:
        seconds_left = max(
            0,
            int((end_date - datetime.now(UTC)).total_seconds()),
        )

    can_topup_regular_traffic = False
    can_topup_premium_traffic = False
    can_topup_traffic = False
    can_topup_devices = False
    topup_always_available = False
    premium_topup_always_available = False
    if settings.tariffs_config and active.get("tariff_key"):
        try:
            tariff = settings.tariffs_config.require(str(active.get("tariff_key")))
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
            max_devices = _coerce_int_or_none(active.get("max_devices"))
            # max_devices == 0 or None means unlimited — top-up is pointless in that case.
            can_topup_devices = bool(
                tariff.billing_model == "period"
                and tariff.has_hwid_device_packages()
                and max_devices not in (None, 0)
            )
        except Exception:
            can_topup_regular_traffic = False
            can_topup_premium_traffic = False
            can_topup_traffic = False
            can_topup_devices = False
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
    provider = str(getattr(local_sub, "provider", "") or "").strip().lower()
    auto_renew_enabled = bool(getattr(local_sub, "auto_renew_enabled", False))
    auto_renew_supported = False
    auto_renew_service_active = False
    auto_renew_provider_label = provider or None
    if provider:
        try:
            from bot.payment_providers import provider_label_map, provider_supports_recurring
            from bot.payment_providers.shared import service_supports_recurring

            auto_renew_supported = provider_supports_recurring(provider)
            if request is not None:
                subscription_service = get_optional_subscription_service(request)
                recurring_service_for = getattr(subscription_service, "recurring_service_for", None)
                service = (
                    recurring_service_for(provider) if callable(recurring_service_for) else None
                )
                auto_renew_service_active = service_supports_recurring(service)
            auto_renew_provider_label = provider_label_map(settings, language=lang).get(
                provider,
                provider,
            )
        except Exception:
            auto_renew_supported = False
            auto_renew_service_active = False
    return {
        "active": seconds_left > 0,
        "status": active.get("status_from_panel") or "UNKNOWN",
        "end_date": end_date.isoformat() if end_date else None,
        "end_date_text": end_date.strftime("%d.%m.%Y %H:%M") if end_date else "N/A",
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
        "premium_limit": _format_bytes(active.get("premium_limit_bytes"), zero_as_unlimited=True),
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
        "premium_is_limited": bool(active.get("premium_is_limited")),
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
        "auto_renew_available": bool(
            auto_renew_supported and (auto_renew_enabled or auto_renew_service_active)
        ),
        "auto_renew_can_enable": bool(auto_renew_supported and auto_renew_service_active),
        "auto_renew_provider_label": auto_renew_provider_label,
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
            months = int(plan.get("months") or 0)
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
            "pricing_period_months": int(quote.get("pricing_period_months") or months),
            "traffic_bonus_gb": subscription_service.hwid_device_traffic_bonus_gb(
                int(quote.get("device_count") or 0)
            ),
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


def _serialize_plans(
    settings: Settings,
    lang: str,
    *,
    subscription_options: dict[int, float] | None = None,
    stars_subscription_options: dict[int, int] | None = None,
    traffic_packages: dict[float, float] | None = None,
    stars_traffic_packages: dict[float, int] | None = None,
) -> list[dict[str, Any]]:
    tariffs_config = settings.tariffs_config
    if tariffs_config:
        default_currency = default_currency_key_for_settings(settings)
        default_currency_code = payment_currency_code(default_currency)
        plans = []
        for tariff in tariffs_config.enabled_tariffs:
            common = {
                "tariff_key": tariff.key,
                "is_default_tariff": tariff.key == tariffs_config.default_tariff,
                "tariff_name": tariff.name(lang),
                "billing_model": tariff.billing_model,
                "description": tariff.description(lang),
                "squad_uuids": tariff.squad_uuids,
                "currency": default_currency_code,
                "hwid_device_limit": tariff.hwid_device_limit,
                "hwid_device_packages": _serialize_hwid_device_packages(
                    settings,
                    tariff,
                    tariff.hwid_device_packages,
                    lang,
                )
                if tariff.billing_model == "period"
                else [],
            }
            if tariff.billing_model == "period":
                # Render periods in the configured order (enabled_periods is the
                # source of truth for purchase-period ordering, matching the bot
                # keyboards). Do not sort so admins can reorder via drag & drop.
                for months in tariff.enabled_periods:
                    price = tariff.period_price(int(months), default_currency)
                    stars_price = tariff.period_price(int(months), "stars")
                    if price is None and (stars_price is None or int(stars_price) <= 0):
                        continue
                    plan = {
                        **common,
                        "id": f"{tariff.key}:period:{int(months)}",
                        "sale_mode": "subscription",
                        "months": int(months),
                        "price": float(price or 0),
                        "title": tariff.name(lang),
                        "subtitle": _format_months_title(int(months), lang),
                        "monthly_gb": tariff.monthly_gb,
                    }
                    if stars_price is not None and int(stars_price) > 0:
                        plan["stars_price"] = int(stars_price)
                    plans.append(plan)
            else:
                currency_packages = {
                    float(package.gb): float(package.price)
                    for package in (
                        tariff.traffic_packages.for_currency(default_currency)
                        if tariff.traffic_packages
                        else []
                    )
                }
                stars_packages = {
                    float(package.gb): int(float(package.price))
                    for package in (
                        tariff.traffic_packages.stars if tariff.traffic_packages else []
                    )
                }
                # Preserve the configured package order (default-currency list first,
                # then any Stars-only volumes) so admins can reorder via drag & drop.
                # Matches the bot keyboard, which iterates the package list as-is.
                ordered_gb: list[float] = []
                for traffic_gb in list(currency_packages) + list(stars_packages):
                    if traffic_gb not in ordered_gb:
                        ordered_gb.append(traffic_gb)
                for traffic_gb in ordered_gb:
                    price = currency_packages.get(traffic_gb)
                    stars_price = stars_packages.get(traffic_gb)
                    if price is None and (stars_price is None or int(stars_price) <= 0):
                        continue
                    traffic_value = float(traffic_gb)
                    plan = {
                        **common,
                        "id": f"{tariff.key}:traffic:{_format_number_for_payload(traffic_value)}",
                        "sale_mode": "traffic_package",
                        "months": int(traffic_value)
                        if traffic_value.is_integer()
                        else traffic_value,
                        "traffic_gb": traffic_value,
                        "price": float(price or 0),
                        "title": tariff.name(lang),
                        "subtitle": _format_traffic_title(traffic_value, lang),
                    }
                    if stars_price is not None and int(stars_price) > 0:
                        plan["stars_price"] = int(stars_price)
                    plans.append(plan)
        return plans

    if settings.traffic_sale_mode:
        active_traffic_packages = traffic_packages or settings.traffic_packages
        active_stars_traffic_packages = stars_traffic_packages or settings.stars_traffic_packages
        traffic_units = sorted(set(active_traffic_packages) | set(active_stars_traffic_packages))
        plans = []
        for traffic_gb in traffic_units:
            price = active_traffic_packages.get(traffic_gb)
            stars_price = active_stars_traffic_packages.get(traffic_gb)
            if price is None and (stars_price is None or int(stars_price) <= 0):
                continue
            traffic_value = float(traffic_gb)
            plan = {
                "months": int(traffic_value) if traffic_value.is_integer() else traffic_value,
                "traffic_gb": traffic_value,
                "price": float(price or 0),
                "currency": settings.DEFAULT_CURRENCY_SYMBOL or "RUB",
                "title": _format_traffic_title(traffic_value, lang),
                "sale_mode": "traffic",
            }
            if stars_price is not None and int(stars_price) > 0:
                plan["stars_price"] = int(stars_price)
            plans.append(plan)
        return plans

    active_subscription_options = subscription_options or settings.subscription_options
    active_stars_subscription_options = (
        stars_subscription_options or settings.stars_subscription_options
    )
    plans = []
    for months in sorted(set(active_subscription_options) | set(active_stars_subscription_options)):
        price = active_subscription_options.get(months)
        stars_price = active_stars_subscription_options.get(months)
        if price is None and (stars_price is None or int(stars_price) <= 0):
            continue
        plan = {
            "months": int(months),
            "price": float(price or 0),
            "currency": settings.DEFAULT_CURRENCY_SYMBOL or "RUB",
            "title": _format_months_title(int(months), lang),
            "sale_mode": "subscription",
        }
        if stars_price is not None and int(stars_price) > 0:
            plan["stars_price"] = int(stars_price)
        plans.append(plan)
    return plans
