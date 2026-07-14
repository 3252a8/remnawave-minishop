import hashlib
import hmac
import json
import logging
import secrets
from typing import TYPE_CHECKING, Any

from aiogram import Bot, F, Router, types
from aiohttp import web
from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
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
    CreatePaymentRequest,
    CreateResult,
    HttpClientMixin,
    LinkPaymentDescriptor,
    PaymentSuccessRequest,
    finalize_successful_payment,
    first_value,
    format_decimal_amount,
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

if TYPE_CHECKING:
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService
else:
    ReferralService = object
    SubscriptionService = object

logger = logging.getLogger(__name__)

_LOG = "severpay"


class SeverPayConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="SEVERPAY_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    MID: int | None = None
    TOKEN: str | None = None
    RETURN_URL: str | None = None
    BASE_URL: str = Field(default="https://severpay.io/api/merchant")
    LIFETIME_MINUTES: int | None = None
    SUPPORTED_CURRENCIES: str = Field(default="RUB,USD")

    @field_validator("MID", "LIFETIME_MINUTES", mode="before")
    @classmethod
    def _empty_to_none_int(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
        return v

    @field_validator("TOKEN", "RETURN_URL", mode="before")
    @classmethod
    def _strip_optional(cls, v: Any) -> Any:
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

    WEBAPP_LABEL_RU: str | None = None
    WEBAPP_LABEL_EN: str | None = None
    WEBAPP_ICON: str | None = None
    TELEGRAM_LABEL_RU: str | None = None
    TELEGRAM_LABEL_EN: str | None = None
    TELEGRAM_EMOJI: str | None = None


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
            logger.warning(
                "SeverPayService initialized but not fully configured. Payments disabled."
            )

    @property
    def configured(self) -> bool:
        return bool(provider_runtime_enabled(self.config) and self.mid and self.token)

    @property
    def base_url(self) -> str:
        return (self.config.BASE_URL or "https://severpay.io/api/merchant").rstrip("/")

    @property
    def mid(self) -> int | None:
        return self.config.MID

    @property
    def token(self) -> str:
        return self.config.TOKEN or ""

    @property
    def return_url(self) -> str:
        return self.config.RETURN_URL or f"https://t.me/{self._default_return_url}"

    @property
    def lifetime_minutes(self) -> int | None:
        return self.config.LIFETIME_MINUTES

    @staticmethod
    def _format_amount(amount: float) -> str:
        return f"{format_decimal_amount(amount):.2f}"

    def _sign_payload(self, payload: dict[str, Any]) -> str:
        message = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return hmac.new(
            self.token.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _build_signed_body(self, extra: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "mid": self.mid,
            "salt": secrets.token_hex(8),
        }
        body.update(extra)
        sorted_body = dict(sorted(body.items()))
        sorted_body["sign"] = self._sign_payload(sorted_body)
        return sorted_body

    def _validate_signature(self, payload: dict[str, Any]) -> bool:
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
        currency: str | None,
    ) -> tuple[bool, dict[str, Any]]:
        if not self.configured:
            logger.error("SeverPayService is not configured. Cannot create payment.")
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

        body: dict[str, Any] = {
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

    async def get_payment(self, provider_payment_id: str) -> tuple[bool, dict[str, Any]]:
        if not self.configured:
            return False, {"message": "service_not_configured"}

        provider_payment_id = str(provider_payment_id or "").strip()
        if not provider_payment_id:
            return False, {"message": "missing_payment_id"}

        identifier: dict[str, Any]
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

    async def try_reuse_pending_payment(self, payment: Any) -> str | None:
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
            logger.exception("SeverPay webhook: failed to parse JSON.")
            return web.json_response({"status": False, "msg": "bad_request"}, status=400)

        if not isinstance(payload, dict) or not self._validate_signature(payload):
            logger.error("SeverPay webhook: invalid signature or payload.")
            return web.json_response({"status": False, "msg": "invalid_signature"}, status=403)

        event_type = str(payload.get("type") or "").lower()
        data = payload.get("data") or {}

        if event_type != "payin" or not isinstance(data, dict):
            logger.warning("SeverPay webhook: unsupported event type '%s'", event_type)
            return web.json_response({"status": True})

        provider_payment_id = str(data.get("id") or data.get("uid") or "")
        order_id_raw = data.get("order_id")
        status = str(data.get("status") or "").lower()
        amount = data.get("amount")
        currency = data.get("currency")

        async with self.async_session_factory() as session:
            payment = await lookup_payment_by_order_or_provider_id(
                session,
                order_id_raw=order_id_raw,
                provider_payment_id=provider_payment_id or None,
            )
            if not payment:
                logger.error(
                    "SeverPay webhook: payment not found (order_id=%s, provider_id=%s)",
                    order_id_raw,
                    provider_payment_id,
                )
                return web.json_response({"status": False, "msg": "payment_not_found"}, status=404)

            resolved_provider_id = provider_payment_id or str(payment.payment_id)
            if status == "success":
                if payment.status == "succeeded":
                    logger.info(
                        "SeverPay webhook: payment %s already succeeded.",
                        payment.payment_id,
                    )
                    return web.json_response({"status": True})

                if not payment_amount_and_currency_match(
                    expected_amount=payment.amount,
                    expected_currency=payment.currency,
                    received_amount=amount,
                    received_currency=currency,
                    allow_overpayment=True,
                ):
                    logger.warning(
                        "SeverPay webhook: amount or currency mismatch for payment %s "
                        "(expected=%s %s, got=%s %s)",
                        payment.payment_id,
                        payment.amount,
                        payment.currency,
                        amount,
                        currency,
                    )
                    return web.json_response(
                        {"status": False, "msg": "amount_mismatch"},
                        status=400,
                    )

                try:
                    claimed_payment = await payment_dal.claim_payment_finalization(
                        session,
                        payment.payment_id,
                        provider_payment_id=resolved_provider_id,
                    )
                except Exception:
                    await session.rollback()
                    logger.exception(
                        "SeverPay webhook: failed to mark payment %s as succeeded.",
                        resolved_provider_id,
                    )
                    return web.json_response(
                        {"status": False, "msg": "processing_error"}, status=500
                    )

                if claimed_payment is None:
                    return web.json_response({"status": True})
                payment = claimed_payment

                sale_mode = payment.sale_mode or (
                    "traffic" if self.settings.traffic_sale_mode else "subscription"
                )
                payment_months = payment_units_for_activation(payment, sale_mode)

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
                    logger.exception(
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
                    logger.exception(
                        "SeverPay webhook: failed to update pending status for %s.",
                        resolved_provider_id,
                    )
                return web.json_response({"status": True})

            logger.warning(
                "SeverPay webhook: unhandled status '%s' for payment %s",
                status,
                resolved_provider_id,
            )
            return web.json_response({"status": True})


async def severpay_webhook_route(request: web.Request) -> web.Response:
    service: SeverPayService = app_required(request, "severpay_service", SeverPayService)
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_severpay_router")


@router.callback_query(F.data.startswith("pay_severpay:"))
async def pay_severpay_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    severpay_service: SeverPayService,
    session: AsyncSession,
) -> None:
    await run_callback_payment(
        _DESCRIPTOR, callback, settings, i18n_data, severpay_service, session
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
    logo_url="/provider-logos/severpay.png",
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
    info_url="https://severpay.io/",
    currency_support_url="https://docs.severpay.io/ru/payin/create",
)


async def _create_payment(service: SeverPayService, req: CreatePaymentRequest) -> CreateResult:
    return await service.create_payment(
        payment_db_id=req.payment.payment_id,
        user_id=req.user_id,
        amount=req.amount,
        currency=req.currency,
    )


async def _reuse_payment(service: SeverPayService, payment: Any) -> str | None:
    return await service.try_reuse_pending_payment(payment)


_DESCRIPTOR: LinkPaymentDescriptor[SeverPayService] = LinkPaymentDescriptor(
    spec=SPEC,
    provider_key="severpay",
    pending_status="pending_severpay",
    display_name="SeverPay",
    log_prefix=_LOG,
    service_app_key="severpay_service",
    service_type=SeverPayService,
    create=_create_payment,
    reuse=_reuse_payment,
    extract_url=lambda r: first_value(r, "url", "payment_url", "paymentUrl"),
    extract_provider_id=lambda r: first_value(r, "id", "uid"),
)
