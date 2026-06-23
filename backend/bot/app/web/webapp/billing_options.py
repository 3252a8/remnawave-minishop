from bot.app.web.context import (
    get_session_factory,
    get_settings,
    get_subscription_service,
)
from bot.app.web.webapp.auth import _require_user_id
from bot.app.web.webapp.common import (
    _json_error,
    _parse_model_payload,
)
from bot.app.web.webapp.payloads import (
    WebAppPaymentCreatePayload,
    WebAppTariffChangePayload,
)

from ._runtime import (
    Settings,
    SubscriptionService,
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
    json_response,
    payment_currency_code,
    sessionmaker,
    subscription_dal,
    user_dal,
    web,
)
from .billing_common import _billing_datetime_text, _billing_iso_datetime
from .billing_payments import _create_subscription_payment
from .common import (
    _coerce_int_or_none,
)
from .serializers import (
    _serialize_tariff_change_target,
    _serialize_topup_packages,
    _traffic_percent,
)


async def tariff_topup_options_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    config = settings.tariffs_config
    topup_kind = str(request.query.get("kind") or "all").strip().lower()
    if topup_kind not in {"all", "regular", "premium"}:
        return _json_error(400, "invalid_topup_kind", "Invalid topup kind")
    if not config:
        return _json_error(404, "tariffs_unavailable", "Tariffs are not configured")

    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, db_user.panel_user_uuid
        )
        if not sub or not sub.tariff_key:
            return _json_error(
                400, "subscription_required", "Active tariff subscription is required"
            )
        lang = db_user.language_code or settings.DEFAULT_LANGUAGE
        tariff = config.require(sub.tariff_key)
        plans = (
            _serialize_topup_packages(settings, tariff, config.topup_packages_for(tariff), lang)
            if topup_kind in {"all", "regular"}
            else []
        )
        premium_plans = (
            _serialize_topup_packages(
                settings,
                tariff,
                tariff.premium_topup_packages,
                lang,
                sale_mode="premium_topup",
                title_prefix=f"{tariff.premium_name(lang)} ",
            )
            if topup_kind in {"all", "premium"} and tariff.premium_squad_uuids
            else []
        )
        premium_bonus_bytes = int(getattr(sub, "premium_bonus_bytes", 0) or 0)
        premium_unlimited_override = bool(getattr(sub, "premium_unlimited_override", False))
        premium_limit_bytes = (
            int(sub.premium_baseline_bytes or 0)
            + int(sub.premium_topup_balance_bytes or 0)
            + int(getattr(sub, "premium_topup_used_bytes", 0) or 0)
            + premium_bonus_bytes
        )
        premium_access = await get_subscription_service(request).premium_access_for_tariff(tariff)
        return json_response(
            {
                "ok": True,
                "tariff_key": tariff.key,
                "tariff_name": tariff.name(lang),
                "topup_kind": topup_kind,
                "premium_title": tariff.premium_name(lang),
                "traffic_percent": _traffic_percent(
                    sub.traffic_used_bytes, sub.traffic_limit_bytes
                ),
                "premium_traffic_percent": 0
                if premium_unlimited_override
                else _traffic_percent(
                    sub.premium_used_bytes,
                    premium_limit_bytes,
                ),
                "premium_limit_bytes": premium_limit_bytes,
                "premium_used_bytes": int(sub.premium_used_bytes or 0),
                "premium_baseline_bytes": int(sub.premium_baseline_bytes or 0),
                "premium_topup_balance_bytes": int(sub.premium_topup_balance_bytes or 0),
                "premium_topup_used_bytes": int(getattr(sub, "premium_topup_used_bytes", 0) or 0),
                "premium_bonus_bytes": premium_bonus_bytes,
                "premium_unlimited_override": premium_unlimited_override,
                "premium_is_limited": bool(sub.premium_is_limited),
                "premium_squad_labels": premium_access.get("squad_labels") or [],
                "premium_node_labels": premium_access.get("node_labels") or [],
                "warning_levels": settings.tariff_traffic_warning_levels,
                "plans": plans + premium_plans,
            }
        )


async def tariff_change_options_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    config = settings.tariffs_config
    if not config:
        return _json_error(404, "tariffs_unavailable", "Tariffs are not configured")

    async_session_factory: sessionmaker = get_session_factory(request)
    subscription_service: SubscriptionService = get_subscription_service(request)
    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, db_user.panel_user_uuid
        )
        if not sub or not sub.tariff_key:
            return _json_error(
                400, "subscription_required", "Active tariff subscription is required"
            )
        lang = db_user.language_code or settings.DEFAULT_LANGUAGE
        current = config.require(sub.tariff_key)
        targets = []
        for tariff in config.enabled_tariffs:
            if tariff.key == current.key:
                continue
            options = await subscription_service.calculate_tariff_switch_options_with_hwid(
                session, sub, tariff
            )
            targets.append(_serialize_tariff_change_target(settings, config, tariff, options, lang))
        return json_response(
            {
                "ok": True,
                "current": {
                    "tariff_key": current.key,
                    "title": current.name(lang),
                    "description": current.description(lang),
                    "billing_model": current.billing_model,
                },
                "targets": targets,
            }
        )


async def tariff_change_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    change_payload = await _parse_model_payload(request, WebAppTariffChangePayload)
    mode = str(change_payload.mode or "").strip()
    if mode not in {"recalc_days", "convert_days_to_gb"}:
        return _json_error(400, "invalid_change_mode", "This tariff change requires payment")

    settings: Settings = get_settings(request)
    if not settings.tariffs_config:
        return _json_error(404, "tariffs_unavailable", "Tariffs are not configured")
    async_session_factory: sessionmaker = get_session_factory(request)
    subscription_service: SubscriptionService = get_subscription_service(request)
    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        result = await subscription_service.switch_tariff_without_payment(
            session,
            user_id,
            str(change_payload.tariff_key),
            mode,
        )
        if not result:
            await session.rollback()
            return _json_error(400, "change_failed", "Tariff change failed")
        await session.commit()
        return json_response({"ok": True, **result})


async def tariff_change_payment_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    payment_payload = await _parse_model_payload(request, WebAppPaymentCreatePayload)
    method = str(payment_payload.method or "").strip().lower()
    tariff_key = str(payment_payload.tariff_key or "").strip()
    settings: Settings = get_settings(request)
    config = settings.tariffs_config
    default_currency_code = default_payment_currency_code_for_settings(settings)
    if not config:
        return _json_error(404, "tariffs_unavailable", "Tariffs are not configured")
    if not tariff_key:
        return _json_error(400, "invalid_plan", "Tariff is not selected")

    async_session_factory: sessionmaker = get_session_factory(request)
    subscription_service: SubscriptionService = get_subscription_service(request)
    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, db_user.panel_user_uuid
        )
        if not sub:
            return _json_error(
                400, "subscription_required", "Active tariff subscription is required"
            )
        target = config.require(tariff_key)
        options = await subscription_service.calculate_tariff_switch_options_with_hwid(
            session, sub, target
        )
        price = float(options.get("paid_diff_rub") or 0)
        if price <= 0:
            return _json_error(
                400, "payment_not_required", "Payment is not required for this tariff change"
            )
        return await _create_subscription_payment(
            request=request,
            session=session,
            user_id=user_id,
            method=method,
            months=1,
            price=price,
            stars_price=None,
            currency=default_currency_code,
            lang=db_user.language_code or settings.DEFAULT_LANGUAGE,
            sale_mode=f"tariff_upgrade@{target.key}",
        )


async def device_topup_options_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    config = settings.tariffs_config
    if not settings.MY_DEVICES_SECTION_ENABLED:
        return _json_error(404, "devices_disabled", "Devices section is disabled")
    if not config:
        return _json_error(404, "tariffs_unavailable", "Tariffs are not configured")

    async_session_factory: sessionmaker = get_session_factory(request)
    subscription_service: SubscriptionService = get_subscription_service(request)
    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, db_user.panel_user_uuid
        )
        if not sub or not sub.tariff_key:
            return _json_error(
                400, "subscription_required", "Active tariff subscription is required"
            )
        tariff = config.require(sub.tariff_key)
        if tariff.billing_model != "period":
            return _json_error(400, "device_topup_unavailable", "Device top-up is not available")
        lang = db_user.language_code or settings.DEFAULT_LANGUAGE
        active = await subscription_service.get_active_subscription_details(session, user_id)
        extra_hwid_valid_until = active.get("extra_hwid_devices_valid_until") if active else None
        extra_hwid_valid_until_text = (
            active.get("extra_hwid_devices_valid_until_text") if active else None
        ) or _billing_datetime_text(extra_hwid_valid_until)
        packages = tariff.hwid_device_packages
        default_currency = default_currency_key_for_settings(settings)
        default_currency_code = payment_currency_code(default_currency)
        if packages and hasattr(packages, "for_currency"):
            default_packages = packages.for_currency(default_currency)
        else:
            default_packages = getattr(packages, default_currency, []) if packages else []
        currency_counts = {int(package.count) for package in default_packages}
        stars_counts = {int(package.count) for package in (packages.stars if packages else [])}
        plans = []
        for count in sorted(currency_counts | stars_counts):
            currency_quote = (
                await subscription_service.quote_hwid_device_topup(
                    session,
                    user_id=user_id,
                    device_count=count,
                    tariff_key=tariff.key,
                    renewal=False,
                    currency=default_currency,
                )
                if count in currency_counts
                else None
            )
            stars_quote = (
                await subscription_service.quote_hwid_device_topup(
                    session,
                    user_id=user_id,
                    device_count=count,
                    tariff_key=tariff.key,
                    renewal=False,
                    currency="stars",
                )
                if count in stars_counts
                else None
            )
            if not currency_quote and not stars_quote:
                continue
            quote = currency_quote or stars_quote
            assert quote is not None
            valid_from = quote.get("valid_from")
            valid_until = quote.get("valid_until")
            plan = {
                "id": f"{tariff.key}:hwid:{count}",
                "tariff_key": tariff.key,
                "tariff_name": tariff.name(lang),
                "billing_model": tariff.billing_model,
                "sale_mode": "hwid_devices",
                "renewal": False,
                "months": count,
                "device_count": count,
                "price": float(currency_quote.get("price") if currency_quote else 0),
                "currency": default_currency_code,
                "title": f"+{count}",
                "subtitle": tariff.name(lang),
                "valid_from": _billing_iso_datetime(valid_from),
                "valid_from_text": _billing_datetime_text(valid_from),
                "valid_until": _billing_iso_datetime(valid_until),
                "valid_until_text": _billing_datetime_text(valid_until),
                "proration_ratio": float(quote.get("proration_ratio") or 0),
            }
            if stars_quote and int(stars_quote.get("price") or 0) > 0:
                plan["stars_price"] = int(stars_quote["price"])
            plans.append(plan)
        return json_response(
            {
                "ok": True,
                "tariff_key": tariff.key,
                "tariff_name": tariff.name(lang),
                "current_limit": _coerce_int_or_none(active.get("max_devices")) if active else None,
                "extra_hwid_devices": int(active.get("extra_hwid_devices") or 0)
                if active
                else int(sub.extra_hwid_devices or 0),
                "extra_hwid_devices_valid_until": _billing_iso_datetime(extra_hwid_valid_until),
                "extra_hwid_devices_valid_until_text": extra_hwid_valid_until_text,
                "renewal_available": False,
                "renewal_recommended_count": 0,
                "plans": plans,
            }
        )
