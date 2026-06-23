import hashlib
import hmac
import json
import logging
from typing import Optional

from aiocryptopay import AioCryptoPay, Networks
from aiocryptopay.models.update import Update
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
    BaseProviderService,
    PaymentProviderSpec,
    ProviderEnvConfig,
    ProviderManifestField,
    ProviderWebhookPayload,
    ServiceFactoryContext,
    WebAppPaymentContext,
    normalize_payment_currency_code,
    provider_env_file,
    provider_runtime_enabled,
)
from ..shared import (
    PAYMENT_STATUS_PENDING_FINALIZATION,
    PaymentSuccessRequest,
    describe_payment,
    finalize_successful_payment,
    make_translator,
    notify_callback_parse_error,
    notify_service_unavailable,
    parse_payment_callback,
    payment_failed,
    payment_link_response,
    payment_record_amounts,
    payment_unavailable,
    quote_hwid_callback_parts,
    render_payment_link,
    sale_mode_base,
    sale_mode_is_traffic,
    sale_mode_tariff_key,
)

logger = logging.getLogger(__name__)
_LOG = "cryptopay"
CRYPTOPAY_FIAT_CURRENCIES = (
    "USD",
    "EUR",
    "RUB",
    "BYN",
    "UAH",
    "GBP",
    "CNY",
    "KZT",
    "UZS",
    "GEL",
    "TRY",
    "AMD",
    "THB",
    "INR",
    "BRL",
    "IDR",
    "AZN",
    "AED",
    "PLN",
    "ILS",
)
CRYPTOPAY_CRYPTO_ASSETS = ("USDT", "TON", "BTC", "ETH", "LTC", "BNB", "TRX", "USDC")


def _cryptopay_supported_currencies(config) -> tuple[str, ...]:
    currency_type = str(getattr(config, "CURRENCY_TYPE", "fiat") or "fiat").strip().lower()
    return CRYPTOPAY_CRYPTO_ASSETS if currency_type == "crypto" else CRYPTOPAY_FIAT_CURRENCIES


class CryptoPayConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="CRYPTOPAY_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=True)
    TOKEN: Optional[str] = None
    NETWORK: str = Field(default="mainnet")
    CURRENCY_TYPE: str = Field(default="fiat")
    ASSET: str = Field(default="RUB")

    @field_validator("TOKEN", mode="before")
    @classmethod
    def _strip_optional(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def webhook_path(self) -> str:
        return "/webhook/cryptopay"


class CryptoPayPresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_CRYPTOPAY_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: Optional[str] = None
    WEBAPP_LABEL_EN: Optional[str] = None
    WEBAPP_ICON: Optional[str] = None
    TELEGRAM_LABEL_RU: Optional[str] = None
    TELEGRAM_LABEL_EN: Optional[str] = None
    TELEGRAM_EMOJI: Optional[str] = None


class CryptoPayService(BaseProviderService):
    provider_key = "cryptopay"
    disabled_response_text = "cryptopay_disabled"

    def __init__(
        self,
        bot: Bot,
        settings: Settings,
        config: CryptoPayConfig,
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
        self._client = None
        self._client_token = None
        self._client_network = None
        if not self.config.TOKEN:
            logging.warning("CryptoPay token not provided. CryptoPay disabled")

    @property
    def token(self):
        return self.config.TOKEN

    @property
    def configured(self) -> bool:
        return bool(provider_runtime_enabled(self.config) and self.config.TOKEN)

    @property
    def webhook_available(self) -> bool:
        return bool(self.configured and self.client)

    @property
    def client(self):
        # Recreate the SDK client whenever the admin changes the token / network
        # at runtime — otherwise we'd keep talking to the old account.
        token = self.config.TOKEN
        network = self.config.NETWORK
        if not token:
            return None
        if self._client is None or token != self._client_token or network != self._client_network:
            net = Networks.TEST_NET if str(network).lower() == "testnet" else Networks.MAIN_NET
            self._client = AioCryptoPay(token=token, network=net)
            self._client.register_pay_handler(self._invoice_paid_handler)
            self._client_token = token
            self._client_network = network
        return self._client

    async def close(self):
        if self._client:
            try:
                await self._client.close()
                logging.info("CryptoPay client session closed.")
            except Exception as e:
                logging.warning("Failed to close CryptoPay client: %s", e)

    async def create_invoice(
        self,
        session: AsyncSession,
        user_id: int,
        months: float,
        amount: float,
        description: str,
        sale_mode: str = "subscription",
        url_kind: str = "bot",
        hwid_quote: Optional[dict] = None,
        hwid_device_count: Optional[int] = None,
        currency: Optional[str] = None,
    ) -> Optional[str]:
        if not self.configured or not self.client:
            logging.error("CryptoPayService not configured")
            return None

        currency_code = normalize_payment_currency_code(currency or self.config.ASSET)
        currency_type = str(self.config.CURRENCY_TYPE or "fiat").strip().lower()
        supported = _cryptopay_supported_currencies(self.config)
        if currency_code not in supported:
            logging.error(
                "CryptoPay currency %s is not supported for currency_type=%s",
                currency_code,
                currency_type,
            )
            return None

        sale_base = sale_mode_base(sale_mode)
        if hwid_device_count is None and hwid_quote:
            hwid_device_count = hwid_quote.get("device_count")
        amounts = payment_record_amounts(
            months=months,
            sale_mode=sale_mode,
            hwid_device_count=hwid_device_count,
        )
        try:
            payment_record = await payment_dal.create_payment_record(
                session,
                {
                    "user_id": user_id,
                    "amount": float(amount),
                    "currency": currency_code,
                    "status": "pending_cryptopay",
                    "description": description,
                    "subscription_duration_months": (
                        int(months) if sale_base == "subscription" else None
                    ),
                    "provider": "cryptopay",
                    "sale_mode": sale_mode,
                    "tariff_key": sale_mode_tariff_key(sale_mode),
                    "purchased_gb": amounts.purchased_gb,
                    "purchased_hwid_devices": amounts.purchased_hwid_devices,
                    "hwid_valid_from": hwid_quote.get("valid_from") if hwid_quote else None,
                    "hwid_valid_until": hwid_quote.get("valid_until") if hwid_quote else None,
                    "hwid_pricing_period_months": hwid_quote.get("pricing_period_months")
                    if hwid_quote
                    else None,
                    "hwid_proration_ratio": hwid_quote.get("proration_ratio")
                    if hwid_quote
                    else None,
                    "hwid_full_price": hwid_quote.get("full_price") if hwid_quote else None,
                },
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logging.exception("Failed to create cryptopay payment record for user %s.", user_id)
            return None

        payload = json.dumps(
            {
                "user_id": str(user_id),
                "subscription_months": str(months),
                "payment_db_id": str(payment_record.payment_id),
                "sale_mode": sale_mode,
                "traffic_gb": str(months) if sale_mode_is_traffic(sale_mode) else None,
                "hwid_devices": amounts.purchased_hwid_devices,
            }
        )
        try:
            invoice = await self.client.create_invoice(
                amount=amount,
                currency_type=currency_type,
                fiat=currency_code if currency_type == "fiat" else None,
                asset=currency_code if currency_type == "crypto" else None,
                description=description,
                payload=payload,
            )
            try:
                await payment_dal.update_provider_payment_and_status(
                    session,
                    payment_record.payment_id,
                    str(invoice.invoice_id),
                    str(invoice.status),
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logging.exception(
                    "Failed to update cryptopay payment record %s.",
                    payment_record.payment_id,
                )
                return None
            if url_kind == "web":
                return (
                    getattr(invoice, "web_app_invoice_url", None)
                    or getattr(invoice, "mini_app_invoice_url", None)
                    or invoice.bot_invoice_url
                )
            return invoice.bot_invoice_url
        except Exception:
            logging.exception("CryptoPay invoice creation failed.")
            return None

    async def _invoice_paid_handler(self, update: Update, app: web.Application):
        invoice = update.payload
        if not invoice.payload:
            logging.warning("CryptoPay webhook without payload")
            return
        try:
            meta = json.loads(invoice.payload)
            user_id = int(meta["user_id"])
            months = float(meta.get("subscription_months") or 0)
            payment_db_id = int(meta["payment_db_id"])
            sale_mode = meta.get("sale_mode") or (
                "traffic" if self.settings.traffic_sale_mode else "subscription"
            )
            traffic_gb = float(meta.get("traffic_gb")) if meta.get("traffic_gb") else months
        except Exception:
            logging.exception("Failed to parse CryptoPay payload.")
            return

        async_session_factory: sessionmaker = app["async_session_factory"]
        bot: Bot = app["bot"]
        settings: Settings = app["settings"]
        i18n: JsonI18n = app["i18n"]
        subscription_service: SubscriptionService = app["subscription_service"]
        referral_service: ReferralService = app["referral_service"]

        async with async_session_factory() as session:
            payment = await payment_dal.get_payment_by_db_id(session, payment_db_id)
            if not payment:
                logging.error("CryptoPay webhook: payment %s not found.", payment_db_id)
                return
            if payment.status == "succeeded":
                logging.info("CryptoPay webhook: payment %s already succeeded.", payment_db_id)
                return

            try:
                await payment_dal.update_provider_payment_and_status(
                    session,
                    payment_db_id,
                    str(invoice.invoice_id),
                    PAYMENT_STATUS_PENDING_FINALIZATION,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logging.exception(
                    "Failed to mark CryptoPay invoice %s as succeeded.",
                    payment_db_id,
                )
                return

            payment = await payment_dal.get_payment_by_db_id(session, payment_db_id)
            if not payment:
                logging.error(
                    "CryptoPay webhook: payment %s vanished after status update.",
                    payment_db_id,
                )
                return

            currency = invoice.asset or settings.DEFAULT_CURRENCY_SYMBOL
            await finalize_successful_payment(
                PaymentSuccessRequest(
                    bot=bot,
                    settings=settings,
                    i18n=i18n,
                    session=session,
                    subscription_service=subscription_service,
                    referral_service=referral_service,
                    payment=payment,
                    user_id=user_id,
                    amount=float(invoice.amount),
                    currency=str(currency),
                    sale_mode=sale_mode,
                    months=int(months) if months else int(traffic_gb),
                    traffic_amount=float(traffic_gb),
                    provider_subscription="cryptopay",
                    provider_notification="crypto_pay",
                    log_prefix="CryptoPay webhook",
                )
            )

    def _validate_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        if not self.token:
            return False

        expected_signature = hmac.new(
            hashlib.sha256(self.token.encode("utf-8")).digest(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_signature, signature or ""):
            logger.error("CryptoPay signature mismatch")
            return False
        return True

    async def parse_payload(self, request: web.Request) -> ProviderWebhookPayload:
        raw_body = await request.read()
        signature = request.headers.get("crypto-pay-api-signature", "")
        return ProviderWebhookPayload(raw_body=raw_body, signature=signature)

    def verify_signature(self, payload: ProviderWebhookPayload) -> bool:
        return self._validate_webhook_signature(payload.raw_body, payload.signature)

    async def handle_verified_webhook(
        self,
        request: web.Request,
        payload: ProviderWebhookPayload,
    ) -> web.Response:
        del payload
        client = self.client
        if not client:
            return web.Response(status=503, text=self.disabled_response_text)
        return await client.get_updates(request)


async def cryptopay_webhook_route(request: web.Request) -> web.Response:
    service: CryptoPayService = request.app["cryptopay_service"]
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_crypto_router")


@router.callback_query(F.data.startswith("pay_crypto:"))
async def pay_crypto_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    cryptopay_service: CryptoPayService,
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

    if not cryptopay_service or not getattr(cryptopay_service, "configured", False):
        await notify_service_unavailable(callback, translator)
        return

    parts = parse_payment_callback(callback.data or "")
    if not parts:
        await notify_callback_parse_error(callback, translator)
        return
    parts, hwid_quote = await quote_hwid_callback_parts(
        session=session,
        user_id=callback.from_user.id,
        parts=parts,
        subscription_service=cryptopay_service.subscription_service,
        currency=default_currency_key_for_settings(settings),
    )
    if not parts:
        await notify_callback_parse_error(callback, translator)
        return

    payment_description = describe_payment(translator, parts)
    invoice_url = await cryptopay_service.create_invoice(
        session=session,
        user_id=callback.from_user.id,
        months=parts.months,
        amount=parts.price,
        description=payment_description,
        sale_mode=parts.sale_mode,
        hwid_quote=hwid_quote,
        currency=default_payment_currency_code_for_settings(settings),
    )

    if invoice_url:
        await render_payment_link(
            callback,
            translator=translator,
            current_lang=current_lang,
            i18n=i18n,
            parts=parts,
            payment_url=invoice_url,
            log_prefix=_LOG,
        )
        return

    from ..shared import safe_callback_answer

    await safe_callback_answer(callback, translator("error_payment_gateway"), show_alert=True)


def create_service(ctx: ServiceFactoryContext) -> CryptoPayService:
    bundle = ctx.config_for("cryptopay_service")
    config = (
        bundle.config
        if bundle and isinstance(bundle.config, CryptoPayConfig)
        else CryptoPayConfig()
    )
    return CryptoPayService(
        bot=ctx.bot,
        settings=ctx.settings,
        config=config,
        i18n=ctx.i18n,
        async_session_factory=ctx.async_session_factory,
        subscription_service=ctx.subscription_service,
        referral_service=ctx.referral_service,
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    service: CryptoPayService = ctx.request.app["cryptopay_service"]
    if not service or not service.configured:
        return payment_unavailable()
    url = await service.create_invoice(
        session=ctx.session,
        user_id=ctx.user_id,
        months=ctx.months,
        amount=ctx.price,
        description=ctx.description,
        sale_mode=ctx.sale_mode,
        url_kind="web",
        currency=ctx.currency,
        hwid_quote={
            "valid_from": ctx.hwid_valid_from,
            "valid_until": ctx.hwid_valid_until,
            "pricing_period_months": ctx.hwid_pricing_period_months,
            "proration_ratio": ctx.hwid_proration_ratio,
            "full_price": ctx.hwid_full_price,
        }
        if ctx.hwid_valid_from and ctx.hwid_valid_until
        else None,
        hwid_device_count=ctx.hwid_device_count,
    )
    if not url:
        return payment_failed()
    return payment_link_response(payment_url=url, payment_id=None)


_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="CryptoPay",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_CRYPTOPAY_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_CRYPTOPAY_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_CRYPTOPAY_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "Bitcoin",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_CRYPTOPAY_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_CRYPTOPAY_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_CRYPTOPAY_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            "₿",
            "TELEGRAM_EMOJI",
        ),
    )
)

_CONFIG_MANIFEST = (
    ProviderManifestField(
        "CRYPTOPAY_ENABLED", "bool", "Включена", subsection="CryptoPay", attr="ENABLED"
    ),
    ProviderManifestField(
        "CRYPTOPAY_TOKEN", "string", "Token", subsection="CryptoPay", secret=True, attr="TOKEN"
    ),
    ProviderManifestField(
        "CRYPTOPAY_NETWORK",
        "string",
        "Network",
        placeholder="mainnet",
        subsection="CryptoPay",
        attr="NETWORK",
    ),
    ProviderManifestField(
        "CRYPTOPAY_CURRENCY_TYPE",
        "string",
        "Currency type",
        description="fiat or crypto.",
        placeholder="fiat",
        subsection="CryptoPay",
        attr="CURRENCY_TYPE",
    ),
    ProviderManifestField(
        "CRYPTOPAY_ASSET",
        "string",
        "Asset",
        placeholder="RUB",
        subsection="CryptoPay",
        attr="ASSET",
    ),
)


SPEC = PaymentProviderSpec(
    id="cryptopay",
    provider_key="cryptopay",
    label="CryptoPay",
    webapp_label="CryptoPay",
    webapp_labels={"ru": "CryptoPay", "en": "CryptoPay"},
    webapp_icon="Bitcoin",
    telegram_labels={"ru": "CryptoBot", "en": "CryptoBot"},
    pending_status="pending_cryptopay",
    enabled=lambda config: bool(getattr(config, "ENABLED", False)),
    service_key="cryptopay_service",
    callback_prefix="pay_crypto",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/cryptopay",
    webhook_route=cryptopay_webhook_route,
    create_webapp_payment=create_webapp_payment,
    emoji="₿",
    telegram_emoji="₿",
    config_class=CryptoPayConfig,
    presentation_class=CryptoPayPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supported_currencies_resolver=_cryptopay_supported_currencies,
    currency_support_note=(
        "Crypto Pay supports different sets for fiat invoices and crypto invoices; "
        "CURRENCY_TYPE selects which set is active."
    ),
    currency_support_url="https://help.crypt.bot/crypto-pay-api/",
)
