import asyncio
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qsl

from aiogram import Bot, F, Router, types
from aiohttp import web
from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.services.referral_service import ReferralService
from bot.services.subscription_service import SubscriptionService
from bot.utils.request_security import ip_in_allowlist, request_client_ip
from config.settings import Settings
from db.dal import payment_dal

from .base import (
    PaymentProviderSpec,
    ProviderEnvConfig,
    ProviderManifestField,
    ServiceFactoryContext,
    WebAppPaymentContext,
    provider_env_file,
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
    make_translator,
    notify_callback_parse_error,
    notify_payment_record_failure,
    notify_service_unavailable,
    parse_payment_callback,
    payment_failed,
    payment_unavailable,
    post_json_request,
    render_link_or_fail,
)

_LOG = "freekassa"


class FreeKassaConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="FREEKASSA_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    MERCHANT_ID: Optional[str] = None
    FIRST_SECRET: Optional[str] = None
    SECOND_SECRET: Optional[str] = None
    PAYMENT_URL: str = Field(default="https://pay.freekassa.ru/")
    API_KEY: Optional[str] = None
    PAYMENT_IP: Optional[str] = None
    PAYMENT_METHOD_ID: Optional[int] = None
    TRUSTED_IPS: str = Field(default="168.119.157.136,168.119.60.227,178.154.197.79,51.250.54.238")

    @field_validator("PAYMENT_METHOD_ID", mode="before")
    @classmethod
    def _empty_to_none_int(cls, v):
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
    def _strip_optional(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def webhook_path(self) -> str:
        return "/webhook/freekassa"

    @property
    def trusted_ips_list(self) -> list:
        return [item.strip() for item in (self.TRUSTED_IPS or "").split(",") if item.strip()]


class FreeKassaPresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_FREEKASSA_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: Optional[str] = None
    WEBAPP_LABEL_EN: Optional[str] = None
    WEBAPP_ICON: Optional[str] = None
    TELEGRAM_LABEL_RU: Optional[str] = None
    TELEGRAM_LABEL_EN: Optional[str] = None
    TELEGRAM_EMOJI: Optional[str] = None


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
    ):
        self.bot = bot
        self.settings = settings
        self.config = config
        self.i18n = i18n
        self.async_session_factory = async_session_factory
        self.subscription_service = subscription_service
        self.referral_service = referral_service

        self.default_currency: str = (settings.DEFAULT_CURRENCY_SYMBOL or "RUB").upper()

        self.api_base_url: str = "https://api.fk.life/v1"
        self._init_http_client(total_timeout=15)
        self._nonce_lock = asyncio.Lock()
        self._last_nonce = int(time.time() * 1000)

        if not self.configured:
            logging.warning(
                "FreeKassaService initialized but not fully configured. Payments disabled."
            )
        if config.ENABLED and not self.server_ip:
            logging.warning(
                "FreeKassaService: FREEKASSA_PAYMENT_IP is not set. Requests may be rejected by the provider."  # noqa: E501
            )

    @property
    def configured(self) -> bool:
        return bool(self.config.ENABLED and self.shop_id and self.api_key)

    @property
    def shop_id(self):
        return self.config.MERCHANT_ID

    @property
    def api_key(self):
        return self.config.API_KEY

    @property
    def second_secret(self):
        return self.config.SECOND_SECRET

    @property
    def server_ip(self):
        return self.config.PAYMENT_IP

    @property
    def payment_method_id(self):
        return self.config.PAYMENT_METHOD_ID

    async def create_order(
        self,
        *,
        payment_db_id: int,
        user_id: int,
        months: int,
        amount: float,
        currency: Optional[str],
        email: Optional[str] = None,
        ip_address: Optional[str] = None,
        payment_method_id: Optional[int] = None,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            logging.error("FreeKassaService is not configured. Cannot create order.")
            return False, {"message": "service_not_configured"}

        ip_address = ip_address or self.server_ip
        if not ip_address:
            logging.error("FreeKassaService: payment IP is required but not configured.")
            return False, {"message": "missing_ip"}

        email = email or f"{user_id}@telegram.org"
        currency_code = (currency or self.default_currency or "RUB").upper()

        payload: Dict[str, Any] = {
            "shopId": int(self.shop_id),
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

    async def _generate_nonce(self) -> int:
        async with self._nonce_lock:
            candidate = int(time.time() * 1000)
            if candidate <= self._last_nonce:
                candidate = self._last_nonce + 1
            self._last_nonce = candidate
            return candidate

    def _sign_payload(self, payload: Dict[str, Any]) -> str:
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
        return hmac.compare_digest(expected_signature, provided_signature)

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.Response(status=503, text="freekassa_disabled")

        try:
            client_ip = request_client_ip(request, trusted_proxies=self.settings.trusted_proxies)
            trusted = self.config.trusted_ips_list
            if not ip_in_allowlist(client_ip, trusted):
                logging.warning(
                    "FreeKassa webhook denied from unauthorized IP source "
                    "(client_ip=%s remote=%s x_forwarded_for=%s trusted_ips=%s "
                    "trusted_proxies=%s).",
                    client_ip,
                    request.remote,
                    request.headers.get("X-Forwarded-For"),
                    trusted,
                    self.settings.trusted_proxies,
                )
                return web.Response(status=403)

            raw_body = await request.read()
        except Exception:
            logging.exception("FreeKassa webhook: failed to read request body.")
            return web.Response(status=400, text="bad_request")

        payload_dict: Dict[str, Any] = {}
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

        def _get(key: str, default: Optional[str] = None) -> Optional[str]:
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
            logging.error("FreeKassa webhook: invalid order_id value %r", order_id_str)
            return web.Response(status=400, text="invalid_order_id")

        async with self.async_session_factory() as session:
            payment = await payment_dal.get_payment_by_db_id(session, payment_db_id)
            if not payment:
                logging.error("FreeKassa webhook: payment %s not found", payment_db_id)
                return web.Response(status=404, text="payment_not_found")

            if payment.status == "succeeded":
                logging.info("FreeKassa webhook: payment %s already succeeded", payment_db_id)
                return web.Response(text="YES")

            try:
                if not decimal_amounts_equal(amount_str, payment.amount):
                    logging.warning(
                        "FreeKassa webhook: amount mismatch for payment %s (expected %s, got %s)",
                        payment_db_id,
                        format_decimal_amount(payment.amount),
                        format_decimal_amount(amount_str),
                    )
            except Exception as exc:
                logging.warning(
                    "FreeKassa webhook: failed to compare amount for payment %s: %s",
                    payment_db_id,
                    exc,
                )

            resolved_provider_id = str(provider_payment_id or f"freekassa:{order_id_str}")
            try:
                await payment_dal.update_provider_payment_and_status(
                    session=session,
                    payment_db_id=payment.payment_id,
                    provider_payment_id=resolved_provider_id,
                    new_status="succeeded",
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logging.exception(
                    "FreeKassa webhook: failed to mark payment %s as succeeded.", payment_db_id
                )
                return web.Response(status=500, text="processing_error")

            months = payment.purchased_gb or payment.subscription_duration_months or 1
            sale_mode = payment.sale_mode or (
                "traffic" if self.settings.traffic_sale_mode else "subscription"
            )

            success_prefix: Optional[str] = None
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
                    date=datetime.now().strftime("%Y-%m-%d"),
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
                    currency=self.default_currency,
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
    service: FreeKassaService = request.app["freekassa_service"]
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_freekassa_router")


@router.callback_query(F.data.startswith("pay_fk:"))
async def pay_fk_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    freekassa_service: FreeKassaService,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    translator = make_translator(i18n, current_lang)

    if not i18n or not callback.message:
        await notify_callback_parse_error(callback, translator)
        return

    if not freekassa_service or not freekassa_service.configured:
        logging.error("FreeKassa service is not configured or unavailable.")
        await notify_service_unavailable(callback, translator)
        return

    parts = parse_payment_callback(callback.data or "")
    if not parts:
        logging.error("Invalid pay_fk data in callback: %s", callback.data)
        await notify_callback_parse_error(callback, translator)
        return

    currency_code = (
        getattr(freekassa_service, "default_currency", None)
        or settings.DEFAULT_CURRENCY_SYMBOL
        or "RUB"
    )
    payment_description = describe_payment(translator, parts)
    record_payload = build_payment_record_payload(
        user_id=callback.from_user.id,
        amount=parts.price,
        currency=currency_code,
        status="pending_freekassa",
        description=payment_description,
        months=parts.months,
        provider="freekassa",
        sale_mode=parts.sale_mode,
    )

    try:
        payment_record = await payment_dal.create_payment_record(session, record_payload)
        await session.commit()
    except Exception:
        await session.rollback()
        logging.exception(
            "FreeKassa: failed to create payment record for user %s.", callback.from_user.id
        )
        await notify_payment_record_failure(callback, translator)
        return

    success, response_data = await freekassa_service.create_order(
        payment_db_id=payment_record.payment_id,
        user_id=payment_record.user_id,
        months=parts.months,
        amount=parts.price,
        currency=freekassa_service.default_currency,
        payment_method_id=freekassa_service.payment_method_id,
        ip_address=freekassa_service.server_ip,
        extra_params={
            "us_method": freekassa_service.payment_method_id,
        },
    )

    location = first_value(response_data, "location")
    provider_identifier = first_value(response_data, "orderHash", "orderId")
    lead_text: Optional[str] = None
    if success and location:
        order_id_display = (
            first_value(response_data, "orderId")
            or provider_identifier
            or str(payment_record.payment_id)
        )
        lead_text = translator(
            "free_kassa_order_info",
            order_id=order_id_display,
            date=datetime.now().strftime("%Y-%m-%d"),
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
        payment_url=location,
        provider_payment_id=provider_identifier,
        lead_text=lead_text,
        log_prefix=_LOG,
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
    service: FreeKassaService = ctx.request.app["freekassa_service"]
    if not service or not service.configured or not service.payment_method_id:
        return payment_unavailable()

    try:
        payment = await create_webapp_payment_record(
            ctx,
            amount=ctx.price,
            currency=service.default_currency,
            status="pending_freekassa",
            provider="freekassa",
        )
        success, response_data = await service.create_order(
            payment_db_id=payment.payment_id,
            user_id=ctx.user_id,
            months=ctx.months,
            amount=ctx.price,
            currency=service.default_currency,
            payment_method_id=service.payment_method_id,
            ip_address=service.server_ip,
            extra_params={"us_method": service.payment_method_id},
        )
    except Exception:
        await ctx.session.rollback()
        logging.exception("FreeKassa WebApp payment failed")
        return payment_failed()

    return await finalize_webapp_link_payment(
        session=ctx.session,
        payment=payment,
        api_success=success,
        payment_url=first_value(response_data, "location") if success else None,
        provider_payment_id=first_value(response_data, "orderHash", "orderId"),
        log_prefix="FreeKassa",
    )


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
        placeholder="https://pay.freekassa.ru/",
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
    config_class=FreeKassaConfig,
    presentation_class=FreeKassaPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
)
