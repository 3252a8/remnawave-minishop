from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from aiogram import Bot, F, Router, types
from aiohttp import web
from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n

if TYPE_CHECKING:
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService
else:
    ReferralService = object
    SubscriptionService = object
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
    payment_units_for_activation,
    run_callback_payment,
    run_reuse_webapp_payment,
    run_webapp_payment,
)
from ..shared.app_context import app_required

_LOG = "bepusdt"
_CREATE_TRANSACTION_PATH = "/api/v1/order/create-transaction"
_SUCCESS_STATUSES = {"2"}


def calculate_signature(params: Dict[str, Any], token: str) -> str:
    pairs = []
    for key in sorted(params):
        if key == "signature":
            continue
        value = params[key]
        if value is None or value == "":
            continue
        pairs.append(f"{key}={value}")
    sign_text = "&".join(pairs) + token
    return hashlib.md5(sign_text.encode("utf-8")).hexdigest()


class BepusdtConfig(ProviderEnvConfig):
    """All BEPUSDT env vars. Lives inside the provider module."""

    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="BEPUSDT_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    API_BASE_URL: str = Field(default="http://127.0.0.1:8080")
    API_TOKEN: Optional[str] = None
    TRADE_TYPE: str = Field(default="usdt.trc20")
    FIAT: str = Field(default="CNY")
    CREATE_MODE: str = Field(default="transaction")
    RETURN_URL: Optional[str] = None
    SUPPORTED_CURRENCIES: str = Field(default="CNY,USD,EUR,GBP,JPY,USDT")

    @field_validator("API_TOKEN", "RETURN_URL", mode="before")
    @classmethod
    def _strip_optional(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator(
        "API_BASE_URL",
        "TRADE_TYPE",
        "FIAT",
        "CREATE_MODE",
        "SUPPORTED_CURRENCIES",
        mode="before",
    )
    @classmethod
    def _strip_required(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip()
        return v

    @property
    def webhook_path(self) -> str:
        return "/webhook/bepusdt"

    def full_webhook_url(self, base: Optional[str]) -> Optional[str]:
        if not base:
            return None
        return f"{base.rstrip('/')}{self.webhook_path}"


class BepusdtPresentation(ProviderEnvConfig):
    """Admin-tunable button text/icon overrides for BEPUSDT."""

    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_BEPUSDT_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: Optional[str] = None
    WEBAPP_LABEL_EN: Optional[str] = None
    WEBAPP_LABEL_ZH: Optional[str] = None
    WEBAPP_ICON: Optional[str] = None
    TELEGRAM_LABEL_RU: Optional[str] = None
    TELEGRAM_LABEL_EN: Optional[str] = None
    TELEGRAM_LABEL_ZH: Optional[str] = None
    TELEGRAM_EMOJI: Optional[str] = None


class BepusdtService(HttpClientMixin):
    """Client for BEPUSDT hosted-link transactions."""

    def __init__(
        self,
        *,
        bot: Bot,
        settings: Settings,
        config: BepusdtConfig,
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
            logging.warning(
                "BepusdtService initialized but not fully configured. Payments disabled."
            )

    @property
    def configured(self) -> bool:
        return bool(provider_runtime_enabled(self.config) and self.api_base_url and self.api_token)

    @property
    def api_base_url(self) -> str:
        return (self.config.API_BASE_URL or "").rstrip("/")

    @property
    def api_token(self) -> str:
        return (self.config.API_TOKEN or "").strip()

    @property
    def return_url(self) -> str:
        return (
            self.config.RETURN_URL
            or getattr(self.settings, "SUBSCRIPTION_MINI_APP_URL", None)
            or f"https://t.me/{self._default_return_url}"
        )

    @property
    def supported_currencies(self) -> tuple[str, ...]:
        parsed = parse_supported_currency_codes(self.config.SUPPORTED_CURRENCIES)
        return parsed or ("CNY", "USD", "EUR", "GBP", "JPY", "USDT")

    async def _post_signed(self, path: str, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        url = f"{self.api_base_url}/{path.lstrip('/')}"
        signed_payload = dict(payload)
        signed_payload["signature"] = calculate_signature(signed_payload, self.api_token)
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        session = await self._get_session()
        try:
            async with session.post(url, json=signed_payload, headers=headers) as response:
                response_text = await response.text()
                try:
                    response_data = json.loads(response_text) if response_text else {}
                except json.JSONDecodeError:
                    logging.error(
                        "BEPUSDT %s: invalid JSON response: %s",
                        path,
                        response_text[:500],
                    )
                    return False, {"status": response.status, "message": "invalid_json"}
                if not isinstance(response_data, dict):
                    response_data = {"data": response_data}
                status_code = response_data.get("status_code", response_data.get("code"))
                api_error = response_data.get("error") or response_data.get("message")
                if response.status >= 400 or (
                    status_code is not None and str(status_code) not in {"0", "200"}
                ):
                    logging.error(
                        "BEPUSDT %s: API error (http=%s, body=%s)",
                        path,
                        response.status,
                        response_data,
                    )
                    return False, {
                        "status": response.status,
                        "message": api_error or "bepusdt_api_error",
                        "code": status_code,
                    }
                data = response_data.get("data")
                return True, data if isinstance(data, dict) else response_data
        except Exception as exc:
            logging.exception("BEPUSDT %s: request failed.", path)
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
            logging.error("BepusdtService is not configured. Cannot create payment.")
            return False, {"message": "service_not_configured"}

        currency_code = normalize_payment_currency_code(
            currency or self.settings.DEFAULT_CURRENCY_SYMBOL or self.config.FIAT
        )
        if currency_code not in self.supported_currencies:
            return False, {
                "message": "unsupported_currency",
                "currency": currency_code,
                "supported_currencies": list(self.supported_currencies),
            }

        body: Dict[str, Any] = {
            "order_id": str(payment_db_id),
            "amount": str(format_decimal_amount(amount)),
            "trade_type": self.config.TRADE_TYPE or "usdt.trc20",
            "fiat": currency_code if currency_code != "USDT" else (self.config.FIAT or "CNY"),
        }
        notify_url = self.config.full_webhook_url(getattr(self.settings, "WEBHOOK_BASE_URL", None))
        if notify_url:
            body["notify_url"] = notify_url
        if self.return_url:
            body["redirect_url"] = self.return_url
        if description:
            body["description"] = description[:255]

        return await self._post_signed(_CREATE_TRANSACTION_PATH, body)

    async def try_reuse_pending_payment(self, payment: Any) -> Optional[str]:
        payment_url = str(getattr(payment, "provider_payment_url", None) or "").strip()
        provider_payment_id = str(getattr(payment, "provider_payment_id", None) or "").strip()
        if payment_url and provider_payment_id:
            return payment_url
        return None

    def verify_callback_signature(self, payload: Dict[str, Any]) -> bool:
        received = str(payload.get("signature") or "").strip()
        if not received:
            logging.warning("BEPUSDT webhook: missing signature.")
            return False
        if not self.api_token:
            logging.error("BEPUSDT webhook: no API token configured.")
            return False
        expected = calculate_signature(payload, self.api_token)
        return received.lower() == expected.lower()

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.Response(status=503, text="bepusdt_disabled")

        raw_body = await request.read()
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except (UnicodeDecodeError, ValueError, TypeError):
            logging.exception("BEPUSDT webhook: failed to parse JSON.")
            return web.Response(status=400, text="bad_request")
        if not isinstance(payload, dict):
            return web.Response(status=400, text="bad_request")

        if not self.verify_callback_signature(payload):
            logging.error("BEPUSDT webhook: invalid signature.")
            return web.Response(status=403, text="invalid_signature")

        provider_payment_id = str(payload.get("trade_id") or "").strip()
        order_id_raw = payload.get("order_id")
        status = str(payload.get("status") or "").strip()

        async with self.async_session_factory() as session:
            payment = await lookup_payment_by_order_or_provider_id(
                session,
                order_id_raw=order_id_raw,
                provider_payment_id=provider_payment_id or None,
            )
            if not payment:
                logging.error(
                    "BEPUSDT webhook: payment not found (order_id=%s, provider_id=%s)",
                    order_id_raw,
                    provider_payment_id,
                )
                return web.Response(status=404, text="payment_not_found")

            resolved_provider_id = provider_payment_id or str(payment.payment_id)
            if status not in _SUCCESS_STATUSES:
                logging.info(
                    "BEPUSDT webhook: ignoring non-success status %s for payment %s.",
                    status,
                    resolved_provider_id,
                )
                return web.Response(text="success")

            if payment.status == "succeeded":
                logging.info("BEPUSDT webhook: payment %s already succeeded.", payment.payment_id)
                return web.Response(text="success")

            webhook_amount = payload.get("amount")
            if webhook_amount is not None and not decimal_amounts_equal(
                webhook_amount,
                payment.amount,
            ):
                logging.error(
                    "BEPUSDT webhook: amount mismatch for payment %s (expected=%s, received=%s)",
                    payment.payment_id,
                    payment.amount,
                    webhook_amount,
                )
                return web.Response(status=400, text="amount_mismatch")

            sale_mode = payment.sale_mode or (
                "traffic" if self.settings.traffic_sale_mode else "subscription"
            )
            payment_months = payment_units_for_activation(payment, sale_mode)

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
                    "BEPUSDT webhook: failed to mark payment %s as succeeded.",
                    resolved_provider_id,
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
                    currency=payment.currency,
                    sale_mode=sale_mode,
                    months=payment_months,
                    traffic_amount=float(payment_months),
                    provider_subscription="bepusdt",
                    provider_notification="bepusdt",
                    db_user=payment.user,
                    log_prefix="BEPUSDT webhook",
                )
            )
            if outcome is None:
                return web.Response(status=500, text="processing_error")
            return web.Response(text="success")


async def bepusdt_webhook_route(request: web.Request) -> web.Response:
    service: BepusdtService = app_required(request, "bepusdt_service", BepusdtService)
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_bepusdt_router")


@router.callback_query(F.data.startswith("pay_bepusdt:"))
async def pay_bepusdt_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    bepusdt_service: BepusdtService,
    session: AsyncSession,
) -> None:
    await run_callback_payment(_DESCRIPTOR, callback, settings, i18n_data, bepusdt_service, session)


def create_service(ctx: ServiceFactoryContext) -> BepusdtService:
    bundle = ctx.config_for("bepusdt_service")
    config = (
        bundle.config if bundle and isinstance(bundle.config, BepusdtConfig) else BepusdtConfig()
    )
    return BepusdtService(
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
        subsection="BEPUSDT",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_BEPUSDT_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_BEPUSDT_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_BEPUSDT_WEBAPP_LABEL_ZH",
            "string",
            "WebApp button text (ZH)",
            "Custom Chinese text shown in the Web App payment method button.",
            "USDT 支付",
            "WEBAPP_LABEL_ZH",
        ),
        (
            "PAYMENT_BEPUSDT_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "WalletCards",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_BEPUSDT_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_BEPUSDT_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_BEPUSDT_TELEGRAM_LABEL_ZH",
            "string",
            "Telegram button text (ZH)",
            "Custom Chinese text shown in Telegram bot payment buttons.",
            "USDT 支付",
            "TELEGRAM_LABEL_ZH",
        ),
        (
            "PAYMENT_BEPUSDT_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            "💵",
            "TELEGRAM_EMOJI",
        ),
    )
)

_CONFIG_MANIFEST = (
    ProviderManifestField(
        "BEPUSDT_ENABLED",
        "bool",
        "Enabled",
        subsection="BEPUSDT",
        attr="ENABLED",
    ),
    ProviderManifestField(
        "BEPUSDT_API_BASE_URL",
        "url",
        "API base URL",
        placeholder="https://pay.example.com",
        subsection="BEPUSDT",
        attr="API_BASE_URL",
    ),
    ProviderManifestField(
        "BEPUSDT_API_TOKEN",
        "string",
        "API token",
        description="Token appended to sorted callback/request parameters before MD5 signing.",
        subsection="BEPUSDT",
        secret=True,
        attr="API_TOKEN",
    ),
    ProviderManifestField(
        "BEPUSDT_TRADE_TYPE",
        "string",
        "Trade type",
        placeholder="usdt.trc20",
        subsection="BEPUSDT",
        attr="TRADE_TYPE",
    ),
    ProviderManifestField(
        "BEPUSDT_FIAT",
        "string",
        "Default fiat",
        placeholder="CNY",
        subsection="BEPUSDT",
        attr="FIAT",
    ),
    ProviderManifestField(
        "BEPUSDT_RETURN_URL",
        "url",
        "Return URL",
        subsection="BEPUSDT",
        attr="RETURN_URL",
    ),
    ProviderManifestField(
        "BEPUSDT_SUPPORTED_CURRENCIES",
        "string",
        "Supported currencies",
        placeholder="CNY,USD,EUR,GBP,JPY,USDT",
        subsection="BEPUSDT",
        attr="SUPPORTED_CURRENCIES",
    ),
)


SPEC = PaymentProviderSpec(
    id="bepusdt",
    provider_key="bepusdt",
    label="BEPUSDT",
    webapp_label="BEPUSDT",
    webapp_labels={"ru": "BEPUSDT", "en": "BEPUSDT", "zh": "USDT 支付"},
    webapp_icon="WalletCards",
    telegram_labels={"ru": "BEPUSDT", "en": "BEPUSDT", "zh": "USDT 支付"},
    telegram_emoji="💵",
    pending_status="pending_bepusdt",
    enabled=lambda config: bool(getattr(config, "ENABLED", False)),
    service_key="bepusdt_service",
    callback_prefix="pay_bepusdt",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/bepusdt",
    webhook_route=bepusdt_webhook_route,
    webhook_requires_base_url=True,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=BepusdtConfig,
    presentation_class=BepusdtPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supported_currencies=None,
    supported_currencies_resolver=lambda config: parse_supported_currency_codes(
        getattr(config, "SUPPORTED_CURRENCIES", None)
    ),
    currency_support_note=(
        "BEPUSDT creates USDT collection links and can denominate orders in "
        "configured fiat currencies."
    ),
    currency_support_url="https://github.com/v03413/BEpusdt",
)


async def _create_payment(service: BepusdtService, req: CreatePaymentRequest) -> CreateResult:
    return await service.create_payment(
        payment_db_id=req.payment.payment_id,
        amount=req.amount,
        currency=req.currency,
        description=req.description,
    )


async def _reuse_payment(service: BepusdtService, payment: Any) -> Optional[str]:
    return await service.try_reuse_pending_payment(payment)


_DESCRIPTOR: LinkPaymentDescriptor[BepusdtService] = LinkPaymentDescriptor(
    spec=SPEC,
    provider_key="bepusdt",
    pending_status="pending_bepusdt",
    display_name="BEPUSDT",
    log_prefix=_LOG,
    service_app_key="bepusdt_service",
    service_type=BepusdtService,
    create=_create_payment,
    reuse=_reuse_payment,
    extract_url=lambda r: first_value(r, "payment_url", "url", "paymentUrl"),
    extract_provider_id=lambda r: first_value(r, "trade_id", "id"),
)
