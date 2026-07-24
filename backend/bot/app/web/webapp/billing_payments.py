import logging
from dataclasses import dataclass
from typing import Any

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
from bot.app.web.webapp.auth import _require_user_id
from bot.app.web.webapp.common import (
    _json_error,
    _parse_model_payload,
)
from bot.app.web.webapp.payloads import (
    WebAppPaymentCreatePayload,
    WebAppPromoQuotePayload,
)
from bot.middlewares.i18n import JsonI18n, get_i18n_instance
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings
from config.tariffs_config import (
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
    payment_currency_code,
)
from db.dal import subscription_dal, user_dal

from .billing_checkout_adjustments import (
    CheckoutPromoError,
    CheckoutPromoResult,
    _resolve_checkout_promo,
)
from .billing_common import _parse_positive_int_units
from .billing_sale_modes import (
    _sale_mode_base,
    _sale_mode_is_hwid_devices,
    _sale_mode_is_traffic,
    _sale_mode_tariff_key,
)
from .common import (
    _resolve_numeric_option_key,
)
from .response_helpers import json_response

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BasePaymentQuote:
    payment_units: int | float
    price: float
    stars_price: int | None
    sale_mode: str
    traffic_gb_for_payment: float | None
    default_currency_code: str


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


def _payment_amount_error(
    *,
    request: web.Request,
    settings: Settings,
    method: str,
    currency: str,
    amount: float,
    is_admin: bool = False,
) -> CheckoutPromoError | None:
    from bot.payment_providers import get_provider_spec

    provider_spec = get_provider_spec(method)
    if provider_spec is None or not provider_spec.create_webapp_payment:
        return CheckoutPromoError(400, "payment_unavailable", "Payment method unavailable")
    if not provider_spec.is_usable_for_payment_amount(settings, currency, amount):
        return CheckoutPromoError(
            400,
            "payment_amount_below_minimum",
            "Payment amount is below the provider minimum",
        )
    if not provider_spec.is_visible_for_user(settings, request.app, is_admin=is_admin):
        return CheckoutPromoError(400, "payment_unavailable", "Payment method unavailable")
    return None


async def quote_promo_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    payment_payload = await _parse_model_payload(request, WebAppPromoQuotePayload)
    method = str(payment_payload.method or "").strip().lower()
    settings: Settings = get_settings(request)
    subscription_service: SubscriptionService = get_subscription_service(request)
    async_session_factory: sessionmaker = get_session_factory(request)

    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        admin_ids = {int(item) for item in (settings.ADMIN_IDS or [])}
        is_admin = bool(db_user.telegram_id and int(db_user.telegram_id) in admin_ids)

        base_quote, quote_error = await _resolve_base_payment_quote(
            request=request,
            session=session,
            user_id=user_id,
            db_user=db_user,
            payment_payload=payment_payload,
            method=method,
            settings=settings,
            subscription_service=subscription_service,
        )
        if quote_error is not None:
            return quote_error
        if base_quote is None:
            return _json_error(400, "invalid_plan", "Plan is not available")

        promo_result, promo_error = await _resolve_checkout_promo(
            session=session,
            settings=settings,
            user_id=user_id,
            code_input=payment_payload.promo_code,
            sale_mode=base_quote.sale_mode,
            payment_units=base_quote.payment_units,
            traffic_gb=base_quote.traffic_gb_for_payment,
            method=method,
            base_amount=base_quote.price,
            base_stars=base_quote.stars_price,
        )
        if promo_error is not None or promo_result is None:
            reason = promo_error.message if promo_error is not None else "Code does not apply"
            reason_key = (
                promo_error.code if promo_error is not None else "promo_code_not_applicable"
            )
            return json_response(
                {
                    "ok": True,
                    "valid": False,
                    "reason": reason,
                    "reason_key": reason_key,
                }
            )

        payment_error = _payment_amount_error(
            request=request,
            settings=settings,
            method=method,
            currency=base_quote.default_currency_code,
            amount=promo_result.effective_amount,
            is_admin=is_admin,
        )
        if payment_error is not None:
            return json_response(
                {
                    "ok": True,
                    "valid": False,
                    "payable": False,
                    "reason": payment_error.message,
                    "reason_key": payment_error.code,
                }
            )

        return json_response(
            {
                "ok": True,
                "valid": True,
                "payable": True,
                "code": promo_result.code,
                "promo_code_id": promo_result.promo_code_id,
                "currency": base_quote.default_currency_code,
                "discount_percent": promo_result.discount_percent,
                "base_amount": base_quote.price,
                "effective_amount": promo_result.effective_amount,
                "base_stars": base_quote.stars_price,
                "effective_stars": promo_result.effective_stars,
                "discount_amount": promo_result.discount_amount,
                "effect_summary": promo_result.effect_summary,
                "applies_to": promo_result.effects.applies_to,
                "min_subscription_months": promo_result.effects.min_subscription_months,
                "min_traffic_gb": promo_result.effects.min_traffic_gb,
            }
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
                months = int(float(payment_payload.months))
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
            months = int(float(payment_payload.months))
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

    if _sale_mode_is_hwid_devices(sale_mode):
        sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, db_user.panel_user_uuid
        )
        sale_tariff_key = _sale_mode_tariff_key(sale_mode)
        if not sub or not sub.tariff_key or sub.tariff_key != sale_tariff_key:
            return None, _json_error(
                400, "subscription_required", "Active tariff subscription is required"
            )
        try:
            active_tariff = tariffs_config.require(sub.tariff_key) if tariffs_config else None
        except Exception:
            active_tariff = None
        if not active_tariff or active_tariff.billing_model != "period":
            return None, _json_error(400, "invalid_plan", "Device top-up is not available")
        currency = "stars" if method == "stars" else default_currency
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

    return (
        BasePaymentQuote(
            payment_units=payment_units,
            price=float(price or 0),
            stars_price=stars_price,
            sale_mode=sale_mode,
            traffic_gb_for_payment=traffic_gb_for_payment,
            default_currency_code=default_currency_code,
        ),
        None,
    )


async def create_payment_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    rate_limit_response = await _enforce_webapp_rate_limit(
        request,
        user_id=user_id,
        action="payments_create",
    )
    if rate_limit_response:
        return rate_limit_response

    payment_payload = await _parse_model_payload(request, WebAppPaymentCreatePayload)
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
    requested_sale_mode = _sale_mode_base(str(payment_payload.sale_mode or ""))
    payment_units: int | float

    if tariffs_config and requested_sale_mode == "hwid_devices_renewal":
        return _json_error(400, "invalid_plan", "Device renewal is part of subscription renewal")
    if tariffs_config and requested_sale_mode in {
        "hwid_device",
        "hwid_devices",
    }:
        tariff_key = str(payment_payload.tariff_key or "").strip()
        if not tariff_key:
            return _json_error(400, "invalid_plan", "Tariff is not selected")
        try:
            tariff = tariffs_config.require(tariff_key)
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
            tariff = tariffs_config.require(tariff_key)
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
            tariff = tariffs_config.require(tariff_key)
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
                months = int(float(payment_payload.months))
            except (TypeError, ValueError):
                return _json_error(400, "invalid_plan", "Invalid subscription period")
            if months not in tariff.enabled_periods:
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
            months = int(float(payment_payload.months))
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

    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        lang = db_user.language_code or settings.DEFAULT_LANGUAGE
        if _sale_mode_is_hwid_devices(sale_mode):
            sub = await subscription_dal.get_active_subscription_by_user_id(
                session, user_id, db_user.panel_user_uuid
            )
            sale_tariff_key = _sale_mode_tariff_key(sale_mode)
            if not sub or not sub.tariff_key or sub.tariff_key != sale_tariff_key:
                return _json_error(
                    400, "subscription_required", "Active tariff subscription is required"
                )
            try:
                active_tariff = tariffs_config.require(sub.tariff_key) if tariffs_config else None
            except Exception:
                active_tariff = None
            if not active_tariff or active_tariff.billing_model != "period":
                return _json_error(400, "invalid_plan", "Device top-up is not available")
            currency = "stars" if method == "stars" else default_currency
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
                if method == "stars":
                    stars_price = int(stars_price or 0) + int(hwid_quote["price"])
                else:
                    price = float(price or 0) + float(hwid_quote["price"])
                    stars_price = None
        admin_ids = {int(item) for item in (settings.ADMIN_IDS or [])}
        is_admin = bool(db_user.telegram_id and int(db_user.telegram_id) in admin_ids)
        base_price = float(price or 0)
        base_stars_price = stars_price
        promo_result, promo_error = await _resolve_checkout_promo(
            session=session,
            settings=settings,
            user_id=user_id,
            code_input=payment_payload.promo_code,
            sale_mode=sale_mode,
            payment_units=payment_units,
            traffic_gb=traffic_gb_for_payment,
            method=method,
            base_amount=base_price,
            base_stars=base_stars_price,
            lock_for_checkout=True,
        )
        if promo_error is not None:
            return promo_error.to_response()
        if promo_result is not None:
            if method == "stars":
                stars_price = promo_result.effective_stars
            else:
                price = promo_result.effective_amount
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
            promo_code_id=promo_result.promo_code_id if promo_result else None,
            promo_result=promo_result,
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
    promo_code_id: int | None = None,
    promo_result: CheckoutPromoResult | None = None,
) -> web.Response:
    settings: Settings = get_settings(request)
    payment_currency = (currency or default_payment_currency_code_for_settings(settings)).upper()
    sale_mode = str(sale_mode or "subscription")
    description = _localized_payment_description(
        i18n=get_i18n(request),
        lang=lang,
        units=months,
        sale_mode=sale_mode,
        traffic_gb=traffic_gb,
    )

    from bot.payment_providers import WebAppPaymentContext, get_provider_spec

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
        payment_context = WebAppPaymentContext(
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
            hwid_pricing_period_months=hwid_quote.get("pricing_period_months")
            if hwid_quote
            else None,
            hwid_proration_ratio=hwid_quote.get("proration_ratio") if hwid_quote else None,
            hwid_full_price=hwid_quote.get("full_price") if hwid_quote else None,
            hwid_traffic_bonus_bytes=hwid_quote.get("traffic_bonus_bytes") if hwid_quote else None,
            promo_code_id=promo_code_id,
            promo_effect_summary=promo_result.effect_summary if promo_result else None,
            promo_bonus_days=promo_result.effects.bonus_days if promo_result else None,
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
            checkout_base_amount=promo_result.base_amount if promo_result else None,
            checkout_discount_amount=promo_result.discount_amount if promo_result else None,
            checkout_charged_months=promo_result.charged_months if promo_result else None,
            checkout_charged_gb=promo_result.charged_gb if promo_result else None,
            checkout_quoted_at=promo_result.quoted_at if promo_result else None,
        )
        if provider_spec.reuse_webapp_payment:
            from bot.payment_providers.shared import reusable_webapp_payment_response

            try:
                reusable_response = await reusable_webapp_payment_response(
                    payment_context,
                    provider_spec,
                )
            except Exception:
                logger.exception(
                    "Failed to verify reusable payment: user_id=%s provider=%s",
                    user_id,
                    provider_spec.provider_key,
                )
                reusable_response = None
            if reusable_response is not None:
                return reusable_response
        return await provider_spec.create_webapp_payment(payment_context)

    return _json_error(400, "payment_unavailable", "Payment method unavailable")
