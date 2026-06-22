import base64
import hashlib
import hmac
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from aiogram import Bot, F, Router, types
from aiohttp import web
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
    quote_hwid_callback_parts,
    render_link_or_fail,
    render_payment_link,
)

router = Router(name="user_subscription_payments_heleket_router")
_LOG = "heleket"

_SUCCESS_STATUSES = {"paid", "paid_over"}
_FAILED_STATUSES = {"fail", "wrong_amount", "cancel", "system_fail"}
HELEKET_DEFAULT_SUPPORTED_CURRENCIES = (
    "RUB,USD,EUR,USDT,USDC,BTC,ETH,LTC,TON,TRX,BNB,BCH,DASH,DAI,DOGE,"
    "MATIC,SHIB,SOL,XMR,AVAX,BUSD,VERSE"
)


class HeleketConfig(ProviderEnvConfig):
    """All Heleket-specific env vars. Lives inside the provider module."""

    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="HELEKET_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    MERCHANT_ID: Optional[str] = None
    API_KEY: Optional[str] = None
    BASE_URL: str = Field(default="https://api.heleket.com")
    CURRENCY: str = Field(default="RUB")
    TO_CURRENCY: Optional[str] = None
    NETWORK: Optional[str] = None
    RETURN_URL: Optional[str] = None
    SUCCESS_URL: Optional[str] = None
    LIFETIME_SECONDS: int = Field(default=3600)
    VERIFY_WEBHOOK_SIGNATURE: bool = Field(default=True)
    TRUSTED_IPS: str = Field(default="31.133.220.8")
    SUPPORTED_CURRENCIES: str = Field(default=HELEKET_DEFAULT_SUPPORTED_CURRENCIES)

    @field_validator("LIFETIME_SECONDS", mode="before")
    @classmethod
    def _clamp_lifetime(cls, v):
        if isinstance(v, str):
            v = v.strip()
        try:
            value = int(v)
        except (TypeError, ValueError):
            return 3600
        return min(43200, max(300, value))

    @field_validator(
        "MERCHANT_ID",
        "API_KEY",
        "TO_CURRENCY",
        "NETWORK",
        "RETURN_URL",
        "SUCCESS_URL",
        mode="before",
    )
    @classmethod
    def _strip_optional(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def webhook_path(self) -> str:
        return "/webhook/heleket"

    def full_webhook_url(self, base: Optional[str]) -> Optional[str]:
        if not base:
            return None
        return f"{base.rstrip('/')}{self.webhook_path}"

    @property
    def trusted_ips_list(self) -> List[str]:
        return [item.strip() for item in (self.TRUSTED_IPS or "").split(",") if item.strip()]


class HeleketPresentation(ProviderEnvConfig):
    """Admin-tunable button text/icon overrides for Heleket."""

    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_HELEKET_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: Optional[str] = None
    WEBAPP_LABEL_EN: Optional[str] = None
    WEBAPP_ICON: Optional[str] = None
    TELEGRAM_LABEL_RU: Optional[str] = None
    TELEGRAM_LABEL_EN: Optional[str] = None
    TELEGRAM_EMOJI: Optional[str] = None


def _serialize_for_signature(
    payload: Dict[str, Any],
    *,
    ensure_ascii: bool = False,
    escape_slashes: bool = True,
) -> str:
    """Serialize JSON exactly the way Heleket signs it.

    Heleket's PHP example uses ``json_encode`` with ``JSON_UNESCAPED_UNICODE``
    and default forward-slash escaping. We replicate both: ``ensure_ascii=False``
    keeps unicode untouched, then we manually escape ``/`` so that the base64
    payload matches the one signed on the Heleket side.
    """
    encoded = json.dumps(payload, ensure_ascii=ensure_ascii, separators=(",", ":"))
    return encoded.replace("/", "\\/") if escape_slashes else encoded


def _compute_signature(
    payload: Dict[str, Any],
    api_key: str,
    *,
    ensure_ascii: bool = False,
    escape_slashes: bool = True,
) -> str:
    body = _serialize_for_signature(
        payload,
        ensure_ascii=ensure_ascii,
        escape_slashes=escape_slashes,
    ).encode("utf-8")
    b64 = base64.b64encode(body).decode("ascii")
    return hashlib.md5((b64 + str(api_key or "")).encode("utf-8")).hexdigest()


def _signature_candidates(payload: Dict[str, Any], api_key: str) -> List[Tuple[str, str, str]]:
    variants = (
        ("php_unicode_slash", False, True),
        ("unicode_no_slash", False, False),
        ("ascii_slash", True, True),
        ("ascii_no_slash", True, False),
    )
    candidates: List[Tuple[str, str, str]] = []
    seen: set[str] = set()
    for name, ensure_ascii, escape_slashes in variants:
        signature = _compute_signature(
            payload,
            api_key,
            ensure_ascii=ensure_ascii,
            escape_slashes=escape_slashes,
        )
        if signature in seen:
            continue
        seen.add(signature)
        canonical = _serialize_for_signature(
            payload,
            ensure_ascii=ensure_ascii,
            escape_slashes=escape_slashes,
        )
        candidates.append((name, signature, canonical))
    return candidates


def _signature_preview(signature: str) -> str:
    signature = str(signature or "")
    if len(signature) <= 12:
        return signature
    return f"{signature[:6]}...{signature[-6:]}"


class HeleketService(HttpClientMixin):
    def __init__(
        self,
        *,
        bot: Bot,
        settings: Settings,
        config: HeleketConfig,
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
                "HeleketService initialized but not fully configured. Payments disabled."
            )

    # All of the following are properties on top of the live ``self.config``
    # so admin UI changes (which mutate the config bundle) take effect without
    # restarting the bot — otherwise ``configured`` would be frozen to the
    # ``False`` state from startup and the button would never appear.
    @property
    def configured(self) -> bool:
        return bool(provider_runtime_enabled(self.config) and self.merchant_id and self.api_key)

    @property
    def base_url(self) -> str:
        return (self.config.BASE_URL or "https://api.heleket.com").rstrip("/")

    @property
    def merchant_id(self) -> str:
        return (self.config.MERCHANT_ID or "").strip()

    @property
    def api_key(self) -> str:
        return (self.config.API_KEY or "").strip()

    @property
    def currency(self) -> str:
        return (self.config.CURRENCY or "RUB").upper()

    @property
    def to_currency(self):
        return (self.config.TO_CURRENCY or "").strip() or None

    @property
    def network(self):
        return (self.config.NETWORK or "").strip() or None

    @property
    def return_url(self) -> str:
        return self.config.RETURN_URL or f"https://t.me/{self._default_return_url}"

    @property
    def success_url(self) -> str:
        return self.config.SUCCESS_URL or self.return_url

    @property
    def lifetime_seconds(self) -> int:
        return self.config.LIFETIME_SECONDS

    @property
    def verify_webhook_signature(self) -> bool:
        return self.config.VERIFY_WEBHOOK_SIGNATURE

    async def create_payment_link(
        self,
        *,
        payment_db_id: int,
        amount: float,
        currency: Optional[str],
        description: str,
        url_callback: Optional[str],
    ) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            logging.error("HeleketService is not configured. Cannot create payment link.")
            return False, {"message": "service_not_configured"}

        currency_code = normalize_payment_currency_code(currency or self.currency)
        supported = parse_supported_currency_codes(self.config.SUPPORTED_CURRENCIES)
        if supported and currency_code not in supported:
            return False, {
                "message": "unsupported_currency",
                "currency": currency_code,
                "supported_currencies": list(supported),
            }

        body: Dict[str, Any] = {
            "amount": str(format_decimal_amount(amount)),
            "currency": currency_code,
            "order_id": str(payment_db_id),
            "url_return": self.return_url,
            "url_success": self.success_url,
            "lifetime": int(self.lifetime_seconds),
        }
        if description:
            body["additional_data"] = description[:255]
        if self.to_currency:
            body["to_currency"] = self.to_currency
        if self.network:
            body["network"] = self.network
        if url_callback:
            body["url_callback"] = url_callback

        signed_body = _serialize_for_signature(body).encode("utf-8")
        headers = {
            "merchant": self.merchant_id,
            "sign": _compute_signature(body, self.api_key),
            "Content-Type": "application/json",
        }
        session = await self._get_session()
        try:
            async with session.post(
                f"{self.base_url}/v1/payment",
                data=signed_body,
                headers=headers,
            ) as response:
                response_text = await response.text()
                try:
                    response_data = json.loads(response_text) if response_text else {}
                except json.JSONDecodeError:
                    logging.error("Heleket create_payment_link: invalid JSON: %s", response_text)
                    return False, {
                        "status": response.status,
                        "message": "invalid_json",
                        "raw": response_text,
                    }
                state = response_data.get("state") if isinstance(response_data, dict) else None
                if response.status != 200 or state != 0:
                    logging.error(
                        "Heleket create_payment_link: API error (status=%s, body=%s)",
                        response.status,
                        response_data,
                    )
                    return False, {"status": response.status, "message": response_data}
                return True, response_data
        except Exception as exc:
            logging.exception("Heleket create_payment_link: request failed.")
            return False, {"message": str(exc)}

    async def get_payment_info(self, payment_uuid: str) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            return False, {"message": "service_not_configured"}

        payment_uuid = str(payment_uuid or "").strip()
        if not payment_uuid:
            return False, {"message": "missing_payment_uuid"}

        body = {"uuid": payment_uuid}
        headers = {
            "merchant": self.merchant_id,
            "sign": _compute_signature(body, self.api_key),
            "Content-Type": "application/json",
        }
        session = await self._get_session()
        try:
            async with session.post(
                f"{self.base_url}/v1/payment/info",
                data=_serialize_for_signature(body).encode("utf-8"),
                headers=headers,
            ) as response:
                response_data = await response.json(content_type=None)
                state = response_data.get("state") if isinstance(response_data, dict) else None
                if response.status != 200 or state != 0:
                    logging.warning(
                        "Heleket get_payment_info failed: uuid=%s status=%s body=%s",
                        payment_uuid,
                        response.status,
                        response_data,
                    )
                    return False, {"status": response.status, "message": response_data}
                result = response_data.get("result") or {}
                return isinstance(result, dict), result
        except Exception as exc:
            logging.exception("Heleket get_payment_info request failed: uuid=%s", payment_uuid)
            return False, {"message": str(exc)}

    async def try_reuse_pending_payment(self, payment: Any) -> Optional[str]:
        payment_uuid = str(getattr(payment, "provider_payment_id", None) or "").strip()
        if not payment_uuid:
            return None

        success, data = await self.get_payment_info(payment_uuid)
        if not success or not isinstance(data, dict):
            return None
        status = str(data.get("payment_status") or data.get("status") or "").lower()
        if status != "check" or bool(data.get("is_final")):
            return None
        if str(data.get("uuid") or "") != payment_uuid:
            return None
        if str(data.get("order_id") or "") != str(payment.payment_id):
            return None
        try:
            expired_at = int(data.get("expired_at") or 0)
        except (TypeError, ValueError):
            return None
        if expired_at and expired_at <= int(time.time()):
            return None
        return (
            str(data.get("url") or "").strip()
            or str(getattr(payment, "provider_payment_url", None) or "").strip()
            or None
        )

    def _verify_signature(self, payload: Dict[str, Any]) -> bool:
        received = payload.get("sign")
        if not isinstance(received, str) or not received:
            return False
        data = OrderedDict((k, v) for k, v in payload.items() if k != "sign")
        candidates = _signature_candidates(data, self.api_key)
        for name, expected, _canonical in candidates:
            if hmac.compare_digest(expected, received):
                if name != "php_unicode_slash":
                    logging.info("Heleket webhook: signature matched variant %s.", name)
                return True
        logging.warning(
            "Heleket webhook: invalid signature "
            "(received=%s expected=%s canonical_json_sha256=%s api_key_len=%s).",
            _signature_preview(received),
            [_signature_preview(expected) for _name, expected, _canonical in candidates],
            [
                hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                for _name, _expected, canonical in candidates
            ],
            len(self.api_key),
        )
        return False

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.Response(status=503, text="heleket_disabled")

        client_ip = request_client_ip(request, trusted_proxies=self.settings.trusted_proxies)
        trusted = self.config.trusted_ips_list
        if trusted and not ip_in_allowlist(client_ip, trusted):
            logging.warning(
                "Heleket webhook denied from unauthorized IP source "
                "(client_ip=%s remote=%s x_forwarded_for=%s trusted_ips=%s trusted_proxies=%s).",
                client_ip,
                request.remote,
                request.headers.get("X-Forwarded-For"),
                trusted,
                self.settings.trusted_proxies,
            )
            return web.Response(status=403, text="forbidden")

        raw_body = await request.read()
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            logging.exception("Heleket webhook: failed to parse JSON.")
            return web.Response(status=400, text="bad_request")

        if not isinstance(payload, dict):
            return web.Response(status=400, text="bad_request")

        if self.verify_webhook_signature and not self._verify_signature(payload):
            return web.Response(status=403, text="invalid_signature")

        uuid_value = str(payload.get("uuid") or "").strip()
        status = str(payload.get("status") or "").strip().lower()
        order_id_raw = payload.get("order_id")
        amount_raw = payload.get("amount")
        currency = payload.get("currency") or self.currency

        if not status or not (uuid_value or order_id_raw):
            logging.error("Heleket webhook: missing status or ids: %s", payload)
            return web.Response(status=400, text="missing_fields")

        async with self.async_session_factory() as session:
            payment = await lookup_payment_by_order_or_provider_id(
                session,
                order_id_raw=order_id_raw,
                provider_payment_id=uuid_value or None,
            )
            if not payment:
                logging.error(
                    "Heleket webhook: payment not found (order_id=%s, uuid=%s)",
                    order_id_raw,
                    uuid_value,
                )
                return web.Response(status=404, text="payment_not_found")

            if payment.status == "succeeded" and status in _SUCCESS_STATUSES:
                return web.Response(text="ok")

            resolved_id = uuid_value or str(payment.payment_id)

            if status in _SUCCESS_STATUSES:
                if amount_raw is not None:
                    try:
                        if not decimal_amounts_equal(amount_raw, payment.amount):
                            logging.warning(
                                "Heleket webhook: amount mismatch for payment %s "
                                "(expected %s, got %s)",
                                payment.payment_id,
                                format_decimal_amount(payment.amount),
                                format_decimal_amount(amount_raw),
                            )
                    except Exception as exc:
                        logging.warning(
                            "Heleket webhook: failed to compare amounts for %s: %s",
                            payment.payment_id,
                            exc,
                        )

                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        resolved_id,
                        PAYMENT_STATUS_PENDING_FINALIZATION,
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logging.exception(
                        "Heleket webhook: failed to mark payment %s as succeeded.",
                        resolved_id,
                    )
                    return web.Response(status=500, text="processing_error")

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
                        provider_subscription="heleket",
                        provider_notification="heleket",
                        db_user=payment.user,
                        log_prefix="Heleket webhook",
                    )
                )
                if outcome is None:
                    return web.Response(status=500, text="processing_error")
                return web.Response(text="ok")

            if status in _FAILED_STATUSES:
                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        resolved_id,
                        "failed",
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logging.exception(
                        "Heleket webhook: failed to mark payment %s as failed.",
                        resolved_id,
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

            logging.info(
                "Heleket webhook: intermediate status '%s' for payment %s",
                status,
                resolved_id,
            )
            return web.Response(status=202, text="status_ignored")


@router.callback_query(F.data.startswith("pay_heleket:"))
async def pay_heleket_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    heleket_service: HeleketService,
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

    if not heleket_service or not heleket_service.configured:
        logging.error("Heleket service is not configured or unavailable.")
        await notify_service_unavailable(callback, translator)
        return

    parts = parse_payment_callback(callback.data or "")
    if not parts:
        logging.error("Invalid pay_heleket data in callback: %s", callback.data)
        await notify_callback_parse_error(callback, translator)
        return
    parts, hwid_quote = await quote_hwid_callback_parts(
        session=session,
        user_id=callback.from_user.id,
        parts=parts,
        subscription_service=heleket_service.subscription_service,
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
        status="pending_heleket",
        description=payment_description,
        months=parts.months,
        provider="heleket",
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
        provider="heleket",
        pending_status="pending_heleket",
        amount=parts.price,
        currency=currency_code,
        sale_mode=parts.sale_mode,
        months=reuse_amounts.months,
        purchased_gb=reuse_amounts.purchased_gb,
        purchased_hwid_devices=reuse_amounts.purchased_hwid_devices,
        tariff_key=reuse_amounts.tariff_key,
    )
    if reusable_payment is not None:
        reusable_url = await heleket_service.try_reuse_pending_payment(reusable_payment)
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
            "Heleket: failed to create payment record for user %s.", callback.from_user.id
        )
        await notify_payment_record_failure(callback, translator)
        return

    success, response_data = await heleket_service.create_payment_link(
        payment_db_id=payment_record.payment_id,
        amount=parts.price,
        currency=currency_code,
        description=payment_description,
        url_callback=heleket_service.config.full_webhook_url(settings.WEBHOOK_BASE_URL),
    )
    result = response_data.get("result") if isinstance(response_data, dict) else None
    await render_link_or_fail(
        callback,
        translator=translator,
        current_lang=current_lang,
        i18n=i18n,
        parts=parts,
        session=session,
        payment=payment_record,
        api_success=success,
        payment_url=first_value(result, "url"),
        provider_payment_id=first_value(result, "uuid"),
        provider_response=response_data,
        log_prefix=_LOG,
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    settings: Settings = ctx.request.app["settings"]
    service: HeleketService = ctx.request.app["heleket_service"]
    if not service or not service.configured:
        return payment_unavailable()

    currency = ctx.currency or default_payment_currency_code_for_settings(settings)
    try:
        payment = await create_webapp_payment_record(
            ctx,
            amount=ctx.price,
            currency=currency,
            status="pending_heleket",
            provider="heleket",
        )
        success, response_data = await service.create_payment_link(
            payment_db_id=payment.payment_id,
            amount=ctx.price,
            currency=currency,
            description=ctx.description,
            url_callback=service.config.full_webhook_url(settings.WEBHOOK_BASE_URL),
        )
    except Exception:
        await ctx.session.rollback()
        logging.exception("Heleket WebApp payment failed")
        return payment_failed()

    result = response_data.get("result") if isinstance(response_data, dict) else None
    return await finalize_webapp_link_payment(
        session=ctx.session,
        payment=payment,
        api_success=success,
        payment_url=first_value(result, "url") if success else None,
        provider_payment_id=first_value(result, "uuid"),
        provider_response=response_data,
        log_prefix="Heleket",
    )


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> Optional[str]:
    service: HeleketService = ctx.request.app.get("heleket_service")
    if not service or not service.configured:
        return None
    return await service.try_reuse_pending_payment(payment)


async def heleket_webhook_route(request: web.Request) -> web.Response:
    service: HeleketService = request.app["heleket_service"]
    return await service.webhook_route(request)


def create_service(ctx: ServiceFactoryContext) -> HeleketService:
    bundle = ctx.config_for("heleket_service")
    config = (
        bundle.config if bundle and isinstance(bundle.config, HeleketConfig) else HeleketConfig()
    )
    return HeleketService(
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
        subsection="Heleket",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_HELEKET_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_HELEKET_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_HELEKET_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "Bitcoin",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_HELEKET_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_HELEKET_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_HELEKET_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            "🪙",
            "TELEGRAM_EMOJI",
        ),
    )
)


_CONFIG_MANIFEST = (
    ProviderManifestField(
        "HELEKET_ENABLED", "bool", "Enabled", subsection="Heleket", attr="ENABLED"
    ),
    ProviderManifestField(
        "HELEKET_MERCHANT_ID",
        "string",
        "Merchant ID",
        subsection="Heleket",
        secret=True,
        attr="MERCHANT_ID",
    ),
    ProviderManifestField(
        "HELEKET_API_KEY",
        "string",
        "Payment API key",
        subsection="Heleket",
        secret=True,
        attr="API_KEY",
    ),
    ProviderManifestField(
        "HELEKET_BASE_URL",
        "url",
        "Base URL",
        placeholder="https://api.heleket.com",
        subsection="Heleket",
        attr="BASE_URL",
    ),
    ProviderManifestField(
        "HELEKET_CURRENCY",
        "string",
        "Invoice currency",
        description="Fiat or crypto code (RUB, USD, USDT).",
        placeholder="RUB",
        subsection="Heleket",
        attr="CURRENCY",
    ),
    ProviderManifestField(
        "HELEKET_SUPPORTED_CURRENCIES",
        "string",
        "Supported currencies",
        description=(
            "Comma-separated invoice currencies allowed for Heleket in this shop. "
            "Heleket can reject unsupported codes per account/service."
        ),
        placeholder=HELEKET_DEFAULT_SUPPORTED_CURRENCIES,
        subsection="Heleket",
        attr="SUPPORTED_CURRENCIES",
    ),
    ProviderManifestField(
        "HELEKET_TO_CURRENCY",
        "string",
        "Target crypto",
        description="Optional target cryptocurrency for conversion.",
        subsection="Heleket",
        attr="TO_CURRENCY",
    ),
    ProviderManifestField(
        "HELEKET_NETWORK",
        "string",
        "Blockchain network",
        description="Optional blockchain network code (tron, bsc, eth).",
        subsection="Heleket",
        attr="NETWORK",
    ),
    ProviderManifestField(
        "HELEKET_RETURN_URL", "url", "Return URL", subsection="Heleket", attr="RETURN_URL"
    ),
    ProviderManifestField(
        "HELEKET_SUCCESS_URL", "url", "Success URL", subsection="Heleket", attr="SUCCESS_URL"
    ),
    ProviderManifestField(
        "HELEKET_LIFETIME_SECONDS",
        "int",
        "Invoice lifetime (seconds)",
        description="300..43200; Heleket defaults to 3600.",
        subsection="Heleket",
        min=300,
        max=43200,
        attr="LIFETIME_SECONDS",
    ),
    ProviderManifestField(
        "HELEKET_VERIFY_WEBHOOK_SIGNATURE",
        "bool",
        "Verify webhook signature",
        subsection="Heleket",
        attr="VERIFY_WEBHOOK_SIGNATURE",
    ),
    ProviderManifestField(
        "HELEKET_TRUSTED_IPS",
        "string",
        "Trusted IPs",
        description="Comma-separated IP addresses accepted for Heleket webhooks.",
        subsection="Heleket",
        attr="TRUSTED_IPS",
    ),
)


SPEC = PaymentProviderSpec(
    id="heleket",
    provider_key="heleket",
    label="Heleket",
    webapp_label="Heleket",
    webapp_labels={"ru": "Heleket", "en": "Heleket"},
    webapp_icon="Bitcoin",
    telegram_labels={"ru": "Heleket", "en": "Heleket"},
    telegram_emoji="🪙",
    pending_status="pending_heleket",
    enabled=lambda config: bool(getattr(config, "ENABLED", False)),
    service_key="heleket_service",
    callback_prefix="pay_heleket",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/heleket",
    webhook_route=heleket_webhook_route,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    emoji="🪙",
    config_class=HeleketConfig,
    presentation_class=HeleketPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supported_currencies_resolver=lambda config: getattr(
        config, "SUPPORTED_CURRENCIES", HELEKET_DEFAULT_SUPPORTED_CURRENCIES
    ),
    currency_support_note=(
        "Heleket supports crypto and fiat invoice currencies, but exact availability "
        "can depend on service/account settings."
    ),
    currency_support_url="https://doc.heleket.com/methods/payments/creating-invoice",
)
