from __future__ import annotations

import logging
from typing import Literal, TypedDict

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.context import (
    get_bot,
    get_i18n,
    get_referral_service,
    get_settings,
    get_subscription_service,
)
from bot.payment_providers.base import PaymentProviderSpec, WebAppPaymentContext
from bot.payment_providers.shared import create_webapp_payment_record
from bot.payment_providers.shared.success import (
    PaymentSuccessRequest,
    finalize_successful_payment,
)
from bot.services.partner_checkout_balance import (
    PartnerCheckoutBalanceAllocation,
    PartnerCheckoutBalanceService,
    provider_minimum_amount,
)
from bot.services.partner_common import PartnerError
from bot.services.user_balance_service import (
    UserBalanceAllocation,
    UserBalanceError,
    UserBalanceService,
)
from config.settings import Settings
from db.dal import payment_dal

from .common import _json_error
from .response_helpers import json_response

logger = logging.getLogger(__name__)


class PartnerCheckoutContextFields(TypedDict):
    checkout_base_amount: float | None
    checkout_total_amount: float | None
    partner_balance_partner_id: int | None
    partner_balance_amount_minor: int | None
    partner_balance_currency_scale: int | None


class BalanceCheckoutContextFields(PartnerCheckoutContextFields):
    user_balance_user_id: int | None
    user_balance_amount_minor: int | None
    user_balance_currency_scale: int | None


type BalanceCheckoutAllocation = PartnerCheckoutBalanceAllocation | UserBalanceAllocation


async def allocate_partner_checkout_balance(
    *,
    requested: bool,
    settings: Settings,
    session: AsyncSession,
    user_id: int,
    payment_currency: str,
    checkout_total: float,
    provider_spec: PaymentProviderSpec,
    months: object,
    sale_mode: str,
) -> PartnerCheckoutBalanceAllocation | None:
    if not requested:
        return None
    if provider_spec.price_source == "stars" or provider_spec.is_price_managed_externally(
        settings,
        months,
        sale_mode,
    ):
        raise PartnerError(
            "partner_balance_payment_not_supported",
            409,
            "Partner balance cannot be combined with this payment method",
        )
    return await PartnerCheckoutBalanceService(settings).quote(
        session,
        user_id=user_id,
        currency=payment_currency,
        checkout_total=checkout_total,
        minimum_external_amount=provider_minimum_amount(
            provider_spec.payment_minimum(settings, payment_currency)
        ),
    )


async def allocate_checkout_balance(
    *,
    balance_source: Literal["user", "partner"] | None,
    settings: Settings,
    session: AsyncSession,
    user_id: int,
    payment_currency: str,
    checkout_total: float,
    provider_spec: PaymentProviderSpec,
    months: object,
    sale_mode: str,
) -> BalanceCheckoutAllocation | None:
    if balance_source is None:
        return None
    if balance_source == "partner":
        return await allocate_partner_checkout_balance(
            requested=True,
            settings=settings,
            session=session,
            user_id=user_id,
            payment_currency=payment_currency,
            checkout_total=checkout_total,
            provider_spec=provider_spec,
            months=months,
            sale_mode=sale_mode,
        )
    if provider_spec.price_source == "stars" or provider_spec.is_price_managed_externally(
        settings,
        months,
        sale_mode,
    ):
        raise UserBalanceError(
            "user_balance_payment_not_supported",
            409,
            "User balance cannot be combined with this payment method",
        )
    return await UserBalanceService(settings).quote(
        session,
        user_id=user_id,
        currency=payment_currency,
        checkout_total=checkout_total,
        minimum_external_amount=provider_minimum_amount(
            provider_spec.payment_minimum(settings, payment_currency)
        ),
    )


def partner_checkout_context_fields(
    allocation: PartnerCheckoutBalanceAllocation | None,
    *,
    promo_base_amount: float | None,
) -> PartnerCheckoutContextFields:
    return {
        "checkout_base_amount": (
            promo_base_amount
            if promo_base_amount is not None
            else (allocation.checkout_total_amount if allocation else None)
        ),
        "checkout_total_amount": allocation.checkout_total_amount if allocation else None,
        "partner_balance_partner_id": allocation.partner_id if allocation else None,
        "partner_balance_amount_minor": allocation.applied_minor if allocation else None,
        "partner_balance_currency_scale": allocation.currency_scale if allocation else None,
    }


def balance_checkout_context_fields(
    allocation: BalanceCheckoutAllocation | None,
    *,
    promo_base_amount: float | None,
) -> BalanceCheckoutContextFields:
    partner_allocation = (
        allocation if isinstance(allocation, PartnerCheckoutBalanceAllocation) else None
    )
    user_allocation = allocation if isinstance(allocation, UserBalanceAllocation) else None
    return {
        "checkout_base_amount": (
            promo_base_amount
            if promo_base_amount is not None
            else (allocation.checkout_total_amount if allocation else None)
        ),
        "checkout_total_amount": allocation.checkout_total_amount if allocation else None,
        "user_balance_user_id": user_allocation.user_id if user_allocation else None,
        "user_balance_amount_minor": user_allocation.applied_minor if user_allocation else None,
        "user_balance_currency_scale": (
            user_allocation.currency_scale if user_allocation else None
        ),
        "partner_balance_partner_id": (
            partner_allocation.partner_id if partner_allocation else None
        ),
        "partner_balance_amount_minor": (
            partner_allocation.applied_minor if partner_allocation else None
        ),
        "partner_balance_currency_scale": (
            partner_allocation.currency_scale if partner_allocation else None
        ),
    }


async def create_fully_partner_funded_payment(
    *,
    request: web.Request,
    payment_context: WebAppPaymentContext,
    allocation: PartnerCheckoutBalanceAllocation,
) -> web.Response:
    try:
        payment = await create_webapp_payment_record(
            payment_context,
            amount=allocation.checkout_total_amount,
            currency=allocation.currency,
            status="succeeded_pending_finalization",
            provider="partner_balance",
            funding_source="internal_partner_balance",
        )
    except PartnerError as exc:
        await payment_context.session.rollback()
        return _json_error(exc.status, exc.code, exc.message or str(exc))
    except Exception:
        await payment_context.session.rollback()
        logger.exception(
            "Failed to reserve partner balance for fully funded checkout: user_id=%s",
            payment_context.user_id,
        )
        return _json_error(409, "partner_balance_checkout_failed", "Checkout could not be created")

    referral_service = get_referral_service(request)
    if referral_service is None:
        await payment_dal.update_payment_status_by_db_id(
            payment_context.session,
            int(payment.payment_id),
            "activation_failed",
        )
        await payment_context.session.commit()
        return _json_error(503, "payment_service_unavailable", "Payment service unavailable")

    try:
        outcome = await finalize_successful_payment(
            PaymentSuccessRequest(
                bot=get_bot(request),
                settings=get_settings(request),
                i18n=get_i18n(request),
                session=payment_context.session,
                subscription_service=get_subscription_service(request),
                referral_service=referral_service,
                payment=payment,
                user_id=payment_context.user_id,
                amount=allocation.checkout_total_amount,
                currency=allocation.currency,
                sale_mode=payment_context.sale_mode,
                months=payment_context.months,
                traffic_amount=payment_context.traffic_gb,
                provider_subscription="partner_balance",
                provider_notification="partner_balance",
                skip_referral_bonus=True,
            )
        )
    except Exception:
        await payment_context.session.rollback()
        logger.exception(
            "Fully partner-funded checkout finalization crashed for payment %s",
            payment.payment_id,
        )
        try:
            await payment_dal.update_payment_status_by_db_id(
                payment_context.session,
                int(payment.payment_id),
                "activation_failed",
            )
            await payment_context.session.commit()
        except Exception:
            await payment_context.session.rollback()
            logger.exception(
                "Failed to release partner balance after checkout finalization crash for "
                "payment %s; the reconciler will retry it",
                payment.payment_id,
            )
        return _json_error(
            409,
            "subscription_activation_failed",
            "Purchase activation failed",
        )
    if outcome is None:
        current = await payment_dal.get_payment_by_db_id(
            payment_context.session,
            int(payment.payment_id),
        )
        if current is None or str(current.status).strip().lower() != "succeeded":
            return _json_error(
                409,
                "subscription_activation_failed",
                "Purchase activation failed",
            )
    return json_response(
        {
            "ok": True,
            "action": "completed",
            "payment_id": int(payment.payment_id),
            "status": "succeeded",
            "paid": True,
        }
    )


async def create_fully_balance_funded_payment(
    *,
    request: web.Request,
    payment_context: WebAppPaymentContext,
    allocation: BalanceCheckoutAllocation,
) -> web.Response:
    if isinstance(allocation, PartnerCheckoutBalanceAllocation):
        return await create_fully_partner_funded_payment(
            request=request,
            payment_context=payment_context,
            allocation=allocation,
        )
    try:
        payment = await create_webapp_payment_record(
            payment_context,
            amount=allocation.checkout_total_amount,
            currency=allocation.currency,
            status="succeeded_pending_finalization",
            provider="user_balance",
            funding_source="internal_user_balance",
        )
    except UserBalanceError as exc:
        await payment_context.session.rollback()
        return _json_error(exc.status, exc.code, exc.message or str(exc))
    except Exception:
        await payment_context.session.rollback()
        logger.exception(
            "Failed to reserve user balance for fully funded checkout: user_id=%s",
            payment_context.user_id,
        )
        return _json_error(409, "user_balance_checkout_failed", "Checkout could not be created")

    referral_service = get_referral_service(request)
    if referral_service is None:
        await payment_dal.update_payment_status_by_db_id(
            payment_context.session,
            int(payment.payment_id),
            "activation_failed",
        )
        await payment_context.session.commit()
        return _json_error(503, "payment_service_unavailable", "Payment service unavailable")
    try:
        outcome = await finalize_successful_payment(
            PaymentSuccessRequest(
                bot=get_bot(request),
                settings=get_settings(request),
                i18n=get_i18n(request),
                session=payment_context.session,
                subscription_service=get_subscription_service(request),
                referral_service=referral_service,
                payment=payment,
                user_id=payment_context.user_id,
                amount=allocation.checkout_total_amount,
                currency=allocation.currency,
                sale_mode=payment_context.sale_mode,
                months=payment_context.months,
                traffic_amount=payment_context.traffic_gb,
                provider_subscription="user_balance",
                provider_notification="user_balance",
                skip_referral_bonus=True,
            )
        )
    except Exception:
        await payment_context.session.rollback()
        logger.exception(
            "Fully user-balance-funded checkout finalization crashed for payment %s",
            payment.payment_id,
        )
        try:
            await payment_dal.update_payment_status_by_db_id(
                payment_context.session,
                int(payment.payment_id),
                "activation_failed",
            )
            await payment_context.session.commit()
        except Exception:
            await payment_context.session.rollback()
            logger.exception(
                "Failed to release user balance after checkout finalization crash for payment %s",
                payment.payment_id,
            )
        return _json_error(409, "subscription_activation_failed", "Purchase activation failed")
    if outcome is None:
        current = await payment_dal.get_payment_by_db_id(
            payment_context.session,
            int(payment.payment_id),
        )
        if current is None or str(current.status).strip().lower() != "succeeded":
            return _json_error(409, "subscription_activation_failed", "Purchase activation failed")
    return json_response(
        {
            "ok": True,
            "action": "completed",
            "payment_id": int(payment.payment_id),
            "status": "succeeded",
            "paid": True,
        }
    )
