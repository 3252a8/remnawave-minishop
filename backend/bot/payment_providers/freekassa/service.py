import asyncio
import hashlib
import hmac
import json
import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl

from aiogram import Bot, F, Router, types
from aiohttp import web
from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from config.tariffs_config import default_payment_currency_code_for_settings
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
    CreatePaymentRequest,
    CreateResult,
    HttpClientMixin,
    LinkPaymentDescriptor,
    PaymentSuccessRequest,
    check_webhook_source_ip,
    constant_time_compare,
    finalize_successful_payment,
    first_value,
    format_decimal_amount,
    make_translator,
    payment_amount_matches,
    payment_units_for_activation,
    post_json_request,
    run_callback_payment,
    run_reuse_webapp_payment,
    run_webapp_payment,
)
from ..shared.app_context import app_required

if TYPE_CHECKING:
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService
else:
    ReferralService = object
    SubscriptionService = object

logger = logging.getLogger(__name__)

_LOG = "freekassa"
FREEKASSA_SUPPORTED_CURRENCIES = ("RUB", "USD", "EUR", "UAH", "KZT")


class FreeKassaConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="FREEKASSA_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    MERCHANT_ID: str | None = None
    FIRST_SECRET: str | None = None
    SECOND_SECRET: str | None = None
    PAYMENT_URL: str = Field(default="https://pay.freekassa.net/")
    API_KEY: str | None = None
    PAYMENT_IP: str | None = None
    PAYMENT_METHOD_ID: int | None = None
    TRUSTED_IPS: str = Field(default="168.119.157.136,168.119.60.227,178.154.197.79,51.250.54.238")

    @field_validator("PAYMENT_METHOD_ID", mode="before")
    @classmethod
    def _empty_to_none_int(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
        return v

    @field_validator(
        "MERCHANT_ID",
        "FIRST_SECRET",
        "SECOND_SECRET",
        "API_KEY",
        "PAYMENT_IP",
        mode="before",
    )
    @classmethod
    def _strip_optional(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def webhook_path(self) -> str:
        return "/webhook/freekassa"

    @property
    def trusted_ips_list(self) -> list[str]:
        return [item.strip() for item in (self.TRUSTED_IPS or "").split(",") if item.strip()]


class FreeKassaPresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_FREEKASSA_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: str | None = None
    WEBAPP_LABEL_EN: str | None = None
    WEBAPP_ICON: str | None = None
    TELEGRAM_LABEL_RU: str | None = None
    TELEGRAM_LABEL_EN: str | None = None
    TELEGRAM_EMOJI: str | None = None


class FreeKassaService(HttpClientMixin):
    def __init__(
        self,
        *,
        bot: Bot,
        settings: Settings,
        config: FreeKassaConfig,
        i18n: JsonI18n,
        async_session_factory: sessionmaker,
        subscription_service: SubscriptionService,
        referral_service: ReferralService,
    ) -> None:
        self.bot = bot
        self.settings = settings
        self.config = config
        self.i18n = i18n
        self.async_session_factory = async_session_factory
        self.subscription_service = subscription_service
        self.referral_service = referral_service

        self.default_currency: str = default_payment_currency_code_for_settings(settings).upper()

        self.api_base_url: str = "https://api.fk.life/v1"
        self._init_http_client(total_timeout=lambda: self.settings.PAYMENT_REQUEST_TIMEOUT_SECONDS)
        self._nonce_lock = asyncio.Lock()
        self._last_nonce = int(time.time() * 1000)

        if not self.configured:
            logger.warning(
                "FreeKassaService initialized but not fully configured. Payments disabled."
            )
        if provider_runtime_enabled(config) and not self.server_ip:
            logger.warning(
                "FreeKassaService: FREEKASSA_PAYMENT_IP is not set. Requests may be rejected by the provider."  # noqa: E501
            )

    @property
    def configured(self) -> bool:
        return bool(provider_runtime_enabled(self.config) and self.shop_id and self.api_key)

    @property
    def shop_id(self) -> str | None:
        return self.config.MERCHANT_ID

    @property
    def api_key(self) -> str | None:
        return self.config.API_KEY

    @property
    def second_secret(self) -> str | None:
        return self.config.SECOND_SECRET

    @property
    def server_ip(self) -> str | None:
        return self.config.PAYMENT_IP

    @property
    def payment_method_id(self) -> int | None:
        return self.config.PAYMENT_METHOD_ID

    async def create_order(
        self,
        *,
        payment_db_id: int,
        user_id: int,
        months: float,
        amount: float,
        currency: str | None,
        email: str | None = None,
        ip_address: str | None = None,
        payment_method_id: int | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        if not self.configured:
            logger.error("FreeKassaService is not configured. Cannot create order.")
            return False, {"message": "service_not_configured"}

        ip_address = ip_address or self.server_ip
        if not ip_address:
            logger.error("FreeKassaService: payment IP is required but not configured.")
            return False, {"message": "missing_ip"}

        email = email or f"{user_id}@telegram.org"
        currency_code = normalize_payment_currency_code(currency or self.default_currency or "RUB")
        if currency_code not in FREEKASSA_SUPPORTED_CURRENCIES:
            return False, {
                "message": "unsupported_currency",
                "currency": currency_code,
                "supported_currencies": list(FREEKASSA_SUPPORTED_CURRENCIES),
            }
        if payment_method_id is None:
            logger.error("FreeKassaService: payment method id is required but not configured.")
            return False, {"message": "missing_payment_method_id"}
        shop_id = self.shop_id
        if shop_id is None:
            return False, {"message": "missing_shop_id"}

        payload: dict[str, Any] = {
            "shopId": int(shop_id),
            "nonce": await self._generate_nonce(),
            "paymentId": str(payment_db_id),
            "i": int(payment_method_id),
            "amount": f"{format_decimal_amount(amount):.2f}",
            "currency": currency_code,
            "email": email,
            "ip": ip_address,
            "us_user_id": str(user_id),
            "us_months": str(months),
            "us_payment_db_id": str(payment_db_id),
        }

        if extra_params:
            for key, value in extra_params.items():
                if value is None:
                    continue
                payload[key] = value

        payload["signature"] = self._sign_payload(payload)

        session = await self._get_session()
        return await post_json_request(
            session,
            f"{self.api_base_url}/orders/create",
            body=payload,
            log_prefix="FreeKassa create_order",
            # FreeKassa returns ``{"type": "success", ...}`` on success.
            is_success=lambda status, data: status == 200 and (data or {}).get("type") == "success",
        )

    async def get_orders(
        self,
        *,
        payment_id: int,
        order_status: int | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        if not self.configured:
            return False, {"message": "service_not_configured"}
        shop_id = self.shop_id
        if shop_id is None:
            return False, {"message": "missing_shop_id"}

        payload: dict[str, Any] = {
            "shopId": int(shop_id),
            "nonce": await self._generate_nonce(),
            "paymentId": str(payment_id),
        }
        if order_status is not None:
            payload["orderStatus"] = int(order_status)
        payload["signature"] = self._sign_payload(payload)

        session = await self._get_session()
        return await post_json_request(
            session,
            f"{self.api_base_url}/orders",
            body=payload,
            log_prefix="FreeKassa get_orders",
            is_success=lambda status, data: status == 200 and (data or {}).get("type") == "success",
        )

    async def try_reuse_pending_order(self, payment: Any) -> str | None:
        order_hash = str(getattr(payment, "provider_payment_id", None) or "").strip()
        if not order_hash:
            return None

        success, response_data = await self.get_orders(
            payment_id=payment.payment_id,
            order_status=0,
        )
        if not success:
            return None

        for order in response_data.get("orders") or []:
            if not isinstance(order, dict):
                continue
            try:
                is_new = int(order.get("status", -1)) == 0
            except (TypeError, ValueError):
                continue
            if not is_new:
                continue
            if str(order.get("merchant_order_id") or "") != str(payment.payment_id):
                continue
            fk_order_id = str(order.get("fk_order_id") or "").strip()
            if fk_order_id:
                payment_url = (self.config.PAYMENT_URL or "https://pay.freekassa.net/").rstrip("/")
                return f"{payment_url}/form/{fk_order_id}/{order_hash}"
        return None

    async def _verify_paid_order(self, payment: Any) -> tuple[bool, str]:
        """Verify the settled FreeKassa order, including its invoice currency.

        FreeKassa's signed Result URL contains ``AMOUNT`` but ``CUR_ID`` is a
        payment-method identifier (for example, a bank card), not the invoice
        currency.  The authenticated Orders API is therefore the authoritative
        source for the settled currency.
        """

        success, response_data = await self.get_orders(
            payment_id=payment.payment_id,
            order_status=1,
        )
        if not success:
            logger.warning(
                "FreeKassa webhook: provider order lookup unavailable for payment %s: %s",
                payment.payment_id,
                response_data,
            )
            return False, "order_verification_unavailable"

        order: dict[str, Any] | None = None
        for candidate in response_data.get("orders") or []:
            if not isinstance(candidate, dict):
                continue
            if str(candidate.get("merchant_order_id") or "") != str(payment.payment_id):
                continue
            try:
                if int(candidate.get("status", -1)) != 1:
                    continue
            except (TypeError, ValueError):
                continue
            order = candidate
            break

        if order is None:
            logger.warning(
                "FreeKassa webhook: paid provider order was not found for payment %s",
                payment.payment_id,
            )
            return False, "order_not_paid"

        order_currency = normalize_payment_currency_code(order.get("currency"), default="")
        expected_currency = normalize_payment_currency_code(payment.currency, default="")
        if not order_currency or order_currency != expected_currency:
            logger.error(
                "FreeKassa webhook: currency mismatch for payment %s (expected=%s, received=%s)",
                payment.payment_id,
                payment.currency,
                order.get("currency"),
            )
            return False, "currency_mismatch"

        if not payment_amount_matches(
            expected_amount=payment.amount,
            received_amount=order.get("amount"),
        ):
            logger.error(
                "FreeKassa webhook: provider order amount mismatch for payment %s "
                "(expected=%s, received=%s)",
                payment.payment_id,
                payment.amount,
                order.get("amount"),
            )
            return False, "amount_mismatch"

        return True, ""

    async def _generate_nonce(self) -> int:
        async with self._nonce_lock:
            candidate = int(time.time() * 1000)
            if candidate <= self._last_nonce:
                candidate = self._last_nonce + 1
            self._last_nonce = candidate
            return candidate

    def _sign_payload(self, payload: dict[str, Any]) -> str:
        if not self.api_key:
            raise RuntimeError("FreeKassa API key is not configured.")
        items = [
            (key, value)
            for key, value in payload.items()
            if key != "signature" and value is not None
        ]
        items.sort(key=lambda pair: pair[0])
        message = "|".join(str(value) for _, value in items)
        return hmac.new(
            self.api_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _validate_signature(self, raw_body: bytes, provided_signature: str) -> bool:
        if not provided_signature or not self.second_secret:
            return False
        expected_signature = hmac.new(
            self.second_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return constant_time_compare(expected_signature, provided_signature)

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.Response(status=503, text="freekassa_disabled")

        try:
            trusted = self.config.trusted_ips_list
            ip_check = check_webhook_source_ip(
                request,
                trusted_ips=trusted,
                trusted_proxies=self.settings.trusted_proxies,
                allow_empty=False,
            )
            if not ip_check.allowed:
                logger.warning(
                    "FreeKassa webhook denied from unauthorized IP source "
                    "(client_ip=%s remote=%s x_forwarded_for=%s).",
                    ip_check.client_ip,
                    request.remote,
                    request.headers.get("X-Forwarded-For"),
                )
                return web.Response(status=403)

            raw_body = await request.read()
        except Exception:
            logger.exception("FreeKassa webhook: failed to read request body.")
            return web.Response(status=400, text="bad_request")

        payload_dict: dict[str, Any] = {}
        if raw_body:
            try:
                if request.content_type.startswith("application/json"):
                    decoded_json = json.loads(raw_body.decode("utf-8"))
                    if isinstance(decoded_json, dict):
                        payload_dict = {str(k): v for k, v in decoded_json.items()}
                else:
                    payload_dict = {
                        str(key): value
                        for key, value in parse_qsl(
                            raw_body.decode("utf-8"), keep_blank_values=True
                        )
                    }
            except Exception:
                payload_dict = {}

        def _get(key: str, default: str | None = None) -> str | None:
            return payload_dict.get(key) or payload_dict.get(key.lower()) or default

        merchant_id = _get("MERCHANT_ID")
        if merchant_id != self.shop_id:
            return web.Response(status=403)

        signature = _get("SIGN") or _get("signature")
        if not signature:
            return web.Response(status=400, text="missing_signature")

        order_id_str = _get("MERCHANT_ORDER_ID") or _get("ORDER_ID") or _get("o")
        amount_str = _get("AMOUNT") or _get("OA") or _get("amount")
        provider_payment_id = _get("intid") or _get("payment_id") or _get("transaction_id")

        if not order_id_str or not amount_str:
            return web.Response(status=400, text="missing_data")

        if not self._validate_signature(raw_body, signature):
            return web.Response(status=403, text="invalid_signature")

        try:
            payment_db_id = int(order_id_str)
        except (TypeError, ValueError):
            logger.error("FreeKassa webhook: invalid order_id value %r", order_id_str)
            return web.Response(status=400, text="invalid_order_id")

        async with self.async_session_factory() as session:
            payment = await payment_dal.get_payment_by_db_id(session, payment_db_id)
            if not payment:
                logger.error("FreeKassa webhook: payment %s not found", payment_db_id)
                return web.Response(status=404, text="payment_not_found")

            if payment.status == "succeeded":
                logger.info("FreeKassa webhook: payment %s already succeeded", payment_db_id)
                return web.Response(text="YES")

            if not payment_amount_matches(
                expected_amount=payment.amount,
                received_amount=amount_str,
            ):
                logger.error(
                    "FreeKassa webhook: amount mismatch for payment %s (expected=%s, received=%s)",
                    payment_db_id,
                    payment.amount,
                    amount_str,
                )
                return web.Response(status=400, text="amount_mismatch")

            order_verified, verification_error = await self._verify_paid_order(payment)
            if not order_verified:
                # The provider retries Result URL delivery until it sees YES.
                # A transient Orders API failure is retried; a verified mismatch
                # is deliberately never finalized locally.
                status = 503 if verification_error == "order_verification_unavailable" else 400
                return web.Response(status=status, text=verification_error)

            resolved_provider_id = str(provider_payment_id or f"freekassa:{order_id_str}")
            try:
                payment = await payment_dal.claim_payment_finalization(
                    session,
                    payment.payment_id,
                    provider_payment_id=resolved_provider_id,
                )
                if payment is None:
                    return web.Response(text="YES")
            except Exception:
                await session.rollback()
                logger.exception(
                    "FreeKassa webhook: failed to mark payment %s as succeeded.", payment_db_id
                )
                return web.Response(status=500, text="processing_error")

            sale_mode = payment.sale_mode or (
                "traffic" if self.settings.traffic_sale_mode else "subscription"
            )
            months = payment_units_for_activation(payment, sale_mode)

            success_prefix: str | None = None
            if provider_payment_id:
                # FreeKassa-specific: prepend "Order N from YYYY-MM-DD" to the success text.
                # ``i18n`` is resolved inside ``finalize_successful_payment`` per user language,
                # so the prefix is built in the admin/default language too — kept here for parity
                # with the original behavior, which used the same key.
                admin_lang = self.settings.DEFAULT_LANGUAGE
                translator = make_translator(self.i18n, admin_lang)
                success_prefix = translator(
                    "free_kassa_order_full",
                    order_id=provider_payment_id,
                    date=datetime.now(UTC).strftime("%Y-%m-%d"),
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
                    months=months,
                    traffic_amount=float(months),
                    provider_subscription="freekassa",
                    provider_notification="freekassa",
                    db_user=payment.user,
                    log_prefix="FreeKassa webhook",
                    text_prefix=success_prefix,
                )
            )
            if outcome is None:
                return web.Response(status=500, text="processing_error")

        return web.Response(text="YES")


async def freekassa_webhook_route(request: web.Request) -> web.Response:
    service: FreeKassaService = app_required(request, "freekassa_service", FreeKassaService)
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_freekassa_router")


@router.callback_query(F.data.startswith("pay_fk:"))
async def pay_fk_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    freekassa_service: FreeKassaService,
    session: AsyncSession,
) -> None:
    await run_callback_payment(
        _DESCRIPTOR, callback, settings, i18n_data, freekassa_service, session
    )


def create_service(ctx: ServiceFactoryContext) -> FreeKassaService:
    bundle = ctx.config_for("freekassa_service")
    config = (
        bundle.config
        if bundle and isinstance(bundle.config, FreeKassaConfig)
        else FreeKassaConfig()
    )
    return FreeKassaService(
        bot=ctx.bot,
        settings=ctx.settings,
        config=config,
        i18n=ctx.i18n,
        async_session_factory=ctx.async_session_factory,
        subscription_service=ctx.subscription_service,
        referral_service=ctx.referral_service,
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_DESCRIPTOR, ctx)


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> str | None:
    return await run_reuse_webapp_payment(_DESCRIPTOR, ctx, payment)


_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="FreeKassa",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_FREEKASSA_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_FREEKASSA_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_FREEKASSA_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "Smartphone",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_FREEKASSA_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_FREEKASSA_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_FREEKASSA_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            "📱",
            "TELEGRAM_EMOJI",
        ),
    )
)

_CONFIG_MANIFEST = (
    ProviderManifestField(
        "FREEKASSA_ENABLED", "bool", "Включена", subsection="FreeKassa", attr="ENABLED"
    ),
    ProviderManifestField(
        "FREEKASSA_MERCHANT_ID", "string", "Merchant ID", subsection="FreeKassa", attr="MERCHANT_ID"
    ),
    ProviderManifestField(
        "FREEKASSA_FIRST_SECRET",
        "string",
        "First secret",
        subsection="FreeKassa",
        secret=True,
        attr="FIRST_SECRET",
    ),
    ProviderManifestField(
        "FREEKASSA_SECOND_SECRET",
        "string",
        "Second secret",
        subsection="FreeKassa",
        secret=True,
        attr="SECOND_SECRET",
    ),
    ProviderManifestField(
        "FREEKASSA_API_KEY",
        "string",
        "API key",
        subsection="FreeKassa",
        secret=True,
        attr="API_KEY",
    ),
    ProviderManifestField(
        "FREEKASSA_PAYMENT_URL",
        "url",
        "Payment URL",
        placeholder="https://pay.freekassa.net/",
        subsection="FreeKassa",
        attr="PAYMENT_URL",
    ),
    ProviderManifestField(
        "FREEKASSA_PAYMENT_METHOD_ID",
        "int",
        "Payment method ID",
        description="See https://merchant.freekassa.net/settings/currencies",
        subsection="FreeKassa",
        attr="PAYMENT_METHOD_ID",
    ),
    ProviderManifestField(
        "FREEKASSA_PAYMENT_IP",
        "string",
        "Server IP",
        description="Public IP address reported to FreeKassa.",
        subsection="FreeKassa",
        attr="PAYMENT_IP",
    ),
    ProviderManifestField(
        "FREEKASSA_TRUSTED_IPS",
        "string",
        "Trusted IPs",
        description="Comma-separated IP addresses accepted for FreeKassa webhooks.",
        subsection="FreeKassa",
        attr="TRUSTED_IPS",
    ),
)


SPEC = PaymentProviderSpec(
    id="freekassa",
    provider_key="freekassa",
    label="FreeKassa",
    webapp_label="FreeKassa / СБП",
    webapp_labels={"ru": "FreeKassa / СБП", "en": "FreeKassa / SBP"},
    webapp_icon="Smartphone",
    logo_url="/provider-logos/freekassa.png",
    telegram_labels={"ru": "СБП", "en": "SBP"},
    telegram_emoji="📱",
    pending_status="pending_freekassa",
    enabled=lambda config: bool(getattr(config, "ENABLED", False)),
    service_key="freekassa_service",
    callback_prefix="pay_fk",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/freekassa",
    webhook_route=freekassa_webhook_route,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=FreeKassaConfig,
    presentation_class=FreeKassaPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supported_currencies=FREEKASSA_SUPPORTED_CURRENCIES,
    currency_support_note=(
        "FreeKassa SCI documents the payment currency parameter as RUB, USD, EUR, UAH or KZT."
    ),
    info_url="https://freekassa.net/",
    currency_support_url="https://docs.freekassa.net/",
)


async def _create_payment(service: FreeKassaService, req: CreatePaymentRequest) -> CreateResult:
    return await service.create_order(
        payment_db_id=req.payment.payment_id,
        user_id=req.user_id,
        months=req.months,
        amount=req.amount,
        currency=req.currency,
        payment_method_id=service.payment_method_id,
        ip_address=service.server_ip,
        extra_params={"us_method": service.payment_method_id},
    )


async def _reuse_payment(service: FreeKassaService, payment: Any) -> str | None:
    return await service.try_reuse_pending_order(payment)


def _callback_currency(service: FreeKassaService, settings: Settings) -> str:
    return (
        getattr(service, "default_currency", None)
        or default_payment_currency_code_for_settings(settings)
        or "RUB"
    )


def _webapp_currency(
    ctx: WebAppPaymentContext,
    settings: Settings,
    service: FreeKassaService,
) -> str:
    return ctx.currency or service.default_currency


def _callback_lead_text(
    req: CreatePaymentRequest,
    response_data: dict,
    translator: Any,
) -> str | None:
    location = first_value(response_data, "location")
    if not location:
        return None
    provider_identifier = first_value(response_data, "orderHash", "orderId")
    order_id_display = (
        first_value(response_data, "orderId") or provider_identifier or str(req.payment.payment_id)
    )
    return translator(
        "free_kassa_order_info",
        order_id=order_id_display,
        date=datetime.now(UTC).strftime("%Y-%m-%d"),
    )


_DESCRIPTOR: LinkPaymentDescriptor[FreeKassaService] = LinkPaymentDescriptor(
    spec=SPEC,
    provider_key="freekassa",
    pending_status="pending_freekassa",
    display_name="FreeKassa",
    log_prefix=_LOG,
    service_app_key="freekassa_service",
    service_type=FreeKassaService,
    create=_create_payment,
    reuse=_reuse_payment,
    extract_url=lambda r: first_value(r, "location"),
    extract_provider_id=lambda r: first_value(r, "orderHash", "orderId"),
    callback_currency=_callback_currency,
    callback_lead_text=_callback_lead_text,
    callback_reuse_answer=True,
    webapp_available=lambda service: bool(service.configured and service.payment_method_id),
    webapp_currency=_webapp_currency,
)
