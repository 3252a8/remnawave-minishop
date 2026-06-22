import hashlib
import hmac
import json
import logging
import secrets
from typing import Any, Dict, Optional, Tuple

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
from config.tariffs_config import (
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
)
from db.dal import payment_dal

from ..base import (
    PaymentProviderSpec,
    ProviderEnvConfig,
    ProviderManifestField,
    ServiceFactoryContext,
    WebAppPaymentContext,
    normalize_payment_currency_code,
    parse_supported_currency_codes,
    provider_env_file,
    provider_runtime_enabled,
)
from ..shared import (
    PAYMENT_STATUS_PENDING_FINALIZATION,
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
    payment_record_amounts,
    payment_unavailable,
    payment_units_for_activation,
    post_json_request,
    quote_hwid_callback_parts,
    render_link_or_fail,
    render_payment_link,
)

_LOG = "severpay"


class SeverPayConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="SEVERPAY_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    MID: Optional[int] = None
    TOKEN: Optional[str] = None
    RETURN_URL: Optional[str] = None
    BASE_URL: str = Field(default="https://severpay.io/api/merchant")
    LIFETIME_MINUTES: Optional[int] = None
    SUPPORTED_CURRENCIES: str = Field(default="RUB,USD")

    @field_validator("MID", "LIFETIME_MINUTES", mode="before")
    @classmethod
    def _empty_to_none_int(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
        return v

    @field_validator("TOKEN", "RETURN_URL", mode="before")
    @classmethod
    def _strip_optional(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def webhook_path(self) -> str:
        return "/webhook/severpay"


class SeverPayPresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_SEVERPAY_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: Optional[str] = None
    WEBAPP_LABEL_EN: Optional[str] = None
    WEBAPP_ICON: Optional[str] = None
    TELEGRAM_LABEL_RU: Optional[str] = None
    TELEGRAM_LABEL_EN: Optional[str] = None
    TELEGRAM_EMOJI: Optional[str] = None


class SeverPayService(HttpClientMixin):
    def __init__(
        self,
        *,
        bot: Bot,
        settings: Settings,
        config: SeverPayConfig,
        i18n: JsonI18n,
        async_session_factory: sessionmaker,
        subscription_service: SubscriptionService,
        referral_service: ReferralService,
        default_return_url: str,
    ):
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
            logging.warning(
                "SeverPayService initialized but not fully configured. Payments disabled."
            )

    @property
    def configured(self) -> bool:
        return bool(provider_runtime_enabled(self.config) and self.mid and self.token)

    @property
    def base_url(self) -> str:
        return (self.config.BASE_URL or "https://severpay.io/api/merchant").rstrip("/")

    @property
    def mid(self):
        return self.config.MID

    @property
    def token(self) -> str:
        return self.config.TOKEN or ""

    @property
    def return_url(self) -> str:
        return self.config.RETURN_URL or f"https://t.me/{self._default_return_url}"

    @property
    def lifetime_minutes(self):
        return self.config.LIFETIME_MINUTES

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

        currency_code = normalize_payment_currency_code(
            currency or self.settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
        )
        supported = parse_supported_currency_codes(self.config.SUPPORTED_CURRENCIES)
        if supported and currency_code not in supported:
            return False, {
                "message": "unsupported_currency",
                "currency": currency_code,
                "supported_currencies": list(supported),
            }

        session = await self._get_session()
        url = f"{self.base_url}/payin/create"

        body: Dict[str, Any] = {
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

    async def get_payment(self, provider_payment_id: str) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            return False, {"message": "service_not_configured"}

        provider_payment_id = str(provider_payment_id or "").strip()
        if not provider_payment_id:
            return False, {"message": "missing_payment_id"}

        identifier: Dict[str, Any]
        if provider_payment_id.isdigit():
            identifier = {"id": int(provider_payment_id)}
        else:
            identifier = {"uid": provider_payment_id}

        session = await self._get_session()
        success, response_data = await post_json_request(
            session,
            f"{self.base_url}/payin/get",
            body=self._build_signed_body(identifier),
            log_prefix="SeverPay get_payment",
            is_success=lambda status, data: status == 200 and bool((data or {}).get("status")),
        )
        if success:
            return True, response_data.get("data") or response_data
        return False, response_data

    async def try_reuse_pending_payment(self, payment: Any) -> Optional[str]:
        provider_payment_id = str(getattr(payment, "provider_payment_id", None) or "").strip()
        payment_url = str(getattr(payment, "provider_payment_url", None) or "").strip()
        if not provider_payment_id or not payment_url:
            return None

        success, data = await self.get_payment(provider_payment_id)
        if not success or str(data.get("status") or "").lower() not in {"new", "process"}:
            return None
        returned_ids = {str(data.get("id") or ""), str(data.get("uid") or "")}
        if provider_payment_id not in returned_ids:
            return None
        if str(data.get("order_id") or "") != str(payment.payment_id):
            return None
        return payment_url

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
            sale_mode = payment.sale_mode or (
                "traffic" if self.settings.traffic_sale_mode else "subscription"
            )
            payment_months = payment_units_for_activation(payment, sale_mode)

            if status == "success":
                if payment.status == "succeeded":
                    logging.info(
                        "SeverPay webhook: payment %s already succeeded.",
                        payment.payment_id,
                    )
                    return web.json_response({"status": True})

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

    if not SPEC.is_available_to_user(
        settings,
        user_id=callback.from_user.id,
        require_configured=False,
    ):
        await notify_service_unavailable(callback, translator)
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
    parts, hwid_quote = await quote_hwid_callback_parts(
        session=session,
        user_id=callback.from_user.id,
        parts=parts,
        subscription_service=severpay_service.subscription_service,
        currency=default_currency_key_for_settings(settings),
    )
    if not parts:
        await notify_callback_parse_error(callback, translator)
        return

    currency_code = default_payment_currency_code_for_settings(settings)
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
        hwid_quote=hwid_quote,
    )

    reuse_amounts = payment_record_amounts(
        months=parts.months,
        sale_mode=parts.sale_mode,
        hwid_device_count=hwid_quote.get("device_count") if hwid_quote else None,
    )
    reusable_payment = await payment_dal.find_recent_pending_provider_payment(
        session,
        user_id=callback.from_user.id,
        provider="severpay",
        pending_status="pending_severpay",
        amount=parts.price,
        currency=currency_code,
        sale_mode=parts.sale_mode,
        months=reuse_amounts.months,
        purchased_gb=reuse_amounts.purchased_gb,
        purchased_hwid_devices=reuse_amounts.purchased_hwid_devices,
        tariff_key=reuse_amounts.tariff_key,
    )
    if reusable_payment is not None:
        reusable_url = await severpay_service.try_reuse_pending_payment(reusable_payment)
        if reusable_url:
            await render_payment_link(
                callback,
                translator=translator,
                current_lang=current_lang,
                i18n=i18n,
                parts=parts,
                payment_url=reusable_url,
                log_prefix=_LOG,
            )
            return

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
        provider_response=response_data,
        log_prefix=_LOG,
    )


def create_service(ctx: ServiceFactoryContext) -> SeverPayService:
    bundle = ctx.config_for("severpay_service")
    config = (
        bundle.config if bundle and isinstance(bundle.config, SeverPayConfig) else SeverPayConfig()
    )
    return SeverPayService(
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
    settings = ctx.request.app["settings"]
    service: SeverPayService = ctx.request.app["severpay_service"]
    if not service or not service.configured:
        return payment_unavailable()

    currency = ctx.currency or settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
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
        provider_response=response_data,
        log_prefix="SeverPay",
    )


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> Optional[str]:
    service: SeverPayService = ctx.request.app.get("severpay_service")
    if not service or not service.configured:
        return None
    return await service.try_reuse_pending_payment(payment)


_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="SeverPay",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_SEVERPAY_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_SEVERPAY_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_SEVERPAY_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "CreditCard",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_SEVERPAY_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_SEVERPAY_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_SEVERPAY_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            "💳",
            "TELEGRAM_EMOJI",
        ),
    )
)

_CONFIG_MANIFEST = (
    ProviderManifestField(
        "SEVERPAY_ENABLED", "bool", "Включена", subsection="SeverPay", attr="ENABLED"
    ),
    ProviderManifestField("SEVERPAY_MID", "int", "MID", subsection="SeverPay", attr="MID"),
    ProviderManifestField(
        "SEVERPAY_TOKEN", "string", "Token", subsection="SeverPay", secret=True, attr="TOKEN"
    ),
    ProviderManifestField(
        "SEVERPAY_BASE_URL",
        "url",
        "Base URL",
        placeholder="https://severpay.io/api/merchant",
        subsection="SeverPay",
        attr="BASE_URL",
    ),
    ProviderManifestField(
        "SEVERPAY_RETURN_URL", "url", "Return URL", subsection="SeverPay", attr="RETURN_URL"
    ),
    ProviderManifestField(
        "SEVERPAY_LIFETIME_MINUTES",
        "int",
        "Payment link lifetime (minutes)",
        description="30..4320; leave empty for the SeverPay default.",
        subsection="SeverPay",
        min=30,
        max=4320,
        attr="LIFETIME_MINUTES",
    ),
    ProviderManifestField(
        "SEVERPAY_SUPPORTED_CURRENCIES",
        "string",
        "Supported currencies",
        description=(
            "Comma-separated currencies enabled for your SeverPay merchant. "
            "The public PayIn docs show USD examples but do not publish a fixed global list."
        ),
        placeholder="RUB,USD",
        subsection="SeverPay",
        attr="SUPPORTED_CURRENCIES",
    ),
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
    enabled=lambda config: bool(getattr(config, "ENABLED", False)),
    service_key="severpay_service",
    callback_prefix="pay_severpay",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/severpay",
    webhook_route=severpay_webhook_route,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=SeverPayConfig,
    presentation_class=SeverPayPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supported_currencies_resolver=lambda config: getattr(config, "SUPPORTED_CURRENCIES", "RUB,USD"),
    currency_support_note=(
        "SeverPay PayIn requires a currency; keep this list aligned with your merchant account."
    ),
    currency_support_url="https://docs.severpay.io/ru/payin/create",
)
