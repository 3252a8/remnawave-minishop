from __future__ import annotations

import json
from typing import Any

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_bot,
    get_i18n,
    get_referral_service,
    get_session_factory,
    get_settings,
    get_subscription_service,
)
from bot.app.web.webapp.billing_checkout_adjustments import _resolve_checkout_promo
from bot.app.web.webapp.billing_payments import _resolve_base_payment_quote
from bot.app.web.webapp.payloads import WebAppPaymentCreatePayload
from bot.payment_providers.shared.entitlement_context import (
    EntitlementContextError,
    snapshot_current_entitlement_context,
)
from bot.payment_providers.shared.success import (
    PaymentSuccessRequest,
    finalize_successful_payment,
)
from bot.services.checkout_promos import checkout_promo_payment_fields
from bot.services.partner_commission_service import PartnerCommissionService
from bot.services.partner_common import PartnerError, amount_to_minor, currency_scale
from config.settings import Settings
from config.subscription_periods import days_to_legacy_months, resolve_period_days
from db.dal import partner_dal, payment_dal, subscription_dal, user_dal


class PartnerBalanceService:
    def __init__(
        self,
        *,
        request: web.Request,
        settings: Settings,
        session_factory: sessionmaker,
    ) -> None:
        self.request = request
        self.settings = settings
        self.session_factory = session_factory

    @classmethod
    def from_request(cls, request: web.Request) -> PartnerBalanceService:
        return cls(
            request=request,
            settings=get_settings(request),
            session_factory=get_session_factory(request),
        )

    @staticmethod
    def _validate_existing_payment(
        payment: Any,
        *,
        user_id: int,
        tariff_key: str,
        months: int,
        duration_days: int | None = None,
    ) -> None:
        stored_tariff = str(getattr(payment, "tariff_key", "") or "").strip()
        stored_months = int(getattr(payment, "subscription_duration_months", 0) or 0)
        if (
            int(payment.user_id) != user_id
            or str(payment.provider) != "partner_balance"
            or stored_tariff != tariff_key.strip()
            or (
                int(getattr(payment, "subscription_duration_days", 0) or 0) != duration_days
                if duration_days is not None
                and getattr(payment, "subscription_duration_days", None) is not None
                else stored_months != months
            )
        ):
            raise PartnerError("idempotency_key_conflict", 409)

    async def _release_failed_payment(self, payment_id: int) -> None:
        async with self.session_factory() as session, session.begin():
            payment = await payment_dal.get_payment_by_db_id(session, payment_id)
            if payment is not None and str(payment.status) == "succeeded":
                return
            await PartnerCommissionService(self.settings).release_subscription_spend(
                session,
                payment_id=payment_id,
            )
            if payment is not None:
                await payment_dal.update_payment_status_by_db_id(
                    session,
                    payment_id,
                    "activation_failed",
                )

    async def renew(
        self,
        *,
        user_id: int,
        tariff_key: str,
        months: int | None,
        duration_days: int | None = None,
        promo_code: str | None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        config = self.settings.partner_settings
        if not config.enabled:
            raise PartnerError("partner_program_disabled", 403)
        if not config.balance_payment_enabled:
            raise PartnerError("partner_balance_payment_disabled", 403)
        try:
            duration_days = resolve_period_days(duration_days=duration_days, months=months)
        except ValueError as exc:
            raise PartnerError("invalid_plan", 400) from exc
        months = days_to_legacy_months(duration_days) or 0
        payment_key = f"partner-balance:{user_id}:{idempotency_key}"
        payment_id: int
        amount: float
        currency: str
        sale_mode: str
        payment_status: str

        async with self.session_factory() as session:
            existing = await payment_dal.get_payment_by_idempotence_key(
                session,
                payment_key,
                fresh=True,
            )
            if existing:
                self._validate_existing_payment(
                    existing,
                    user_id=user_id,
                    tariff_key=tariff_key,
                    months=months,
                    duration_days=duration_days,
                )
                payment_id = int(existing.payment_id)
                amount = float(existing.amount)
                currency = str(existing.currency)
                sale_mode = str(existing.sale_mode or "subscription")
                payment_status = str(existing.status)
            else:
                await session.rollback()
                async with session.begin():
                    db_user = await user_dal.lock_user_by_id(session, user_id)
                    if not db_user or db_user.is_banned:
                        raise PartnerError("access_denied", 403)
                    existing = await payment_dal.get_payment_by_idempotence_key(
                        session,
                        payment_key,
                        fresh=True,
                    )
                    if existing:
                        self._validate_existing_payment(
                            existing,
                            user_id=user_id,
                            tariff_key=tariff_key,
                            months=months,
                            duration_days=duration_days,
                        )
                        payment_id = int(existing.payment_id)
                        amount = float(existing.amount)
                        currency = str(existing.currency)
                        sale_mode = str(existing.sale_mode or "subscription")
                        payment_status = str(existing.status)
                        profile = await partner_dal.get_profile_by_user_id(session, user_id)
                        if not profile:
                            raise PartnerError("partner_not_found", 404)
                    else:
                        profile = await partner_dal.get_profile_by_user_id(
                            session,
                            user_id,
                            for_update=True,
                        )
                    if existing:
                        pass
                    else:
                        if not profile:
                            raise PartnerError("partner_not_found", 404)
                        if profile.status != "active":
                            raise PartnerError("partner_not_active", 403)
                        subscription = (
                            await subscription_dal.get_active_subscription_by_user_id_for_update(
                                session,
                                user_id,
                            )
                        )
                        if not subscription:
                            raise PartnerError("active_subscription_required", 409)
                        if (
                            subscription.tariff_key
                            and str(subscription.tariff_key).strip() != tariff_key.strip()
                        ):
                            raise PartnerError("partner_balance_renewal_only", 409)
                        tariffs = self.settings.tariffs_config
                        if tariffs:
                            try:
                                tariff = tariffs.require(tariff_key)
                            except Exception as exc:
                                raise PartnerError("invalid_plan", 400) from exc
                            if tariff.billing_model != "period":
                                raise PartnerError("partner_balance_period_only", 400)
                        payment_payload = WebAppPaymentCreatePayload(
                            method="partner_balance",
                            duration_days=duration_days,
                            tariff_key=tariff_key,
                            sale_mode="subscription",
                            renew_hwid_devices=False,
                            promo_code=promo_code,
                        )
                        quote, quote_error = await _resolve_base_payment_quote(
                            request=self.request,
                            session=session,
                            user_id=user_id,
                            db_user=db_user,
                            payment_payload=payment_payload,
                            method="partner_balance",
                            settings=self.settings,
                            subscription_service=get_subscription_service(self.request),
                        )
                        if quote_error is not None or quote is None:
                            code = "invalid_plan"
                            if quote_error is not None:
                                try:
                                    payload = json.loads(quote_error.text)
                                    code = str(payload.get("error") or code)
                                except Exception:
                                    pass
                            raise PartnerError(code, quote_error.status if quote_error else 400)
                        if not str(quote.sale_mode).startswith("subscription"):
                            raise PartnerError("partner_balance_period_only", 400)
                        promo_result, promo_error = await _resolve_checkout_promo(
                            session=session,
                            settings=self.settings,
                            user_id=user_id,
                            code_input=promo_code,
                            sale_mode=quote.sale_mode,
                            payment_units=quote.payment_units,
                            traffic_gb=None,
                            method="partner_balance",
                            base_amount=quote.price,
                            base_stars=None,
                            lock_for_checkout=True,
                        )
                        if promo_error:
                            raise PartnerError(
                                promo_error.code, promo_error.status, promo_error.message
                            )
                        amount = promo_result.effective_amount if promo_result else quote.price
                        if amount <= 0:
                            raise PartnerError("partner_balance_zero_amount", 400)
                        currency = quote.default_currency_code.upper()
                        scale = currency_scale(currency)
                        amount_minor = amount_to_minor(amount, scale=scale)
                        if amount_minor <= 0:
                            raise PartnerError("partner_balance_zero_amount", 400)
                        try:
                            entitlement_snapshot = await snapshot_current_entitlement_context(
                                session,
                                user_id=user_id,
                                sale_mode=quote.sale_mode,
                            )
                        except EntitlementContextError as exc:
                            raise PartnerError("entitlement_context_changed", 409) from exc
                        payment = await payment_dal.create_payment_record(
                            session,
                            {
                                "user_id": user_id,
                                "provider": "partner_balance",
                                "funding_source": "internal_partner_balance",
                                "idempotence_key": payment_key,
                                "amount": amount,
                                "currency": currency,
                                "status": "succeeded_pending_finalization",
                                "description": "Subscription renewal from partner balance",
                                "subscription_duration_months": int(quote.payment_units),
                                "sale_mode": quote.sale_mode,
                                "tariff_key": tariff_key,
                                "entitlement_context_snapshot": entitlement_snapshot,
                                **checkout_promo_payment_fields(promo_result),
                            },
                        )
                        payment_id = int(payment.payment_id)
                        sale_mode = str(quote.sale_mode)
                        payment_status = str(payment.status)
                        await PartnerCommissionService(self.settings).reserve_subscription_spend(
                            session,
                            profile=profile,
                            payment_id=payment_id,
                            currency=currency,
                            scale=scale,
                            amount_minor=amount_minor,
                        )

            if payment_status in {"succeeded", "activation_failed"}:
                profile = await partner_dal.get_profile_by_user_id(session, user_id)
                remaining = (
                    await partner_dal.balance_minor(
                        session,
                        int(profile.partner_id),
                        currency,
                    )
                    if profile
                    else 0
                )
                return {
                    "payment_id": payment_id,
                    "status": payment_status,
                    "remaining_balance_minor": remaining,
                }

        try:
            async with self.session_factory() as finalization_session:
                payment = await payment_dal.get_payment_by_db_id(finalization_session, payment_id)
                if not payment:
                    raise PartnerError("payment_not_found", 500)
                referral_service = get_referral_service(self.request)
                if referral_service is None:
                    raise PartnerError("payment_service_unavailable", 503)
                outcome = await finalize_successful_payment(
                    PaymentSuccessRequest(
                        bot=get_bot(self.request),
                        settings=self.settings,
                        i18n=get_i18n(self.request),
                        session=finalization_session,
                        subscription_service=get_subscription_service(self.request),
                        referral_service=referral_service,
                        payment=payment,
                        user_id=user_id,
                        amount=amount,
                        currency=currency,
                        sale_mode=sale_mode,
                        months=int(payment.subscription_duration_months or months),
                        traffic_amount=None,
                        provider_subscription="partner_balance",
                        provider_notification="partner_balance",
                        skip_referral_bonus=True,
                    )
                )
        except Exception:
            await self._release_failed_payment(payment_id)
            raise

        if outcome is None:
            async with self.session_factory() as status_session:
                current_payment = await payment_dal.get_payment_by_db_id(
                    status_session,
                    payment_id,
                )
                if current_payment is not None and str(current_payment.status) == "succeeded":
                    profile = await partner_dal.get_profile_by_user_id(status_session, user_id)
                    remaining = (
                        await partner_dal.balance_minor(
                            status_session,
                            int(profile.partner_id),
                            currency,
                        )
                        if profile
                        else 0
                    )
                    return {
                        "payment_id": payment_id,
                        "status": "succeeded",
                        "remaining_balance_minor": remaining,
                    }
            await self._release_failed_payment(payment_id)
            raise PartnerError("subscription_activation_failed", 409)

        async with self.session_factory() as session:
            profile = await partner_dal.get_profile_by_user_id(session, user_id)
            remaining = await partner_dal.balance_minor(
                session,
                int(profile.partner_id),
                currency,
            )
        return {
            "payment_id": payment_id,
            "status": "succeeded",
            "remaining_balance_minor": remaining,
        }
