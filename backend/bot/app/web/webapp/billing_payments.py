import logging
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Literal

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_i18n,
    get_session_factory,
    get_settings,
    get_subscription_service,
)
from bot.app.web.webapp.assets import _enforce_webapp_rate_limit, _get_cached_webapp_settings
from bot.app.web.webapp.auth import _require_user_id, _trial_telegram_required_reason
from bot.app.web.webapp.common import (
    _json_error,
    _parse_model_payload,
)
from bot.app.web.webapp.payloads import (
    WebAppPaymentCreatePayload,
)
from bot.payment_providers.base import WebAppPaymentContext
from bot.payment_providers.shared.entitlement_context import (
    EntitlementContextError,
    build_entitlement_context_snapshot_from_values,
    snapshot_current_entitlement_context,
)
from bot.services.checkout_addons import checkout_addon_grants
from bot.services.device_topup_availability import resolve_device_topup_availability
from bot.services.partner_common import PartnerError
from bot.services.subscription_gifts import gift_payment_method_available, is_gift_sale
from bot.services.subscription_order_terms import freeze_subscription_terms
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.services.trial_days import TRIAL_DAYS_START_FROM_PAYMENT
from bot.services.user_balance_service import UserBalanceError
from config.settings import Settings
from config.subscription_periods import (
    add_period_days,
    checkout_duration_days,
    days_to_legacy_months,
    multiplied_bonus_days,
    resolve_period_days,
    tariff_period_key,
    with_period_days,
)
from config.tariffs_config import (
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
    payment_currency_code,
)
from db.dal import subscription_dal, user_dal

from .billing_checkout_adjustments import (
    CheckoutPromoResult,
    _resolve_checkout_promo,
)
from .billing_checkout_bundle import (
    CheckoutBundleError,
    build_checkout_bundle,
    normalize_checkout_device_selection,
)
from .billing_common import _parse_positive_int_units, _subscription_is_trial
from .billing_partner_checkout import (
    allocate_checkout_balance,
    balance_checkout_context_fields,
    create_fully_balance_funded_payment,
)
from .billing_payment_policy import _active_tribute_recurrence, _payment_promo_error
from .billing_payment_reuse import reuse_checkout_if_available
from .billing_promo_checkout import create_fully_discounted_payment
from .billing_quotes import (
    BasePaymentQuote as BasePaymentQuote,
)
from .billing_quotes import (
    _configured_tariff,
    _localized_payment_description,
    _resolve_checkout_pricing_context,
    _subscription_effective_hwid_limit,
)
from .billing_quotes import (
    _resolve_base_payment_quote as _resolve_base_payment_quote,
)
from .billing_sale_modes import (
    _sale_mode_base,
    _sale_mode_is_hwid_devices,
    _sale_mode_tariff_key,
)
from .billing_sale_modes import (
    _sale_mode_is_traffic as _sale_mode_is_traffic,
)
from .billing_tariff_access import request_tariff_access_code, require_user_available_tariff
from .common import (
    _resolve_numeric_option_key,
)

logger = logging.getLogger(__name__)


async def create_payment_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    rate_limit_response = await _enforce_webapp_rate_limit(
        request,
        user_id=user_id,
        action="payments_create",
    )
    if rate_limit_response:
        return rate_limit_response

    payment_payload = normalize_checkout_device_selection(
        await _parse_model_payload(request, WebAppPaymentCreatePayload)
    )
    method = str(payment_payload.method or "").strip().lower()
    settings: Settings = get_settings(request)
    subscription_service: SubscriptionService = get_subscription_service(request)
    cached = _get_cached_webapp_settings(request)
    tariffs_config = settings.tariffs_config
    default_currency = default_currency_key_for_settings(settings)
    default_currency_code = payment_currency_code(default_currency)
    traffic_mode = bool(settings.traffic_sale_mode)
    sale_mode = "subscription"
    traffic_gb_for_payment: float | None = None
    hwid_quote: dict[str, Any] | None = None
    quoted_entitlement_context_snapshot: str | None = None
    requested_sale_mode = _sale_mode_base(str(payment_payload.sale_mode or ""))
    if is_gift_sale(payment_payload.sale_mode) and not payment_payload.gift:
        return _json_error(400, "gift_purchase_unavailable", "Gift checkout must be explicit")
    if payment_payload.gift and (
        not settings.GIFTS_ENABLED
        or requested_sale_mode not in {"", "subscription"}
        or payment_payload.renew_hwid_devices
        or not gift_payment_method_available(method)
    ):
        return _json_error(400, "gift_purchase_unavailable", "Unsupported gift purchase options")
    if payment_payload.gift_recipient_email and (
        not payment_payload.gift
        or not settings.smtp_delivery_configured
        or not settings.SUBSCRIPTION_MINI_APP_URL
    ):
        return _json_error(400, "gift_email_unavailable", "Gift email delivery is unavailable")
    payment_units: int | float
    price: float | None = None
    stars_price: int | None = None

    async def resolve_requested_tariff(tariff_key: str) -> Any:
        if tariffs_config is None:
            raise KeyError(tariff_key)
        try:
            return tariffs_config.require(tariff_key)
        except KeyError:
            if payment_payload.gift:
                raise
            async with get_session_factory(request)() as eligibility_session:
                return await require_user_available_tariff(
                    eligibility_session,
                    tariffs_config,
                    user_id=user_id,
                    tariff_key=tariff_key,
                    access_code=request_tariff_access_code(request),
                )

    if requested_sale_mode == "trial":
        if (
            not settings.TRIAL_ENABLED
            or settings.TRIAL_DURATION_DAYS <= 0
            or not settings.TRIAL_PAYMENT_ENABLED
        ):
            return _json_error(400, "trial_payment_unavailable", "Paid trial is not available")
        price = max(0.0, float(settings.TRIAL_PAYMENT_PRICE or 0))
        stars_price = max(0, int(settings.TRIAL_PAYMENT_STARS_PRICE or 0))
        if method == "stars" and stars_price <= 0:
            return _json_error(400, "invalid_plan", "Stars price is not configured")
        if method != "stars" and price <= 0:
            return _json_error(400, "invalid_plan", "Trial price is not configured")
        payment_units = 1
        sale_mode = "trial"
    elif tariffs_config and requested_sale_mode == "hwid_devices_renewal":
        return _json_error(400, "invalid_plan", "Device renewal is part of subscription renewal")
    elif tariffs_config and requested_sale_mode in {
        "hwid_device",
        "hwid_devices",
    }:
        if not settings.MY_DEVICES_SECTION_ENABLED:
            return _json_error(
                404,
                "device_topup_section_disabled",
                "Devices section is disabled",
            )
        tariff_key = str(payment_payload.tariff_key or "").strip()
        if not tariff_key:
            return _json_error(400, "invalid_plan", "Tariff is not selected")
        try:
            tariff = await resolve_requested_tariff(tariff_key)
        except Exception:
            return _json_error(400, "invalid_plan", "Tariff is not available")
        if tariff.billing_model != "period":
            return _json_error(400, "invalid_plan", "Device top-up is not available")
        device_count = _parse_positive_int_units(
            payment_payload.device_count
            if payment_payload.device_count is not None
            else payment_payload.months
        )
        if device_count is None:
            return _json_error(400, "invalid_plan", "Invalid device package")
        if not tariff.hwid_device_packages:
            return _json_error(400, "invalid_plan", "Device package is not available")
        payment_units = device_count
        sale_mode = f"{requested_sale_mode}@{tariff.key}"
    elif tariffs_config and requested_sale_mode in {"topup", "premium_topup"}:
        tariff_key = str(payment_payload.tariff_key or "").strip()
        if not tariff_key:
            return _json_error(400, "invalid_plan", "Tariff is not selected")
        try:
            tariff = await resolve_requested_tariff(tariff_key)
        except Exception:
            return _json_error(400, "invalid_plan", "Tariff is not available")
        try:
            traffic_gb = float(
                payment_payload.traffic_gb
                if payment_payload.traffic_gb is not None
                else payment_payload.months
            )
        except (TypeError, ValueError):
            return _json_error(400, "invalid_plan", "Invalid traffic package")
        packages = (
            tariff.premium_topup_packages
            if requested_sale_mode == "premium_topup"
            else tariffs_config.topup_packages_for(tariff)
        )
        currency_packages = {
            float(package.gb): float(package.price)
            for package in (packages.for_currency(default_currency) if packages else [])
        }
        stars_packages = {
            float(package.gb): int(float(package.price))
            for package in (packages.stars if packages else [])
        }
        package_key = _resolve_numeric_option_key(currency_packages, traffic_gb)
        stars_package_key = _resolve_numeric_option_key(stars_packages, traffic_gb)
        price = currency_packages.get(package_key) if package_key is not None else None
        stars_price = (
            stars_packages.get(stars_package_key) if stars_package_key is not None else None
        )
        if price is None and method != "stars":
            return _json_error(400, "invalid_plan", "Traffic package is not available")
        if method == "stars" and (stars_price is None or int(stars_price) <= 0):
            return _json_error(400, "invalid_plan", "Stars price is not configured")
        payment_units = int(traffic_gb) if float(traffic_gb).is_integer() else traffic_gb
        traffic_gb_for_payment = float(payment_units)
        sale_mode = f"{requested_sale_mode}@{tariff.key}"
    elif tariffs_config:
        tariff_key = str(payment_payload.tariff_key or "").strip()
        if not tariff_key:
            return _json_error(400, "invalid_plan", "Tariff is not selected")
        try:
            tariff = await resolve_requested_tariff(tariff_key)
        except Exception:
            return _json_error(400, "invalid_plan", "Tariff is not available")

        if tariff.billing_model == "traffic":
            try:
                traffic_gb = float(
                    payment_payload.traffic_gb
                    if payment_payload.traffic_gb is not None
                    else payment_payload.months
                )
            except (TypeError, ValueError):
                return _json_error(400, "invalid_plan", "Invalid traffic package")
            if traffic_gb <= 0:
                return _json_error(400, "invalid_plan", "Invalid traffic package")
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
                for package in (tariff.traffic_packages.stars if tariff.traffic_packages else [])
            }
            package_key = _resolve_numeric_option_key(currency_packages, traffic_gb)
            stars_package_key = _resolve_numeric_option_key(stars_packages, traffic_gb)
            price = currency_packages.get(package_key) if package_key is not None else None
            stars_price = (
                stars_packages.get(stars_package_key) if stars_package_key is not None else None
            )
            if price is None and method != "stars":
                return _json_error(400, "invalid_plan", "Traffic package is not available")
            if method == "stars" and (stars_price is None or int(stars_price) <= 0):
                return _json_error(400, "invalid_plan", "Stars price is not configured")
            payment_units = int(traffic_gb) if float(traffic_gb).is_integer() else traffic_gb
            traffic_gb_for_payment = float(payment_units)
            sale_mode = f"traffic_package@{tariff.key}"
        else:
            try:
                months = tariff_period_key(
                    tariff,
                    duration_days=payment_payload.duration_days,
                    months=payment_payload.months,
                )
            except (TypeError, ValueError):
                return _json_error(400, "invalid_plan", "Invalid subscription period")
            if months is None or months not in tariff.enabled_periods:
                return _json_error(400, "invalid_plan", "Subscription period is not available")
            price = tariff.period_price(months, default_currency)
            stars_price_raw = tariff.period_price(months, "stars")
            stars_price = int(stars_price_raw) if stars_price_raw and stars_price_raw > 0 else None
            if price is None and method != "stars":
                return _json_error(400, "invalid_plan", "Subscription period is not available")
            if method == "stars" and (stars_price is None or int(stars_price) <= 0):
                return _json_error(400, "invalid_plan", "Stars price is not configured")
            payment_units = months
            sale_mode = f"subscription@{tariff.key}"
    elif traffic_mode:
        try:
            traffic_gb = float(
                payment_payload.traffic_gb
                if payment_payload.traffic_gb is not None
                else payment_payload.months
            )
        except (TypeError, ValueError):
            return _json_error(400, "invalid_plan", "Invalid traffic package")
        if traffic_gb <= 0:
            return _json_error(400, "invalid_plan", "Invalid traffic package")
        package_key = _resolve_numeric_option_key(cached["traffic_packages"], traffic_gb)
        stars_package_key = _resolve_numeric_option_key(
            cached["stars_traffic_packages"], traffic_gb
        )
        price = cached["traffic_packages"].get(package_key) if package_key is not None else None
        stars_price = (
            cached["stars_traffic_packages"].get(stars_package_key)
            if stars_package_key is not None
            else None
        )
        if price is None and method != "stars":
            return _json_error(400, "invalid_plan", "Traffic package is not available")
        if method == "stars" and (stars_price is None or int(stars_price) <= 0):
            return _json_error(400, "invalid_plan", "Stars price is not configured")
        payment_units = int(traffic_gb) if float(traffic_gb).is_integer() else traffic_gb
        traffic_gb_for_payment = float(payment_units)
        sale_mode = "traffic"
    else:
        try:
            months = days_to_legacy_months(
                resolve_period_days(
                    duration_days=payment_payload.duration_days, months=payment_payload.months
                )
            )
            if months is None:
                raise ValueError("duration is not available")
        except (TypeError, ValueError):
            return _json_error(400, "invalid_plan", "Invalid subscription period")
        price = cached["subscription_options"].get(months)
        stars_price = cached["stars_subscription_options"].get(months)
        if price is None and method != "stars":
            return _json_error(400, "invalid_plan", "Subscription period is not available")
        if method == "stars" and (stars_price is None or int(stars_price) <= 0):
            return _json_error(400, "invalid_plan", "Stars price is not configured")
        payment_units = months
        sale_mode = "subscription"

    if payment_payload.gift:
        if _sale_mode_base(sale_mode) != "subscription":
            return _json_error(
                400, "gift_purchase_unavailable", "Gifts require a period subscription"
            )
        sale_mode += "|gift"
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        lang = db_user.language_code or settings.DEFAULT_LANGUAGE
        if _sale_mode_base(sale_mode) == "trial":
            telegram_required_reason = _trial_telegram_required_reason(settings, db_user)
            if telegram_required_reason:
                return _json_error(
                    400,
                    "trial_telegram_required",
                    telegram_required_reason,
                )
            if await subscription_service.has_trial_blocking_subscription(session, user_id):
                return _json_error(
                    409,
                    "trial_already_had_subscription_or_trial",
                    "Trial is not available for this account",
                )
            admin_ids = {int(item) for item in (settings.ADMIN_IDS or [])}
            is_admin = bool(db_user.telegram_id and int(db_user.telegram_id) in admin_ids)
            return await _create_subscription_payment(
                request=request,
                session=session,
                user_id=user_id,
                method=method,
                months=payment_units,
                price=float(price or 0),
                stars_price=stars_price,
                currency=default_currency_code,
                lang=lang,
                sale_mode=sale_mode,
                is_admin=is_admin,
            )
        checkout_pricing_context, pricing_context_error = await _resolve_checkout_pricing_context(
            session=session,
            user_id=user_id,
            db_user=db_user,
            payment_payload=payment_payload,
            settings=settings,
            sale_mode=sale_mode,
        )
        if pricing_context_error is not None:
            return pricing_context_error
        if _sale_mode_is_hwid_devices(sale_mode):
            sub = await subscription_dal.get_active_subscription_by_user_id(
                session, user_id, db_user.panel_user_uuid
            )
            sale_tariff_key = _sale_mode_tariff_key(sale_mode)
            active_tariff = _configured_tariff(
                tariffs_config,
                sub.tariff_key if sub is not None else None,
            )
            currency = "stars" if method == "stars" else default_currency
            availability = resolve_device_topup_availability(
                settings,
                subscription_active=sub is not None,
                tariff_key=sub.tariff_key if sub is not None else None,
                max_devices=(
                    _subscription_effective_hwid_limit(settings, sub, active_tariff)
                    if sub is not None and active_tariff is not None
                    else None
                ),
                expected_tariff_key=sale_tariff_key,
            )
            if not availability.allowed or not availability.supports(
                int(payment_units),
                currency,
            ):
                return _json_error(
                    400,
                    availability.error_code,
                    "Device top-up is not available",
                )
            hwid_quote = await subscription_service.quote_hwid_device_topup(
                session,
                user_id=user_id,
                device_count=int(payment_units),
                tariff_key=sale_tariff_key,
                renewal=False,
                currency=currency,
            )
            if not hwid_quote:
                return _json_error(400, "invalid_plan", "Device package is not available")
            try:
                quoted_entitlement_context_snapshot = (
                    build_entitlement_context_snapshot_from_values(
                        sale_mode=sale_mode,
                        active_subscription_id=hwid_quote.get("subscription_id"),
                        active_tariff_key=hwid_quote.get("tariff_key"),
                    )
                )
            except EntitlementContextError:
                return _json_error(
                    409,
                    "entitlement_context_changed",
                    "The active subscription no longer matches this purchase",
                )
            if method == "stars":
                stars_price = int(hwid_quote["price"])
                price = 0.0
                if stars_price <= 0:
                    return _json_error(400, "invalid_plan", "Stars price is not configured")
            else:
                price = float(hwid_quote["price"])
                stars_price = None
        elif _sale_mode_base(sale_mode) == "subscription" and bool(
            payment_payload.renew_hwid_devices
        ):
            currency = "stars" if method == "stars" else default_currency
            sale_tariff_key = _sale_mode_tariff_key(sale_mode)
            if sale_tariff_key:
                hwid_quote = await subscription_service.quote_hwid_device_renewal_for_subscription(
                    session,
                    user_id=user_id,
                    target_tariff_key=sale_tariff_key,
                    months=int(payment_units),
                    currency=currency,
                )
            if hwid_quote:
                try:
                    quoted_entitlement_context_snapshot = (
                        build_entitlement_context_snapshot_from_values(
                            sale_mode=sale_mode,
                            active_subscription_id=hwid_quote.get("subscription_id"),
                            active_tariff_key=hwid_quote.get("tariff_key"),
                            bind_to_active_subscription=True,
                        )
                    )
                except EntitlementContextError:
                    return _json_error(
                        409,
                        "entitlement_context_changed",
                        "The active subscription no longer matches this purchase",
                    )
                if method == "stars":
                    stars_price = int(stars_price or 0) + int(hwid_quote["price"])
                else:
                    price = float(price or 0) + float(hwid_quote["price"])
                    stars_price = None
        try:
            bundled_quote, checkout_bundle = build_checkout_bundle(
                BasePaymentQuote(
                    payment_units=payment_units,
                    price=float(price or 0),
                    stars_price=stars_price,
                    sale_mode=sale_mode,
                    traffic_gb_for_payment=traffic_gb_for_payment,
                    default_currency_code=default_currency_code,
                ),
                settings=settings,
                payment_payload=payment_payload,
                method=method,
                pricing_context=checkout_pricing_context,
            )
        except CheckoutBundleError as exc:
            return _json_error(400, exc.code, exc.message)
        price = bundled_quote.price
        stars_price = bundled_quote.stars_price
        if payment_payload.gift:
            from .gift_checkout import attach_gift_delivery

            checkout_bundle = attach_gift_delivery(
                checkout_bundle, payment_payload, settings.TRIAL_DAYS_STRATEGY
            )
        admin_ids = {int(item) for item in (settings.ADMIN_IDS or [])}
        is_admin = bool(db_user.telegram_id and int(db_user.telegram_id) in admin_ids)
        return await _create_subscription_payment(
            request=request,
            session=session,
            user_id=user_id,
            method=method,
            months=payment_units,
            price=float(price or 0),
            stars_price=stars_price,
            currency=default_currency_code,
            lang=lang,
            sale_mode=sale_mode,
            traffic_gb=traffic_gb_for_payment,
            is_admin=is_admin,
            hwid_quote=hwid_quote,
            promo_code=payment_payload.promo_code,
            entitlement_context_snapshot=quoted_entitlement_context_snapshot,
            balance_source=payment_payload.balance_source,
            use_partner_balance=payment_payload.use_partner_balance,
            checkout_bundle_snapshot=checkout_bundle.snapshot,
            checkout_bundle_hash=checkout_bundle.digest,
        )


async def _create_subscription_payment(
    *,
    request: web.Request,
    session: AsyncSession,
    user_id: int,
    method: str,
    months: Any,
    price: float,
    stars_price: int | None,
    lang: str,
    currency: str | None = None,
    sale_mode: str = "subscription",
    traffic_gb: float | None = None,
    is_admin: bool = False,
    hwid_quote: dict[str, Any] | None = None,
    promo_code: str | None = None,
    promo_code_id: int | None = None,
    promo_result: CheckoutPromoResult | None = None,
    tariff_change_quote_snapshot: str | None = None,
    entitlement_context_snapshot: str | None = None,
    balance_source: Literal["user", "partner"] | None = None,
    use_partner_balance: bool = False,
    checkout_bundle_snapshot: str | None = None,
    checkout_bundle_hash: str | None = None,
) -> web.Response:
    settings: Settings = get_settings(request)
    checkout_grants = checkout_addon_grants(checkout_bundle_snapshot)
    selected_balance_source = balance_source or ("partner" if use_partner_balance else None)
    payment_currency = (currency or default_payment_currency_code_for_settings(settings)).upper()
    sale_mode = str(sale_mode or "subscription")
    try:
        fixed_days = checkout_duration_days(settings, months, sale_mode)
    except ValueError:
        return _json_error(400, "invalid_plan", "Subscription end date is out of range")
    if fixed_days is not None:
        sale_mode = with_period_days(sale_mode, fixed_days)
    if (
        entitlement_context_snapshot is None
        and _sale_mode_base(sale_mode) != "balance_topup"
        and not is_gift_sale(sale_mode)
    ):
        try:
            entitlement_context_snapshot = await snapshot_current_entitlement_context(
                session,
                user_id=int(user_id),
                sale_mode=sale_mode,
            )
        except EntitlementContextError as exc:
            logger.warning(
                "Rejecting one-time checkout for stale entitlement context: "
                "user_id=%s sale_mode=%s reason=%s",
                user_id,
                sale_mode,
                exc,
            )
            return _json_error(
                409,
                "entitlement_context_changed",
                "The active subscription no longer matches this purchase",
            )
    if _sale_mode_base(sale_mode) in {"subscription", "tariff_upgrade"} and not is_gift_sale(
        sale_mode
    ):
        active_subscription = await subscription_dal.get_active_subscription_by_user_id(
            session,
            int(user_id),
        )
        if _active_tribute_recurrence(active_subscription):
            return _json_error(
                409,
                "tribute_recurring_conflict",
                "Cancel the active Tribute subscription before changing or replacing the tariff",
            )
        if fixed_days is not None:
            try:
                period_start = datetime.now(UTC)
                if (
                    active_subscription is not None
                    and active_subscription.end_date is not None
                    and not (
                        _subscription_is_trial(active_subscription)
                        and checkout_grants.trial_days_strategy == TRIAL_DAYS_START_FROM_PAYMENT
                    )
                ):
                    period_start = max(
                        period_start,
                        active_subscription.end_date.replace(tzinfo=UTC)
                        if active_subscription.end_date.tzinfo is None
                        else active_subscription.end_date,
                    )
                add_period_days(period_start, fixed_days)
            except (ValueError, OverflowError):
                return _json_error(400, "invalid_plan", "Subscription end date is out of range")

    description = (
        "Balance top-up"
        if _sale_mode_base(sale_mode) == "balance_topup"
        else _localized_payment_description(
            i18n=get_i18n(request),
            lang=lang,
            units=months,
            sale_mode=sale_mode,
            traffic_gb=traffic_gb,
        )
    )

    from bot.payment_providers import get_provider_spec

    provider_spec = get_provider_spec(method)
    if provider_spec and provider_spec.create_webapp_payment:
        if not provider_spec.is_visible_for_user(settings, request.app, is_admin=is_admin):
            logger.warning(
                "WebApp payment method unavailable: method=%s enabled=%s configured=%s",
                method,
                provider_spec.is_effectively_enabled(settings),
                provider_spec.is_service_configured(request.app),
            )
            return _json_error(400, "payment_unavailable", "Payment method unavailable")
        if not provider_spec.is_usable_for_payment_currency(settings, payment_currency):
            logger.warning(
                "WebApp payment method does not support currency: method=%s currency=%s",
                method,
                payment_currency,
            )
            return _json_error(
                400,
                "unsupported_currency",
                "Payment method does not support this currency",
            )
        if not provider_spec.is_usable_for_payment_context(settings, months, sale_mode):
            logger.warning(
                "WebApp payment method does not support checkout context: "
                "method=%s months=%s sale_mode=%s",
                method,
                months,
                sale_mode,
            )
            return _json_error(
                400,
                "payment_unavailable",
                "Payment method unavailable for this plan",
            )
        if checkout_grants.has_addons and not provider_spec.is_checkout_addon_supported(
            settings,
            months,
            sale_mode,
        ):
            return _json_error(
                400,
                "checkout_addons_payment_unavailable",
                "Payment method does not support subscription add-ons",
            )
        payment_context = WebAppPaymentContext(
            duration_days=checkout_duration_days(settings, months, sale_mode),
            subscription_terms_snapshot=freeze_subscription_terms(settings, sale_mode),
            request=request,
            session=session,
            user_id=user_id,
            method=method,
            months=months,
            price=price,
            stars_price=stars_price,
            currency=payment_currency,
            description=description,
            sale_mode=sale_mode,
            traffic_gb=traffic_gb,
            hwid_device_count=hwid_quote.get("device_count") if hwid_quote else None,
            hwid_valid_from=hwid_quote.get("valid_from") if hwid_quote else None,
            hwid_valid_until=hwid_quote.get("valid_until") if hwid_quote else None,
            hwid_pricing_period_months=(
                hwid_quote.get("pricing_period_months") if hwid_quote else None
            ),
            hwid_pricing_period_days=hwid_quote.get("pricing_period_days") if hwid_quote else None,
            hwid_proration_ratio=hwid_quote.get("proration_ratio") if hwid_quote else None,
            hwid_full_price=hwid_quote.get("full_price") if hwid_quote else None,
            hwid_traffic_bonus_bytes=(
                hwid_quote.get("traffic_bonus_bytes") if hwid_quote else None
            ),
            promo_code_id=promo_code_id,
            tariff_change_quote_snapshot=tariff_change_quote_snapshot,
            entitlement_context_snapshot=entitlement_context_snapshot,
            checkout_bundle_snapshot=checkout_bundle_snapshot,
            checkout_bundle_hash=checkout_bundle_hash,
        )
        requested_promo_code = str(promo_code or "").strip()
        if (
            provider_spec.reuse_webapp_payment
            and selected_balance_source != "user"
            and (
                requested_promo_code
                or promo_code_id is not None
                or selected_balance_source == "partner"
            )
        ):
            reusable_response = await reuse_checkout_if_available(
                payment_context,
                provider_spec,
                match_reservations=True,
                requested_promo_code=requested_promo_code,
                preserve_promo_code_case=bool(
                    settings.MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED
                ),
                requested_partner_balance=selected_balance_source == "partner",
            )
            if reusable_response is not None:
                return reusable_response
        if promo_result is None and requested_promo_code:
            promo_result, promo_error = await _resolve_checkout_promo(
                session=session,
                settings=settings,
                user_id=user_id,
                code_input=requested_promo_code,
                promo_code_id=promo_code_id,
                sale_mode=sale_mode,
                payment_units=months,
                traffic_gb=traffic_gb,
                method=method,
                base_amount=price,
                base_stars=stars_price,
                lock_for_checkout=True,
            )
            if promo_error is not None:
                return _json_error(promo_error.status, promo_error.code, promo_error.message)
        if promo_result is not None:
            if fixed_days is not None:
                try:
                    bonus_days = promo_result.effects.bonus_days + multiplied_bonus_days(
                        fixed_days, promo_result.effects.duration_multiplier
                    )
                    add_period_days(period_start, fixed_days + bonus_days)
                except ValueError:
                    return _json_error(400, "invalid_plan", "Subscription end date is out of range")
            promo_code_id = promo_result.promo_code_id
            if method == "stars":
                stars_price = promo_result.effective_stars
            else:
                price = promo_result.effective_amount
        promo_support_error = _payment_promo_error(
            settings=settings,
            method=method,
            months=months,
            sale_mode=sale_mode,
            promo_result=promo_result,
        )
        if promo_support_error is not None:
            return _json_error(
                promo_support_error.status,
                promo_support_error.code,
                promo_support_error.message,
            )
        payment_context = replace(
            payment_context,
            price=price,
            stars_price=stars_price,
            promo_code_id=promo_code_id,
            promo_effect_summary=promo_result.effect_summary if promo_result else None,
            promo_bonus_days=promo_result.effects.bonus_days if promo_result else None,
            promo_regular_traffic_gb=(
                promo_result.effects.regular_traffic_gb if promo_result else None
            ),
            promo_premium_traffic_gb=(
                promo_result.effects.premium_traffic_gb if promo_result else None
            ),
            promo_discount_percent=promo_result.effects.discount_percent if promo_result else None,
            promo_duration_multiplier=(
                promo_result.effects.duration_multiplier
                if promo_result and promo_result.effects.duration_multiplier != 1.0
                else None
            ),
            promo_traffic_multiplier=(
                promo_result.effects.traffic_multiplier
                if promo_result and promo_result.effects.traffic_multiplier != 1.0
                else None
            ),
            promo_applies_to=promo_result.effects.applies_to if promo_result else None,
            promo_min_subscription_months=promo_result.effects.min_subscription_months
            if promo_result
            else None,
            promo_min_traffic_gb=promo_result.effects.min_traffic_gb if promo_result else None,
            checkout_discount_amount=promo_result.discount_amount if promo_result else None,
            checkout_charged_months=promo_result.charged_months if promo_result else None,
            checkout_charged_gb=promo_result.charged_gb if promo_result else None,
            checkout_quoted_at=promo_result.quoted_at if promo_result else None,
            **balance_checkout_context_fields(
                None,
                promo_base_amount=promo_result.base_amount if promo_result else None,
            ),
        )
        if promo_result is not None and method != "stars" and price <= 0:
            return await create_fully_discounted_payment(
                request=request,
                payment_context=payment_context,
            )
        try:
            balance_allocation = await allocate_checkout_balance(
                balance_source=selected_balance_source,
                settings=settings,
                session=session,
                user_id=user_id,
                payment_currency=payment_currency,
                checkout_total=price,
                provider_spec=provider_spec,
                months=months,
                sale_mode=sale_mode,
            )
        except (PartnerError, UserBalanceError) as exc:
            return _json_error(exc.status, exc.code, exc.message or str(exc))
        if balance_allocation is not None:
            price = balance_allocation.external_amount
        payment_context = replace(
            payment_context,
            price=price,
            **balance_checkout_context_fields(
                balance_allocation,
                promo_base_amount=promo_result.base_amount if promo_result else None,
            ),
        )
        if balance_allocation is not None and balance_allocation.external_minor == 0:
            return await create_fully_balance_funded_payment(
                request=request,
                payment_context=payment_context,
                allocation=balance_allocation,
            )
        if not provider_spec.is_usable_for_payment_amount(
            settings,
            payment_currency,
            price,
        ):
            logger.warning(
                "WebApp payment method does not support amount: method=%s amount=%s currency=%s",
                method,
                price,
                payment_currency,
            )
            return _json_error(
                400,
                "payment_amount_below_minimum",
                "Payment amount is below the provider minimum",
            )
        if provider_spec.reuse_webapp_payment and selected_balance_source is None:
            reusable_response = await reuse_checkout_if_available(
                payment_context,
                provider_spec,
            )
            if reusable_response is not None:
                return reusable_response
        return await provider_spec.create_webapp_payment(payment_context)

    return _json_error(400, "payment_unavailable", "Payment method unavailable")
