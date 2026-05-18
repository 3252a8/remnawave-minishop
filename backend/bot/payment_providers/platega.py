import hmac
import json
import logging
from typing import Any, Dict, Optional, Tuple

from aiogram import Bot, F, Router, types
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.services.referral_service import ReferralService
from bot.services.subscription_service import SubscriptionService
from config.settings import Settings
from db.dal import payment_dal

from .base import (
    PaymentProviderSpec,
    ServiceFactoryContext,
    WebAppPaymentContext,
)
from .shared import (
    HttpClientMixin,
    PaymentSuccessRequest,
    build_payment_record_payload,
    create_webapp_payment_record,
    decimal_amounts_equal,
    describe_payment,
    finalize_successful_payment,
    finalize_webapp_link_payment,
    first_value,
    format_decimal_amount,
    format_number_for_payload,
    notify_callback_parse_error,
    notify_payment_record_failure,
    notify_service_unavailable,
    notify_user_payment_failed,
    parse_payment_callback,
    payment_failed,
    payment_record_amounts,
    payment_unavailable,
    post_json_request,
    render_link_or_fail,
    safe_callback_answer,
)

_LOG = "platega"


class PlategaService(HttpClientMixin):
    def __init__(
        self,
        *,
        bot: Bot,
        settings: Settings,
        i18n: JsonI18n,
        async_session_factory: sessionmaker,
        subscription_service: SubscriptionService,
        referral_service: ReferralService,
        default_return_url: str,
    ):
        self.bot = bot
        self.settings = settings
        self.i18n = i18n
        self.async_session_factory = async_session_factory
        self.subscription_service = subscription_service
        self.referral_service = referral_service

        self.base_url = (settings.PLATEGA_BASE_URL or "https://app.platega.io").rstrip("/")
        self.merchant_id = settings.PLATEGA_MERCHANT_ID
        self.secret = settings.PLATEGA_SECRET
        self.payment_method = settings.PLATEGA_PAYMENT_METHOD
        self.sbp_method = settings.platega_sbp_method_resolved
        self.crypto_method = settings.PLATEGA_CRYPTO_METHOD
        self.return_url = settings.PLATEGA_RETURN_URL or f"https://t.me/{default_return_url}"
        self.failed_url = settings.PLATEGA_FAILED_URL or self.return_url

        self._init_http_client(total_timeout=20)
        self._auth_headers = {
            "X-MerchantId": self.merchant_id or "",
            "X-Secret": self.secret or "",
            "Content-Type": "application/json",
        }
        self.configured: bool = bool(settings.PLATEGA_ENABLED and self.merchant_id and self.secret)
        if not self.configured:
            logging.warning(
                "PlategaService initialized but not fully configured. Payments disabled."
            )
        else:
            logging.info(
                "PlategaService configured. SBP button: %s (method=%s), Crypto button: %s (method=%s)",  # noqa: E501
                "ON" if settings.PLATEGA_SBP_ENABLED else "OFF",
                self.sbp_method,
                "ON" if settings.PLATEGA_CRYPTO_ENABLED else "OFF",
                self.crypto_method,
            )

    async def create_transaction(
        self,
        *,
        amount: float,
        currency: Optional[str],
        description: str,
        payload: Optional[str] = None,
        payment_method: Optional[int] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            logging.error("PlategaService is not configured. Cannot create transaction.")
            return False, {"message": "service_not_configured"}

        session = await self._get_session()
        url = f"{self.base_url}/transaction/process"
        currency_code = (currency or self.settings.DEFAULT_CURRENCY_SYMBOL or "RUB").upper()
        method_id = int(payment_method if payment_method is not None else self.payment_method)

        body: Dict[str, Any] = {
            "paymentMethod": method_id,
            "paymentDetails": {"amount": float(amount), "currency": currency_code},
            "description": description,
            "return": self.return_url,
            "failedUrl": self.failed_url,
            "payload": payload,
        }

        # Remove optional keys with falsy values to avoid validation errors
        clean_body = {k: v for k, v in body.items() if v not in (None, "")}
        safe_headers = {
            "X-MerchantId": self._auth_headers.get("X-MerchantId"),
            "X-Secret": "***" if self._auth_headers.get("X-Secret") else "",
            "Content-Type": self._auth_headers.get("Content-Type"),
        }
        logging.info(
            "Platega create_transaction request: url=%s headers=%s body=%s",
            url,
            safe_headers,
            clean_body,
        )

        return await post_json_request(
            session,
            url,
            body=clean_body,
            headers=self._auth_headers,
            log_prefix="Platega create_transaction",
        )

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.Response(status=503, text="platega_disabled")

        try:
            data = await request.json()
        except Exception:
            logging.exception("Platega webhook: failed to parse JSON.")
            return web.Response(status=400, text="bad_request")

        header_merchant = request.headers.get("X-MerchantId")
        header_secret = request.headers.get("X-Secret")
        if not (
            hmac.compare_digest(str(header_merchant or ""), str(self.merchant_id or ""))
            and hmac.compare_digest(str(header_secret or ""), str(self.secret or ""))
        ):
            logging.error("Platega webhook: invalid auth headers")
            return web.Response(status=403, text="forbidden")

        transaction_id = str(data.get("id") or data.get("transactionId") or "").strip()
        status = str(data.get("status") or "").upper()
        amount_raw = data.get("amount")
        currency = data.get("currency") or self.settings.DEFAULT_CURRENCY_SYMBOL or "RUB"

        if not transaction_id or not status:
            logging.error("Platega webhook: missing transaction id or status in payload: %s", data)
            return web.Response(status=400, text="missing_fields")

        async with self.async_session_factory() as session:
            payment = await payment_dal.get_payment_by_provider_payment_id(session, transaction_id)
            if not payment:
                logging.error(
                    "Platega webhook: payment not found for transaction %s", transaction_id
                )
                return web.Response(status=404, text="payment_not_found")

            if payment.status == "succeeded" and status == "CONFIRMED":
                return web.Response(text="ok")

            payment_months = payment.purchased_gb or payment.subscription_duration_months or 1
            sale_mode = payment.sale_mode or (
                "traffic" if self.settings.traffic_sale_mode else "subscription"
            )

            if status == "CONFIRMED":
                if amount_raw is not None:
                    try:
                        if not decimal_amounts_equal(amount_raw, payment.amount):
                            logging.warning(
                                "Platega webhook: amount mismatch for payment %s (expected %s, got %s)",  # noqa: E501
                                payment.payment_id,
                                format_decimal_amount(payment.amount),
                                format_decimal_amount(amount_raw),
                            )
                    except Exception as exc:
                        logging.warning(
                            "Platega webhook: failed to compare amounts for %s: %s",
                            payment.payment_id,
                            exc,
                        )

                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        transaction_id,
                        "succeeded",
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logging.exception(
                        "Platega webhook: failed to mark payment %s as succeeded.", transaction_id
                    )
                    return web.Response(status=500, text="processing_error")

                outcome = await finalize_successful_payment(
                    PaymentSuccessRequest(
                        bot=self.bot,
                        settings=self.settings,
                        i18n=self.i18n,
                        session=session,
                        subscription_service=self.subscription_service,
                        referral_service=self.referral_service,
                        payment=payment,
                        user_id=payment.user_id,
                        amount=float(payment.amount),
                        currency=str(currency),
                        sale_mode=sale_mode,
                        months=payment_months,
                        traffic_amount=float(payment_months),
                        provider_subscription="platega",
                        provider_notification="platega",
                        log_prefix="Platega webhook",
                    )
                )
                if outcome is None:
                    return web.Response(status=500, text="processing_error")
                return web.Response(text="ok")

            if status in {"CANCELED", "CANCELLED", "CHARGEBACKED"}:
                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        transaction_id,
                        "canceled",
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logging.exception(
                        "Platega webhook: failed to cancel payment %s.", transaction_id
                    )
                    return web.Response(status=500, text="processing_error")
                await notify_user_payment_failed(
                    bot=self.bot,
                    settings=self.settings,
                    i18n=self.i18n,
                    session=session,
                    payment=payment,
                )
                return web.Response(text="ok_canceled")

            logging.warning(
                "Platega webhook: unhandled status '%s' for transaction %s", status, transaction_id
            )
            return web.Response(status=202, text="status_ignored")


async def platega_webhook_route(request: web.Request) -> web.Response:
    service: PlategaService = request.app["platega_service"]
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_platega_router")


def _resolve_platega_variant(callback_prefix: str, settings: Settings) -> Optional[Tuple[str, int]]:
    """Map the callback prefix to (variant, payment_method_id) or ``None`` if disabled."""
    if callback_prefix == "pay_platega_crypto":
        if not settings.PLATEGA_CRYPTO_ENABLED:
            return None
        return "crypto", settings.PLATEGA_CRYPTO_METHOD
    if callback_prefix == "pay_platega_sbp":
        if not settings.PLATEGA_SBP_ENABLED:
            return None
        return "sbp", settings.platega_sbp_method_resolved
    # Legacy "pay_platega:" callback — keep working as SBP.
    return "sbp", settings.platega_sbp_method_resolved


@router.callback_query(
    F.data.startswith("pay_platega_sbp:")
    | F.data.startswith("pay_platega_crypto:")
    | F.data.startswith("pay_platega:")
)
async def pay_platega_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    platega_service: PlategaService,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    from .shared import make_translator

    translator = make_translator(i18n, current_lang)

    if not i18n or not callback.message:
        await notify_callback_parse_error(callback, translator)
        return

    callback_prefix, _, _ = (callback.data or "").partition(":")
    variant = _resolve_platega_variant(callback_prefix, settings)
    if variant is None:
        await safe_callback_answer(callback)
        return
    platega_variant, platega_method_id = variant

    if not platega_service or not platega_service.configured:
        logging.error("Platega service is not configured or unavailable.")
        await notify_service_unavailable(callback, translator)
        return

    parts = parse_payment_callback(callback.data or "")
    if not parts:
        logging.error("Invalid pay_platega data in callback: %s", callback.data)
        await notify_callback_parse_error(callback, translator)
        return

    currency_code = settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
    payment_description = describe_payment(translator, parts)
    record_payload = build_payment_record_payload(
        user_id=callback.from_user.id,
        amount=parts.price,
        currency=currency_code,
        status="pending_platega",
        description=payment_description,
        months=parts.months,
        provider="platega",
        sale_mode=parts.sale_mode,
    )

    try:
        payment_record = await payment_dal.create_payment_record(session, record_payload)
        await session.commit()
    except Exception:
        await session.rollback()
        logging.exception(
            "Platega: failed to create payment record for user %s.", callback.from_user.id
        )
        await notify_payment_record_failure(callback, translator)
        return

    payload_meta = json.dumps(
        {
            "payment_db_id": payment_record.payment_id,
            "user_id": callback.from_user.id,
            "months": parts.months,
            "sale_mode": parts.sale_mode,
            "platega_variant": platega_variant,
        }
    )

    success, response_data = await platega_service.create_transaction(
        amount=parts.price,
        currency=currency_code,
        description=payment_description,
        payload=payload_meta,
        payment_method=platega_method_id,
    )
    transaction_id = first_value(response_data, "transactionId", "id")
    redirect_url = first_value(response_data, "redirect", "url", "paymentUrl")
    provider_status = str((response_data or {}).get("status") or payment_record.status)
    # Platega requires *both* a transaction id and a redirect url to count as a
    # usable payment — neither field is sufficient on its own. Skipping the
    # persistence step when the redirect is missing matches the pre-refactor
    # behavior (we never stored a transaction id without a link).
    persistable_id = transaction_id if redirect_url else None
    await render_link_or_fail(
        callback,
        translator=translator,
        current_lang=current_lang,
        i18n=i18n,
        parts=parts,
        session=session,
        payment=payment_record,
        api_success=success,
        payment_url=redirect_url,
        provider_payment_id=persistable_id,
        new_status=provider_status if persistable_id else None,
        log_prefix=_LOG,
    )


def create_service(ctx: ServiceFactoryContext) -> PlategaService:
    return PlategaService(
        bot=ctx.bot,
        settings=ctx.settings,
        i18n=ctx.i18n,
        async_session_factory=ctx.async_session_factory,
        subscription_service=ctx.subscription_service,
        referral_service=ctx.referral_service,
        default_return_url=ctx.bot_username_for_default_return,
    )


async def _create_webapp_payment(ctx: WebAppPaymentContext, variant: str) -> web.Response:
    settings = ctx.request.app["settings"]
    service: PlategaService = ctx.request.app["platega_service"]
    if not service or not service.configured:
        return payment_unavailable()
    if variant == "platega_crypto":
        if not settings.PLATEGA_CRYPTO_ENABLED:
            return payment_unavailable()
        platega_method_id = settings.PLATEGA_CRYPTO_METHOD
    else:
        if variant == "platega_sbp" and not settings.PLATEGA_SBP_ENABLED:
            return payment_unavailable()
        platega_method_id = settings.platega_sbp_method_resolved

    try:
        amounts = payment_record_amounts(
            months=ctx.months,
            sale_mode=ctx.sale_mode,
            traffic_gb=ctx.traffic_gb,
        )
        payment = await create_webapp_payment_record(
            ctx,
            amount=ctx.price,
            currency=settings.DEFAULT_CURRENCY_SYMBOL or "RUB",
            status="pending_platega",
            provider="platega",
        )
        payload = json.dumps(
            {
                "payment_db_id": payment.payment_id,
                "user_id": ctx.user_id,
                "months": amounts.months if not amounts.traffic_sale else 0,
                "sale_mode": ctx.sale_mode,
                "traffic_gb": format_number_for_payload(ctx.traffic_gb or ctx.months)
                if amounts.traffic_sale
                else None,
                "hwid_devices": amounts.purchased_hwid_devices,
                "source": "webapp",
                "platega_variant": "crypto" if variant == "platega_crypto" else "sbp",
            }
        )
        success, response_data = await service.create_transaction(
            amount=ctx.price,
            currency=settings.DEFAULT_CURRENCY_SYMBOL or "RUB",
            description=ctx.description,
            payload=payload,
            payment_method=platega_method_id,
        )
    except Exception:
        await ctx.session.rollback()
        logging.exception("Platega WebApp payment failed")
        return payment_failed()

    return await finalize_webapp_link_payment(
        session=ctx.session,
        payment=payment,
        api_success=success,
        payment_url=(
            first_value(response_data, "redirect", "url", "paymentUrl") if success else None
        ),
        provider_payment_id=first_value(response_data, "transactionId", "id"),
        new_status=str((response_data or {}).get("status") or payment.status),
        log_prefix="Platega",
    )


async def create_sbp_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await _create_webapp_payment(ctx, "platega_sbp")


async def create_crypto_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await _create_webapp_payment(ctx, "platega_crypto")


SBP_SPEC = PaymentProviderSpec(
    id="platega_sbp",
    provider_key="platega",
    label="Platega",
    webapp_label="Platega · СБП",
    webapp_labels={"ru": "Оплата картой (СБП)", "en": "Pay with card (SBP)"},
    webapp_icon="CreditCard",
    telegram_labels={"ru": "Оплата через СБП", "en": "Pay via SBP"},
    telegram_emoji="🏦",
    pending_status="pending_platega",
    enabled=lambda settings: settings.PLATEGA_ENABLED and settings.PLATEGA_SBP_ENABLED,
    service_key="platega_service",
    button_text_key="pay_with_platega_sbp_button",
    callback_prefix="pay_platega_sbp",
    aliases=("platega",),
    router=router,
    create_service=create_service,
    webhook_path=lambda settings: settings.platega_webhook_path,
    webhook_route=platega_webhook_route,
    create_webapp_payment=create_sbp_webapp_payment,
)

CRYPTO_SPEC = PaymentProviderSpec(
    id="platega_crypto",
    provider_key="platega",
    label="Platega",
    webapp_label="Platega · Crypto",
    webapp_labels={"ru": "Крипта", "en": "Crypto"},
    webapp_icon="Bitcoin",
    telegram_labels={"ru": "Оплата криптой", "en": "Pay with crypto"},
    telegram_emoji="🪙",
    pending_status="pending_platega",
    enabled=lambda settings: settings.PLATEGA_ENABLED and settings.PLATEGA_CRYPTO_ENABLED,
    service_key="platega_service",
    button_text_key="pay_with_platega_crypto_button",
    callback_prefix="pay_platega_crypto",
    create_webapp_payment=create_crypto_webapp_payment,
)

SPECS = (SBP_SPEC, CRYPTO_SPEC)
