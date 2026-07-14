from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
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
from db.dal import payment_dal

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
    constant_time_compare,
    finalize_successful_payment,
    first_value,
    format_decimal_amount,
    lookup_payment_by_order_or_provider_id,
    notify_user_payment_failed,
    payment_amount_matches,
    payment_units_for_activation,
    run_callback_payment,
    run_reuse_webapp_payment,
    run_webapp_payment,
    safe_callback_answer,
)
from ..shared.app_context import app_required
from .manifest import _CONFIG_MANIFEST, _PRESENTATION_MANIFEST

if TYPE_CHECKING:
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService
else:
    ReferralService = object
    SubscriptionService = object

logger = logging.getLogger(__name__)

_LOG = "pally"
PALLY_SUPPORTED_CURRENCIES = ("RUB", "USD", "EUR")

_SUCCESS_STATUSES = {"success", "overpaid"}
_FAILED_STATUSES = {"fail", "failed", "cancelled", "canceled"}
_PENDING_STATUSES = {"new", "process", "underpaid"}
_PAYMENT_METHODS = {"BANK_CARD", "SBP"}


class PallyConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PALLY_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    API_TOKEN: str | None = None
    SIGNATURE_TOKEN: str | None = None
    SHOP_ID: str | None = None
    BASE_URL: str = Field(default="https://pally.info/api/v1")
    RETURN_URL: str | None = None
    SUCCESS_URL: str | None = None
    FAIL_URL: str | None = None
    TTL_SECONDS: int | None = None
    PAYER_PAYS_COMMISSION: bool | None = None
    PAYMENT_METHOD: str | None = None
    LOCALE: str | None = None
    NAME: str | None = None

    @field_validator("TTL_SECONDS", mode="before")
    @classmethod
    def _empty_to_none_int(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
        return v

    @field_validator(
        "API_TOKEN",
        "SIGNATURE_TOKEN",
        "SHOP_ID",
        "RETURN_URL",
        "SUCCESS_URL",
        "FAIL_URL",
        "PAYMENT_METHOD",
        "LOCALE",
        "NAME",
        mode="before",
    )
    @classmethod
    def _strip_optional(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("PAYMENT_METHOD")
    @classmethod
    def _normalize_payment_method(cls, v: Any) -> str | None:
        if v is None:
            return None
        method = str(v).strip().upper()
        if not method:
            return None
        if method not in _PAYMENT_METHODS:
            raise ValueError("PALLY_PAYMENT_METHOD must be one of: BANK_CARD, SBP")
        return method

    @field_validator("LOCALE")
    @classmethod
    def _normalize_locale(cls, v: Any) -> str | None:
        if v is None:
            return None
        locale = str(v).strip().lower().split("-", 1)[0].split("_", 1)[0]
        return locale if locale in {"ru", "en"} else None

    @property
    def webhook_path(self) -> str:
        return "/webhook/pally"


class PallyPresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_PALLY_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: str | None = None
    WEBAPP_LABEL_EN: str | None = None
    WEBAPP_ICON: str | None = None
    TELEGRAM_LABEL_RU: str | None = None
    TELEGRAM_LABEL_EN: str | None = None
    TELEGRAM_EMOJI: str | None = None


def _payload_success(status: int, payload: Mapping[str, Any]) -> bool:
    if status < 200 or status >= 300:
        return False
    if "success" not in payload:
        return True
    value = payload.get("success")
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "success"}


def _response_error(payload: Mapping[str, Any]) -> Any:
    return payload.get("message") or payload.get("error") or payload.get("errors") or payload


def _bool_form_value(value: bool | None) -> str | None:
    if value is None:
        return None
    return "1" if value else "0"


def _status_value(payload: Mapping[str, Any] | None) -> str:
    if not payload:
        return ""
    return str(payload.get("status") or payload.get("Status") or "").strip().lower()


def _bill_id_value(payload: Mapping[str, Any] | None) -> str | None:
    return first_value(payload, "bill_id", "billId", "id", "TrsId", "trs_id")


def _payment_page_url(payload: Mapping[str, Any] | None) -> str | None:
    return first_value(
        payload,
        "link_page_url",
        "linkPageUrl",
        "page_url",
        "pageUrl",
        "transfer_url",
        "transferUrl",
        "link_url",
        "linkUrl",
        "payment_url",
        "paymentUrl",
        "url",
    )


class PallyService(HttpClientMixin):
    """Client for Pally / PayPalych bill API.

    The API accepts Bearer auth and form fields for bill creation. Payment
    postbacks are form-urlencoded and signed as uppercase MD5 of
    ``OutSum:InvId:token`` according to the provider contract.
    """

    def __init__(
        self,
        *,
        bot: Bot,
        settings: Settings,
        config: PallyConfig,
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
            logger.warning("PallyService initialized but not fully configured. Payments disabled.")

    @property
    def configured(self) -> bool:
        return bool(provider_runtime_enabled(self.config) and self.api_token and self.shop_id)

    @property
    def base_url(self) -> str:
        return (self.config.BASE_URL or "https://pally.info/api/v1").rstrip("/")

    @property
    def api_token(self) -> str:
        return (self.config.API_TOKEN or "").strip()

    @property
    def signature_token(self) -> str:
        return (self.config.SIGNATURE_TOKEN or "").strip() or self.api_token

    @property
    def shop_id(self) -> str:
        return (self.config.SHOP_ID or "").strip()

    @property
    def return_url(self) -> str:
        return self.config.RETURN_URL or f"https://t.me/{self._default_return_url}"

    @property
    def ttl_seconds(self) -> int | None:
        if self.config.TTL_SECONDS is None:
            return None
        return max(1, int(self.config.TTL_SECONDS))

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
        }

    async def _post_form(self, path: str, body: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        if not self.configured:
            logger.error("PallyService is not configured. Cannot call %s.", path)
            return False, {"message": "service_not_configured"}

        session = await self._get_session()
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            async with session.post(url, data=body, headers=self._auth_headers()) as response:
                response_text = await response.text()
                try:
                    response_data = json.loads(response_text) if response_text else {}
                except json.JSONDecodeError:
                    logger.error("Pally %s: invalid JSON response: %s", path, response_text[:500])
                    return False, {
                        "status": response.status,
                        "message": "invalid_json",
                        "raw": response_text,
                    }
                if not isinstance(response_data, dict):
                    response_data = {"data": response_data}
                if not _payload_success(response.status, response_data):
                    logger.error(
                        "Pally %s: API error (http=%s, body=%s)",
                        path,
                        response.status,
                        response_data,
                    )
                    return False, {
                        "status": response.status,
                        "message": _response_error(response_data),
                    }
                return True, response_data
        except Exception as exc:
            logger.exception("Pally %s: request failed.", path)
            return False, {"message": str(exc)}

    async def _get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        if not self.configured:
            return False, {"message": "service_not_configured"}

        session = await self._get_session()
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            async with session.get(
                url,
                params=dict(params or {}),
                headers=self._auth_headers(),
            ) as response:
                response_text = await response.text()
                try:
                    response_data = json.loads(response_text) if response_text else {}
                except json.JSONDecodeError:
                    logger.error("Pally %s: invalid JSON response: %s", path, response_text[:500])
                    return False, {
                        "status": response.status,
                        "message": "invalid_json",
                        "raw": response_text,
                    }
                if not isinstance(response_data, dict):
                    response_data = {"data": response_data}
                if not _payload_success(response.status, response_data):
                    logger.error(
                        "Pally %s: API error (http=%s, body=%s)",
                        path,
                        response.status,
                        response_data,
                    )
                    return False, {
                        "status": response.status,
                        "message": _response_error(response_data),
                    }
                return True, response_data
        except Exception as exc:
            logger.exception("Pally %s: request failed.", path)
            return False, {"message": str(exc)}

    async def create_bill(
        self,
        *,
        payment_db_id: int,
        amount: float,
        currency: str | None,
        description: str | None = None,
        language: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        if not self.configured:
            logger.error("PallyService is not configured. Cannot create bill.")
            return False, {"message": "service_not_configured"}

        currency_code = normalize_payment_currency_code(
            currency or self.settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
        )
        if currency_code not in PALLY_SUPPORTED_CURRENCIES:
            return False, {
                "message": "unsupported_currency",
                "currency": currency_code,
                "supported_currencies": list(PALLY_SUPPORTED_CURRENCIES),
            }

        locale = self.config.LOCALE
        if not locale and language:
            locale = str(language).strip().lower().split("-", 1)[0].split("_", 1)[0]
            if locale not in {"ru", "en"}:
                locale = None

        body: dict[str, Any] = {
            "amount": str(format_decimal_amount(amount)),
            "shop_id": self.shop_id,
            "order_id": str(payment_db_id),
            "description": (description or "Payment")[:255],
            "type": "normal",
            "currency_in": currency_code,
        }
        if locale:
            body["locale"] = locale
        if self.config.NAME:
            body["name"] = self.config.NAME[:255]
        if self.ttl_seconds:
            body["ttl"] = str(self.ttl_seconds)
        if self.return_url:
            body["return_url"] = self.return_url[:500]
        if self.config.SUCCESS_URL:
            body["success_url"] = self.config.SUCCESS_URL[:500]
        if self.config.FAIL_URL:
            body["fail_url"] = self.config.FAIL_URL[:500]
        commission = _bool_form_value(self.config.PAYER_PAYS_COMMISSION)
        if commission is not None:
            body["payer_pays_commission"] = commission
        if self.config.PAYMENT_METHOD:
            body["payment_method"] = self.config.PAYMENT_METHOD

        return await self._post_form("/bill/create", body)

    async def get_bill_status(self, bill_id: str) -> tuple[bool, dict[str, Any]]:
        if not bill_id:
            return False, {"message": "missing_bill_id"}
        return await self._get_json("/bill/status", params={"id": bill_id})

    async def try_reuse_pending_bill(self, payment: Any) -> str | None:
        provider_payment_id = str(getattr(payment, "provider_payment_id", None) or "").strip()
        payment_url = str(getattr(payment, "provider_payment_url", None) or "").strip()
        if not provider_payment_id or not payment_url:
            return None

        success, data = await self.get_bill_status(provider_payment_id)
        if not success or _status_value(data) not in _PENDING_STATUSES:
            return None
        returned_ids = {
            str(data.get("id") or "").strip(),
            str(data.get("bill_id") or "").strip(),
        }
        returned_ids.discard("")
        if returned_ids and provider_payment_id not in returned_ids:
            return None
        order_id = first_value(data, "order_id", "orderId")
        if order_id is not None and str(order_id) != str(payment.payment_id):
            return None
        return payment_url

    def calculate_signature(self, out_sum: Any, inv_id: Any) -> str | None:
        token = self.signature_token
        if not token:
            return None
        raw = f"{out_sum}:{inv_id}:{token}".encode()
        try:
            digest = hashlib.md5(raw, usedforsecurity=False)
        except TypeError:  # pragma: no cover - Python without usedforsecurity
            digest = hashlib.md5(raw)
        return digest.hexdigest().upper()

    def verify_signature(self, out_sum: Any, inv_id: Any, received_signature: Any) -> bool:
        received = str(received_signature or "").strip().upper()
        if not received:
            logger.warning("Pally webhook: missing signature.")
            return False
        expected = self.calculate_signature(out_sum, inv_id)
        if not expected:
            logger.error("Pally webhook: no signature token configured.")
            return False
        return constant_time_compare(expected, received)

    def _amount_matches_payment(
        self, payload: Mapping[str, Any], payment: Any, status: str
    ) -> bool:
        out_sum = payload.get("OutSum")
        if out_sum is None:
            out_sum = payload.get("out_sum")
        out_sum_decimal = self._strict_callback_amount(out_sum)
        if out_sum_decimal is None:
            return False

        expected = format_decimal_amount(getattr(payment, "amount", 0))
        if payment_amount_matches(
            expected_amount=payment.amount,
            received_amount=out_sum_decimal,
        ):
            return True
        # The webhook signature covers OutSum, not BalanceAmount, Amount, or
        # Commission.  When the configured bill asks the payer to cover fees,
        # the signed OutSum may legitimately exceed the local invoice; the
        # entitlement is still always the fixed local order.  OVERPAID has the
        # same provider-documented treatment.
        return bool(
            out_sum_decimal > expected
            and (status == "overpaid" or bool(self.config.PAYER_PAYS_COMMISSION))
        )

    @staticmethod
    def _strict_callback_amount(value: Any) -> Decimal | None:
        """Return a finite cent-precision callback amount without rounding it."""
        if value is None or str(value).strip() == "":
            return None
        try:
            amount = Decimal(str(value).strip())
            if not amount.is_finite():
                return None
            rounded = format_decimal_amount(amount)
        except (InvalidOperation, TypeError, ValueError):
            return None
        return rounded if amount == rounded else None

    @staticmethod
    def _currency_matches_payment(payload: Mapping[str, Any], payment: Any) -> bool:
        currency = payload.get("CurrencyIn")
        if currency is None:
            currency = payload.get("currency_in")
        expected_currency = normalize_payment_currency_code(payment.currency, default="")
        received_currency = normalize_payment_currency_code(currency, default="")
        return bool(expected_currency and expected_currency == received_currency)

    async def _parse_webhook_payload(self, request: web.Request) -> dict[str, Any]:
        raw_body = await request.read()
        try:
            text = raw_body.decode("utf-8")
        except UnicodeDecodeError:
            text = raw_body.decode("utf-8", "replace")
        stripped = text.strip()
        if stripped.startswith("{"):
            try:
                payload = json.loads(stripped)
                return payload if isinstance(payload, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {str(key): value for key, value in parse_qsl(text, keep_blank_values=True)}

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.Response(status=503, text="pally_disabled")

        payload = await self._parse_webhook_payload(request)
        inv_id = payload.get("InvId") or payload.get("InvID") or payload.get("order_id")
        out_sum = payload.get("OutSum") or payload.get("out_sum") or payload.get("Amount")
        signature = payload.get("SignatureValue") or payload.get("signature")
        status = str(payload.get("Status") or payload.get("status") or "").strip().lower()
        provider_payment_id = first_value(payload, "TrsId", "TrsID", "bill_id", "BillId", "id")

        if not inv_id or out_sum is None or not status or not signature:
            logger.error("Pally webhook: missing required fields: %s", payload)
            return web.Response(status=400, text="missing_fields")
        if not self.verify_signature(out_sum, inv_id, signature):
            logger.error("Pally webhook: invalid signature.")
            return web.Response(status=403, text="invalid_signature")

        async with self.async_session_factory() as session:
            payment = await lookup_payment_by_order_or_provider_id(
                session,
                order_id_raw=inv_id,
                provider_payment_id=provider_payment_id,
            )
            if not payment:
                logger.error(
                    "Pally webhook: payment not found (inv_id=%s, provider_id=%s)",
                    inv_id,
                    provider_payment_id,
                )
                return web.Response(status=404, text="payment_not_found")

            resolved_provider_id = provider_payment_id or str(payment.payment_id)
            sale_mode = payment.sale_mode or (
                "traffic" if self.settings.traffic_sale_mode else "subscription"
            )
            payment_months = payment_units_for_activation(payment, sale_mode)

            if status in _SUCCESS_STATUSES:
                if payment.status == "succeeded":
                    logger.info("Pally webhook: payment %s already succeeded.", payment.payment_id)
                    return web.Response(text="OK")

                if not self._currency_matches_payment(payload, payment):
                    logger.error(
                        "Pally webhook: currency mismatch for payment %s (expected=%s, payload=%s)",
                        payment.payment_id,
                        payment.currency,
                        payload.get("CurrencyIn") or payload.get("currency_in"),
                    )
                    return web.Response(status=400, text="currency_mismatch")

                if not self._amount_matches_payment(payload, payment, status):
                    logger.error(
                        "Pally webhook: amount mismatch for payment %s (expected=%s, payload=%s)",
                        payment.payment_id,
                        payment.amount,
                        payload,
                    )
                    return web.Response(status=400, text="amount_mismatch")

                try:
                    payment = await payment_dal.claim_payment_finalization(
                        session,
                        payment.payment_id,
                        provider_payment_id=resolved_provider_id,
                    )
                    if payment is None:
                        return web.Response(text="OK")
                except Exception:
                    await session.rollback()
                    logger.exception(
                        "Pally webhook: failed to mark payment %s as succeeded.",
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
                        provider_subscription="pally",
                        provider_notification="pally",
                        db_user=payment.user,
                        log_prefix="Pally webhook",
                    )
                )
                if outcome is None:
                    return web.Response(status=500, text="processing_error")
                return web.Response(text="OK")

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
                        "Pally webhook: failed to mark payment %s as failed.",
                        resolved_provider_id,
                    )
                    return web.Response(status=500, text="processing_error")
                await notify_user_payment_failed(
                    bot=self.bot,
                    settings=self.settings,
                    i18n=self.i18n,
                    session=session,
                    payment=payment,
                )
                return web.Response(text="OK")

            if status in _PENDING_STATUSES:
                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        resolved_provider_id,
                        "pending_pally",
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logger.exception(
                        "Pally webhook: failed to update pending status for %s.",
                        resolved_provider_id,
                    )
                return web.Response(text="OK")

            logger.warning(
                "Pally webhook: unhandled status '%s' for payment %s",
                status,
                resolved_provider_id,
            )
            return web.Response(text="status_ignored")


async def pally_webhook_route(request: web.Request) -> web.Response:
    service: PallyService = app_required(request, "pally_service", PallyService)
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_pally_router")


@router.callback_query(F.data.startswith("pay_pally:"))
async def pay_pally_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    pally_service: PallyService,
    session: AsyncSession,
) -> None:
    await run_callback_payment(
        _DESCRIPTOR,
        callback,
        settings,
        i18n_data,
        pally_service,
        session,
    )


def create_service(ctx: ServiceFactoryContext) -> PallyService:
    bundle = ctx.config_for("pally_service")
    config = bundle.config if bundle and isinstance(bundle.config, PallyConfig) else PallyConfig()
    return PallyService(
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
    service: PallyService,
    request: CreatePaymentRequest,
) -> tuple[bool, dict]:
    return await service.create_bill(
        payment_db_id=request.payment.payment_id,
        amount=request.amount,
        currency=request.currency,
        description=request.description,
        language=request.language,
    )


async def _reuse_payment(service: PallyService, payment: Any) -> str | None:
    return await service.try_reuse_pending_bill(payment)


SPEC = PaymentProviderSpec(
    id="pally",
    provider_key="pally",
    label="Pally",
    webapp_label="Pally",
    webapp_labels={"ru": "Pally", "en": "Pally"},
    webapp_icon="WalletCards",
    logo_url="/provider-logos/pally.png",
    telegram_labels={"ru": "Pally", "en": "Pally"},
    telegram_emoji="\U0001f4b3",
    pending_status="pending_pally",
    enabled=lambda config: bool(getattr(config, "ENABLED", False)),
    service_key="pally_service",
    callback_prefix="pay_pally",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/pally",
    webhook_route=pally_webhook_route,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=PallyConfig,
    presentation_class=PallyPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supported_currencies=PALLY_SUPPORTED_CURRENCIES,
    currency_support_note="Pally bills support RUB, USD and EUR.",
    info_url="https://pally.info/",
    currency_support_url="https://pally.info/reference/api",
)

_DESCRIPTOR: LinkPaymentDescriptor[PallyService] = LinkPaymentDescriptor(
    spec=SPEC,
    provider_key="pally",
    pending_status="pending_pally",
    display_name="Pally",
    log_prefix=_LOG,
    service_app_key="pally_service",
    service_type=PallyService,
    create=_create_payment,
    reuse=_reuse_payment,
    extract_url=_payment_page_url,
    extract_provider_id=_bill_id_value,
    callback_before_create=safe_callback_answer,
)
