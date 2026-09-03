from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.webapp.assets import _get_cached_webapp_settings
from bot.app.web.webapp.common import _json_error
from bot.app.web.webapp.payloads import WebAppPaymentCreatePayload
from bot.middlewares.i18n import JsonI18n, get_i18n_instance
from bot.services.device_topup_availability import resolve_device_topup_availability
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.services.subscription_service_impl.hwid_limits import resolve_hwid_base_limit
from config.settings import Settings
from config.subscription_periods import (
    checkout_duration_days,
    days_to_legacy_months,
    resolve_period_days,
    tariff_period_key,
    with_period_days,
)
from config.tariffs_config import default_currency_key_for_settings, payment_currency_code
from db.dal import subscription_dal, tariff_dal

from .billing_checkout_bundle import (
    CheckoutBundleError,
    CheckoutPricingContext,
    build_checkout_bundle,
    checkout_pricing_windows_from_records,
    normalize_checkout_device_selection,
)
from .billing_common import _parse_positive_int_units, _subscription_is_trial
from .billing_sale_modes import (
    _sale_mode_base,
    _sale_mode_is_hwid_devices,
    _sale_mode_is_traffic,
    _sale_mode_tariff_key,
)
from .common import _resolve_numeric_option_key


@dataclass(frozen=True)
class BasePaymentQuote:
    payment_units: int | float
    price: float
    stars_price: int | None
    sale_mode: str
    traffic_gb_for_payment: float | None
    default_currency_code: str
    checkout_bundle_snapshot: str | None = None
    checkout_bundle_hash: str | None = None
    checkout_addon_amount: float = 0.0
    checkout_addon_stars: int = 0
    duration_days: int | None = None
    period_start: datetime | None = None


def _subscription_effective_hwid_limit(
    settings: Settings,
    subscription: Any,
    tariff: Any,
) -> int:
    configured_base = getattr(tariff, "hwid_device_limit", None)
    if configured_base is None:
        configured_base = settings.USER_HWID_DEVICE_LIMIT
    base_limit = resolve_hwid_base_limit(
        getattr(subscription, "hwid_device_limit", None),
        configured_base,
        is_override=bool(getattr(subscription, "hwid_device_limit_is_override", False)),
    )
    if base_limit is None:
        return 0
    normalized_base = max(0, int(base_limit))
    if normalized_base == 0:
        return 0
    return normalized_base + max(0, int(getattr(subscription, "extra_hwid_devices", 0) or 0))


def _configured_tariff(config: Any, tariff_key: str | None) -> Any | None:
    if config is None or not tariff_key:
        return None
    getter = getattr(config, "get", None)
    if callable(getter):
        return getter(tariff_key)
    require = getattr(config, "require", None)
    if not callable(require):
        return None
    try:
        return require(tariff_key)
    except Exception:
        return None


def _localized_payment_description(
    *,
    i18n: JsonI18n | None,
    lang: str,
    units: object,
    sale_mode: str,
    traffic_gb: float | None = None,
) -> str:
    from bot.payment_providers.shared import build_payment_description, make_translator

    effective_i18n = i18n or get_i18n_instance()
    description_units = (
        traffic_gb if _sale_mode_is_traffic(sale_mode) and traffic_gb is not None else units
    )
    return build_payment_description(
        make_translator(effective_i18n, lang),
        months=description_units,
        sale_mode=sale_mode,
    )


async def _resolve_checkout_pricing_context(
    *,
    session: AsyncSession,
    user_id: int,
    db_user: Any,
    payment_payload: WebAppPaymentCreatePayload,
    settings: Settings,
    sale_mode: str,
) -> tuple[CheckoutPricingContext | None, web.Response | None]:
    tariffs_config = settings.tariffs_config
    if not tariffs_config or _sale_mode_base(sale_mode) != "subscription":
        return None, None

    active_sub = await subscription_dal.get_active_subscription_by_user_id(
        session,
        user_id,
        db_user.panel_user_uuid,
    )
    target_tariff_key = _sale_mode_tariff_key(sale_mode)
    if active_sub is not None and _subscription_is_trial(active_sub):
        default_tariff_key = str(getattr(tariffs_config, "default_tariff", "") or "").strip()
        if target_tariff_key == default_tariff_key:
            return None, None
        return None, _json_error(
            409,
            "tariff_switch_required",
            "Switch the active tariff before purchasing its renewal",
        )
    active_tariff = _configured_tariff(
        tariffs_config,
        getattr(active_sub, "tariff_key", None) if active_sub is not None else None,
    )
    if active_sub is not None and (active_tariff is None or active_tariff.key != target_tariff_key):
        return None, _json_error(
            409,
            "tariff_switch_required",
            "Switch the active tariff before purchasing its renewal",
        )
    if active_sub is None:
        return None, None

    assert active_tariff is not None
    bytes_per_gb = 1024**3
    pricing_now = datetime.now(UTC)
    flexible_records = await tariff_dal.get_active_flexible_traffic_limit_records(
        session,
        subscription_id=int(active_sub.subscription_id),
        at=pricing_now,
    )
    flexible_window_records = await tariff_dal.list_flexible_traffic_limit_records_in_window(
        session,
        subscription_id=int(active_sub.subscription_id),
        valid_from=pricing_now,
        valid_until=active_sub.end_date,
    )
    hwid_summary = await tariff_dal.get_hwid_device_entitlement_summary(
        session,
        subscription_id=int(active_sub.subscription_id),
        at=pricing_now,
        include_future=True,
    )
    next_hwid_window = hwid_summary.get("next_valid_from")
    if next_hwid_window is not None and next_hwid_window.tzinfo is None:
        next_hwid_window = next_hwid_window.replace(tzinfo=UTC)
    active_end_at = active_sub.end_date
    if active_end_at.tzinfo is None:
        active_end_at = active_end_at.replace(tzinfo=UTC)
    selected_device_count = float(
        getattr(getattr(payment_payload, "checkout_addons", None), "device_count", 0) or 0
    )
    if (
        selected_device_count > 0
        and next_hwid_window is not None
        and next_hwid_window < active_end_at
    ):
        return None, _json_error(
            409,
            "checkout_device_schedule_conflict",
            "A future device entitlement is already scheduled for this subscription",
        )
    regular_record = flexible_records.get("traffic")
    premium_record = flexible_records.get("premium_traffic")
    current_regular_limit_gb = (
        float(active_sub.tier_baseline_bytes or active_tariff.monthly_bytes or 0) / bytes_per_gb
    )
    current_premium_limit_gb = (
        float(active_sub.premium_baseline_bytes or active_tariff.premium_monthly_bytes or 0)
        / bytes_per_gb
    )
    current_regular_monthly_price = float(getattr(regular_record, "monthly_amount", 0) or 0)
    current_premium_monthly_price = float(getattr(premium_record, "monthly_amount", 0) or 0)
    current_regular_monthly_stars = int(getattr(regular_record, "monthly_stars_amount", 0) or 0)
    current_premium_monthly_stars = int(getattr(premium_record, "monthly_stars_amount", 0) or 0)
    return (
        CheckoutPricingContext(
            active_subscription_id=int(active_sub.subscription_id),
            active_tariff_key=active_tariff.key,
            active_end_at=active_sub.end_date,
            current_device_count=max(0, int(active_sub.extra_hwid_devices or 0)),
            current_regular_limit_gb=current_regular_limit_gb,
            current_premium_limit_gb=current_premium_limit_gb,
            current_regular_monthly_price=current_regular_monthly_price,
            current_premium_monthly_price=current_premium_monthly_price,
            current_regular_monthly_stars=current_regular_monthly_stars,
            current_premium_monthly_stars=current_premium_monthly_stars,
            regular_windows=checkout_pricing_windows_from_records(
                flexible_window_records,
                kind="traffic",
                start_at=pricing_now,
                end_at=active_sub.end_date,
                fallback_units=current_regular_limit_gb,
                fallback_monthly_price=current_regular_monthly_price,
                fallback_monthly_stars=current_regular_monthly_stars,
            ),
            premium_windows=checkout_pricing_windows_from_records(
                flexible_window_records,
                kind="premium_traffic",
                start_at=pricing_now,
                end_at=active_sub.end_date,
                fallback_units=current_premium_limit_gb,
                fallback_monthly_price=current_premium_monthly_price,
                fallback_monthly_stars=current_premium_monthly_stars,
            ),
        ),
        None,
    )


async def _resolve_base_payment_quote(
    *,
    request: web.Request,
    session: AsyncSession,
    user_id: int,
    db_user: Any,
    payment_payload: WebAppPaymentCreatePayload,
    method: str,
    settings: Settings,
    subscription_service: SubscriptionService,
) -> tuple[BasePaymentQuote | None, web.Response | None]:
    payment_payload = normalize_checkout_device_selection(payment_payload)
    cached = _get_cached_webapp_settings(request)
    tariffs_config = settings.tariffs_config
    default_currency = default_currency_key_for_settings(settings)
    default_currency_code = payment_currency_code(default_currency)
    traffic_mode = bool(settings.traffic_sale_mode)
    sale_mode = "subscription"
    traffic_gb_for_payment: float | None = None
    requested_sale_mode = _sale_mode_base(str(payment_payload.sale_mode or ""))
    price: float | None = None
    stars_price: int | None = None
    payment_units: int | float

    if tariffs_config and requested_sale_mode == "hwid_devices_renewal":
        return None, _json_error(
            400,
            "invalid_plan",
            "Device renewal is part of subscription renewal",
        )
    if tariffs_config and requested_sale_mode in {"hwid_device", "hwid_devices"}:
        if not settings.MY_DEVICES_SECTION_ENABLED:
            return None, _json_error(
                404,
                "device_topup_section_disabled",
                "Devices section is disabled",
            )
        tariff_key = str(payment_payload.tariff_key or "").strip()
        if not tariff_key:
            return None, _json_error(400, "invalid_plan", "Tariff is not selected")
        try:
            tariff = tariffs_config.require(tariff_key)
        except Exception:
            return None, _json_error(400, "invalid_plan", "Tariff is not available")
        if tariff.billing_model != "period":
            return None, _json_error(400, "invalid_plan", "Device top-up is not available")
        device_count = _parse_positive_int_units(
            payment_payload.device_count
            if payment_payload.device_count is not None
            else payment_payload.months
        )
        if device_count is None or not tariff.hwid_device_packages:
            return None, _json_error(400, "invalid_plan", "Device package is not available")
        payment_units = device_count
        sale_mode = f"{requested_sale_mode}@{tariff.key}"
    elif tariffs_config and requested_sale_mode in {"topup", "premium_topup"}:
        tariff_key = str(payment_payload.tariff_key or "").strip()
        if not tariff_key:
            return None, _json_error(400, "invalid_plan", "Tariff is not selected")
        try:
            tariff = tariffs_config.require(tariff_key)
        except Exception:
            return None, _json_error(400, "invalid_plan", "Tariff is not available")
        try:
            traffic_gb = float(
                payment_payload.traffic_gb
                if payment_payload.traffic_gb is not None
                else payment_payload.months
            )
        except (TypeError, ValueError):
            return None, _json_error(400, "invalid_plan", "Invalid traffic package")
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
            return None, _json_error(400, "invalid_plan", "Traffic package is not available")
        if method == "stars" and (stars_price is None or int(stars_price) <= 0):
            return None, _json_error(400, "invalid_plan", "Stars price is not configured")
        payment_units = int(traffic_gb) if float(traffic_gb).is_integer() else traffic_gb
        traffic_gb_for_payment = float(payment_units)
        sale_mode = f"{requested_sale_mode}@{tariff.key}"
    elif tariffs_config:
        tariff_key = str(payment_payload.tariff_key or "").strip()
        if not tariff_key:
            return None, _json_error(400, "invalid_plan", "Tariff is not selected")
        try:
            tariff = tariffs_config.require(tariff_key)
        except Exception:
            return None, _json_error(400, "invalid_plan", "Tariff is not available")
        if tariff.billing_model == "traffic":
            try:
                traffic_gb = float(
                    payment_payload.traffic_gb
                    if payment_payload.traffic_gb is not None
                    else payment_payload.months
                )
            except (TypeError, ValueError):
                return None, _json_error(400, "invalid_plan", "Invalid traffic package")
            if traffic_gb <= 0:
                return None, _json_error(400, "invalid_plan", "Invalid traffic package")
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
                return None, _json_error(400, "invalid_plan", "Traffic package is not available")
            if method == "stars" and (stars_price is None or int(stars_price) <= 0):
                return None, _json_error(400, "invalid_plan", "Stars price is not configured")
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
                return None, _json_error(400, "invalid_plan", "Invalid subscription period")
            if months not in tariff.enabled_periods:
                return None, _json_error(
                    400, "invalid_plan", "Subscription period is not available"
                )
            price = tariff.period_price(months, default_currency)
            stars_price_raw = tariff.period_price(months, "stars")
            stars_price = int(stars_price_raw) if stars_price_raw and stars_price_raw > 0 else None
            if price is None and method != "stars":
                return None, _json_error(
                    400, "invalid_plan", "Subscription period is not available"
                )
            if method == "stars" and (stars_price is None or int(stars_price) <= 0):
                return None, _json_error(400, "invalid_plan", "Stars price is not configured")
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
            return None, _json_error(400, "invalid_plan", "Invalid traffic package")
        if traffic_gb <= 0:
            return None, _json_error(400, "invalid_plan", "Invalid traffic package")
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
            return None, _json_error(400, "invalid_plan", "Traffic package is not available")
        if method == "stars" and (stars_price is None or int(stars_price) <= 0):
            return None, _json_error(400, "invalid_plan", "Stars price is not configured")
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
            return None, _json_error(400, "invalid_plan", "Invalid subscription period")
        price = cached["subscription_options"].get(months)
        stars_price = cached["stars_subscription_options"].get(months)
        if price is None and method != "stars":
            return None, _json_error(400, "invalid_plan", "Subscription period is not available")
        if method == "stars" and (stars_price is None or int(stars_price) <= 0):
            return None, _json_error(400, "invalid_plan", "Stars price is not configured")
        payment_units = months
        sale_mode = "subscription"

    checkout_pricing_context, pricing_context_error = await _resolve_checkout_pricing_context(
        session=session,
        user_id=user_id,
        db_user=db_user,
        payment_payload=payment_payload,
        settings=settings,
        sale_mode=sale_mode,
    )
    if pricing_context_error is not None:
        return None, pricing_context_error

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
        if not availability.allowed or not availability.supports(int(payment_units), currency):
            return None, _json_error(
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
            return None, _json_error(400, "invalid_plan", "Device package is not available")
        if method == "stars":
            stars_price = int(hwid_quote["price"])
            price = 0.0
        else:
            price = float(hwid_quote["price"])
            stars_price = None
    elif _sale_mode_base(sale_mode) == "subscription" and bool(payment_payload.renew_hwid_devices):
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
            if method == "stars":
                stars_price = int(stars_price or 0) + int(hwid_quote["price"])
            else:
                price = float(price or 0) + float(hwid_quote["price"])
                stars_price = None

    try:
        duration_days = checkout_duration_days(settings, payment_units, sale_mode)
    except ValueError:
        return None, _json_error(400, "invalid_plan", "Subscription end date is out of range")
    if duration_days is not None:
        sale_mode = with_period_days(sale_mode, duration_days)

    base_quote = BasePaymentQuote(
        payment_units=payment_units,
        price=float(price or 0),
        stars_price=stars_price,
        sale_mode=sale_mode,
        traffic_gb_for_payment=traffic_gb_for_payment,
        default_currency_code=default_currency_code,
    )
    try:
        quoted, bundle = build_checkout_bundle(
            base_quote,
            settings=settings,
            payment_payload=payment_payload,
            method=method,
            pricing_context=checkout_pricing_context,
        )
    except CheckoutBundleError as exc:
        return None, _json_error(400, exc.code, exc.message)
    return (
        BasePaymentQuote(
            payment_units=quoted.payment_units,
            price=quoted.price,
            stars_price=quoted.stars_price,
            sale_mode=quoted.sale_mode,
            traffic_gb_for_payment=quoted.traffic_gb_for_payment,
            default_currency_code=quoted.default_currency_code,
            checkout_bundle_snapshot=bundle.snapshot,
            checkout_bundle_hash=bundle.digest,
            checkout_addon_amount=bundle.addon_amount,
            checkout_addon_stars=bundle.addon_stars,
            duration_days=duration_days,
            period_start=checkout_pricing_context.active_end_at
            if checkout_pricing_context
            else None,
        ),
        None,
    )
