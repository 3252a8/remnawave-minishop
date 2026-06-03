# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405

from config.subscription_guides_config import subscription_guides_available
from config.webapp_themes_config import public_themes_catalog_payload
from bot.services.telegram_notifications import (
    TELEGRAM_NOTIFICATIONS_ENABLED,
    normalize_telegram_notification_status,
    telegram_notifications_need_prompt,
    telegram_notifications_start_link,
)


async def _build_user_payload(request: web.Request, user_id: int) -> Dict[str, Any]:
    settings: Settings = request.app["settings"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    subscription_service: SubscriptionService = request.app["subscription_service"]
    cached = _get_cached_webapp_settings(request)

    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            raise web.HTTPForbidden(
                text=json.dumps({"ok": False, "error": "access_denied"}),
                content_type="application/json",
            )

        active = await subscription_service.get_active_subscription_details(session, user_id)
        referral_code = await user_dal.ensure_referral_code(session, db_user)
        referral_service: Optional[ReferralService] = request.app.get("referral_service")
        bot_username = request.app.get("bot_username") or ""
        referral_link = None
        if referral_service and bot_username:
            referral_link = await referral_service.generate_referral_link(
                session,
                bot_username,
                user_id,
            )
        webapp_referral_link = _build_webapp_referral_link(
            request.app["settings"].SUBSCRIPTION_MINI_APP_URL,
            referral_code,
        )
        referral_stats = (
            await referral_service.get_referral_stats(session, user_id)
            if referral_service
            else {"invited_count": 0, "purchased_count": 0}
        )
        support_unread_count = (
            await support_dal.count_user_unread(session, user_id)
            if settings.SUPPORT_TICKETS_ENABLED
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
        trial_available = bool(
            settings.TRIAL_ENABLED
            and settings.TRIAL_DURATION_DAYS > 0
            and not await subscription_service.has_trial_blocking_subscription(session, user_id)
        )
        avatar = await _ensure_cached_telegram_avatar(request, session, db_user)
        try:
            await session.commit()
        except Exception:
            await session.rollback()

    lang = _normalize_language(db_user.language_code or settings.DEFAULT_LANGUAGE)
    admin_ids = {int(x) for x in (settings.ADMIN_IDS or [])}
    is_admin = bool(db_user.telegram_id and int(db_user.telegram_id) in admin_ids)
    telegram_notifications_status = normalize_telegram_notification_status(
        getattr(db_user, "telegram_notifications_status", None)
    )
    telegram_notifications_link = telegram_notifications_start_link(
        request.app.get("bot_username") or ""
    )
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
            "telegram_linked": bool(_telegram_id_for_user(db_user)),
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
            "welcome_bonus_days": max(
                0, int(getattr(settings, "REFERRAL_WELCOME_BONUS_DAYS", 0) or 0)
            ),
            "one_bonus_per_referee": bool(
                getattr(settings, "REFERRAL_ONE_BONUS_PER_REFEREE", False)
            ),
            "bonus_details": _serialize_referral_bonus_details(settings, lang),
        },
        "plans": _serialize_plans(
            settings,
            lang,
            subscription_options=cached["subscription_options"],
            stars_subscription_options=cached["stars_subscription_options"],
            traffic_packages=cached["traffic_packages"],
            stars_traffic_packages=cached["stars_traffic_packages"],
        ),
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
            "support_url": settings.SUPPORT_LINK,
            "support_tickets_enabled": bool(settings.SUPPORT_TICKETS_ENABLED),
            "support_ticket_max_body_length": int(settings.SUPPORT_TICKET_MAX_BODY_LENGTH or 4000),
            "support_ticket_max_subject_length": int(
                settings.SUPPORT_TICKET_MAX_SUBJECT_LENGTH or 160
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
            "trial_duration_days": int(settings.TRIAL_DURATION_DAYS or 0),
            "trial_traffic_limit_gb": float(settings.TRIAL_TRAFFIC_LIMIT_GB or 0),
            "trial_traffic_strategy": getattr(settings, "TRIAL_TRAFFIC_STRATEGY", "NO_RESET"),
            "subscription_purchase_description": settings.subscription_purchase_description(lang),
            "subscription_guides_enabled": subscription_guides_available(settings),
            "email_auth_enabled": settings.email_auth_configured,
        },
    }


def _legacy_referral_bonus_periods(settings: Settings) -> List[int]:
    if getattr(settings, "traffic_sale_mode", False):
        return []

    return sorted(int(months) for months in settings.subscription_options)


def _serialize_tariff_period_referral_bonus_details(tariff: Any, lang: str) -> List[Dict[str, Any]]:
    details: List[Dict[str, Any]] = []
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


def _serialize_tariff_referral_bonus_details(settings: Settings, lang: str) -> List[Dict[str, Any]]:
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

    summaries: List[Dict[str, Any]] = []
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


def _serialize_referral_bonus_details(settings: Settings, lang: str) -> List[Dict[str, Any]]:
    if settings.tariffs_config:
        return _serialize_tariff_referral_bonus_details(settings, lang)

    details: List[Dict[str, Any]] = []
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
    base_url: Optional[str],
    referral_code: Optional[str],
) -> Optional[str]:
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
    active_or_local_sub: Optional[Any] = None,
    local_sub_or_lang: Optional[Any] = None,
    lang: Optional[str] = None,
    *,
    install_share_token: Optional[str] = None,
) -> Dict[str, Any]:
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
        end_date = end_date.replace(tzinfo=timezone.utc)

    seconds_left = 0
    if end_date:
        seconds_left = max(
            0,
            int((end_date - datetime.now(timezone.utc)).total_seconds()),
        )

    can_topup_regular_traffic = False
    can_topup_premium_traffic = False
    can_topup_traffic = False
    can_topup_devices = False
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
            # max_devices == 0 means unlimited — top-up is pointless in that case.
            can_topup_devices = bool(
                tariff.billing_model == "period"
                and tariff.has_hwid_device_packages()
                and _coerce_int_or_none(active.get("max_devices")) != 0
            )
        except Exception:
            can_topup_regular_traffic = False
            can_topup_premium_traffic = False
            can_topup_traffic = False
            can_topup_devices = False

    panel_short_uuid = str(active.get("panel_short_uuid") or "").strip()
    share_token = str(
        install_share_token or getattr(local_sub, "install_share_token", "") or ""
    ).strip()
    extra_hwid_valid_until = active.get("extra_hwid_devices_valid_until")
    if extra_hwid_valid_until and extra_hwid_valid_until.tzinfo is None:
        extra_hwid_valid_until = extra_hwid_valid_until.replace(tzinfo=timezone.utc)
    extra_hwid_next_valid_from = active.get("extra_hwid_devices_next_valid_from")
    if extra_hwid_next_valid_from and extra_hwid_next_valid_from.tzinfo is None:
        extra_hwid_next_valid_from = extra_hwid_next_valid_from.replace(tzinfo=timezone.utc)
    extra_hwid_count = _coerce_int_or_none(active.get("extra_hwid_devices")) or 0
    device_topup_renewal_available = bool(
        extra_hwid_count > 0
        and extra_hwid_valid_until
        and end_date
        and extra_hwid_valid_until < end_date
    )
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
        "premium_squad_labels": list(active.get("premium_squad_labels") or []),
        "premium_node_labels": list(active.get("premium_node_labels") or []),
        "can_topup_traffic": can_topup_traffic,
        "can_topup_regular_traffic": can_topup_regular_traffic,
        "can_topup_premium_traffic": can_topup_premium_traffic,
        "can_topup_devices": can_topup_devices,
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
        "auto_renew_enabled": bool(getattr(local_sub, "auto_renew_enabled", False)),
        "provider": getattr(local_sub, "provider", None),
    }


def _build_install_share_link(
    request: Optional[web.Request],
    settings: Settings,
    share_token: str,
) -> Optional[str]:
    share_token = subscription_dal.normalize_install_share_token(share_token)
    if not share_token or request is None:
        return None
    configured_base = str(getattr(settings, "SUBSCRIPTION_MINI_APP_URL", "") or "").strip()
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
    subscription_options: Optional[Dict[int, float]] = None,
    stars_subscription_options: Optional[Dict[int, int]] = None,
    traffic_packages: Optional[Dict[float, float]] = None,
    stars_traffic_packages: Optional[Dict[float, int]] = None,
) -> List[Dict[str, Any]]:
    tariffs_config = settings.tariffs_config
    if tariffs_config:
        default_currency = default_currency_key_for_settings(settings)
        default_currency_code = payment_currency_code(default_currency)
        plans: List[Dict[str, Any]] = []
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
                ordered_gb: List[float] = []
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

    if getattr(settings, "traffic_sale_mode", False):
        active_traffic_packages = traffic_packages or settings.traffic_packages
        active_stars_traffic_packages = stars_traffic_packages or settings.stars_traffic_packages
        traffic_units = sorted(set(active_traffic_packages) | set(active_stars_traffic_packages))
        plans: List[Dict[str, Any]] = []
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
    plans: List[Dict[str, Any]] = []
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


def _traffic_percent(used: Optional[int], limit: Optional[int]) -> int:
    used_val = int(used or 0)
    limit_val = int(limit or 0)
    if limit_val <= 0:
        return 0
    return max(0, min(100, round((used_val / limit_val) * 100)))


def _serialize_topup_packages(
    settings: Settings,
    tariff: Any,
    packages: Optional[Any],
    lang: str,
    *,
    sale_mode: str = "topup",
    title_prefix: str = "",
) -> List[Dict[str, Any]]:
    default_currency = default_currency_key_for_settings(settings)
    default_currency_code = payment_currency_code(default_currency)
    currency_packages = {
        float(package.gb): float(package.price)
        for package in (packages.for_currency(default_currency) if packages else [])
    }
    stars_packages = {
        float(package.gb): int(float(package.price))
        for package in (packages.stars if packages else [])
    }
    plans: List[Dict[str, Any]] = []
    for traffic_gb in sorted(set(currency_packages) | set(stars_packages)):
        price = currency_packages.get(traffic_gb)
        stars_price = stars_packages.get(traffic_gb)
        if price is None and (stars_price is None or int(stars_price) <= 0):
            continue
        traffic_value = float(traffic_gb)
        plan: Dict[str, Any] = {
            "id": f"{tariff.key}:{sale_mode}:{_format_number_for_payload(traffic_value)}",
            "tariff_key": tariff.key,
            "tariff_name": tariff.name(lang),
            "billing_model": tariff.billing_model,
            "sale_mode": sale_mode,
            "months": int(traffic_value) if traffic_value.is_integer() else traffic_value,
            "traffic_gb": traffic_value,
            "price": float(price or 0),
            "currency": default_currency_code,
            "title": f"{title_prefix}{_format_traffic_title(traffic_value, lang)}",
            "subtitle": tariff.premium_name(lang)
            if sale_mode == "premium_topup"
            else tariff.name(lang),
        }
        if stars_price is not None and int(stars_price) > 0:
            plan["stars_price"] = int(stars_price)
        plans.append(plan)
    return plans


def _serialize_hwid_device_packages(
    settings: Settings,
    tariff: Any,
    packages: Optional[Any],
    lang: str,
) -> List[Dict[str, Any]]:
    default_currency = default_currency_key_for_settings(settings)
    default_currency_code = payment_currency_code(default_currency)
    currency_packages = {
        int(package.count): float(package.price)
        for package in (packages.for_currency(default_currency) if packages else [])
    }
    stars_packages = {
        int(package.count): int(float(package.price))
        for package in (packages.stars if packages else [])
    }
    plans: List[Dict[str, Any]] = []
    for count in sorted(set(currency_packages) | set(stars_packages)):
        price = currency_packages.get(count)
        stars_price = stars_packages.get(count)
        if price is None and (stars_price is None or int(stars_price) <= 0):
            continue
        plan: Dict[str, Any] = {
            "id": f"{tariff.key}:hwid:{count}",
            "tariff_key": tariff.key,
            "tariff_name": tariff.name(lang),
            "billing_model": tariff.billing_model,
            "sale_mode": "hwid_devices",
            "months": int(count),
            "device_count": int(count),
            "price": float(price or 0),
            "currency": default_currency_code,
            "title": f"+{count}",
            "subtitle": tariff.name(lang),
        }
        if stars_price is not None and int(stars_price) > 0:
            plan["stars_price"] = int(stars_price)
        plans.append(plan)
    return plans


def _serialize_tariff_change_target(
    settings: Settings,
    config: Any,
    tariff: Any,
    options: Dict[str, Any],
    lang: str,
) -> Dict[str, Any]:
    default_currency = default_currency_key_for_settings(settings)
    default_currency_code = payment_currency_code(default_currency)
    actions: List[Dict[str, Any]] = []
    mode = str(options.get("mode") or "")
    if mode == "period_to_period":
        actions.append(
            {
                "mode": "recalc_days",
                "kind": "free",
                "title": "recalc_days",
                "days_after": int(options.get("recalc_days") or 0),
                "remaining_days": int(options.get("remaining_days") or 0),
                "converted_hwid_value_rub": float(options.get("converted_hwid_value_rub") or 0),
                "converted_hwid_days": int(options.get("converted_hwid_days") or 0),
            }
        )
        paid_diff = float(options.get("paid_diff_rub") or 0)
        if paid_diff > 0:
            actions.append(
                {
                    "mode": "paid_diff",
                    "kind": "payment",
                    "title": "paid_diff",
                    "price": paid_diff,
                    "currency": default_currency_code,
                }
            )
    elif mode == "period_to_traffic":
        actions.append(
            {
                "mode": "convert_days_to_gb",
                "kind": "free",
                "title": "convert_days_to_gb",
                "converted_gb": float(options.get("converted_gb") or 0),
                "remaining_days": int(options.get("remaining_days") or 0),
                "converted_hwid_value_rub": float(options.get("converted_hwid_value_rub") or 0),
                "converted_hwid_gb": float(options.get("converted_hwid_gb") or 0),
            }
        )
        actions.extend(
            {
                "mode": "buy_package",
                "kind": "payment",
                "title": f"+{package.gb:g} GB",
                "traffic_gb": float(package.gb),
                "price": float(package.price),
                "currency": default_currency_code,
            }
            for package in (
                tariff.traffic_packages.for_currency(default_currency)
                if tariff.traffic_packages
                else []
            )
        )
    else:
        for months in tariff.enabled_periods:
            price = tariff.period_price(int(months), default_currency)
            if price:
                actions.append(
                    {
                        "mode": "buy_period",
                        "kind": "payment",
                        "months": int(months),
                        "title": _format_months_title(int(months), lang),
                        "price": float(price),
                        "currency": default_currency_code,
                    }
                )
    return {
        "tariff_key": tariff.key,
        "title": tariff.name(lang),
        "description": tariff.description(lang),
        "billing_model": tariff.billing_model,
        "monthly_gb": tariff.monthly_gb,
        "options": options,
        "actions": actions,
    }


def _serialize_payment_methods(
    settings: Settings,
    app: web.Application,
    lang: str = "ru",
    *,
    is_admin: bool = False,
) -> List[Dict[str, Any]]:
    from bot.payment_providers import get_provider_spec, resolve_provider_presentation

    methods: List[Dict[str, Any]] = []
    payment_currency = default_payment_currency_code_for_settings(settings)
    for method in settings.payment_methods_order:
        method = method.lower()
        spec = get_provider_spec(method)
        if (
            spec
            and spec.is_visible_for_user(settings, app, is_admin=is_admin)
            and spec.is_usable_for_payment_currency(settings, payment_currency)
        ):
            presentation = resolve_provider_presentation(spec, settings, language=lang)
            methods.append(
                {
                    "id": method,
                    "name": presentation.webapp_label,
                    "icon": presentation.webapp_icon,
                }
            )
    return methods


def _service_configured(app: web.Application, key: str) -> bool:
    service = app.get(key)
    return bool(service and getattr(service, "configured", False))
