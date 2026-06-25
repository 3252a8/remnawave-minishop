import hashlib
import hmac
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from aiogram import Bot, F, Router, types
from aiohttp import web
from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.services.referral_service import ReferralService
from bot.services.subscription_service import SubscriptionService
from config.settings import Settings
from db.dal import payment_dal

from ..base import (
    PaymentProviderSpec,
    ProviderEnvConfig,
    ProviderManifestField,
    ServiceFactoryContext,
    WebAppPaymentContext,
    normalize_payment_currency_code,
    provider_env_file,
    provider_runtime_enabled,
)
from ..shared import (
    PAYMENT_STATUS_PENDING_FINALIZATION,
    CreatePaymentRequest,
    CreateResult,
    HttpClientMixin,
    LinkPaymentDescriptor,
    PaymentSuccessRequest,
    decimal_amounts_equal,
    finalize_successful_payment,
    first_value,
    format_decimal_amount,
    lookup_payment_by_order_or_provider_id,
    notify_user_payment_failed,
    payment_units_for_activation,
    run_callback_payment,
    run_reuse_webapp_payment,
    run_webapp_payment,
)
from ..shared.app_context import app_required

_LOG = "lava"

# LAVA Business invoice statuses (https://dev.lava.ru/business-objects-invoice).
_SUCCESS_STATUSES = {"success"}
_FAILED_STATUSES = {"cancel", "cancelled", "error", "failed", "expired"}
_PENDING_STATUSES = {"created", "pending", "processing"}


class LavaConfig(ProviderEnvConfig):
    """All LAVA Business env vars. Lives inside the provider module."""

    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="LAVA_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    SHOP_ID: Optional[str] = None
    SECRET_KEY: Optional[str] = None
    WEBHOOK_SECRET: Optional[str] = None
    BASE_URL: str = Field(default="https://api.lava.ru")
    RETURN_URL: Optional[str] = None
    LIFETIME_MINUTES: Optional[int] = None
    INCLUDE_SERVICES: Optional[str] = None

    @field_validator("LIFETIME_MINUTES", mode="before")
    @classmethod
    def _empty_to_none_int(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
        return v

    @field_validator("SHOP_ID", "SECRET_KEY", "WEBHOOK_SECRET", "RETURN_URL", mode="before")
    @classmethod
    def _strip_optional(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def webhook_path(self) -> str:
        return "/webhook/lava"

    def full_webhook_url(self, base: Optional[str]) -> Optional[str]:
        if not base:
            return None
        return f"{base.rstrip('/')}{self.webhook_path}"

    @property
    def include_services_list(self) -> List[str]:
        return [item.strip() for item in (self.INCLUDE_SERVICES or "").split(",") if item.strip()]


class LavaPresentation(ProviderEnvConfig):
    """Admin-tunable button text/icon overrides for LAVA."""

    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_LAVA_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: Optional[str] = None
    WEBAPP_LABEL_EN: Optional[str] = None
    WEBAPP_ICON: Optional[str] = None
    TELEGRAM_LABEL_RU: Optional[str] = None
    TELEGRAM_LABEL_EN: Optional[str] = None
    TELEGRAM_EMOJI: Optional[str] = None


def _canonical_json(payload: Dict[str, Any]) -> str:
    """JSON with sorted keys, the way legacy LAVA PHP-SDK shops sign webhooks.

    Only used as a webhook-verification fallback: outgoing requests sign the
    exact raw bytes that go on the wire, never a re-serialization. The
    ``signature`` field is dropped and ``float n.0`` collapses to ``int``
    for PHP ``json_encode`` compatibility.
    """

    def normalize(value: Any) -> Any:
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items() if key != "signature"}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    without_sig = {key: normalize(value) for key, value in payload.items() if key != "signature"}
    return json.dumps(without_sig, sort_keys=True, separators=(",", ":"))


class LavaService(HttpClientMixin):
    """Client for LAVA Business API (api.lava.ru).

    Outgoing requests are signed with HMAC-SHA256 over the exact raw body
    bytes using ``LAVA_SECRET_KEY``; the hex digest travels in the
    ``Signature`` HTTP header. Webhooks arrive signed with the shop's
    additional key (``LAVA_WEBHOOK_SECRET``) in the ``Authorization`` header;
    some shops sign the raw body, others a sorted-keys re-serialization, so
    verification accepts either canonicalization.
    """

    def __init__(
        self,
        *,
        bot: Bot,
        settings: Settings,
        config: LavaConfig,
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
            logging.warning("LavaService initialized but not fully configured. Payments disabled.")

    @property
    def configured(self) -> bool:
        return bool(provider_runtime_enabled(self.config) and self.shop_id and self.secret_key)

    @property
    def base_url(self) -> str:
        return (self.config.BASE_URL or "https://api.lava.ru").rstrip("/")

    @property
    def shop_id(self) -> str:
        return (self.config.SHOP_ID or "").strip()

    @property
    def secret_key(self) -> str:
        return (self.config.SECRET_KEY or "").strip()

    @property
    def webhook_secret(self) -> str:
        # LAVA signs webhooks with the shop's "additional key"; merchants that
        # use a single key can leave WEBHOOK_SECRET empty to reuse SECRET_KEY.
        return (self.config.WEBHOOK_SECRET or "").strip() or self.secret_key

    @property
    def return_url(self) -> str:
        return self.config.RETURN_URL or f"https://t.me/{self._default_return_url}"

    @property
    def lifetime_minutes(self) -> Optional[int]:
        return self.config.LIFETIME_MINUTES

    def _hmac_hex(self, message: bytes, key: str) -> str:
        return hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()

    async def _post_signed(self, path: str, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """POST to LAVA signing the exact bytes that go on the wire."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        body_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Signature": self._hmac_hex(body_bytes, self.secret_key),
        }
        session = await self._get_session()
        try:
            async with session.post(url, data=body_bytes, headers=headers) as response:
                response_text = await response.text()
                try:
                    response_data = json.loads(response_text) if response_text else {}
                except json.JSONDecodeError:
                    logging.error("LAVA %s: invalid JSON response: %s", path, response_text[:500])
                    return False, {"status": response.status, "message": "invalid_json"}
                if not isinstance(response_data, dict):
                    response_data = {"data": response_data}
                api_status = str(response_data.get("status") or "").lower()
                if response.status != 200 or api_status == "error":
                    logging.error(
                        "LAVA %s: API error (http=%s, body=%s)",
                        path,
                        response.status,
                        response_data,
                    )
                    return False, {
                        "status": response.status,
                        "message": response_data.get("error")
                        or response_data.get("message")
                        or "lava_api_error",
                        "code": response_data.get("code"),
                    }
                data = response_data.get("data")
                return True, data if isinstance(data, dict) else response_data
        except Exception as exc:
            logging.exception("LAVA %s: request failed.", path)
            return False, {"message": str(exc)}

    async def create_payment(
        self,
        *,
        payment_db_id: int,
        amount: float,
        currency: Optional[str],
        description: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            logging.error("LavaService is not configured. Cannot create payment.")
            return False, {"message": "service_not_configured"}

        currency_code = normalize_payment_currency_code(
            currency or self.settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
        )
        if currency_code != "RUB":
            return False, {
                "message": "unsupported_currency",
                "currency": currency_code,
                "supported_currencies": ["RUB"],
            }

        body: Dict[str, Any] = {
            "sum": float(format_decimal_amount(amount)),
            "orderId": str(payment_db_id),
            "shopId": self.shop_id,
        }
        hook_url = self.config.full_webhook_url(getattr(self.settings, "WEBHOOK_BASE_URL", None))
        if hook_url:
            body["hookUrl"] = hook_url[:500]
        if self.return_url:
            body["successUrl"] = self.return_url[:500]
            body["failUrl"] = self.return_url[:500]
        if self.lifetime_minutes:
            # LAVA accepts 1..7200 minutes (5 days).
            body["expire"] = max(1, min(7200, int(self.lifetime_minutes)))
        if description:
            body["comment"] = description[:255]
        include_services = self.config.include_services_list
        if include_services:
            body["includeService"] = include_services

        return await self._post_signed("/business/invoice/create", body)

    async def get_invoice_status(
        self,
        *,
        order_id: Optional[str] = None,
        invoice_id: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            return False, {"message": "service_not_configured"}
        if not order_id and not invoice_id:
            return False, {"message": "missing_identifier"}

        body: Dict[str, Any] = {"shopId": self.shop_id}
        if invoice_id:
            body["invoiceId"] = str(invoice_id)
        if order_id:
            body["orderId"] = str(order_id)
        return await self._post_signed("/business/invoice/status", body)

    async def try_reuse_pending_payment(self, payment: Any) -> Optional[str]:
        provider_payment_id = str(getattr(payment, "provider_payment_id", None) or "").strip()
        payment_url = str(getattr(payment, "provider_payment_url", None) or "").strip()
        if not provider_payment_id or not payment_url:
            return None

        success, data = await self.get_invoice_status(
            order_id=str(payment.payment_id),
            invoice_id=provider_payment_id,
        )
        if not success or str(data.get("status") or "").lower() not in _PENDING_STATUSES:
            return None
        returned_ids = {str(data.get("id") or ""), str(data.get("invoice_id") or "")}
        if provider_payment_id not in returned_ids:
            return None
        returned_order_id = str(data.get("order_id") or data.get("orderId") or "")
        if returned_order_id and returned_order_id != str(payment.payment_id):
            return None
        return payment_url

    def verify_webhook_signature(self, raw_body: bytes, received_signature: str) -> bool:
        """Verify the ``Authorization`` header HMAC on a LAVA webhook.

        Accepts HMAC of the raw body (current api.lava.ru contract) or of a
        sorted-keys re-serialization (legacy PHP-SDK shops sign that instead).
        """
        received = str(received_signature or "").strip()
        if not received:
            logging.warning("LAVA webhook: missing signature header.")
            return False
        secret = self.webhook_secret
        if not secret:
            logging.error("LAVA webhook: no webhook secret configured.")
            return False

        expected_raw = self._hmac_hex(raw_body, secret)
        if hmac.compare_digest(expected_raw.lower(), received.lower()):
            return True

        try:
            payload = json.loads(raw_body)
        except (ValueError, TypeError):
            return False
        if not isinstance(payload, dict):
            return False
        expected_canonical = self._hmac_hex(_canonical_json(payload).encode("utf-8"), secret)
        return hmac.compare_digest(expected_canonical.lower(), received.lower())

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.json_response({"status": False, "msg": "lava_disabled"}, status=503)

        raw_body = await request.read()
        signature = request.headers.get("Authorization") or request.headers.get("Signature") or ""
        if not self.verify_webhook_signature(raw_body, signature):
            logging.error("LAVA webhook: invalid signature.")
            return web.json_response({"status": False, "msg": "invalid_signature"}, status=403)

        try:
            payload = json.loads(raw_body)
        except (ValueError, TypeError):
            logging.exception("LAVA webhook: failed to parse JSON.")
            return web.json_response({"status": False, "msg": "bad_request"}, status=400)
        if not isinstance(payload, dict):
            logging.error("LAVA webhook: unexpected payload type.")
            return web.json_response({"status": False, "msg": "bad_request"}, status=400)

        provider_payment_id = str(payload.get("invoice_id") or payload.get("id") or "")
        order_id_raw = payload.get("order_id") or payload.get("orderId")
        status = str(payload.get("status") or "").lower()

        async with self.async_session_factory() as session:
            payment = await lookup_payment_by_order_or_provider_id(
                session,
                order_id_raw=order_id_raw,
                provider_payment_id=provider_payment_id or None,
            )
            if not payment:
                logging.error(
                    "LAVA webhook: payment not found (order_id=%s, provider_id=%s)",
                    order_id_raw,
                    provider_payment_id,
                )
                return web.json_response({"status": False, "msg": "payment_not_found"}, status=404)

            resolved_provider_id = provider_payment_id or str(payment.payment_id)
            sale_mode = payment.sale_mode or (
                "traffic" if self.settings.traffic_sale_mode else "subscription"
            )
            payment_months = payment_units_for_activation(payment, sale_mode)

            if status in _SUCCESS_STATUSES:
                if payment.status == "succeeded":
                    logging.info("LAVA webhook: payment %s already succeeded.", payment.payment_id)
                    return web.json_response({"status": True})

                webhook_amount = payload.get("amount")
                if webhook_amount is not None and not decimal_amounts_equal(
                    webhook_amount, payment.amount
                ):
                    logging.error(
                        "LAVA webhook: amount mismatch for payment %s (expected=%s, received=%s)",
                        payment.payment_id,
                        payment.amount,
                        webhook_amount,
                    )
                    return web.json_response(
                        {"status": False, "msg": "amount_mismatch"}, status=400
                    )

                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        resolved_provider_id,
                        PAYMENT_STATUS_PENDING_FINALIZATION,
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logging.exception(
                        "LAVA webhook: failed to mark payment %s as succeeded.",
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
                        provider_subscription="lava",
                        provider_notification="lava",
                        db_user=payment.user,
                        log_prefix="LAVA webhook",
                    )
                )
                if outcome is None:
                    return web.json_response(
                        {"status": False, "msg": "processing_error"}, status=500
                    )
                return web.json_response({"status": True})

            if status in _FAILED_STATUSES:
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
                        "LAVA webhook: failed to mark payment %s as failed.",
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

            if status in _PENDING_STATUSES:
                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        resolved_provider_id,
                        "pending_lava",
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logging.exception(
                        "LAVA webhook: failed to update pending status for %s.",
                        resolved_provider_id,
                    )
                return web.json_response({"status": True})

            logging.warning(
                "LAVA webhook: unhandled status '%s' for payment %s",
                status,
                resolved_provider_id,
            )
            return web.json_response({"status": True})


async def lava_webhook_route(request: web.Request) -> web.Response:
    service: LavaService = app_required(request, "lava_service", LavaService)
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_lava_router")


@router.callback_query(F.data.startswith("pay_lava:"))
async def pay_lava_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    lava_service: LavaService,
    session: AsyncSession,
) -> None:
    await run_callback_payment(_DESCRIPTOR, callback, settings, i18n_data, lava_service, session)


def create_service(ctx: ServiceFactoryContext) -> LavaService:
    bundle = ctx.config_for("lava_service")
    config = bundle.config if bundle and isinstance(bundle.config, LavaConfig) else LavaConfig()
    return LavaService(
        bot=ctx.bot,
        settings=ctx.settings,
        config=config,
        i18n=ctx.i18n,
        async_session_factory=ctx.async_session_factory,
        subscription_service=ctx.subscription_service,
        referral_service=ctx.referral_service,
        default_return_url=ctx.bot_username_for_default_return,
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_DESCRIPTOR, ctx)


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> Optional[str]:
    return await run_reuse_webapp_payment(_DESCRIPTOR, ctx, payment)


_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="LAVA",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_LAVA_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_LAVA_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_LAVA_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "CreditCard",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_LAVA_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_LAVA_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_LAVA_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            "💳",
            "TELEGRAM_EMOJI",
        ),
    )
)

_CONFIG_MANIFEST = (
    ProviderManifestField("LAVA_ENABLED", "bool", "Включена", subsection="LAVA", attr="ENABLED"),
    ProviderManifestField("LAVA_SHOP_ID", "string", "Shop ID", subsection="LAVA", attr="SHOP_ID"),
    ProviderManifestField(
        "LAVA_SECRET_KEY",
        "string",
        "Secret key",
        description="Signs outgoing API requests (HMAC-SHA256 in the Signature header).",
        subsection="LAVA",
        secret=True,
        attr="SECRET_KEY",
    ),
    ProviderManifestField(
        "LAVA_WEBHOOK_SECRET",
        "string",
        "Webhook secret",
        description=(
            "The shop's additional key used to verify webhook signatures. "
            "Leave empty to reuse the secret key."
        ),
        subsection="LAVA",
        secret=True,
        attr="WEBHOOK_SECRET",
    ),
    ProviderManifestField(
        "LAVA_BASE_URL",
        "url",
        "Base URL",
        placeholder="https://api.lava.ru",
        subsection="LAVA",
        attr="BASE_URL",
    ),
    ProviderManifestField(
        "LAVA_RETURN_URL", "url", "Return URL", subsection="LAVA", attr="RETURN_URL"
    ),
    ProviderManifestField(
        "LAVA_LIFETIME_MINUTES",
        "int",
        "Payment link lifetime (minutes)",
        description="1..7200; leave empty for the LAVA default.",
        subsection="LAVA",
        min=1,
        max=7200,
        attr="LIFETIME_MINUTES",
    ),
    ProviderManifestField(
        "LAVA_INCLUDE_SERVICES",
        "string",
        "Payment services filter",
        description=(
            "Comma-separated LAVA pay services to show on the payment page "
            "(e.g. card,sbp). Empty shows everything enabled for the shop."
        ),
        placeholder="card,sbp",
        subsection="LAVA",
        attr="INCLUDE_SERVICES",
    ),
)


SPEC = PaymentProviderSpec(
    id="lava",
    provider_key="lava",
    label="LAVA",
    webapp_label="LAVA",
    webapp_labels={"ru": "LAVA", "en": "LAVA"},
    webapp_icon="CreditCard",
    telegram_labels={"ru": "LAVA", "en": "LAVA"},
    telegram_emoji="💳",
    pending_status="pending_lava",
    enabled=lambda config: bool(getattr(config, "ENABLED", False)),
    service_key="lava_service",
    callback_prefix="pay_lava",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/lava",
    webhook_route=lava_webhook_route,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=LavaConfig,
    presentation_class=LavaPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supported_currencies=("RUB",),
    currency_support_note="LAVA Business invoices are issued in RUB only.",
    currency_support_url="https://dev.lava.ru/",
)


async def _create_payment(service: LavaService, req: CreatePaymentRequest) -> CreateResult:
    return await service.create_payment(
        payment_db_id=req.payment.payment_id,
        amount=req.amount,
        currency=req.currency,
        description=req.description,
    )


async def _reuse_payment(service: LavaService, payment: Any) -> Optional[str]:
    return await service.try_reuse_pending_payment(payment)


_DESCRIPTOR: LinkPaymentDescriptor[LavaService] = LinkPaymentDescriptor(
    spec=SPEC,
    provider_key="lava",
    pending_status="pending_lava",
    display_name="LAVA",
    log_prefix=_LOG,
    service_app_key="lava_service",
    service_type=LavaService,
    create=_create_payment,
    reuse=_reuse_payment,
    extract_url=lambda r: first_value(r, "url", "payment_url", "paymentUrl"),
    extract_provider_id=lambda r: first_value(r, "id", "invoice_id"),
)
