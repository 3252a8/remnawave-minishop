import base64
import hashlib
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
from bot.utils.request_security import ip_in_allowlist, request_client_ip
from config.settings import Settings
from db.dal import payment_dal

from .base import PaymentProviderSpec, ServiceFactoryContext, WebAppPaymentContext
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
    lookup_payment_by_order_or_provider_id,
    make_translator,
    notify_callback_parse_error,
    notify_payment_record_failure,
    notify_service_unavailable,
    notify_user_payment_failed,
    parse_payment_callback,
    payment_failed,
    payment_unavailable,
    render_link_or_fail,
)

router = Router(name="user_subscription_payments_heleket_router")
_LOG = "heleket"

_SUCCESS_STATUSES = {"paid", "paid_over"}
_FAILED_STATUSES = {"fail", "wrong_amount", "cancel", "system_fail"}


def _serialize_for_signature(payload: Dict[str, Any]) -> str:
    """Serialize JSON exactly the way Heleket signs it.

    Heleket's PHP example uses ``json_encode`` with ``JSON_UNESCAPED_UNICODE``
    and default forward-slash escaping. We replicate both: ``ensure_ascii=False``
    keeps unicode untouched, then we manually escape ``/`` so that the base64
    payload matches the one signed on the Heleket side.
    """
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return encoded.replace("/", "\\/")


def _compute_signature(payload: Dict[str, Any], api_key: str) -> str:
    body = _serialize_for_signature(payload).encode("utf-8")
    b64 = base64.b64encode(body).decode("ascii")
    return hashlib.md5((b64 + api_key).encode("utf-8")).hexdigest()


class HeleketService(HttpClientMixin):
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

        self.base_url = (settings.HELEKET_BASE_URL or "https://api.heleket.com").rstrip("/")
        self.merchant_id = settings.HELEKET_MERCHANT_ID or ""
        self.api_key = settings.HELEKET_API_KEY or ""
        self.currency = (settings.HELEKET_CURRENCY or "RUB").upper()
        self.to_currency = (settings.HELEKET_TO_CURRENCY or "").strip() or None
        self.network = (settings.HELEKET_NETWORK or "").strip() or None
        self.return_url = settings.HELEKET_RETURN_URL or f"https://t.me/{default_return_url}"
        self.success_url = settings.HELEKET_SUCCESS_URL or self.return_url
        self.lifetime_seconds = settings.HELEKET_LIFETIME_SECONDS
        self.verify_webhook_signature = settings.HELEKET_VERIFY_WEBHOOK_SIGNATURE

        self._init_http_client(total_timeout=20)
        self.configured: bool = bool(
            settings.HELEKET_ENABLED and self.merchant_id and self.api_key
        )
        if not self.configured:
            logging.warning(
                "HeleketService initialized but not fully configured. Payments disabled."
            )

    async def create_payment_link(
        self,
        *,
        payment_db_id: int,
        amount: float,
        currency: Optional[str],
        description: str,
        url_callback: Optional[str],
    ) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            logging.error("HeleketService is not configured. Cannot create payment link.")
            return False, {"message": "service_not_configured"}

        body: Dict[str, Any] = {
            "amount": str(format_decimal_amount(amount)),
            "currency": (currency or self.currency).upper(),
            "order_id": str(payment_db_id),
            "url_return": self.return_url,
            "url_success": self.success_url,
            "lifetime": int(self.lifetime_seconds),
        }
        if description:
            body["additional_data"] = description[:255]
        if self.to_currency:
            body["to_currency"] = self.to_currency
        if self.network:
            body["network"] = self.network
        if url_callback:
            body["url_callback"] = url_callback

        signed_body = _serialize_for_signature(body).encode("utf-8")
        headers = {
            "merchant": self.merchant_id,
            "sign": _compute_signature(body, self.api_key),
            "Content-Type": "application/json",
        }
        session = await self._get_session()
        try:
            async with session.post(
                f"{self.base_url}/v1/payment",
                data=signed_body,
                headers=headers,
            ) as response:
                response_text = await response.text()
                try:
                    response_data = json.loads(response_text) if response_text else {}
                except json.JSONDecodeError:
                    logging.error("Heleket create_payment_link: invalid JSON: %s", response_text)
                    return False, {
                        "status": response.status,
                        "message": "invalid_json",
                        "raw": response_text,
                    }
                state = response_data.get("state") if isinstance(response_data, dict) else None
                if response.status != 200 or state != 0:
                    logging.error(
                        "Heleket create_payment_link: API error (status=%s, body=%s)",
                        response.status,
                        response_data,
                    )
                    return False, {"status": response.status, "message": response_data}
                return True, response_data
        except Exception as exc:
            logging.exception("Heleket create_payment_link: request failed.")
            return False, {"message": str(exc)}

    def _verify_signature(self, payload: Dict[str, Any]) -> bool:
        received = payload.get("sign")
        if not isinstance(received, str) or not received:
            return False
        data = {k: v for k, v in payload.items() if k != "sign"}
        expected = _compute_signature(data, self.api_key)
        return hmac.compare_digest(expected, received)

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.Response(status=503, text="heleket_disabled")

        client_ip = request_client_ip(request, trusted_proxies=self.settings.trusted_proxies)
        if self.settings.heleket_trusted_ips and not ip_in_allowlist(
            client_ip, self.settings.heleket_trusted_ips
        ):
            logging.warning("Heleket webhook denied from unauthorized IP source.")
            return web.Response(status=403, text="forbidden")

        raw_body = await request.read()
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            logging.exception("Heleket webhook: failed to parse JSON.")
            return web.Response(status=400, text="bad_request")

        if not isinstance(payload, dict):
            return web.Response(status=400, text="bad_request")

        if self.verify_webhook_signature and not self._verify_signature(payload):
            logging.warning("Heleket webhook: invalid signature.")
            return web.Response(status=403, text="invalid_signature")

        uuid_value = str(payload.get("uuid") or "").strip()
        status = str(payload.get("status") or "").strip().lower()
        order_id_raw = payload.get("order_id")
        amount_raw = payload.get("amount")
        currency = payload.get("currency") or self.currency

        if not status or not (uuid_value or order_id_raw):
            logging.error("Heleket webhook: missing status or ids: %s", payload)
            return web.Response(status=400, text="missing_fields")

        async with self.async_session_factory() as session:
            payment = await lookup_payment_by_order_or_provider_id(
                session,
                order_id_raw=order_id_raw,
                provider_payment_id=uuid_value or None,
            )
            if not payment:
                logging.error(
                    "Heleket webhook: payment not found (order_id=%s, uuid=%s)",
                    order_id_raw,
                    uuid_value,
                )
                return web.Response(status=404, text="payment_not_found")

            if payment.status == "succeeded" and status in _SUCCESS_STATUSES:
                return web.Response(text="ok")

            resolved_id = uuid_value or str(payment.payment_id)

            if status in _SUCCESS_STATUSES:
                if amount_raw is not None:
                    try:
                        if not decimal_amounts_equal(amount_raw, payment.amount):
                            logging.warning(
                                "Heleket webhook: amount mismatch for payment %s "
                                "(expected %s, got %s)",
                                payment.payment_id,
                                format_decimal_amount(payment.amount),
                                format_decimal_amount(amount_raw),
                            )
                    except Exception as exc:
                        logging.warning(
                            "Heleket webhook: failed to compare amounts for %s: %s",
                            payment.payment_id,
                            exc,
                        )

                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        resolved_id,
                        "succeeded",
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logging.exception(
                        "Heleket webhook: failed to mark payment %s as succeeded.",
                        resolved_id,
                    )
                    return web.Response(status=500, text="processing_error")

                payment_units = payment.purchased_gb or payment.subscription_duration_months or 1
                sale_mode = payment.sale_mode or (
                    "traffic" if self.settings.traffic_sale_mode else "subscription"
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
                        currency=str(currency),
                        sale_mode=sale_mode,
                        months=payment_units,
                        traffic_amount=float(payment_units),
                        provider_subscription="heleket",
                        provider_notification="heleket",
                        db_user=payment.user,
                        log_prefix="Heleket webhook",
                    )
                )
                if outcome is None:
                    return web.Response(status=500, text="processing_error")
                return web.Response(text="ok")

            if status in _FAILED_STATUSES:
                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        resolved_id,
                        "failed",
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logging.exception(
                        "Heleket webhook: failed to mark payment %s as failed.",
                        resolved_id,
                    )
                    return web.Response(status=500, text="processing_error")
                await notify_user_payment_failed(
                    bot=self.bot,
                    settings=self.settings,
                    i18n=self.i18n,
                    session=session,
                    payment=payment,
                )
                return web.Response(text="ok")

            logging.info(
                "Heleket webhook: intermediate status '%s' for payment %s",
                status,
                resolved_id,
            )
            return web.Response(status=202, text="status_ignored")


@router.callback_query(F.data.startswith("pay_heleket:"))
async def pay_heleket_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    heleket_service: HeleketService,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    translator = make_translator(i18n, current_lang)

    if not i18n or not callback.message:
        await notify_callback_parse_error(callback, translator)
        return

    if not heleket_service or not heleket_service.configured:
        logging.error("Heleket service is not configured or unavailable.")
        await notify_service_unavailable(callback, translator)
        return

    parts = parse_payment_callback(callback.data or "")
    if not parts:
        logging.error("Invalid pay_heleket data in callback: %s", callback.data)
        await notify_callback_parse_error(callback, translator)
        return

    currency_code = (heleket_service.currency or settings.DEFAULT_CURRENCY_SYMBOL or "RUB").upper()
    payment_description = describe_payment(translator, parts)
    record_payload = build_payment_record_payload(
        user_id=callback.from_user.id,
        amount=parts.price,
        currency=currency_code,
        status="pending_heleket",
        description=payment_description,
        months=parts.months,
        provider="heleket",
        sale_mode=parts.sale_mode,
    )

    try:
        payment_record = await payment_dal.create_payment_record(session, record_payload)
        await session.commit()
    except Exception:
        await session.rollback()
        logging.exception(
            "Heleket: failed to create payment record for user %s.", callback.from_user.id
        )
        await notify_payment_record_failure(callback, translator)
        return

    success, response_data = await heleket_service.create_payment_link(
        payment_db_id=payment_record.payment_id,
        amount=parts.price,
        currency=currency_code,
        description=payment_description,
        url_callback=settings.heleket_full_webhook_url,
    )
    result = response_data.get("result") if isinstance(response_data, dict) else None
    await render_link_or_fail(
        callback,
        translator=translator,
        current_lang=current_lang,
        i18n=i18n,
        parts=parts,
        session=session,
        payment=payment_record,
        api_success=success,
        payment_url=first_value(result, "url"),
        provider_payment_id=first_value(result, "uuid"),
        log_prefix=_LOG,
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    settings: Settings = ctx.request.app["settings"]
    service: HeleketService = ctx.request.app["heleket_service"]
    if not service or not service.configured:
        return payment_unavailable()

    currency = (service.currency or settings.DEFAULT_CURRENCY_SYMBOL or "RUB").upper()
    try:
        payment = await create_webapp_payment_record(
            ctx,
            amount=ctx.price,
            currency=currency,
            status="pending_heleket",
            provider="heleket",
        )
        success, response_data = await service.create_payment_link(
            payment_db_id=payment.payment_id,
            amount=ctx.price,
            currency=currency,
            description=ctx.description,
            url_callback=settings.heleket_full_webhook_url,
        )
    except Exception:
        await ctx.session.rollback()
        logging.exception("Heleket WebApp payment failed")
        return payment_failed()

    result = response_data.get("result") if isinstance(response_data, dict) else None
    return await finalize_webapp_link_payment(
        session=ctx.session,
        payment=payment,
        api_success=success,
        payment_url=first_value(result, "url") if success else None,
        provider_payment_id=first_value(result, "uuid"),
        log_prefix="Heleket",
    )


async def heleket_webhook_route(request: web.Request) -> web.Response:
    service: HeleketService = request.app["heleket_service"]
    return await service.webhook_route(request)


def create_service(ctx: ServiceFactoryContext) -> HeleketService:
    return HeleketService(
        bot=ctx.bot,
        settings=ctx.settings,
        i18n=ctx.i18n,
        async_session_factory=ctx.async_session_factory,
        subscription_service=ctx.subscription_service,
        referral_service=ctx.referral_service,
        default_return_url=ctx.bot_username_for_default_return,
    )


SPEC = PaymentProviderSpec(
    id="heleket",
    provider_key="heleket",
    label="Heleket",
    webapp_label="Heleket",
    webapp_labels={"ru": "Heleket", "en": "Heleket"},
    webapp_icon="Bitcoin",
    telegram_labels={"ru": "Heleket", "en": "Heleket"},
    telegram_emoji="🪙",
    pending_status="pending_heleket",
    enabled=lambda settings: settings.HELEKET_ENABLED,
    service_key="heleket_service",
    callback_prefix="pay_heleket",
    router=router,
    create_service=create_service,
    webhook_path=lambda settings: settings.heleket_webhook_path,
    webhook_route=heleket_webhook_route,
    create_webapp_payment=create_webapp_payment,
    emoji="🪙",
)
