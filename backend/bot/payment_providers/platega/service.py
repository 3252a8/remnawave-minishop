import json
import logging
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
    HttpClientMixin,
    LinkPaymentDescriptor,
    PaymentSuccessRequest,
    constant_time_compare,
    finalize_successful_payment,
    first_value,
    format_number_for_payload,
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

_LOG = "platega"


class PlategaConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PLATEGA_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    BASE_URL: str = Field(default="https://app.platega.io")
    MERCHANT_ID: str | None = None
    SECRET: str | None = None
    PAYMENT_METHOD: int = Field(default=2)
    SBP_ENABLED: bool = Field(default=False)
    SBP_ADMIN_ONLY_ENABLED: bool = Field(default=False)
    CRYPTO_ENABLED: bool = Field(default=False)
    CRYPTO_ADMIN_ONLY_ENABLED: bool = Field(default=False)
    SBP_METHOD: int = Field(default=2)
    CRYPTO_METHOD: int = Field(default=13)
    RETURN_URL: str | None = None
    FAILED_URL: str | None = None
    SUPPORTED_CURRENCIES: str = Field(default="RUB")

    @field_validator("MERCHANT_ID", "SECRET", "RETURN_URL", "FAILED_URL", mode="before")
    @classmethod
    def _strip_optional(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def sbp_method_resolved(self) -> int:
        """Falls back to the legacy ``PAYMENT_METHOD`` for backwards compat."""
        if self.SBP_METHOD != 2:
            return self.SBP_METHOD
        return self.PAYMENT_METHOD or 2

    @property
    def webhook_path(self) -> str:
        return "/webhook/platega"


class PlategaSbpPresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_PLATEGA_SBP_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: str | None = None
    WEBAPP_LABEL_EN: str | None = None
    WEBAPP_ICON: str | None = None
    TELEGRAM_LABEL_RU: str | None = None
    TELEGRAM_LABEL_EN: str | None = None
    TELEGRAM_EMOJI: str | None = None


class PlategaCryptoPresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_PLATEGA_CRYPTO_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: str | None = None
    WEBAPP_LABEL_EN: str | None = None
    WEBAPP_ICON: str | None = None
    TELEGRAM_LABEL_RU: str | None = None
    TELEGRAM_LABEL_EN: str | None = None
    TELEGRAM_EMOJI: str | None = None


class PlategaService(HttpClientMixin):
    def __init__(
        self,
        *,
        bot: Bot,
        settings: Settings,
        config: PlategaConfig,
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
            logger.warning(
                "PlategaService initialized but not fully configured. Payments disabled."
            )
        else:
            logger.info(
                "PlategaService configured. SBP button: %s (method=%s), Crypto button: %s (method=%s)",  # noqa: E501
                "ON" if config.SBP_ENABLED else "OFF",
                self.sbp_method,
                "ON" if config.CRYPTO_ENABLED else "OFF",
                self.crypto_method,
            )

    @property
    def configured(self) -> bool:
        return bool(
            provider_runtime_enabled(
                self.config,
                "SBP_ADMIN_ONLY_ENABLED",
                "CRYPTO_ADMIN_ONLY_ENABLED",
            )
            and self.merchant_id
            and self.secret
        )

    @property
    def base_url(self) -> str:
        return (self.config.BASE_URL or "https://app.platega.io").rstrip("/")

    @property
    def merchant_id(self) -> str | None:
        return self.config.MERCHANT_ID

    @property
    def secret(self) -> str | None:
        return self.config.SECRET

    @property
    def payment_method(self) -> int:
        return self.config.PAYMENT_METHOD

    @property
    def sbp_method(self) -> int:
        return self.config.sbp_method_resolved

    @property
    def crypto_method(self) -> int:
        return self.config.CRYPTO_METHOD

    @property
    def return_url(self) -> str:
        return self.config.RETURN_URL or f"https://t.me/{self._default_return_url}"

    @property
    def failed_url(self) -> str:
        return self.config.FAILED_URL or self.return_url

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {
            "X-MerchantId": self.merchant_id or "",
            "X-Secret": self.secret or "",
            "Content-Type": "application/json",
        }

    async def create_transaction(
        self,
        *,
        amount: float,
        currency: str | None,
        description: str,
        payload: str | None = None,
        payment_method: int | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        if not self.configured:
            logger.error("PlategaService is not configured. Cannot create transaction.")
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
        url = f"{self.base_url}/transaction/process"
        method_id = int(payment_method if payment_method is not None else self.payment_method)

        body: dict[str, Any] = {
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
        logger.info(
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

    async def get_transaction(self, transaction_id: str) -> tuple[bool, dict[str, Any]]:
        if not self.configured:
            return False, {"message": "service_not_configured"}

        transaction_id = str(transaction_id or "").strip()
        if not transaction_id:
            return False, {"message": "missing_transaction_id"}

        session = await self._get_session()
        try:
            async with session.get(
                f"{self.base_url}/transaction/{transaction_id}",
                headers=self._auth_headers,
            ) as response:
                data = await response.json(content_type=None)
                if response.status != 200 or not isinstance(data, dict):
                    logger.warning(
                        "Platega get_transaction failed: id=%s status=%s body=%s",
                        transaction_id,
                        response.status,
                        data,
                    )
                    return False, {"status": response.status, "message": data}
                return True, data
        except Exception as exc:
            logger.exception("Platega get_transaction request failed: id=%s", transaction_id)
            return False, {"message": str(exc)}

    async def try_reuse_pending_transaction(
        self,
        payment: Any,
        *,
        user_id: int,
        sale_mode: str,
        variant: str,
    ) -> str | None:
        transaction_id = str(getattr(payment, "provider_payment_id", None) or "").strip()
        payment_url = str(getattr(payment, "provider_payment_url", None) or "").strip()
        if not transaction_id or not payment_url:
            return None

        success, data = await self.get_transaction(transaction_id)
        if not success or str(data.get("status") or "").upper() != "PENDING":
            return None
        if str(data.get("id") or "") != transaction_id:
            return None

        try:
            payload = json.loads(str(data.get("payload") or ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        expected = {
            "payment_db_id": str(payment.payment_id),
            "user_id": str(user_id),
            "sale_mode": str(sale_mode),
            "platega_variant": str(variant),
        }
        if not isinstance(payload, dict) or any(
            str(payload.get(key) or "") != value for key, value in expected.items()
        ):
            return None
        return payment_url

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.Response(status=503, text="platega_disabled")

        try:
            data = await request.json()
        except Exception:
            logger.exception("Platega webhook: failed to parse JSON.")
            return web.Response(status=400, text="bad_request")

        header_merchant = request.headers.get("X-MerchantId")
        header_secret = request.headers.get("X-Secret")
        if not (
            constant_time_compare(header_merchant, self.merchant_id)
            and constant_time_compare(header_secret, self.secret)
        ):
            logger.error("Platega webhook: invalid auth headers")
            return web.Response(status=403, text="forbidden")

        transaction_id = str(data.get("id") or data.get("transactionId") or "").strip()
        status = str(data.get("status") or "").upper()
        amount_raw = data.get("amount")
        currency = data.get("currency")

        if not transaction_id or not status:
            logger.error("Platega webhook: missing transaction id or status in payload: %s", data)
            return web.Response(status=400, text="missing_fields")

        async with self.async_session_factory() as session:
            payment = await payment_dal.get_payment_by_provider_payment_id(session, transaction_id)
            if not payment:
                logger.error(
                    "Platega webhook: payment not found for transaction %s", transaction_id
                )
                return web.Response(status=404, text="payment_not_found")

            if payment.status == "succeeded" and status == "CONFIRMED":
                return web.Response(text="ok")

            if status == "CONFIRMED":
                if not payment_amount_and_currency_match(
                    expected_amount=payment.amount,
                    expected_currency=payment.currency,
                    received_amount=amount_raw,
                    received_currency=currency,
                    # Platega receives the raw numeric amount passed to
                    # create_transaction, so preserve that invoice precision.
                    places=None,
                    allow_overpayment=True,
                ):
                    logger.warning(
                        "Platega webhook: amount or currency mismatch for payment %s "
                        "(expected=%s %s, got=%s %s)",
                        payment.payment_id,
                        payment.amount,
                        payment.currency,
                        amount_raw,
                        currency,
                    )
                    return web.Response(status=400, text="amount_mismatch")

                try:
                    claimed_payment = await payment_dal.claim_payment_finalization(
                        session,
                        payment.payment_id,
                        provider_payment_id=transaction_id,
                    )
                except Exception:
                    await session.rollback()
                    logger.exception(
                        "Platega webhook: failed to mark payment %s as succeeded.", transaction_id
                    )
                    return web.Response(status=500, text="processing_error")

                if claimed_payment is None:
                    return web.Response(text="ok")
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
                        currency=str(payment.currency),
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
                    logger.exception(
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

            logger.warning(
                "Platega webhook: unhandled status '%s' for transaction %s", status, transaction_id
            )
            return web.Response(status=202, text="status_ignored")


async def platega_webhook_route(request: web.Request) -> web.Response:
    service: PlategaService = app_required(request, "platega_service", PlategaService)
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_platega_router")


@router.callback_query(
    F.data.startswith("pay_platega_sbp:")
    | F.data.startswith("pay_platega_crypto:")
    | F.data.startswith("pay_platega:")
)
async def pay_platega_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    platega_service: PlategaService,
    session: AsyncSession,
) -> None:
    callback_prefix, _, _ = (callback.data or "").partition(":")
    await run_callback_payment(
        _platega_descriptor_for_callback_prefix(callback_prefix),
        callback,
        settings,
        i18n_data,
        platega_service,
        session,
    )


def create_service(ctx: ServiceFactoryContext) -> PlategaService:
    bundle = ctx.config_for("platega_service")
    config = (
        bundle.config if bundle and isinstance(bundle.config, PlategaConfig) else PlategaConfig()
    )
    return PlategaService(
        bot=ctx.bot,
        settings=ctx.settings,
        config=config,
        i18n=ctx.i18n,
        async_session_factory=ctx.async_session_factory,
        subscription_service=ctx.subscription_service,
        referral_service=ctx.referral_service,
        default_return_url=ctx.bot_username_for_default_return,
    )


async def create_sbp_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_SBP_DESCRIPTOR, ctx)


async def create_crypto_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_CRYPTO_DESCRIPTOR, ctx)


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> str | None:
    descriptor = _CRYPTO_DESCRIPTOR if ctx.method == "platega_crypto" else _SBP_DESCRIPTOR
    return await run_reuse_webapp_payment(descriptor, ctx, payment)


def _context_for_variant(
    variant: str,
) -> Any:
    def _callback_context(
        callback: types.CallbackQuery,
        parts: Any,
        service: PlategaService,
    ) -> dict[str, Any]:
        return {
            "platega_variant": variant,
            "user_id": callback.from_user.id,
            "sale_mode": parts.sale_mode,
            "source": "callback",
        }

    return _callback_context


def _webapp_context_for_variant(variant: str) -> Any:
    def _webapp_context(ctx: WebAppPaymentContext) -> dict[str, Any]:
        return {
            "platega_variant": variant,
            "user_id": ctx.user_id,
            "sale_mode": ctx.sale_mode,
            "source": "webapp",
            "traffic_gb": ctx.traffic_gb,
            "hwid_device_count": ctx.hwid_device_count,
        }

    return _webapp_context


def _platega_method_id(service: PlategaService, variant: str) -> int:
    return (
        service.config.CRYPTO_METHOD if variant == "crypto" else service.config.sbp_method_resolved
    )


async def _create_payment(
    service: PlategaService,
    request: CreatePaymentRequest,
) -> tuple[bool, dict]:
    context = request.provider_context or {}
    variant = str(context.get("platega_variant") or "sbp")
    payload_data: dict[str, Any] = {
        "payment_db_id": request.payment.payment_id,
        "user_id": request.user_id,
        "months": request.months,
        "sale_mode": request.sale_mode,
        "platega_variant": variant,
    }
    if context.get("source") == "webapp":
        traffic_gb = getattr(request.payment, "purchased_gb", None)
        hwid_devices = getattr(request.payment, "purchased_hwid_devices", None)
        payload_data.update(
            {
                "months": request.months if traffic_gb is None else 0,
                "traffic_gb": format_number_for_payload(traffic_gb)
                if traffic_gb is not None
                else None,
                "hwid_devices": hwid_devices,
                "source": "webapp",
            }
        )
    return await service.create_transaction(
        amount=request.amount,
        currency=request.currency,
        description=request.description,
        payload=json.dumps(payload_data),
        payment_method=_platega_method_id(service, variant),
    )


async def _reuse_payment_with_context(
    service: PlategaService,
    payment: Any,
    context: dict[str, Any] | None,
) -> str | None:
    if not context:
        return None
    return await service.try_reuse_pending_transaction(
        payment,
        user_id=int(context["user_id"]),
        sale_mode=str(context["sale_mode"]),
        variant=str(context["platega_variant"]),
    )


def _extract_payment_url(response_data: dict) -> str | None:
    return first_value(response_data, "redirect", "url", "paymentUrl")


def _extract_provider_id(response_data: dict) -> str | None:
    if not _extract_payment_url(response_data):
        return None
    return first_value(response_data, "transactionId", "id")


def _platega_webapp_available(variant: str) -> Any:
    def _available(service: PlategaService) -> bool:
        if not service.configured:
            return False
        if variant == "crypto":
            return bool(service.config.CRYPTO_ENABLED or service.config.CRYPTO_ADMIN_ONLY_ENABLED)
        return bool(service.config.SBP_ENABLED or service.config.SBP_ADMIN_ONLY_ENABLED)

    return _available


def _platega_descriptor_for_callback_prefix(
    callback_prefix: str,
) -> LinkPaymentDescriptor[PlategaService]:
    if callback_prefix == "pay_platega_crypto":
        return _CRYPTO_DESCRIPTOR
    return _SBP_DESCRIPTOR


def _platega_presentation_manifest(subsection: str, default_icon: str, prefix: str) -> tuple:
    return tuple(
        ProviderManifestField(
            key=f"PAYMENT_{prefix}_{suffix_key}",
            type=type_,
            label=label,
            description=description,
            placeholder=placeholder,
            subsection=subsection,
            target="presentation",
            attr=attr,
        )
        for suffix_key, type_, label, description, placeholder, attr in (
            (
                "WEBAPP_LABEL_RU",
                "string",
                "WebApp button text (RU)",
                "Custom Russian text shown in the Web App payment method button.",
                "",
                "WEBAPP_LABEL_RU",
            ),
            (
                "WEBAPP_LABEL_EN",
                "string",
                "WebApp button text (EN)",
                "Custom English text shown in the Web App payment method button.",
                "",
                "WEBAPP_LABEL_EN",
            ),
            (
                "WEBAPP_ICON",
                "icon",
                "WebApp button icon",
                "Lucide icon name rendered inside the Web App payment method button.",
                default_icon,
                "WEBAPP_ICON",
            ),
            (
                "TELEGRAM_LABEL_RU",
                "string",
                "Telegram button text (RU)",
                "Custom Russian text shown in Telegram bot payment buttons.",
                "",
                "TELEGRAM_LABEL_RU",
            ),
            (
                "TELEGRAM_LABEL_EN",
                "string",
                "Telegram button text (EN)",
                "Custom English text shown in Telegram bot payment buttons.",
                "",
                "TELEGRAM_LABEL_EN",
            ),
            (
                "TELEGRAM_EMOJI",
                "string",
                "Telegram button emoji",
                "Emoji prepended to the Telegram bot payment button when customized.",
                "",
                "TELEGRAM_EMOJI",
            ),
        )
    )


_CONFIG_MANIFEST = (
    ProviderManifestField(
        "PLATEGA_ENABLED", "bool", "Включена", subsection="Platega", attr="ENABLED"
    ),
    ProviderManifestField(
        "PLATEGA_BASE_URL",
        "url",
        "Base URL",
        placeholder="https://app.platega.io",
        subsection="Platega",
        attr="BASE_URL",
    ),
    ProviderManifestField(
        "PLATEGA_MERCHANT_ID", "string", "Merchant ID", subsection="Platega", attr="MERCHANT_ID"
    ),
    ProviderManifestField(
        "PLATEGA_SECRET", "string", "Secret", subsection="Platega", secret=True, attr="SECRET"
    ),
    ProviderManifestField(
        "PLATEGA_PAYMENT_METHOD",
        "int",
        "Метод оплаты (legacy)",
        subsection="Platega",
        attr="PAYMENT_METHOD",
    ),
    ProviderManifestField(
        "PLATEGA_SBP_ENABLED", "bool", "SBP-кнопка", subsection="Platega", attr="SBP_ENABLED"
    ),
    ProviderManifestField(
        "PLATEGA_SBP_METHOD", "int", "SBP method ID", subsection="Platega", attr="SBP_METHOD"
    ),
    ProviderManifestField(
        "PLATEGA_CRYPTO_ENABLED",
        "bool",
        "Crypto-кнопка",
        subsection="Platega",
        attr="CRYPTO_ENABLED",
    ),
    ProviderManifestField(
        "PLATEGA_CRYPTO_METHOD",
        "int",
        "Crypto method ID",
        subsection="Platega",
        attr="CRYPTO_METHOD",
    ),
    ProviderManifestField(
        "PLATEGA_SUPPORTED_CURRENCIES",
        "string",
        "Supported currencies",
        description=(
            "Comma-separated payment currencies enabled for your Platega merchant. "
            "Public docs expose currency per method/limits but do not publish a fixed global list."
        ),
        placeholder="RUB",
        subsection="Platega",
        attr="SUPPORTED_CURRENCIES",
    ),
    ProviderManifestField(
        "PLATEGA_RETURN_URL", "url", "Return URL", subsection="Platega", attr="RETURN_URL"
    ),
    ProviderManifestField(
        "PLATEGA_FAILED_URL", "url", "Failed URL", subsection="Platega", attr="FAILED_URL"
    ),
)


SBP_SPEC = PaymentProviderSpec(
    id="platega_sbp",
    provider_key="platega",
    label="Platega",
    webapp_label="Platega · СБП",
    webapp_labels={"ru": "Оплата картой (СБП)", "en": "Pay with card (SBP)"},
    webapp_icon="CreditCard",
    logo_url="/provider-logos/platega.png",
    telegram_labels={"ru": "Оплата через СБП", "en": "Pay via SBP"},
    telegram_emoji="🏦",
    pending_status="pending_platega",
    enabled=lambda config: bool(
        getattr(config, "ENABLED", False) and getattr(config, "SBP_ENABLED", False)
    ),
    admin_only_enabled=lambda config: bool(getattr(config, "SBP_ADMIN_ONLY_ENABLED", False)),
    admin_only_config_attr="SBP_ADMIN_ONLY_ENABLED",
    service_key="platega_service",
    callback_prefix="pay_platega_sbp",
    aliases=("platega",),
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/platega",
    webhook_route=platega_webhook_route,
    create_webapp_payment=create_sbp_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=PlategaConfig,
    presentation_class=PlategaSbpPresentation,
    manifest_fields=_CONFIG_MANIFEST
    + _platega_presentation_manifest("Platega", "CreditCard", "PLATEGA_SBP"),
    supported_currencies_resolver=lambda config: getattr(config, "SUPPORTED_CURRENCIES", "RUB"),
    currency_support_note=(
        "Platega currencies are merchant/method-specific; configure the codes "
        "enabled for your account."
    ),
    info_url="https://platega.io/",
    currency_support_url="https://docs.platega.io/",
)

CRYPTO_SPEC = PaymentProviderSpec(
    id="platega_crypto",
    provider_key="platega",
    label="Platega",
    webapp_label="Platega · Crypto",
    webapp_labels={"ru": "Крипта", "en": "Crypto"},
    webapp_icon="Bitcoin",
    logo_url="/provider-logos/platega.png",
    telegram_labels={"ru": "Оплата криптой", "en": "Pay with crypto"},
    telegram_emoji="🪙",
    pending_status="pending_platega",
    # Uses the same PlategaConfig as SBP_SPEC (shared service_key); enable
    # flag combines the global PLATEGA_ENABLED with the per-button toggle.
    enabled=lambda config: bool(
        getattr(config, "ENABLED", False) and getattr(config, "CRYPTO_ENABLED", False)
    ),
    admin_only_enabled=lambda config: bool(getattr(config, "CRYPTO_ADMIN_ONLY_ENABLED", False)),
    admin_only_config_attr="CRYPTO_ADMIN_ONLY_ENABLED",
    service_key="platega_service",
    callback_prefix="pay_platega_crypto",
    create_webapp_payment=create_crypto_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=PlategaConfig,
    presentation_class=PlategaCryptoPresentation,
    manifest_fields=_platega_presentation_manifest("Platega", "Bitcoin", "PLATEGA_CRYPTO"),
    supported_currencies_resolver=lambda config: getattr(config, "SUPPORTED_CURRENCIES", "RUB"),
    currency_support_note=(
        "Platega currencies are merchant/method-specific; configure the codes "
        "enabled for your account."
    ),
    info_url="https://platega.io/",
    currency_support_url="https://docs.platega.io/",
)

SPECS = (SBP_SPEC, CRYPTO_SPEC)

_SBP_DESCRIPTOR: LinkPaymentDescriptor[PlategaService] = LinkPaymentDescriptor(
    spec=SBP_SPEC,
    provider_key="platega",
    pending_status="pending_platega",
    display_name="Platega",
    log_prefix=_LOG,
    service_app_key="platega_service",
    service_type=PlategaService,
    create=_create_payment,
    reuse=lambda service, payment: service.try_reuse_pending_transaction(
        payment,
        user_id=getattr(payment, "user_id", 0),
        sale_mode=str(getattr(payment, "sale_mode", "") or ""),
        variant="sbp",
    ),
    reuse_with_context=_reuse_payment_with_context,
    extract_url=_extract_payment_url,
    extract_provider_id=_extract_provider_id,
    callback_context=_context_for_variant("sbp"),
    webapp_context=_webapp_context_for_variant("sbp"),
    webapp_available=_platega_webapp_available("sbp"),
)

_CRYPTO_DESCRIPTOR: LinkPaymentDescriptor[PlategaService] = LinkPaymentDescriptor(
    spec=CRYPTO_SPEC,
    provider_key="platega",
    pending_status="pending_platega",
    display_name="Platega",
    log_prefix=_LOG,
    service_app_key="platega_service",
    service_type=PlategaService,
    create=_create_payment,
    reuse=lambda service, payment: service.try_reuse_pending_transaction(
        payment,
        user_id=getattr(payment, "user_id", 0),
        sale_mode=str(getattr(payment, "sale_mode", "") or ""),
        variant="crypto",
    ),
    reuse_with_context=_reuse_payment_with_context,
    extract_url=_extract_payment_url,
    extract_provider_id=_extract_provider_id,
    callback_context=_context_for_variant("crypto"),
    webapp_context=_webapp_context_for_variant("crypto"),
    webapp_available=_platega_webapp_available("crypto"),
)

_DESCRIPTOR = _SBP_DESCRIPTOR
