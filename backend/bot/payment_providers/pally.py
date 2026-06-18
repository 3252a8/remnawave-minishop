from __future__ import annotations

import hashlib
import hmac
import json
import logging
from decimal import InvalidOperation
from typing import Any, Dict, Mapping, Optional, Tuple
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
from config.settings import Settings
from config.tariffs_config import (
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
)
from db.dal import payment_dal

from .base import (
    PaymentProviderSpec,
    ProviderEnvConfig,
    ProviderManifestField,
    ServiceFactoryContext,
    WebAppPaymentContext,
    normalize_payment_currency_code,
    provider_env_file,
    provider_runtime_enabled,
)
from .shared import (
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
    quote_hwid_callback_parts,
    render_link_or_fail,
    render_payment_link,
    safe_callback_answer,
)

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
    API_TOKEN: Optional[str] = None
    SIGNATURE_TOKEN: Optional[str] = None
    SHOP_ID: Optional[str] = None
    BASE_URL: str = Field(default="https://pally.info/api/v1")
    RETURN_URL: Optional[str] = None
    SUCCESS_URL: Optional[str] = None
    FAIL_URL: Optional[str] = None
    TTL_SECONDS: Optional[int] = None
    PAYER_PAYS_COMMISSION: Optional[bool] = None
    PAYMENT_METHOD: Optional[str] = None
    LOCALE: Optional[str] = None
    NAME: Optional[str] = None

    @field_validator("TTL_SECONDS", mode="before")
    @classmethod
    def _empty_to_none_int(cls, v):
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
    def _strip_optional(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("PAYMENT_METHOD")
    @classmethod
    def _normalize_payment_method(cls, v):
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
    def _normalize_locale(cls, v):
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

    WEBAPP_LABEL_RU: Optional[str] = None
    WEBAPP_LABEL_EN: Optional[str] = None
    WEBAPP_ICON: Optional[str] = None
    TELEGRAM_LABEL_RU: Optional[str] = None
    TELEGRAM_LABEL_EN: Optional[str] = None
    TELEGRAM_EMOJI: Optional[str] = None


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


def _bool_form_value(value: Optional[bool]) -> Optional[str]:
    if value is None:
        return None
    return "1" if value else "0"


def _status_value(payload: Optional[Mapping[str, Any]]) -> str:
    if not payload:
        return ""
    return str(payload.get("status") or payload.get("Status") or "").strip().lower()


def _bill_id_value(payload: Optional[Mapping[str, Any]]) -> Optional[str]:
    return first_value(payload, "bill_id", "billId", "id", "TrsId", "trs_id")


def _payment_page_url(payload: Optional[Mapping[str, Any]]) -> Optional[str]:
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
            logging.warning("PallyService initialized but not fully configured. Payments disabled.")

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
    def ttl_seconds(self) -> Optional[int]:
        if self.config.TTL_SECONDS is None:
            return None
        return max(1, int(self.config.TTL_SECONDS))

    def _auth_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
        }

    async def _post_form(self, path: str, body: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            logging.error("PallyService is not configured. Cannot call %s.", path)
            return False, {"message": "service_not_configured"}

        session = await self._get_session()
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            async with session.post(url, data=body, headers=self._auth_headers()) as response:
                response_text = await response.text()
                try:
                    response_data = json.loads(response_text) if response_text else {}
                except json.JSONDecodeError:
                    logging.error("Pally %s: invalid JSON response: %s", path, response_text[:500])
                    return False, {
                        "status": response.status,
                        "message": "invalid_json",
                        "raw": response_text,
                    }
                if not isinstance(response_data, dict):
                    response_data = {"data": response_data}
                if not _payload_success(response.status, response_data):
                    logging.error(
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
            logging.exception("Pally %s: request failed.", path)
            return False, {"message": str(exc)}

    async def _get_json(
        self,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
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
                    logging.error("Pally %s: invalid JSON response: %s", path, response_text[:500])
                    return False, {
                        "status": response.status,
                        "message": "invalid_json",
                        "raw": response_text,
                    }
                if not isinstance(response_data, dict):
                    response_data = {"data": response_data}
                if not _payload_success(response.status, response_data):
                    logging.error(
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
            logging.exception("Pally %s: request failed.", path)
            return False, {"message": str(exc)}

    async def create_bill(
        self,
        *,
        payment_db_id: int,
        amount: float,
        currency: Optional[str],
        description: Optional[str] = None,
        language: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            logging.error("PallyService is not configured. Cannot create bill.")
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

        body: Dict[str, Any] = {
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

    async def get_bill_status(self, bill_id: str) -> Tuple[bool, Dict[str, Any]]:
        if not bill_id:
            return False, {"message": "missing_bill_id"}
        return await self._get_json("/bill/status", params={"id": bill_id})

    async def try_reuse_pending_bill(self, payment: Any) -> Optional[str]:
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

    def calculate_signature(self, out_sum: Any, inv_id: Any) -> Optional[str]:
        token = self.signature_token
        if not token:
            return None
        raw = f"{out_sum}:{inv_id}:{token}".encode("utf-8")
        try:
            digest = hashlib.md5(raw, usedforsecurity=False)
        except TypeError:  # pragma: no cover - Python without usedforsecurity
            digest = hashlib.md5(raw)
        return digest.hexdigest().upper()

    def verify_signature(self, out_sum: Any, inv_id: Any, received_signature: Any) -> bool:
        received = str(received_signature or "").strip().upper()
        if not received:
            logging.warning("Pally webhook: missing signature.")
            return False
        expected = self.calculate_signature(out_sum, inv_id)
        if not expected:
            logging.error("Pally webhook: no signature token configured.")
            return False
        return hmac.compare_digest(expected, received)

    def _amount_matches_payment(
        self, payload: Mapping[str, Any], payment: Any, status: str
    ) -> bool:
        candidates = [
            payload.get("BalanceAmount"),
            payload.get("balance_amount"),
            payload.get("OutSum"),
            payload.get("out_sum"),
            payload.get("Amount"),
            payload.get("amount"),
        ]
        out_sum = payload.get("OutSum") or payload.get("out_sum")
        commission = payload.get("Commission") or payload.get("commission")
        if out_sum is not None and commission is not None:
            try:
                candidates.append(
                    format_decimal_amount(out_sum) - format_decimal_amount(commission)
                )
            except (InvalidOperation, ValueError, TypeError):
                pass

        expected = format_decimal_amount(getattr(payment, "amount", 0))
        for candidate in candidates:
            if candidate is None or str(candidate).strip() == "":
                continue
            try:
                actual = format_decimal_amount(candidate)
            except (InvalidOperation, ValueError, TypeError):
                continue
            if actual == expected:
                return True
            if status == "overpaid" and actual > expected:
                return True
        return False

    async def _parse_webhook_payload(self, request: web.Request) -> Dict[str, Any]:
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
            logging.error("Pally webhook: missing required fields: %s", payload)
            return web.Response(status=400, text="missing_fields")
        if not self.verify_signature(out_sum, inv_id, signature):
            logging.error("Pally webhook: invalid signature.")
            return web.Response(status=403, text="invalid_signature")

        async with self.async_session_factory() as session:
            payment = await lookup_payment_by_order_or_provider_id(
                session,
                order_id_raw=inv_id,
                provider_payment_id=provider_payment_id,
            )
            if not payment:
                logging.error(
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
                    logging.info("Pally webhook: payment %s already succeeded.", payment.payment_id)
                    return web.Response(text="OK")

                if not self._amount_matches_payment(payload, payment, status):
                    logging.error(
                        "Pally webhook: amount mismatch for payment %s (expected=%s, payload=%s)",
                        payment.payment_id,
                        payment.amount,
                        payload,
                    )
                    return web.Response(status=400, text="amount_mismatch")

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
                    logging.exception(
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
                    logging.exception(
                        "Pally webhook: failed to update pending status for %s.",
                        resolved_provider_id,
                    )
                return web.Response(text="OK")

            logging.warning(
                "Pally webhook: unhandled status '%s' for payment %s",
                status,
                resolved_provider_id,
            )
            return web.Response(text="status_ignored")


async def pally_webhook_route(request: web.Request) -> web.Response:
    service: PallyService = request.app["pally_service"]
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_pally_router")


@router.callback_query(F.data.startswith("pay_pally:"))
async def pay_pally_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    pally_service: PallyService,
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

    if not pally_service or not pally_service.configured:
        logging.error("Pally service is not configured or unavailable.")
        await notify_service_unavailable(callback, translator)
        return

    parts = parse_payment_callback(callback.data or "")
    if not parts:
        logging.error("Invalid pay_pally data in callback: %s", callback.data)
        await notify_callback_parse_error(callback, translator)
        return
    parts, hwid_quote = await quote_hwid_callback_parts(
        session=session,
        user_id=callback.from_user.id,
        parts=parts,
        subscription_service=pally_service.subscription_service,
        currency=default_currency_key_for_settings(settings),
    )
    if not parts:
        await notify_callback_parse_error(callback, translator)
        return

    currency_code = default_payment_currency_code_for_settings(settings)
    payment_description = describe_payment(translator, parts)

    reuse_amounts = payment_record_amounts(
        months=parts.months,
        sale_mode=parts.sale_mode,
        hwid_device_count=hwid_quote.get("device_count") if hwid_quote else None,
    )
    reusable_payment = await payment_dal.find_recent_pending_provider_payment(
        session,
        user_id=callback.from_user.id,
        provider="pally",
        pending_status="pending_pally",
        amount=parts.price,
        currency=currency_code,
        sale_mode=parts.sale_mode,
        months=reuse_amounts.months,
        purchased_gb=reuse_amounts.purchased_gb,
        purchased_hwid_devices=reuse_amounts.purchased_hwid_devices,
        tariff_key=reuse_amounts.tariff_key,
    )
    if reusable_payment is not None:
        reusable_url = await pally_service.try_reuse_pending_bill(reusable_payment)
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

    record_payload = build_payment_record_payload(
        user_id=callback.from_user.id,
        amount=parts.price,
        currency=currency_code,
        status="pending_pally",
        description=payment_description,
        months=parts.months,
        provider="pally",
        sale_mode=parts.sale_mode,
        hwid_quote=hwid_quote,
    )

    try:
        payment_record = await payment_dal.create_payment_record(session, record_payload)
        await session.commit()
    except Exception:
        await session.rollback()
        logging.exception(
            "Pally: failed to create payment record for user %s.", callback.from_user.id
        )
        await notify_payment_record_failure(callback, translator)
        return

    await safe_callback_answer(callback)

    success, response_data = await pally_service.create_bill(
        payment_db_id=payment_record.payment_id,
        amount=parts.price,
        currency=currency_code,
        description=payment_description,
        language=current_lang,
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
        payment_url=_payment_page_url(response_data) if success else None,
        provider_payment_id=_bill_id_value(response_data),
        provider_response=response_data,
        log_prefix="Pally",
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
    settings: Settings = ctx.request.app["settings"]
    service: PallyService = ctx.request.app["pally_service"]
    if not service or not service.configured:
        return payment_unavailable()

    currency = ctx.currency or settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
    try:
        payment = await create_webapp_payment_record(
            ctx,
            amount=ctx.price,
            currency=currency,
            status="pending_pally",
            provider="pally",
        )
        success, response_data = await service.create_bill(
            payment_db_id=payment.payment_id,
            amount=ctx.price,
            currency=currency,
            description=ctx.description,
        )
    except Exception:
        await ctx.session.rollback()
        logging.exception("Pally WebApp payment failed")
        return payment_failed()

    return await finalize_webapp_link_payment(
        session=ctx.session,
        payment=payment,
        api_success=success,
        payment_url=_payment_page_url(response_data) if success else None,
        provider_payment_id=_bill_id_value(response_data),
        provider_response=response_data,
        log_prefix="Pally",
    )


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> Optional[str]:
    service: PallyService = ctx.request.app.get("pally_service")
    if not service or not service.configured:
        return None
    return await service.try_reuse_pending_bill(payment)


_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="Pally",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_PALLY_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_PALLY_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_PALLY_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "WalletCards",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_PALLY_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_PALLY_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_PALLY_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            r"\U0001f4b3",
            "TELEGRAM_EMOJI",
        ),
    )
)

_CONFIG_MANIFEST = (
    ProviderManifestField("PALLY_ENABLED", "bool", "Enabled", subsection="Pally", attr="ENABLED"),
    ProviderManifestField(
        "PALLY_API_TOKEN",
        "string",
        "API token",
        description="Bearer token from the Pally API integrations page.",
        subsection="Pally",
        secret=True,
        attr="API_TOKEN",
    ),
    ProviderManifestField(
        "PALLY_SIGNATURE_TOKEN",
        "string",
        "Signature token",
        description="Token used to verify postback MD5 signatures. Leave empty to use API token.",
        subsection="Pally",
        secret=True,
        attr="SIGNATURE_TOKEN",
    ),
    ProviderManifestField(
        "PALLY_SHOP_ID",
        "string",
        "Shop ID",
        description="Pally shop identifier used by bills and Result URL postbacks.",
        subsection="Pally",
        attr="SHOP_ID",
    ),
    ProviderManifestField(
        "PALLY_BASE_URL",
        "url",
        "Base URL",
        placeholder="https://pally.info/api/v1",
        subsection="Pally",
        attr="BASE_URL",
    ),
    ProviderManifestField(
        "PALLY_RETURN_URL", "url", "Return URL", subsection="Pally", attr="RETURN_URL"
    ),
    ProviderManifestField(
        "PALLY_SUCCESS_URL", "url", "Success URL", subsection="Pally", attr="SUCCESS_URL"
    ),
    ProviderManifestField("PALLY_FAIL_URL", "url", "Fail URL", subsection="Pally", attr="FAIL_URL"),
    ProviderManifestField(
        "PALLY_TTL_SECONDS",
        "int",
        "Bill lifetime (seconds)",
        description="Optional Pally bill lifetime in seconds.",
        subsection="Pally",
        min=1,
        attr="TTL_SECONDS",
    ),
    ProviderManifestField(
        "PALLY_PAYER_PAYS_COMMISSION",
        "bool",
        "Payer pays commission",
        description="Sends payer_pays_commission=1 when enabled.",
        subsection="Pally",
        attr="PAYER_PAYS_COMMISSION",
    ),
    ProviderManifestField(
        "PALLY_PAYMENT_METHOD",
        "string",
        "Preselected payment method",
        description="Optionally lock the hosted payment form to bank card or SBP.",
        subsection="Pally",
        choices=(("BANK_CARD", "Bank card"), ("SBP", "SBP")),
        attr="PAYMENT_METHOD",
    ),
    ProviderManifestField(
        "PALLY_LOCALE",
        "string",
        "Payment page locale",
        description=(
            "Optional payment form locale. Empty follows the user's language where possible."
        ),
        subsection="Pally",
        choices=(("ru", "Russian"), ("en", "English")),
        attr="LOCALE",
    ),
    ProviderManifestField(
        "PALLY_NAME",
        "string",
        "Payment form title",
        description="Optional link name displayed on the Pally payment form.",
        subsection="Pally",
        attr="NAME",
    ),
)


SPEC = PaymentProviderSpec(
    id="pally",
    provider_key="pally",
    label="Pally",
    webapp_label="Pally",
    webapp_labels={"ru": "Pally", "en": "Pally"},
    webapp_icon="WalletCards",
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
    currency_support_url="https://pally.info/reference/api",
)
