import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple

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
    payment_record_amounts,
    payment_unavailable,
    payment_units_for_activation,
    post_json_request,
    quote_hwid_callback_parts,
    render_link_or_fail,
    render_payment_link,
    safe_callback_answer,
)

router = Router(name="user_subscription_payments_wata_router")
_LOG = "wata"
WATA_SUPPORTED_CURRENCIES = ("RUB", "USD", "EUR")
_WATA_IN_PROGRESS_STATUSES = {"created", "pending"}
_WATA_LINK_OPENED_STATUSES = {"opened", "open"}
_WATA_LINK_DEFAULT_TTL_MINUTES = 15
_WATA_LINK_MIN_TTL_MINUTES = 15
_WATA_LINK_MAX_TTL_MINUTES = 30 * 24 * 60


def _clamp_wata_link_ttl_minutes(value: Any, *, default: int) -> int:
    if isinstance(value, str):
        value = value.strip()
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return default
    return min(_WATA_LINK_MAX_TTL_MINUTES, max(_WATA_LINK_MIN_TTL_MINUTES, minutes))


def _parse_wata_datetime(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        iso_value = str(raw).strip()
        if iso_value.endswith("Z"):
            iso_value = iso_value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(iso_value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _wata_success_status(status: int, _body: Any) -> bool:
    return 200 <= status < 300


def _normalized_wata_status(payload: Optional[Mapping[str, Any]]) -> str:
    if not payload:
        return ""
    return (
        str(
            payload.get("transactionStatus")
            or payload.get("status")
            or payload.get("statusName")
            or ""
        )
        .strip()
        .lower()
    )


def _wata_transaction_id(payload: Optional[Mapping[str, Any]]) -> Optional[str]:
    return first_value(payload, "transactionId", "id")


def _wata_payment_link_id(payload: Optional[Mapping[str, Any]]) -> Optional[str]:
    return first_value(payload, "paymentLinkId", "payment_link_id")


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
    LINK_TTL_MINUTES: int = Field(default=_WATA_LINK_DEFAULT_TTL_MINUTES)
    WEBHOOK_VERIFY_SIGNATURE: bool = Field(default=True)
    PUBLIC_KEY: Optional[str] = None
    TRUSTED_IPS: str = Field(default="62.84.126.140,51.250.106.150")

    @field_validator("LINK_TTL_MINUTES", mode="before")
    @classmethod
    def _clamp_link_ttl_minutes(cls, v):
        return _clamp_wata_link_ttl_minutes(v, default=_WATA_LINK_DEFAULT_TTL_MINUTES)

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

        self._init_http_client(total_timeout=lambda: self.settings.PAYMENT_REQUEST_TIMEOUT_SECONDS)
        if not self.configured:
            logging.warning("WataService initialized but not fully configured. Payments disabled.")

    @property
    def configured(self) -> bool:
        return bool(provider_runtime_enabled(self.config) and self.api_token)

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
    def payment_link_ttl_minutes(self) -> int:
        return self.config.LINK_TTL_MINUTES

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

        currency_code = normalize_payment_currency_code(
            currency or self.settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
        )
        if currency_code not in WATA_SUPPORTED_CURRENCIES:
            return False, {
                "message": "unsupported_currency",
                "currency": currency_code,
                "supported_currencies": list(WATA_SUPPORTED_CURRENCIES),
            }

        session = await self._get_session()
        expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=self.payment_link_ttl_minutes)
        ).replace(microsecond=0)
        body: Dict[str, Any] = {
            "amount": float(format_decimal_amount(amount)),
            "currency": currency_code,
            "description": description,
            "orderId": str(payment_db_id),
            "successRedirectUrl": self.return_url,
            "failRedirectUrl": self.failed_url,
            "expirationDateTime": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        return await post_json_request(
            session,
            f"{self.base_url}/links",
            body=body,
            headers=self._auth_headers(),
            log_prefix="Wata create_payment_link",
            is_success=_wata_success_status,
        )

    async def _get_json(
        self,
        url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        log_prefix: str,
    ) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            logging.error("WataService is not configured. Cannot fetch provider state.")
            return False, {"message": "service_not_configured"}

        session = await self._get_session()
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
                    logging.error("%s: invalid JSON response: %s", log_prefix, response_text)
                    return False, {
                        "status": response.status,
                        "message": "invalid_json",
                        "raw": response_text,
                    }
                if not _wata_success_status(response.status, response_data):
                    logging.error(
                        "%s: API returned error (status=%s, body=%s)",
                        log_prefix,
                        response.status,
                        response_data,
                    )
                    return False, {"status": response.status, "message": response_data}
                return True, response_data
        except Exception as exc:
            logging.exception("%s: request failed.", log_prefix)
            return False, {"message": str(exc)}

    async def get_payment_link(self, payment_link_id: str) -> Tuple[bool, Dict[str, Any]]:
        return await self._get_json(
            f"{self.base_url}/links/{payment_link_id}",
            log_prefix="Wata get_payment_link",
        )

    async def try_reuse_pending_link(self, payment: Any) -> Optional[str]:
        """Return the existing payment link URL if it's still usable; else None.

        Used to avoid creating duplicate Wata links each time a user re-clicks
        the pay button. Repeated abandoned links inflate Wata's anti-fraud
        signals and can cause downstream bank-side rejections during the
        bank-selection step.
        """
        if not self.configured:
            return None
        provider_payment_id = str(getattr(payment, "provider_payment_id", "") or "").strip()
        if not provider_payment_id:
            return None

        success, data = await self.get_payment_link(provider_payment_id)
        if not success or not isinstance(data, dict):
            return None

        returned_ids = {
            str(data.get("id") or "").strip(),
            str(data.get("paymentLinkId") or "").strip(),
            str(data.get("payment_link_id") or "").strip(),
        }
        returned_ids.discard("")
        if returned_ids and provider_payment_id not in returned_ids:
            return None

        order_id = first_value(data, "orderId", "order_id")
        if order_id is not None and str(order_id) != str(payment.payment_id):
            return None

        status = _normalized_wata_status(data) or str(data.get("status") or "").strip().lower()
        if status and status not in _WATA_LINK_OPENED_STATUSES:
            return None

        expiration_raw = data.get("expirationDateTime") or data.get("expiration_date_time")
        if expiration_raw:
            exp_dt = _parse_wata_datetime(expiration_raw)
            if exp_dt is None:
                logging.warning(
                    "Wata try_reuse_pending_link: unparseable expirationDateTime %r",
                    expiration_raw,
                )
                return None
            if exp_dt <= datetime.now(timezone.utc):
                return None

        return first_value(data, "url", "paymentUrl", "payment_url")

    async def get_transaction(self, transaction_id: str) -> Tuple[bool, Dict[str, Any]]:
        return await self._get_json(
            f"{self.base_url}/transactions/{transaction_id}",
            log_prefix="Wata get_transaction",
        )

    async def search_transactions(
        self,
        *,
        order_id: Optional[str] = None,
        payment_link_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 5,
    ) -> Tuple[bool, Dict[str, Any]]:
        params: Dict[str, Any] = {
            "skipCount": 0,
            "maxResultCount": max(1, min(int(limit or 5), 1000)),
        }
        if order_id:
            params["orderId"] = order_id
        if payment_link_id:
            params["paymentLinkId"] = payment_link_id
        if status:
            params["statuses"] = status
        return await self._get_json(
            f"{self.base_url}/transactions",
            params=params,
            log_prefix="Wata search_transactions",
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

    def _transaction_matches_payment(
        self,
        payload: Mapping[str, Any],
        payment: Any,
        *,
        provider_payment_id: Optional[str],
    ) -> bool:
        order_id = str(payload.get("orderId") or "").strip()
        if order_id and order_id == str(payment.payment_id):
            return True

        payment_link_id = _wata_payment_link_id(payload)
        if payment_link_id and provider_payment_id and payment_link_id == provider_payment_id:
            return True

        transaction_id = _wata_transaction_id(payload)
        if transaction_id and provider_payment_id and transaction_id == provider_payment_id:
            return True

        return False

    async def _find_transaction_for_payment(
        self,
        payment: Any,
        *,
        status: str,
    ) -> Optional[Dict[str, Any]]:
        provider_payment_id = str(getattr(payment, "provider_payment_id", "") or "").strip()
        success, response_data = await self.search_transactions(
            order_id=str(payment.payment_id),
            status=status,
            limit=5,
        )
        if success:
            for item in response_data.get("items") or []:
                if not isinstance(item, dict):
                    continue
                if _normalized_wata_status(item) != status.lower():
                    continue
                if self._transaction_matches_payment(
                    item,
                    payment,
                    provider_payment_id=provider_payment_id or None,
                ):
                    return item

        return None

    async def _mark_paid_from_payload(
        self,
        session: AsyncSession,
        payment: Any,
        payload: Mapping[str, Any],
        *,
        log_prefix: str,
    ) -> Optional[Any]:
        current = await payment_dal.get_payment_by_db_id(session, payment.payment_id)
        if current:
            payment = current
        if payment.status == "succeeded":
            return payment

        transaction_id = _wata_transaction_id(payload) or str(payment.payment_id)
        amount_raw = payload.get("amount")
        currency = payload.get("currency") or self.settings.DEFAULT_CURRENCY_SYMBOL or "RUB"

        if amount_raw is not None:
            try:
                if not decimal_amounts_equal(amount_raw, payment.amount):
                    logging.warning(
                        "%s: amount mismatch for payment %s (expected %s, got %s)",
                        log_prefix,
                        payment.payment_id,
                        format_decimal_amount(payment.amount),
                        format_decimal_amount(amount_raw),
                    )
            except Exception as exc:
                logging.warning(
                    "%s: failed to compare amounts for %s: %s",
                    log_prefix,
                    payment.payment_id,
                    exc,
                )

        try:
            await payment_dal.update_provider_payment_and_status(
                session,
                payment.payment_id,
                transaction_id,
                "succeeded",
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logging.exception(
                "%s: failed to mark payment %s as succeeded.",
                log_prefix,
                transaction_id,
            )
            return None

        sale_mode = payment.sale_mode or (
            "traffic" if self.settings.traffic_sale_mode else "subscription"
        )
        payment_units = payment_units_for_activation(payment, sale_mode)
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
                log_prefix=log_prefix,
            )
        )
        if outcome is None:
            return None
        return await payment_dal.get_payment_by_db_id(session, payment.payment_id) or payment

    async def _mark_declined_from_payload(
        self,
        session: AsyncSession,
        payment: Any,
        payload: Mapping[str, Any],
        *,
        log_prefix: str,
        notify_user: bool,
    ) -> Optional[Any]:
        transaction_id = _wata_transaction_id(payload) or str(payment.payment_id)
        try:
            await payment_dal.update_provider_payment_and_status(
                session,
                payment.payment_id,
                transaction_id,
                "failed",
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logging.exception(
                "%s: failed to mark payment %s as failed.",
                log_prefix,
                transaction_id,
            )
            return None

        if notify_user:
            await notify_user_payment_failed(
                bot=self.bot,
                settings=self.settings,
                i18n=self.i18n,
                session=session,
                payment=payment,
            )
        return await payment_dal.get_payment_by_db_id(session, payment.payment_id) or payment

    def _local_payment_link_ttl_expired(self, payment: Any) -> bool:
        created_at = getattr(payment, "created_at", None)
        if isinstance(created_at, datetime):
            created_dt = (
                created_at.replace(tzinfo=timezone.utc)
                if created_at.tzinfo is None
                else created_at.astimezone(timezone.utc)
            )
        else:
            created_dt = _parse_wata_datetime(created_at)
        if created_dt is None:
            return False
        expires_at = created_dt + timedelta(minutes=self.payment_link_ttl_minutes)
        return expires_at <= datetime.now(timezone.utc)

    async def _expired_link_payload_for_payment(self, payment: Any) -> Optional[Mapping[str, Any]]:
        provider_payment_id = str(getattr(payment, "provider_payment_id", "") or "").strip()
        if not provider_payment_id:
            return None

        success, data = await self.get_payment_link(provider_payment_id)
        if not success or not isinstance(data, dict):
            status_code = data.get("status") if isinstance(data, dict) else None
            if status_code == 404 and self._local_payment_link_ttl_expired(payment):
                return {"id": provider_payment_id}
            return None

        expiration_raw = data.get("expirationDateTime") or data.get("expiration_date_time")
        expiration_dt = _parse_wata_datetime(expiration_raw)
        if expiration_dt is None:
            return None
        if expiration_dt > datetime.now(timezone.utc):
            return None
        return data

    async def _mark_expired_link(
        self,
        session: AsyncSession,
        payment: Any,
        payload: Mapping[str, Any],
        *,
        log_prefix: str,
    ) -> Optional[Any]:
        provider_payment_id = (
            first_value(payload, "id", "paymentLinkId", "payment_link_id")
            or getattr(payment, "provider_payment_id", None)
            or str(payment.payment_id)
        )
        try:
            await payment_dal.update_provider_payment_and_status(
                session,
                payment.payment_id,
                str(provider_payment_id),
                "canceled",
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logging.exception(
                "%s: failed to mark expired payment link %s as canceled.",
                log_prefix,
                provider_payment_id,
            )
            return None
        return await payment_dal.get_payment_by_db_id(session, payment.payment_id) or payment

    async def refresh_payment_status(self, session: AsyncSession, payment: Any) -> Any:
        if str(getattr(payment, "provider", "") or "").lower() != "wata":
            return payment
        if not self.configured:
            return payment

        current_status = str(getattr(payment, "status", "") or "").lower()
        if current_status == "succeeded" or current_status in {
            "failed",
            "canceled",
            "cancelled",
            "failed_creation",
        }:
            return payment

        paid_payload = await self._find_transaction_for_payment(payment, status="Paid")
        if paid_payload:
            refreshed = await self._mark_paid_from_payload(
                session,
                payment,
                paid_payload,
                log_prefix="Wata status refresh",
            )
            return refreshed or payment

        declined_payload = await self._find_transaction_for_payment(payment, status="Declined")
        if declined_payload:
            refreshed = await self._mark_declined_from_payload(
                session,
                payment,
                declined_payload,
                log_prefix="Wata status refresh",
                notify_user=False,
            )
            return refreshed or payment

        expired_link_payload = await self._expired_link_payload_for_payment(payment)
        if expired_link_payload:
            refreshed = await self._mark_expired_link(
                session,
                payment,
                expired_link_payload,
                log_prefix="Wata status refresh",
            )
            return refreshed or payment

        return payment

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.Response(status=503, text="wata_disabled")

        client_ip = request_client_ip(request, trusted_proxies=self.settings.trusted_proxies)
        trusted = self.config.trusted_ips_list
        if trusted and not ip_in_allowlist(client_ip, trusted):
            logging.warning(
                "Wata webhook denied from unauthorized IP source "
                "(client_ip=%s remote=%s x_forwarded_for=%s trusted_ips=%s trusted_proxies=%s).",
                client_ip,
                request.remote,
                request.headers.get("X-Forwarded-For"),
                trusted,
                self.settings.trusted_proxies,
            )
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
        payment_link_id = str(payload.get("paymentLinkId") or payload.get("id") or "").strip()
        status = str(payload.get("transactionStatus") or "").strip().lower()
        order_id_raw = payload.get("orderId")

        if not status or not (transaction_id or order_id_raw or payment_link_id):
            logging.error("Wata webhook: missing transaction status or ids: %s", payload)
            return web.Response(status=400, text="missing_fields")

        async with self.async_session_factory() as session:
            payment = await lookup_payment_by_order_or_provider_id(
                session,
                order_id_raw=order_id_raw,
                provider_payment_id=transaction_id or None,
            )
            if not payment and payment_link_id:
                payment = await lookup_payment_by_order_or_provider_id(
                    session,
                    provider_payment_id=payment_link_id,
                )
            if not payment:
                logging.error(
                    "Wata webhook: payment not found "
                    "(order_id=%s, transaction_id=%s, payment_link_id=%s)",
                    order_id_raw,
                    transaction_id,
                    payment_link_id,
                )
                return web.Response(status=404, text="payment_not_found")

            if payment.status == "succeeded":
                return web.Response(text="ok")

            if status in _WATA_IN_PROGRESS_STATUSES:
                if transaction_id and payment.provider_payment_id != transaction_id:
                    try:
                        await payment_dal.update_provider_payment_and_status(
                            session,
                            payment.payment_id,
                            transaction_id,
                            payment.status,
                        )
                        await session.commit()
                    except Exception:
                        await session.rollback()
                        logging.exception(
                            "Wata webhook: failed to persist transaction id %s for payment %s.",
                            transaction_id,
                            payment.payment_id,
                        )
                        return web.Response(status=500, text="processing_error")
                return web.Response(text="ok")

            if status == "paid":
                if not await self._mark_paid_from_payload(
                    session,
                    payment,
                    payload,
                    log_prefix="Wata webhook",
                ):
                    return web.Response(status=500, text="processing_error")
                return web.Response(text="ok")

            if status == "declined":
                if not await self._mark_declined_from_payload(
                    session,
                    payment,
                    payload,
                    log_prefix="Wata webhook",
                    notify_user=True,
                ):
                    return web.Response(status=500, text="processing_error")
                return web.Response(text="ok")

            logging.warning(
                "Wata webhook: unhandled status '%s' for transaction %s",
                status,
                transaction_id,
            )
            return web.Response(text="status_ignored")


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

    if not SPEC.is_available_to_user(
        settings,
        user_id=callback.from_user.id,
        require_configured=False,
    ):
        await notify_service_unavailable(callback, translator)
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
    parts, hwid_quote = await quote_hwid_callback_parts(
        session=session,
        user_id=callback.from_user.id,
        parts=parts,
        subscription_service=wata_service.subscription_service,
        currency=default_currency_key_for_settings(settings),
    )
    if not parts:
        await notify_callback_parse_error(callback, translator)
        return

    currency_code = default_payment_currency_code_for_settings(settings)
    payment_description = describe_payment(translator, parts)

    reuse_amounts = payment_record_amounts(months=parts.months, sale_mode=parts.sale_mode)
    reusable_payment = await payment_dal.find_recent_pending_provider_payment(
        session,
        user_id=callback.from_user.id,
        provider="wata",
        pending_status="pending_wata",
        amount=parts.price,
        currency=currency_code,
        sale_mode=parts.sale_mode,
        months=reuse_amounts.months,
        purchased_gb=reuse_amounts.purchased_gb,
        purchased_hwid_devices=reuse_amounts.purchased_hwid_devices,
        tariff_key=reuse_amounts.tariff_key,
        since_minutes=wata_service.payment_link_ttl_minutes,
    )
    if reusable_payment is not None:
        reusable_url = await wata_service.try_reuse_pending_link(reusable_payment)
        if reusable_url:
            await safe_callback_answer(callback)
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
        status="pending_wata",
        description=payment_description,
        months=parts.months,
        provider="wata",
        sale_mode=parts.sale_mode,
        hwid_quote=hwid_quote,
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

    await safe_callback_answer(callback)

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
        payment_url=first_value(response_data, "url", "paymentUrl", "payment_url"),
        provider_payment_id=first_value(response_data, "id", "paymentLinkId"),
        log_prefix=_LOG,
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    settings: Settings = ctx.request.app["settings"]
    service: WataService = ctx.request.app["wata_service"]
    if not service or not service.configured:
        return payment_unavailable()

    currency = ctx.currency or settings.DEFAULT_CURRENCY_SYMBOL or "RUB"

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
        payment_url=first_value(response_data, "url", "paymentUrl", "payment_url")
        if success
        else None,
        provider_payment_id=first_value(response_data, "id", "paymentLinkId"),
        log_prefix="Wata",
    )


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> Optional[str]:
    service: WataService = ctx.request.app.get("wata_service")
    if not service or not service.configured:
        return None
    return await service.try_reuse_pending_link(payment)


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
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="Wata",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_WATA_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_WATA_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_WATA_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "WalletCards",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_WATA_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_WATA_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_WATA_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            "💳",
            "TELEGRAM_EMOJI",
        ),
    )
)

_CONFIG_MANIFEST = (
    ProviderManifestField("WATA_ENABLED", "bool", "Enabled", subsection="Wata", attr="ENABLED"),
    ProviderManifestField(
        "WATA_API_TOKEN", "string", "API token", subsection="Wata", secret=True, attr="API_TOKEN"
    ),
    ProviderManifestField(
        "WATA_BASE_URL",
        "url",
        "Base URL",
        placeholder="https://api.wata.pro/api/h2h",
        subsection="Wata",
        attr="BASE_URL",
    ),
    ProviderManifestField(
        "WATA_RETURN_URL", "url", "Return URL", subsection="Wata", attr="RETURN_URL"
    ),
    ProviderManifestField(
        "WATA_FAILED_URL", "url", "Failed URL", subsection="Wata", attr="FAILED_URL"
    ),
    ProviderManifestField(
        "WATA_LINK_TTL_MINUTES",
        "int",
        "Payment link lifetime (minutes)",
        description=(
            "15..43200; default 15 minutes. Wata requires more than 10 minutes "
            "and allows up to 30 days."
        ),
        subsection="Wata",
        min=_WATA_LINK_MIN_TTL_MINUTES,
        max=_WATA_LINK_MAX_TTL_MINUTES,
        attr="LINK_TTL_MINUTES",
    ),
    ProviderManifestField(
        "WATA_WEBHOOK_VERIFY_SIGNATURE",
        "bool",
        "Verify webhook signature",
        subsection="Wata",
        attr="WEBHOOK_VERIFY_SIGNATURE",
    ),
    ProviderManifestField(
        "WATA_PUBLIC_KEY",
        "text",
        "Webhook public key",
        description="Optional. If empty, the backend fetches it from Wata.",
        subsection="Wata",
        secret=True,
        attr="PUBLIC_KEY",
    ),
    ProviderManifestField(
        "WATA_TRUSTED_IPS",
        "string",
        "Trusted IPs",
        description="Comma-separated IP addresses accepted for Wata webhooks.",
        subsection="Wata",
        attr="TRUSTED_IPS",
    ),
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
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=WataConfig,
    presentation_class=WataPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supported_currencies=WATA_SUPPORTED_CURRENCIES,
    currency_support_note=(
        "WATA H2H payment links and widget document RUB, USD and EUR as payment currencies."
    ),
    currency_support_url="https://wata.pro/api",
)
