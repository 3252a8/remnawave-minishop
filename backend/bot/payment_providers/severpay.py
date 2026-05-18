import hashlib
import hmac
import json
import logging
import secrets
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

from .base import PaymentProviderSpec, ServiceFactoryContext, WebAppPaymentContext
from .shared import (
    HttpClientMixin,
    PaymentSuccessRequest,
    build_payment_record_payload,
    create_webapp_payment_record,
    describe_payment,
    finalize_successful_payment,
    finalize_webapp_link_payment,
    first_value,
    format_decimal_amount,
    lookup_payment_by_order_or_provider_id,
    make_translator,
    notify_callback_parse_error,
    notify_payment_record_failure,
    notify_service_unavailable,
    notify_user_payment_failed,
    parse_payment_callback,
    payment_failed,
    payment_unavailable,
    post_json_request,
    render_link_or_fail,
)

_LOG = "severpay"


class SeverPayService(HttpClientMixin):
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

        self.base_url = (settings.SEVERPAY_BASE_URL or "https://severpay.io/api/merchant").rstrip(
            "/"
        )
        self.mid = settings.SEVERPAY_MID
        self.token = settings.SEVERPAY_TOKEN or ""
        self.return_url = settings.SEVERPAY_RETURN_URL or f"https://t.me/{default_return_url}"
        self.lifetime_minutes = settings.SEVERPAY_LIFETIME_MINUTES

        self._init_http_client(total_timeout=15)

        self.configured: bool = bool(settings.SEVERPAY_ENABLED and self.mid and self.token)
        if not self.configured:
            logging.warning(
                "SeverPayService initialized but not fully configured. Payments disabled."
            )

    @staticmethod
    def _format_amount(amount: float) -> str:
        return f"{format_decimal_amount(amount):.2f}"

    def _sign_payload(self, payload: Dict[str, Any]) -> str:
        message = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return hmac.new(
            self.token.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _build_signed_body(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "mid": self.mid,
            "salt": secrets.token_hex(8),
        }
        body.update(extra)
        sorted_body = dict(sorted(body.items()))
        sorted_body["sign"] = self._sign_payload(sorted_body)
        return sorted_body

    def _validate_signature(self, payload: Dict[str, Any]) -> bool:
        provided_sign = str(payload.get("sign") or "")
        if not provided_sign or not self.token:
            return False
        # Webhook signatures are calculated on the original payload order (without sorting).
        data = {k: v for k, v in payload.items() if k != "sign"}
        expected_sign = self._sign_payload(data)
        return hmac.compare_digest(provided_sign, expected_sign)

    async def create_payment(
        self,
        *,
        payment_db_id: int,
        user_id: int,
        amount: float,
        currency: Optional[str],
    ) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            logging.error("SeverPayService is not configured. Cannot create payment.")
            return False, {"message": "service_not_configured"}

        session = await self._get_session()
        url = f"{self.base_url}/payin/create"
        currency_code = (currency or self.settings.DEFAULT_CURRENCY_SYMBOL or "RUB").upper()

        body = {
            "order_id": str(payment_db_id),
            "amount": self._format_amount(amount),
            "currency": currency_code,
            "client_email": f"{user_id}@telegram.org",
            "client_id": str(user_id),
            "url_return": self.return_url,
        }

        if self.lifetime_minutes:
            body["lifetime"] = int(self.lifetime_minutes)

        success, response_data = await post_json_request(
            session,
            url,
            body=self._build_signed_body(body),
            log_prefix="SeverPay create_payment",
            # SeverPay marks success with both HTTP 200 *and* the top-level ``status`` flag.
            is_success=lambda status, data: status == 200 and bool((data or {}).get("status")),
        )
        if success:
            # SeverPay wraps the useful response inside ``data``; unwrap so callers
            # don't have to know that detail.
            return True, response_data.get("data") or response_data
        return False, response_data

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.json_response({"status": False, "msg": "severpay_disabled"}, status=503)

        try:
            payload = await request.json()
        except Exception:
            logging.exception("SeverPay webhook: failed to parse JSON.")
            return web.json_response({"status": False, "msg": "bad_request"}, status=400)

        if not isinstance(payload, dict) or not self._validate_signature(payload):
            logging.error("SeverPay webhook: invalid signature or payload.")
            return web.json_response({"status": False, "msg": "invalid_signature"}, status=403)

        event_type = str(payload.get("type") or "").lower()
        data = payload.get("data") or {}

        if event_type != "payin" or not isinstance(data, dict):
            logging.warning("SeverPay webhook: unsupported event type '%s'", event_type)
            return web.json_response({"status": True})

        provider_payment_id = str(data.get("id") or data.get("uid") or "")
        order_id_raw = data.get("order_id")
        status = str(data.get("status") or "").lower()

        async with self.async_session_factory() as session:
            payment = await lookup_payment_by_order_or_provider_id(
                session,
                order_id_raw=order_id_raw,
                provider_payment_id=provider_payment_id or None,
            )
            if not payment:
                logging.error(
                    "SeverPay webhook: payment not found (order_id=%s, provider_id=%s)",
                    order_id_raw,
                    provider_payment_id,
                )
                return web.json_response({"status": False, "msg": "payment_not_found"}, status=404)

            resolved_provider_id = provider_payment_id or str(payment.payment_id)
            payment_months = payment.purchased_gb or payment.subscription_duration_months or 1
            sale_mode = payment.sale_mode or (
                "traffic" if self.settings.traffic_sale_mode else "subscription"
            )

            if status == "success":
                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        resolved_provider_id,
                        "succeeded",
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logging.exception(
                        "SeverPay webhook: failed to mark payment %s as succeeded.",
                        resolved_provider_id,
                    )
                    return web.json_response(
                        {"status": False, "msg": "processing_error"}, status=500
                    )

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
                        currency=payment.currency,
                        sale_mode=sale_mode,
                        months=payment_months,
                        traffic_amount=float(payment_months),
                        provider_subscription="severpay",
                        provider_notification="severpay",
                        db_user=payment.user,
                        log_prefix="SeverPay webhook",
                    )
                )
                if outcome is None:
                    return web.json_response(
                        {"status": False, "msg": "processing_error"}, status=500
                    )
                return web.json_response({"status": True})

            if status in {"fail", "decline"}:
                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        resolved_provider_id,
                        "failed",
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logging.exception(
                        "SeverPay webhook: failed to mark payment %s as failed.",
                        resolved_provider_id,
                    )
                    return web.json_response(
                        {"status": False, "msg": "processing_error"}, status=500
                    )
                await notify_user_payment_failed(
                    bot=self.bot,
                    settings=self.settings,
                    i18n=self.i18n,
                    session=session,
                    payment=payment,
                )
                return web.json_response({"status": True})

            if status in {"process", "new"}:
                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        resolved_provider_id,
                        "pending_severpay",
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logging.exception(
                        "SeverPay webhook: failed to update pending status for %s.",
                        resolved_provider_id,
                    )
                return web.json_response({"status": True})

            logging.warning(
                "SeverPay webhook: unhandled status '%s' for payment %s",
                status,
                resolved_provider_id,
            )
            return web.json_response({"status": True})


async def severpay_webhook_route(request: web.Request) -> web.Response:
    service: SeverPayService = request.app["severpay_service"]
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_severpay_router")


@router.callback_query(F.data.startswith("pay_severpay:"))
async def pay_severpay_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    severpay_service: SeverPayService,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    translator = make_translator(i18n, current_lang)

    if not i18n or not callback.message:
        await notify_callback_parse_error(callback, translator)
        return

    if not severpay_service or not severpay_service.configured:
        logging.error("SeverPay service is not configured or unavailable.")
        await notify_service_unavailable(callback, translator)
        return

    parts = parse_payment_callback(callback.data or "")
    if not parts:
        logging.error("Invalid pay_severpay data in callback: %s", callback.data)
        await notify_callback_parse_error(callback, translator)
        return

    currency_code = settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
    payment_description = describe_payment(translator, parts)
    record_payload = build_payment_record_payload(
        user_id=callback.from_user.id,
        amount=parts.price,
        currency=currency_code,
        status="pending_severpay",
        description=payment_description,
        months=parts.months,
        provider="severpay",
        sale_mode=parts.sale_mode,
    )

    try:
        payment_record = await payment_dal.create_payment_record(session, record_payload)
        await session.commit()
    except Exception:
        await session.rollback()
        logging.exception(
            "SeverPay: failed to create payment record for user %s.", callback.from_user.id
        )
        await notify_payment_record_failure(callback, translator)
        return

    success, response_data = await severpay_service.create_payment(
        payment_db_id=payment_record.payment_id,
        user_id=callback.from_user.id,
        amount=parts.price,
        currency=currency_code,
    )
    await render_link_or_fail(
        callback,
        translator=translator,
        current_lang=current_lang,
        i18n=i18n,
        parts=parts,
        session=session,
        payment=payment_record,
        api_success=success,
        payment_url=first_value(response_data, "url", "payment_url", "paymentUrl"),
        provider_payment_id=first_value(response_data, "id", "uid"),
        log_prefix=_LOG,
    )


def create_service(ctx: ServiceFactoryContext) -> SeverPayService:
    return SeverPayService(
        bot=ctx.bot,
        settings=ctx.settings,
        i18n=ctx.i18n,
        async_session_factory=ctx.async_session_factory,
        subscription_service=ctx.subscription_service,
        referral_service=ctx.referral_service,
        default_return_url=ctx.bot_username_for_default_return,
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    settings = ctx.request.app["settings"]
    service: SeverPayService = ctx.request.app["severpay_service"]
    if not service or not service.configured:
        return payment_unavailable()

    currency = settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
    try:
        payment = await create_webapp_payment_record(
            ctx,
            amount=ctx.price,
            currency=currency,
            status="pending_severpay",
            provider="severpay",
        )
        success, response_data = await service.create_payment(
            payment_db_id=payment.payment_id,
            user_id=ctx.user_id,
            amount=ctx.price,
            currency=currency,
        )
    except Exception:
        await ctx.session.rollback()
        logging.exception("SeverPay WebApp payment failed")
        return payment_failed()

    return await finalize_webapp_link_payment(
        session=ctx.session,
        payment=payment,
        api_success=success,
        payment_url=(
            first_value(response_data, "url", "payment_url", "paymentUrl") if success else None
        ),
        provider_payment_id=first_value(response_data, "id", "uid"),
        log_prefix="SeverPay",
    )


SPEC = PaymentProviderSpec(
    id="severpay",
    provider_key="severpay",
    label="SeverPay",
    webapp_label="SeverPay",
    webapp_labels={"ru": "SeverPay", "en": "SeverPay"},
    webapp_icon="CreditCard",
    telegram_labels={"ru": "SeverPay", "en": "SeverPay"},
    telegram_emoji="💳",
    pending_status="pending_severpay",
    enabled=lambda settings: settings.SEVERPAY_ENABLED,
    service_key="severpay_service",
    button_text_key="pay_with_severpay_button",
    callback_prefix="pay_severpay",
    router=router,
    create_service=create_service,
    webhook_path=lambda settings: settings.severpay_webhook_path,
    webhook_route=severpay_webhook_route,
    create_webapp_payment=create_webapp_payment,
)
