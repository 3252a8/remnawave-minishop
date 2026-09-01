from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from aiogram import Bot, F, Router, types
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from db.dal import payment_dal

from ..base import (
    PaymentProviderSpec,
    ServiceFactoryContext,
    WebAppPaymentContext,
    normalize_payment_currency_code,
    provider_runtime_enabled,
)
from ..shared import (
    CreatePaymentRequest,
    CreateResult,
    HttpClientMixin,
    LinkPaymentDescriptor,
    PaymentSuccessRequest,
    check_webhook_source_ip,
    finalize_successful_payment,
    first_value,
    lookup_payment_by_order_or_provider_id,
    notify_user_payment_failed,
    payment_amount_and_currency_match,
    payment_units_for_activation,
    post_json_request,
    run_callback_payment,
    run_reuse_webapp_payment,
    run_webapp_payment,
)
from ..shared.app_context import app_required
from .config import OxaPayConfig, OxaPayPresentation
from .manifest import _CONFIG_MANIFEST, _PRESENTATION_MANIFEST

if TYPE_CHECKING:
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService
else:
    ReferralService = object
    SubscriptionService = object

logger = logging.getLogger(__name__)

router = Router(name="user_subscription_payments_oxapay_router")
_LOG = "oxapay"

_SUCCESS_STATUSES = {"paid", "manual_accept"}
_FAILED_STATUSES = {"expired", "refunded"}
_PENDING_STATUSES = {"new", "waiting", "paying", "underpaid", "refunding"}


def _json_amount(value: Any) -> int | float:
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invoice amount must be numeric") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("invoice amount must be positive and finite")
    if amount == amount.to_integral_value():
        return int(amount)
    return float(amount)


def _api_response_ok(status: int, payload: Any) -> bool:
    if status != 200 or not isinstance(payload, dict):
        return False
    raw_status = payload.get("status")
    if not isinstance(raw_status, (int, str)) or isinstance(raw_status, bool):
        return False
    try:
        api_status = int(raw_status)
    except (TypeError, ValueError):
        return False
    return api_status == 200 and isinstance(payload.get("data"), dict)


def _compute_webhook_signature(raw_body: bytes, merchant_api_key: str) -> str:
    return hmac.new(
        merchant_api_key.encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()


class OxaPayService(HttpClientMixin):
    def __init__(
        self,
        *,
        bot: Bot,
        settings: Settings,
        config: OxaPayConfig,
        i18n: JsonI18n,
        async_session_factory: sessionmaker,
        subscription_service: SubscriptionService,
        referral_service: ReferralService,
        default_return_url: str,
    ) -> None:
        self.bot = bot
        self.settings = settings
        self.config = config
        self.i18n = i18n
        self.async_session_factory = async_session_factory
        self.subscription_service = subscription_service
        self.referral_service = referral_service
        self._default_return_url = default_return_url

        self._init_http_client(total_timeout=lambda: self.settings.PAYMENT_REQUEST_TIMEOUT_SECONDS)
        if not self.configured:
            logger.warning("OxaPayService initialized but not fully configured. Payments disabled.")

    @property
    def configured(self) -> bool:
        return bool(provider_runtime_enabled(self.config) and self.merchant_api_key)

    @property
    def merchant_api_key(self) -> str:
        return (self.config.MERCHANT_API_KEY or "").strip()

    @property
    def base_url(self) -> str:
        return (self.config.BASE_URL or "https://api.oxapay.com/v1").rstrip("/")

    @property
    def return_url(self) -> str:
        return self.config.RETURN_URL or f"https://t.me/{self._default_return_url}"

    @property
    def webhook_url(self) -> str | None:
        return self.config.full_webhook_url(getattr(self.settings, "WEBHOOK_BASE_URL", None))

    @property
    def request_headers(self) -> dict[str, str]:
        return {
            "merchant_api_key": self.merchant_api_key,
            "Content-Type": "application/json",
        }

    async def create_invoice(
        self,
        *,
        payment_db_id: int,
        amount: Any,
        currency: str,
        description: str,
    ) -> tuple[bool, dict[str, Any]]:
        if not self.configured:
            logger.error("OxaPayService is not configured. Cannot create invoice.")
            return False, {"message": "service_not_configured"}

        currency_code = normalize_payment_currency_code(currency, default="")
        if not currency_code:
            return False, {"message": "missing_currency"}
        try:
            invoice_amount = _json_amount(amount)
        except ValueError:
            logger.error("OxaPay create_invoice: invalid amount %r", amount)
            return False, {"message": "invalid_amount"}

        body: dict[str, Any] = {
            "amount": invoice_amount,
            "currency": currency_code,
            "lifetime": int(self.config.LIFETIME_MINUTES),
            "return_url": self.return_url,
            "order_id": str(payment_db_id),
            "sandbox": bool(self.config.SANDBOX),
        }
        if self.webhook_url:
            body["callback_url"] = self.webhook_url
        if description:
            body["description"] = description[:255]
        if self.config.FEE_PAID_BY_PAYER is not None:
            body["fee_paid_by_payer"] = int(self.config.FEE_PAID_BY_PAYER)
        if self.config.UNDER_PAID_COVERAGE is not None:
            body["under_paid_coverage"] = float(self.config.UNDER_PAID_COVERAGE)
        if self.config.TO_CURRENCY:
            body["to_currency"] = self.config.TO_CURRENCY
        if self.config.AUTO_WITHDRAWAL is not None:
            body["auto_withdrawal"] = bool(self.config.AUTO_WITHDRAWAL)
        if self.config.MIXED_PAYMENT is not None:
            body["mixed_payment"] = bool(self.config.MIXED_PAYMENT)

        session = await self._get_session()
        success, response_data = await post_json_request(
            session,
            f"{self.base_url}/payment/invoice",
            body=body,
            headers=self.request_headers,
            log_prefix="OxaPay create_invoice",
            is_success=_api_response_ok,
        )
        if not success:
            return False, response_data

        data = response_data.get("data")
        if (
            not isinstance(data, dict)
            or not first_value(data, "track_id")
            or not first_value(data, "payment_url")
        ):
            logger.error("OxaPay create_invoice: response is missing track_id or payment_url")
            return False, {"message": "invalid_response", "response": response_data}
        return True, data

    async def get_payment_info(self, track_id: str) -> tuple[bool, dict[str, Any]]:
        if not self.configured:
            return False, {"message": "service_not_configured"}

        normalized_track_id = str(track_id or "").strip()
        if not normalized_track_id:
            return False, {"message": "missing_track_id"}

        session = await self._get_session()
        try:
            async with session.get(
                f"{self.base_url}/payment/{quote(normalized_track_id, safe='')}",
                headers=self.request_headers,
            ) as response:
                response_text = await response.text()
                try:
                    response_data = json.loads(response_text) if response_text else {}
                except json.JSONDecodeError:
                    logger.error("OxaPay get_payment_info: invalid JSON: %s", response_text)
                    return False, {
                        "status": response.status,
                        "message": "invalid_json",
                        "raw": response_text,
                    }
                if not _api_response_ok(response.status, response_data):
                    logger.warning(
                        "OxaPay get_payment_info failed: track_id=%s status=%s body=%s",
                        normalized_track_id,
                        response.status,
                        response_data,
                    )
                    return False, {"status": response.status, "message": response_data}
                data = response_data.get("data")
                return isinstance(data, dict), data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.exception(
                "OxaPay get_payment_info request failed: track_id=%s", normalized_track_id
            )
            return False, {"message": str(exc)}

    async def try_reuse_pending_payment(self, payment: Any) -> str | None:
        track_id = str(getattr(payment, "provider_payment_id", None) or "").strip()
        stored_url = str(getattr(payment, "provider_payment_url", None) or "").strip()
        if not track_id or not stored_url:
            return None

        success, data = await self.get_payment_info(track_id)
        if not success:
            return None
        if str(data.get("track_id") or "") != track_id:
            return None
        if str(data.get("order_id") or "") != str(payment.payment_id):
            return None
        status = str(data.get("status") or "").strip().lower()
        if status not in {"new", "waiting", "underpaid"}:
            return None
        try:
            expired_at = int(data.get("expired_at") or 0)
        except (TypeError, ValueError):
            return None
        if expired_at and expired_at <= int(time.time()):
            return None
        return first_value(data, "payment_url") or stored_url

    def _valid_webhook_signature(self, raw_body: bytes, signature: str | None) -> bool:
        received = str(signature or "").strip().lower()
        if not received or not self.merchant_api_key:
            return False
        expected = _compute_webhook_signature(raw_body, self.merchant_api_key)
        return hmac.compare_digest(received, expected)

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.Response(status=503, text="oxapay_disabled")

        ip_check = check_webhook_source_ip(
            request,
            trusted_ips=self.config.trusted_ips_list,
            trusted_proxies=self.settings.trusted_proxies,
            allow_empty=True,
        )
        if not ip_check.allowed:
            logger.warning(
                "OxaPay webhook denied from unauthorized IP source "
                "(client_ip=%s remote=%s x_forwarded_for=%s).",
                ip_check.client_ip,
                request.remote,
                request.headers.get("X-Forwarded-For"),
            )
            return web.Response(status=403, text="forbidden")

        raw_body = await request.read()
        if not self._valid_webhook_signature(raw_body, request.headers.get("HMAC")):
            logger.warning("OxaPay webhook: invalid HMAC signature.")
            return web.Response(status=403, text="invalid_signature")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("OxaPay webhook: invalid JSON payload.")
            return web.Response(status=400, text="bad_request")
        if not isinstance(payload, dict):
            return web.Response(status=400, text="bad_request")

        event_type = str(payload.get("type") or "").strip().lower()
        track_id = str(payload.get("track_id") or "").strip()
        order_id_raw = payload.get("order_id")
        status = str(payload.get("status") or "").strip().lower()
        if event_type != "invoice":
            return web.Response(status=400, text="unsupported_type")
        if not track_id or order_id_raw in (None, "") or not status:
            return web.Response(status=400, text="missing_fields")

        async with self.async_session_factory() as session:
            payment = await lookup_payment_by_order_or_provider_id(
                session,
                providers="oxapay",
                order_id_raw=order_id_raw,
                provider_payment_id=track_id,
            )
            if not payment:
                logger.error(
                    "OxaPay webhook: payment not found (order_id=%s, track_id=%s)",
                    order_id_raw,
                    track_id,
                )
                return web.Response(status=404, text="payment_not_found")
            if str(order_id_raw) != str(payment.payment_id):
                return web.Response(status=400, text="order_id_mismatch")
            stored_track_id = str(getattr(payment, "provider_payment_id", None) or "").strip()
            if stored_track_id and stored_track_id != track_id:
                return web.Response(status=400, text="track_id_mismatch")

            if status in _SUCCESS_STATUSES:
                if payment.status == "succeeded":
                    return web.Response(text="ok")
                if not payment_amount_and_currency_match(
                    expected_amount=payment.amount,
                    expected_currency=payment.currency,
                    received_amount=payload.get("amount"),
                    received_currency=payload.get("currency"),
                    places=None,
                ):
                    logger.warning(
                        "OxaPay webhook: amount or currency mismatch for payment %s "
                        "(expected=%s %s, got=%s %s)",
                        payment.payment_id,
                        payment.amount,
                        payment.currency,
                        payload.get("amount"),
                        payload.get("currency"),
                    )
                    return web.Response(status=400, text="payment_mismatch")

                try:
                    claimed_payment = await payment_dal.claim_payment_finalization(
                        session,
                        payment.payment_id,
                        provider_payment_id=track_id,
                    )
                except Exception:
                    await session.rollback()
                    logger.exception(
                        "OxaPay webhook: failed to claim payment %s for finalization.",
                        payment.payment_id,
                    )
                    return web.Response(status=500, text="processing_error")
                if claimed_payment is None:
                    return web.Response(text="ok")
                payment = claimed_payment

                sale_mode = payment.sale_mode or (
                    "traffic" if self.settings.traffic_sale_mode else "subscription"
                )
                payment_units = payment_units_for_activation(payment, sale_mode)
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
                        months=payment_units,
                        traffic_amount=float(payment_units),
                        provider_subscription="oxapay",
                        provider_notification="oxapay",
                        db_user=payment.user,
                        log_prefix="OxaPay webhook",
                    )
                )
                if outcome is None:
                    return web.Response(status=500, text="processing_error")
                return web.Response(text="ok")

            if status in _FAILED_STATUSES:
                if payment.status in {"succeeded", "failed", "canceled"}:
                    return web.Response(text="ok")
                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        track_id,
                        "failed",
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logger.exception(
                        "OxaPay webhook: failed to mark payment %s as failed.",
                        payment.payment_id,
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

            if status in _PENDING_STATUSES:
                if payment.status not in {"succeeded", "failed", "canceled"}:
                    try:
                        await payment_dal.update_provider_payment_and_status(
                            session,
                            payment.payment_id,
                            track_id,
                            "pending_oxapay",
                        )
                        await session.commit()
                    except Exception:
                        await session.rollback()
                        logger.exception(
                            "OxaPay webhook: failed to update pending payment %s.",
                            payment.payment_id,
                        )
                        return web.Response(status=500, text="processing_error")
                return web.Response(text="ok")

            logger.info(
                "OxaPay webhook: acknowledged unknown status '%s' for payment %s.",
                status,
                payment.payment_id,
            )
            return web.Response(text="ok")


@router.callback_query(F.data.startswith("pay_oxapay:"))
async def pay_oxapay_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    oxapay_service: OxaPayService,
    session: AsyncSession,
) -> None:
    await run_callback_payment(_DESCRIPTOR, callback, settings, i18n_data, oxapay_service, session)


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_DESCRIPTOR, ctx)


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> str | None:
    return await run_reuse_webapp_payment(_DESCRIPTOR, ctx, payment)


async def oxapay_webhook_route(request: web.Request) -> web.Response:
    service: OxaPayService = app_required(request, "oxapay_service", OxaPayService)
    return await service.webhook_route(request)


def create_service(ctx: ServiceFactoryContext) -> OxaPayService:
    bundle = ctx.config_for("oxapay_service")
    config = bundle.config if bundle and isinstance(bundle.config, OxaPayConfig) else OxaPayConfig()
    return OxaPayService(
        bot=ctx.bot,
        settings=ctx.settings,
        config=config,
        i18n=ctx.i18n,
        async_session_factory=ctx.async_session_factory,
        subscription_service=ctx.subscription_service,
        referral_service=ctx.referral_service,
        default_return_url=ctx.bot_username_for_default_return,
    )


SPEC = PaymentProviderSpec(
    id="oxapay",
    provider_key="oxapay",
    label="OxaPay",
    webapp_label="OxaPay",
    webapp_labels={"ru": "OxaPay", "en": "OxaPay"},
    webapp_icon="Bitcoin",
    logo_url="/provider-logos/oxapay.png",
    telegram_labels={"ru": "OxaPay", "en": "OxaPay"},
    telegram_emoji="🪙",
    pending_status="pending_oxapay",
    enabled=lambda config: bool(getattr(config, "ENABLED", False)),
    service_key="oxapay_service",
    callback_prefix="pay_oxapay",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/oxapay",
    webhook_route=oxapay_webhook_route,
    webhook_requires_base_url=True,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    emoji="🪙",
    config_class=OxaPayConfig,
    presentation_class=OxaPayPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supported_currencies=None,
    currency_support_note=(
        "OxaPay Generate Invoice accepts fiat and crypto invoice currencies; exact availability "
        "is validated by OxaPay for the merchant account."
    ),
    info_url="https://oxapay.com/",
    currency_support_url="https://docs.oxapay.com/api-reference/payment/generate-invoice",
)


async def _create_payment(service: OxaPayService, req: CreatePaymentRequest) -> CreateResult:
    return await service.create_invoice(
        payment_db_id=req.payment.payment_id,
        amount=req.amount,
        currency=req.currency,
        description=req.description,
    )


async def _reuse_payment(service: OxaPayService, payment: Any) -> str | None:
    return await service.try_reuse_pending_payment(payment)


_DESCRIPTOR: LinkPaymentDescriptor[OxaPayService] = LinkPaymentDescriptor(
    spec=SPEC,
    provider_key="oxapay",
    pending_status="pending_oxapay",
    display_name="OxaPay",
    log_prefix=_LOG,
    service_app_key="oxapay_service",
    service_type=OxaPayService,
    create=_create_payment,
    reuse=_reuse_payment,
    extract_url=lambda response: first_value(response, "payment_url"),
    extract_provider_id=lambda response: first_value(response, "track_id"),
)


__all__ = [
    "SPEC",
    "OxaPayService",
    "_compute_webhook_signature",
    "create_service",
    "create_webapp_payment",
    "oxapay_webhook_route",
    "pay_oxapay_callback_handler",
    "reuse_webapp_payment",
]
