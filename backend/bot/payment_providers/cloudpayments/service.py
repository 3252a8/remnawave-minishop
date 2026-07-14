from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, unquote_plus

from aiogram import Bot, F, Router, types
from aiohttp import web
from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from db.dal import payment_dal, user_billing_dal

from ..base import (
    PaymentProviderSpec,
    ProviderEnvConfig,
    ServiceFactoryContext,
    WebAppPaymentContext,
    normalize_payment_currency_code,
    provider_env_file,
    provider_runtime_enabled,
)
from ..shared import (
    CreatePaymentRequest,
    HttpClientMixin,
    LinkPaymentDescriptor,
    PaymentSuccessRequest,
    RecurringChargeContext,
    RecurringChargeResult,
    build_payment_record_payload,
    check_webhook_source_ip,
    constant_time_compare,
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
    safe_callback_answer,
)
from ..shared.app_context import app_required
from .manifest import _CONFIG_MANIFEST, _PRESENTATION_MANIFEST

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService

_LOG = "cloudpayments"

# CloudPayments documents these as supported payment currencies for the widget
# and the Orders API (https://developers.cloudpayments.ru/#valyuty).
CLOUDPAYMENTS_SUPPORTED_CURRENCIES = (
    "RUB",
    "USD",
    "EUR",
    "GBP",
    "KZT",
    "UAH",
    "BYN",
    "AZN",
    "AMD",
    "KGS",
)

# Notification ``Status`` values (Pay / Fail webhooks).
_SUCCESS_STATUSES = {"completed", "authorized"}
_FAILED_STATUSES = {"declined", "cancelled", "canceled"}

# CloudPayments interprets the response body ``code`` field; 0 acknowledges the
# notification, any other documented code rejects it.
_CODE_OK = {"code": 0}


class CloudPaymentsConfig(ProviderEnvConfig):
    """All CloudPayments env vars. Lives inside the provider module."""

    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="CLOUDPAYMENTS_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    PUBLIC_ID: str | None = None
    API_SECRET: str | None = None
    BASE_URL: str = Field(default="https://api.cloudpayments.ru")
    RETURN_URL: str | None = None
    FAILED_URL: str | None = None
    RECURRING_ENABLED: bool = Field(default=False)
    VERIFY_WEBHOOK_SIGNATURE: bool = Field(default=True)
    TRUSTED_IPS: str = Field(default="")

    @field_validator(
        "PUBLIC_ID",
        "API_SECRET",
        "RETURN_URL",
        "FAILED_URL",
        mode="before",
    )
    @classmethod
    def _strip_optional(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def webhook_path(self) -> str:
        return "/webhook/cloudpayments"

    @property
    def trusted_ips_list(self) -> list[str]:
        return [item.strip() for item in (self.TRUSTED_IPS or "").split(",") if item.strip()]


class CloudPaymentsPresentation(ProviderEnvConfig):
    """Admin-tunable button text/icon overrides for CloudPayments."""

    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_CLOUDPAYMENTS_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: str | None = None
    WEBAPP_LABEL_EN: str | None = None
    WEBAPP_ICON: str | None = None
    TELEGRAM_LABEL_RU: str | None = None
    TELEGRAM_LABEL_EN: str | None = None
    TELEGRAM_EMOJI: str | None = None


def _cloudpayments_order_success(status: int, data: Any) -> bool:
    return status == 200 and bool((data or {}).get("Success"))


class CloudPaymentsService(HttpClientMixin):
    """Client for the CloudPayments Orders API (api.cloudpayments.ru).

    Outgoing requests authenticate with HTTP Basic auth: the Public ID is the
    username and the API Secret is the password. Pay/Fail notifications arrive
    as ``application/x-www-form-urlencoded`` bodies signed with an
    HMAC-SHA256 (base64) digest of the raw body under the API Secret, carried
    in the ``Content-HMAC`` header (older integrations use ``X-Content-HMAC``).
    """

    def __init__(
        self,
        *,
        bot: Bot,
        settings: Settings,
        config: CloudPaymentsConfig,
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
                "CloudPaymentsService initialized but not fully configured. Payments disabled."
            )

    @property
    def configured(self) -> bool:
        return bool(provider_runtime_enabled(self.config) and self.public_id and self.api_secret)

    @property
    def base_url(self) -> str:
        return (self.config.BASE_URL or "https://api.cloudpayments.ru").rstrip("/")

    @property
    def public_id(self) -> str:
        return (self.config.PUBLIC_ID or "").strip()

    @property
    def api_secret(self) -> str:
        return (self.config.API_SECRET or "").strip()

    @property
    def return_url(self) -> str:
        return self.config.RETURN_URL or f"https://t.me/{self._default_return_url}"

    @property
    def failed_url(self) -> str:
        return self.config.FAILED_URL or self.return_url

    @property
    def verify_webhook_signature(self) -> bool:
        return bool(self.config.VERIFY_WEBHOOK_SIGNATURE)

    @property
    def recurring_active(self) -> bool:
        """Token charges are available only when explicitly enabled."""
        return bool(self.configured and self.config.RECURRING_ENABLED)

    def _auth_headers(self) -> dict[str, str]:
        token = base64.b64encode(f"{self.public_id}:{self.api_secret}".encode()).decode("ascii")
        return {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }

    async def create_order(
        self,
        *,
        payment_db_id: int,
        user_id: int | None,
        amount: float,
        currency: str | None,
        description: str,
        email: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        if not self.configured:
            logger.error("CloudPaymentsService is not configured. Cannot create order.")
            return False, {"message": "service_not_configured"}

        currency_code = normalize_payment_currency_code(
            currency or self.settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
        )
        if currency_code not in CLOUDPAYMENTS_SUPPORTED_CURRENCIES:
            return False, {
                "message": "unsupported_currency",
                "currency": currency_code,
                "supported_currencies": list(CLOUDPAYMENTS_SUPPORTED_CURRENCIES),
            }

        body: dict[str, Any] = {
            "Amount": float(format_decimal_amount(amount)),
            "Currency": currency_code,
            "Description": description[:248] if description else "Payment",
            "InvoiceId": str(payment_db_id),
            "RequireConfirmation": False,
            "SuccessRedirectUrl": self.return_url,
            "FailRedirectUrl": self.failed_url,
        }
        if user_id is not None:
            body["AccountId"] = str(user_id)
        if email:
            body["Email"] = email

        session = await self._get_session()
        success, data = await post_json_request(
            session,
            f"{self.base_url}/orders/create",
            body=body,
            headers=self._auth_headers(),
            log_prefix="CloudPayments create_order",
            is_success=_cloudpayments_order_success,
        )
        if not success:
            return False, data
        model = data.get("Model")
        return True, model if isinstance(model, dict) else data

    async def charge_token(
        self,
        *,
        payment_db_id: int,
        user_id: int,
        token: str,
        amount: float,
        currency: str | None,
        description: str,
        metadata: dict[str, str] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        if not self.configured:
            logger.error("CloudPaymentsService is not configured. Cannot charge token.")
            return False, {"message": "service_not_configured"}

        currency_code = normalize_payment_currency_code(
            currency or self.settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
        )
        if currency_code not in CLOUDPAYMENTS_SUPPORTED_CURRENCIES:
            return False, {
                "message": "unsupported_currency",
                "currency": currency_code,
                "supported_currencies": list(CLOUDPAYMENTS_SUPPORTED_CURRENCIES),
            }

        body: dict[str, Any] = {
            "Amount": float(format_decimal_amount(amount)),
            "Currency": currency_code,
            "Description": description[:248] if description else "Payment",
            "AccountId": str(user_id),
            "InvoiceId": str(payment_db_id),
            "Token": token,
            # Merchant-initiated scheduled charge of saved credentials.
            "TrInitiatorCode": 0,
            "PaymentScheduled": 1,
        }
        if metadata:
            body["JsonData"] = {"cloudpayments": dict(metadata)}

        session = await self._get_session()
        success, data = await post_json_request(
            session,
            f"{self.base_url}/payments/tokens/charge",
            body=body,
            headers=self._auth_headers(),
            log_prefix="CloudPayments token charge",
            is_success=_cloudpayments_order_success,
        )
        if not success:
            return False, data
        model = data.get("Model")
        return True, model if isinstance(model, dict) else data

    async def charge_saved_payment_method(
        self, context: RecurringChargeContext
    ) -> RecurringChargeResult:
        """Charge a stored CloudPayments ``Token`` for auto-renew."""
        if not self.recurring_active:
            return RecurringChargeResult.failed("recurring_inactive")
        token = str(getattr(context.saved_method, "provider_payment_method_id", "") or "").strip()
        if not token:
            return RecurringChargeResult.failed("missing_saved_method")

        payment_payload = build_payment_record_payload(
            user_id=context.user_id,
            amount=float(context.amount),
            currency=context.currency,
            status="pending_cloudpayments",
            description=context.description,
            months=context.months,
            provider="cloudpayments",
            sale_mode=context.sale_mode,
            hwid_quote=dict(context.hwid_quote or {}) or None,
        )
        try:
            payment = await payment_dal.create_payment_record(context.session, payment_payload)
        except Exception as exc:
            logger.exception("CloudPayments auto-renew failed to create local payment record")
            return RecurringChargeResult.failed(str(exc))

        try:
            success, response_data = await self.charge_token(
                payment_db_id=payment.payment_id,
                user_id=context.user_id,
                token=token,
                amount=float(context.amount),
                currency=context.currency,
                description=context.description,
                metadata=dict(context.metadata),
            )
        except Exception as exc:
            logger.exception("CloudPayments auto-renew token charge failed before API response")
            try:
                await payment_dal.update_payment_status_by_db_id(
                    context.session,
                    payment.payment_id,
                    "failed_creation",
                )
            except Exception:
                logger.exception(
                    "CloudPayments auto-renew failed to mark payment %s as failed_creation",
                    payment.payment_id,
                )
            return RecurringChargeResult.failed(str(exc))

        provider_payment_id = first_value(
            response_data,
            "TransactionId",
            "transactionId",
            "Id",
            "id",
        )
        status = str(first_value(response_data, "Status", "status") or "").lower() or None
        charge_declined = status in _FAILED_STATUSES
        if provider_payment_id:
            try:
                await payment_dal.update_provider_payment_and_status(
                    context.session,
                    payment.payment_id,
                    str(provider_payment_id),
                    "pending_cloudpayments",
                )
            except Exception:
                logger.exception(
                    "CloudPayments auto-renew failed to store provider payment id %s",
                    provider_payment_id,
                )
        if not success or charge_declined:
            try:
                await payment_dal.update_payment_status_by_db_id(
                    context.session,
                    payment.payment_id,
                    "failed_creation",
                )
            except Exception:
                logger.exception(
                    "CloudPayments auto-renew failed to mark payment %s as failed_creation",
                    payment.payment_id,
                )
            return RecurringChargeResult.failed(str(response_data.get("Message") or response_data))
        return RecurringChargeResult.ok(
            provider_payment_id=str(provider_payment_id) if provider_payment_id else None,
            status=status,
        )

    async def try_reuse_pending_payment(self, payment: Any) -> str | None:
        """Return the existing order URL when the local payment is still pending.

        CloudPayments order links stay valid until they are paid or expire, and
        a paid order would already have flipped the payment to ``succeeded`` via
        the webhook (so it would not be selected as a reusable pending record).
        Reusing the stored link avoids spawning a duplicate order on re-clicks.
        """
        payment_url = str(getattr(payment, "provider_payment_url", None) or "").strip()
        return payment_url or None

    def verify_signature(self, raw_body: bytes, received_signature: str) -> bool:
        """Verify the ``Content-HMAC`` digest on a CloudPayments notification."""
        received = str(received_signature or "").strip()
        if not received:
            logger.warning("CloudPayments webhook: missing HMAC header.")
            return False
        secret = self.api_secret
        if not secret:
            logger.error("CloudPayments webhook: no API secret configured.")
            return False

        candidates = [raw_body]
        try:
            decoded = unquote_plus(raw_body.decode("utf-8")).encode("utf-8")
            if decoded != raw_body:
                candidates.append(decoded)
        except Exception:
            pass

        for body in candidates:
            digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
            expected = base64.b64encode(digest).decode("ascii")
            if constant_time_compare(expected, received):
                return True
        return False

    async def _persist_recurring_payment_method(
        self,
        session: AsyncSession,
        *,
        payment: Any,
        payload_getter: Any,
    ) -> None:
        if not self.recurring_active:
            return
        token = str(payload_getter("Token") or "").strip()
        if not token:
            return
        user_id = getattr(payment, "user_id", None)
        if user_id is None:
            return
        card_last4 = payload_getter("CardLastFour")
        card_network = payload_getter("CardType") or "Card"
        try:
            await user_billing_dal.upsert_user_payment_method(
                session,
                user_id=int(user_id),
                provider_payment_method_id=token,
                provider="cloudpayments",
                card_last4=card_last4,
                card_network=card_network,
                set_default=True,
            )
        except Exception:
            logger.exception(
                "CloudPayments webhook: failed to persist saved payment token for user %s",
                user_id,
            )

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.json_response({"code": 13}, status=503)

        trusted = self.config.trusted_ips_list
        ip_check = check_webhook_source_ip(
            request,
            trusted_ips=trusted,
            trusted_proxies=self.settings.trusted_proxies,
            allow_empty=True,
        )
        if not ip_check.allowed:
            logger.warning(
                "CloudPayments webhook denied from unauthorized IP source "
                "(client_ip=%s remote=%s x_forwarded_for=%s).",
                ip_check.client_ip,
                request.remote,
                request.headers.get("X-Forwarded-For"),
            )
            return web.json_response({"code": 13}, status=403)

        raw_body = await request.read()
        if self.verify_webhook_signature:
            signatures = (
                request.headers.get("Content-HMAC"),
                request.headers.get("X-Content-HMAC"),
            )
            if not any(
                signature and self.verify_signature(raw_body, signature) for signature in signatures
            ):
                logger.error("CloudPayments webhook: invalid signature.")
                return web.json_response({"code": 13}, status=403)

        payload = {
            str(key): value
            for key, value in parse_qsl(raw_body.decode("utf-8"), keep_blank_values=True)
        }

        def _get(*keys: str) -> str | None:
            for key in keys:
                value = payload.get(key) or payload.get(key.lower())
                if value:
                    return value
            return None

        order_id_raw = _get("InvoiceId")
        provider_payment_id = _get("TransactionId")
        status = (_get("Status") or "").strip().lower()

        if not order_id_raw and not provider_payment_id:
            logger.error("CloudPayments webhook: missing identifiers: %s", payload)
            return web.json_response({"code": 13}, status=400)

        async with self.async_session_factory() as session:
            payment = await lookup_payment_by_order_or_provider_id(
                session,
                order_id_raw=order_id_raw,
                provider_payment_id=provider_payment_id,
            )
            if not payment:
                logger.error(
                    "CloudPayments webhook: payment not found (invoice_id=%s, transaction_id=%s)",
                    order_id_raw,
                    provider_payment_id,
                )
                return web.json_response({"code": 13}, status=404)

            resolved_provider_id = provider_payment_id or str(payment.payment_id)
            sale_mode = payment.sale_mode or (
                "traffic" if self.settings.traffic_sale_mode else "subscription"
            )
            payment_months = payment_units_for_activation(payment, sale_mode)

            is_success = status in _SUCCESS_STATUSES
            if is_success:
                if payment.status == "succeeded":
                    logger.info(
                        "CloudPayments webhook: payment %s already succeeded.", payment.payment_id
                    )
                    return web.json_response(_CODE_OK)

                webhook_amount = _get("Amount")
                webhook_currency = _get("Currency")
                if not payment_amount_and_currency_match(
                    expected_amount=payment.amount,
                    expected_currency=payment.currency,
                    received_amount=webhook_amount,
                    received_currency=webhook_currency,
                    allow_overpayment=True,
                ):
                    logger.error(
                        "CloudPayments webhook: payment details mismatch for payment %s "
                        "(expected=%s %s, received=%s %s)",
                        payment.payment_id,
                        payment.amount,
                        payment.currency,
                        webhook_amount,
                        webhook_currency,
                    )
                    return web.json_response({"code": 12}, status=200)

                try:
                    payment = await payment_dal.claim_payment_finalization(
                        session,
                        payment.payment_id,
                        provider_payment_id=resolved_provider_id,
                    )
                    if payment is None:
                        return web.json_response(_CODE_OK)
                    await self._persist_recurring_payment_method(
                        session,
                        payment=payment,
                        payload_getter=_get,
                    )
                except Exception:
                    await session.rollback()
                    logger.exception(
                        "CloudPayments webhook: failed to mark payment %s as succeeded.",
                        resolved_provider_id,
                    )
                    return web.json_response({"code": 13}, status=500)

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
                        provider_subscription="cloudpayments",
                        provider_notification="cloudpayments",
                        db_user=payment.user,
                        log_prefix="CloudPayments webhook",
                    )
                )
                if outcome is None:
                    return web.json_response({"code": 13}, status=500)
                return web.json_response(_CODE_OK)

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
                    logger.exception(
                        "CloudPayments webhook: failed to mark payment %s as failed.",
                        resolved_provider_id,
                    )
                    return web.json_response({"code": 13}, status=500)
                await notify_user_payment_failed(
                    bot=self.bot,
                    settings=self.settings,
                    i18n=self.i18n,
                    session=session,
                    payment=payment,
                )
                return web.json_response(_CODE_OK)

            logger.warning(
                "CloudPayments webhook: unhandled status '%s' for payment %s",
                status,
                resolved_provider_id,
            )
            return web.json_response(_CODE_OK)


async def cloudpayments_webhook_route(request: web.Request) -> web.Response:
    service: CloudPaymentsService = app_required(
        request, "cloudpayments_service", CloudPaymentsService
    )
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_cloudpayments_router")


@router.callback_query(F.data.startswith("pay_cp:"))
async def pay_cloudpayments_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    cloudpayments_service: CloudPaymentsService,
    session: AsyncSession,
) -> None:
    await run_callback_payment(
        _DESCRIPTOR,
        callback,
        settings,
        i18n_data,
        cloudpayments_service,
        session,
    )


def create_service(ctx: ServiceFactoryContext) -> CloudPaymentsService:
    bundle = ctx.config_for("cloudpayments_service")
    config = (
        bundle.config
        if bundle and isinstance(bundle.config, CloudPaymentsConfig)
        else CloudPaymentsConfig()
    )
    return CloudPaymentsService(
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


async def _create_payment(
    service: CloudPaymentsService,
    request: CreatePaymentRequest,
) -> tuple[bool, dict]:
    return await service.create_order(
        payment_db_id=request.payment.payment_id,
        user_id=request.user_id,
        amount=request.amount,
        currency=request.currency,
        description=request.description,
    )


async def _reuse_payment(service: CloudPaymentsService, payment: Any) -> str | None:
    return await service.try_reuse_pending_payment(payment)


def _extract_payment_url(response_data: dict) -> str | None:
    return first_value(response_data, "Url", "url")


def _extract_provider_id(response_data: dict) -> str | None:
    return first_value(response_data, "Id", "Number", "id")


SPEC = PaymentProviderSpec(
    id="cloudpayments",
    provider_key="cloudpayments",
    label="CloudPayments",
    webapp_label="CloudPayments",
    webapp_labels={"ru": "CloudPayments", "en": "CloudPayments"},
    webapp_icon="CreditCard",
    logo_url="/provider-logos/cloudpayments.png",
    telegram_labels={"ru": "CloudPayments", "en": "CloudPayments"},
    telegram_emoji="💳",
    pending_status="pending_cloudpayments",
    enabled=lambda config: bool(getattr(config, "ENABLED", False)),
    service_key="cloudpayments_service",
    callback_prefix="pay_cp",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/cloudpayments",
    webhook_route=cloudpayments_webhook_route,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=CloudPaymentsConfig,
    presentation_class=CloudPaymentsPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supports_recurring=True,
    supported_currencies=CLOUDPAYMENTS_SUPPORTED_CURRENCIES,
    currency_support_note=(
        "CloudPayments orders accept RUB, USD, EUR, GBP and CIS currencies as the payment currency."
    ),
    info_url="https://cloudpayments.ru/",
    currency_support_url="https://developers.cloudpayments.ru/#valyuty",
)

_DESCRIPTOR: LinkPaymentDescriptor[CloudPaymentsService] = LinkPaymentDescriptor(
    spec=SPEC,
    provider_key="cloudpayments",
    pending_status="pending_cloudpayments",
    display_name="CloudPayments",
    log_prefix=_LOG,
    service_app_key="cloudpayments_service",
    service_type=CloudPaymentsService,
    create=_create_payment,
    reuse=_reuse_payment,
    extract_url=_extract_payment_url,
    extract_provider_id=_extract_provider_id,
    callback_before_create=safe_callback_answer,
    callback_reuse_answer=True,
)
