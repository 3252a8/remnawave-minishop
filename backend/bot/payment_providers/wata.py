import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from aiogram import Bot, F, Router, types
from aiohttp import web
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
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
    lookup_payment_by_order_or_provider_id,
    make_translator,
    notify_callback_parse_error,
    notify_payment_record_failure,
    notify_service_unavailable,
    notify_user_payment_failed,
    parse_payment_callback,
    payment_failed,
    payment_unavailable,
    post_json_request,
    render_link_or_fail,
)

router = Router(name="user_subscription_payments_wata_router")
_LOG = "wata"


class WataConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="WATA_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    API_TOKEN: Optional[str] = None
    BASE_URL: str = Field(default="https://api.wata.pro/api/h2h")
    RETURN_URL: Optional[str] = None
    FAILED_URL: Optional[str] = None
    PAYMENT_LINK_TTL_DAYS: int = Field(default=3)
    WEBHOOK_VERIFY_SIGNATURE: bool = Field(default=True)
    PUBLIC_KEY: Optional[str] = None
    TRUSTED_IPS: str = Field(default="62.84.126.140,51.250.106.150")

    @field_validator("PAYMENT_LINK_TTL_DAYS", mode="before")
    @classmethod
    def _clamp_ttl(cls, v):
        if isinstance(v, str):
            v = v.strip()
        try:
            value = int(v)
        except (TypeError, ValueError):
            return 3
        return min(30, max(1, value))

    @field_validator("API_TOKEN", "RETURN_URL", "FAILED_URL", "PUBLIC_KEY", mode="before")
    @classmethod
    def _strip_optional(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def webhook_path(self) -> str:
        return "/webhook/wata"

    @property
    def trusted_ips_list(self) -> List[str]:
        return [item.strip() for item in (self.TRUSTED_IPS or "").split(",") if item.strip()]


class WataPresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_WATA_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: Optional[str] = None
    WEBAPP_LABEL_EN: Optional[str] = None
    WEBAPP_ICON: Optional[str] = None
    TELEGRAM_LABEL_RU: Optional[str] = None
    TELEGRAM_LABEL_EN: Optional[str] = None
    TELEGRAM_EMOJI: Optional[str] = None


class WataService(HttpClientMixin):
    def __init__(
        self,
        *,
        bot: Bot,
        settings: Settings,
        config: WataConfig,
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
        self._cached_public_key_pem = None  # populated by webhook on first verify

        self._init_http_client(total_timeout=20)
        if not self.configured:
            logging.warning("WataService initialized but not fully configured. Payments disabled.")

    @property
    def configured(self) -> bool:
        return bool(self.config.ENABLED and self.api_token)

    @property
    def base_url(self) -> str:
        return (self.config.BASE_URL or "https://api.wata.pro/api/h2h").rstrip("/")

    @property
    def api_token(self) -> str:
        return self.config.API_TOKEN or ""

    @property
    def return_url(self) -> str:
        return self.config.RETURN_URL or f"https://t.me/{self._default_return_url}"

    @property
    def failed_url(self) -> str:
        return self.config.FAILED_URL or self.return_url

    @property
    def payment_link_ttl_days(self) -> int:
        return self.config.PAYMENT_LINK_TTL_DAYS

    @property
    def verify_webhook_signature(self) -> bool:
        return self.config.WEBHOOK_VERIFY_SIGNATURE

    @property
    def _public_key_pem(self):
        return self.config.PUBLIC_KEY or self._cached_public_key_pem

    @_public_key_pem.setter
    def _public_key_pem(self, value):
        self._cached_public_key_pem = value

    def _auth_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    async def create_payment_link(
        self,
        *,
        payment_db_id: int,
        amount: float,
        currency: Optional[str],
        description: str,
    ) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            logging.error("WataService is not configured. Cannot create payment link.")
            return False, {"message": "service_not_configured"}

        session = await self._get_session()
        expires_at = datetime.now(timezone.utc) + timedelta(days=self.payment_link_ttl_days)
        body: Dict[str, Any] = {
            "amount": float(format_decimal_amount(amount)),
            "currency": (currency or self.settings.DEFAULT_CURRENCY_SYMBOL or "RUB").upper(),
            "description": description,
            "orderId": str(payment_db_id),
            "successRedirectUrl": self.return_url,
            "failRedirectUrl": self.failed_url,
            "expirationDateTime": expires_at.isoformat().replace("+00:00", "Z"),
        }
        return await post_json_request(
            session,
            f"{self.base_url}/links",
            body=body,
            headers=self._auth_headers(),
            log_prefix="Wata create_payment_link",
        )

    async def _get_public_key_pem(self) -> Optional[str]:
        if self._public_key_pem:
            value = self._public_key_pem
            return value.replace("\\n", "\n") if isinstance(value, str) else None

        session = await self._get_session()
        try:
            async with session.get(f"{self.base_url}/public-key") as response:
                if response.status != 200:
                    logging.error("Wata public key request failed with status %s", response.status)
                    return None
                data = await response.json()
                value = data.get("value") if isinstance(data, dict) else None
                if isinstance(value, str) and value.strip():
                    self._public_key_pem = value
                    return value.replace("\\n", "\n")
        except Exception:
            logging.exception("Wata public key request failed.")
        return None

    async def _verify_signature(self, raw_body: bytes, signature_header: str) -> bool:
        if not signature_header:
            return False
        public_key_pem = await self._get_public_key_pem()
        if not public_key_pem:
            return False
        try:
            public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
            signature = base64.b64decode(signature_header)
            public_key.verify(signature, raw_body, padding.PKCS1v15(), hashes.SHA512())
            return True
        except (InvalidSignature, ValueError, TypeError):
            logging.warning("Wata webhook: invalid signature.")
            return False
        except Exception:
            logging.exception("Wata webhook: signature verification failed.")
            return False

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.Response(status=503, text="wata_disabled")

        client_ip = request_client_ip(request, trusted_proxies=self.settings.trusted_proxies)
        trusted = self.config.trusted_ips_list
        if trusted and not ip_in_allowlist(client_ip, trusted):
            logging.warning("Wata webhook denied from unauthorized IP source.")
            return web.Response(status=403, text="forbidden")

        raw_body = await request.read()
        if self.verify_webhook_signature:
            signature = request.headers.get("X-Signature", "")
            if not await self._verify_signature(raw_body, signature):
                return web.Response(status=403, text="invalid_signature")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            logging.exception("Wata webhook: failed to parse JSON.")
            return web.Response(status=400, text="bad_request")

        transaction_id = str(payload.get("transactionId") or "").strip()
        status = str(payload.get("transactionStatus") or "").strip().lower()
        order_id_raw = payload.get("orderId")
        amount_raw = payload.get("amount")
        currency = payload.get("currency") or self.settings.DEFAULT_CURRENCY_SYMBOL or "RUB"

        if not status or not (transaction_id or order_id_raw):
            logging.error("Wata webhook: missing transaction status or ids: %s", payload)
            return web.Response(status=400, text="missing_fields")

        async with self.async_session_factory() as session:
            payment = await lookup_payment_by_order_or_provider_id(
                session,
                order_id_raw=order_id_raw,
                provider_payment_id=transaction_id or None,
            )
            if not payment:
                logging.error(
                    "Wata webhook: payment not found (order_id=%s, transaction_id=%s)",
                    order_id_raw,
                    transaction_id,
                )
                return web.Response(status=404, text="payment_not_found")

            if payment.status == "succeeded" and status == "paid":
                return web.Response(text="ok")

            resolved_transaction_id = transaction_id or str(payment.payment_id)

            if status == "paid":
                if amount_raw is not None:
                    try:
                        if not decimal_amounts_equal(amount_raw, payment.amount):
                            logging.warning(
                                "Wata webhook: amount mismatch for payment %s "
                                "(expected %s, got %s)",
                                payment.payment_id,
                                format_decimal_amount(payment.amount),
                                format_decimal_amount(amount_raw),
                            )
                    except Exception as exc:
                        logging.warning(
                            "Wata webhook: failed to compare amounts for %s: %s",
                            payment.payment_id,
                            exc,
                        )

                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        resolved_transaction_id,
                        "succeeded",
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logging.exception(
                        "Wata webhook: failed to mark payment %s as succeeded.",
                        resolved_transaction_id,
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
                        provider_subscription="wata",
                        provider_notification="wata",
                        db_user=payment.user,
                        log_prefix="Wata webhook",
                    )
                )
                if outcome is None:
                    return web.Response(status=500, text="processing_error")
                return web.Response(text="ok")

            if status == "declined":
                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        resolved_transaction_id,
                        "failed",
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logging.exception(
                        "Wata webhook: failed to mark payment %s as failed.",
                        resolved_transaction_id,
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

            logging.warning(
                "Wata webhook: unhandled status '%s' for transaction %s",
                status,
                transaction_id,
            )
            return web.Response(status=202, text="status_ignored")


@router.callback_query(F.data.startswith("pay_wata:"))
async def pay_wata_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    wata_service: WataService,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    translator = make_translator(i18n, current_lang)

    if not i18n or not callback.message:
        await notify_callback_parse_error(callback, translator)
        return

    if not wata_service or not wata_service.configured:
        logging.error("Wata service is not configured or unavailable.")
        await notify_service_unavailable(callback, translator)
        return

    parts = parse_payment_callback(callback.data or "")
    if not parts:
        logging.error("Invalid pay_wata data in callback: %s", callback.data)
        await notify_callback_parse_error(callback, translator)
        return

    currency_code = settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
    payment_description = describe_payment(translator, parts)
    record_payload = build_payment_record_payload(
        user_id=callback.from_user.id,
        amount=parts.price,
        currency=currency_code,
        status="pending_wata",
        description=payment_description,
        months=parts.months,
        provider="wata",
        sale_mode=parts.sale_mode,
    )

    try:
        payment_record = await payment_dal.create_payment_record(session, record_payload)
        await session.commit()
    except Exception:
        await session.rollback()
        logging.exception(
            "Wata: failed to create payment record for user %s.", callback.from_user.id
        )
        await notify_payment_record_failure(callback, translator)
        return

    success, response_data = await wata_service.create_payment_link(
        payment_db_id=payment_record.payment_id,
        amount=parts.price,
        currency=currency_code,
        description=payment_description,
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
        payment_url=first_value(response_data, "url"),
        provider_payment_id=first_value(response_data, "id"),
        log_prefix=_LOG,
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    settings: Settings = ctx.request.app["settings"]
    service: WataService = ctx.request.app["wata_service"]
    if not service or not service.configured:
        return payment_unavailable()

    currency = settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
    try:
        payment = await create_webapp_payment_record(
            ctx,
            amount=ctx.price,
            currency=currency,
            status="pending_wata",
            provider="wata",
        )
        success, response_data = await service.create_payment_link(
            payment_db_id=payment.payment_id,
            amount=ctx.price,
            currency=currency,
            description=ctx.description,
        )
    except Exception:
        await ctx.session.rollback()
        logging.exception("Wata WebApp payment failed")
        return payment_failed()

    return await finalize_webapp_link_payment(
        session=ctx.session,
        payment=payment,
        api_success=success,
        payment_url=first_value(response_data, "url") if success else None,
        provider_payment_id=first_value(response_data, "id"),
        log_prefix="Wata",
    )


async def wata_webhook_route(request: web.Request) -> web.Response:
    service: WataService = request.app["wata_service"]
    return await service.webhook_route(request)


def create_service(ctx: ServiceFactoryContext) -> WataService:
    bundle = ctx.config_for("wata_service")
    config = bundle.config if bundle and isinstance(bundle.config, WataConfig) else WataConfig()
    return WataService(
        bot=ctx.bot,
        settings=ctx.settings,
        config=config,
        i18n=ctx.i18n,
        async_session_factory=ctx.async_session_factory,
        subscription_service=ctx.subscription_service,
        referral_service=ctx.referral_service,
        default_return_url=ctx.bot_username_for_default_return,
    )


_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key, type=type_, label=label, description=description,
        placeholder=placeholder, subsection="Wata",
        target="presentation", attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        ("PAYMENT_WATA_WEBAPP_LABEL_RU", "string", "WebApp button text (RU)",
         "Custom Russian text shown in the Web App payment method button.", "", "WEBAPP_LABEL_RU"),
        ("PAYMENT_WATA_WEBAPP_LABEL_EN", "string", "WebApp button text (EN)",
         "Custom English text shown in the Web App payment method button.", "", "WEBAPP_LABEL_EN"),
        ("PAYMENT_WATA_WEBAPP_ICON", "icon", "WebApp button icon",
         "Lucide icon name rendered inside the Web App payment method button.",
         "WalletCards", "WEBAPP_ICON"),
        ("PAYMENT_WATA_TELEGRAM_LABEL_RU", "string", "Telegram button text (RU)",
         "Custom Russian text shown in Telegram bot payment buttons.", "", "TELEGRAM_LABEL_RU"),
        ("PAYMENT_WATA_TELEGRAM_LABEL_EN", "string", "Telegram button text (EN)",
         "Custom English text shown in Telegram bot payment buttons.", "", "TELEGRAM_LABEL_EN"),
        ("PAYMENT_WATA_TELEGRAM_EMOJI", "string", "Telegram button emoji",
         "Emoji prepended to the Telegram bot payment button when customized.",
         "💳", "TELEGRAM_EMOJI"),
    )
)

_CONFIG_MANIFEST = (
    ProviderManifestField("WATA_ENABLED", "bool", "Enabled", subsection="Wata", attr="ENABLED"),
    ProviderManifestField("WATA_API_TOKEN", "string", "API token", subsection="Wata",
                          secret=True, attr="API_TOKEN"),
    ProviderManifestField("WATA_BASE_URL", "url", "Base URL",
                          placeholder="https://api.wata.pro/api/h2h",
                          subsection="Wata", attr="BASE_URL"),
    ProviderManifestField("WATA_RETURN_URL", "url", "Return URL",
                          subsection="Wata", attr="RETURN_URL"),
    ProviderManifestField("WATA_FAILED_URL", "url", "Failed URL",
                          subsection="Wata", attr="FAILED_URL"),
    ProviderManifestField("WATA_PAYMENT_LINK_TTL_DAYS", "int", "Payment link lifetime (days)",
                          description="1..30; Wata defaults to 3 days and allows up to 30 days.",
                          subsection="Wata", min=1, max=30, attr="PAYMENT_LINK_TTL_DAYS"),
    ProviderManifestField("WATA_WEBHOOK_VERIFY_SIGNATURE", "bool", "Verify webhook signature",
                          subsection="Wata", attr="WEBHOOK_VERIFY_SIGNATURE"),
    ProviderManifestField("WATA_PUBLIC_KEY", "text", "Webhook public key",
                          description="Optional. If empty, the backend fetches it from Wata.",
                          subsection="Wata", secret=True, attr="PUBLIC_KEY"),
    ProviderManifestField("WATA_TRUSTED_IPS", "string", "Trusted IPs",
                          description="Comma-separated IP addresses accepted for Wata webhooks.",
                          subsection="Wata", attr="TRUSTED_IPS"),
)


SPEC = PaymentProviderSpec(
    id="wata",
    provider_key="wata",
    label="Wata",
    webapp_label="Wata",
    webapp_labels={"ru": "Wata", "en": "Wata"},
    webapp_icon="WalletCards",
    telegram_labels={"ru": "Wata", "en": "Wata"},
    telegram_emoji="💳",
    pending_status="pending_wata",
    enabled=lambda config: bool(getattr(config, "ENABLED", False)),
    service_key="wata_service",
    callback_prefix="pay_wata",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/wata",
    webhook_route=wata_webhook_route,
    create_webapp_payment=create_webapp_payment,
    config_class=WataConfig,
    presentation_class=WataPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
)
