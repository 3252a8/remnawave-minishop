import base64
import hashlib
import hmac
import json
import logging
import time
from collections import OrderedDict
from typing import TYPE_CHECKING, Any

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
from bot.utils.request_security import ip_in_allowlist, request_client_ip
from config.settings import Settings
from config.tariffs_config import (
    default_payment_currency_code_for_settings,
)
from db.dal import payment_dal

from ..base import (
    PaymentProviderSpec,
    ProviderEnvConfig,
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
    notify_user_payment_failed,
    payment_units_for_activation,
    run_callback_payment,
    run_reuse_webapp_payment,
    run_webapp_payment,
)
from ..shared.app_context import app_required
from .constants import HELEKET_DEFAULT_SUPPORTED_CURRENCIES
from .manifest import _CONFIG_MANIFEST, _PRESENTATION_MANIFEST

router = Router(name="user_subscription_payments_heleket_router")
_LOG = "heleket"

_SUCCESS_STATUSES = {"paid", "paid_over"}
_FAILED_STATUSES = {"fail", "wrong_amount", "cancel", "system_fail"}


class HeleketConfig(ProviderEnvConfig):
    """All Heleket-specific env vars. Lives inside the provider module."""

    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="HELEKET_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    MERCHANT_ID: str | None = None
    API_KEY: str | None = None
    BASE_URL: str = Field(default="https://api.heleket.com")
    CURRENCY: str = Field(default="RUB")
    TO_CURRENCY: str | None = None
    NETWORK: str | None = None
    RETURN_URL: str | None = None
    SUCCESS_URL: str | None = None
    LIFETIME_SECONDS: int = Field(default=3600)
    VERIFY_WEBHOOK_SIGNATURE: bool = Field(default=True)
    TRUSTED_IPS: str = Field(default="31.133.220.8")
    SUPPORTED_CURRENCIES: str = Field(default=HELEKET_DEFAULT_SUPPORTED_CURRENCIES)

    @field_validator("LIFETIME_SECONDS", mode="before")
    @classmethod
    def _clamp_lifetime(cls, v: Any) -> int:
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
    def _strip_optional(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def webhook_path(self) -> str:
        return "/webhook/heleket"

    def full_webhook_url(self, base: str | None) -> str | None:
        if not base:
            return None
        return f"{base.rstrip('/')}{self.webhook_path}"

    @property
    def trusted_ips_list(self) -> list[str]:
        return [item.strip() for item in (self.TRUSTED_IPS or "").split(",") if item.strip()]


class HeleketPresentation(ProviderEnvConfig):
    """Admin-tunable button text/icon overrides for Heleket."""

    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_HELEKET_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: str | None = None
    WEBAPP_LABEL_EN: str | None = None
    WEBAPP_ICON: str | None = None
    TELEGRAM_LABEL_RU: str | None = None
    TELEGRAM_LABEL_EN: str | None = None
    TELEGRAM_EMOJI: str | None = None


def _serialize_for_signature(
    payload: dict[str, Any],
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
    payload: dict[str, Any],
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


def _signature_candidates(payload: dict[str, Any], api_key: str) -> list[tuple[str, str, str]]:
    variants = (
        ("php_unicode_slash", False, True),
        ("unicode_no_slash", False, False),
        ("ascii_slash", True, True),
        ("ascii_no_slash", True, False),
    )
    candidates: list[tuple[str, str, str]] = []
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
    def to_currency(self) -> str | None:
        return (self.config.TO_CURRENCY or "").strip() or None

    @property
    def network(self) -> str | None:
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
        currency: str | None,
        description: str,
        url_callback: str | None,
    ) -> tuple[bool, dict[str, Any]]:
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

        body: dict[str, Any] = {
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

    async def get_payment_info(self, payment_uuid: str) -> tuple[bool, dict[str, Any]]:
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

    async def try_reuse_pending_payment(self, payment: Any) -> str | None:
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

    def _verify_signature(self, payload: dict[str, Any]) -> bool:
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
                "(client_ip=%s remote=%s x_forwarded_for=%s).",
                client_ip,
                request.remote,
                request.headers.get("X-Forwarded-For"),
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
    i18n_data: dict[str, Any],
    heleket_service: HeleketService,
    session: AsyncSession,
) -> None:
    await run_callback_payment(_DESCRIPTOR, callback, settings, i18n_data, heleket_service, session)


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_DESCRIPTOR, ctx)


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> str | None:
    return await run_reuse_webapp_payment(_DESCRIPTOR, ctx, payment)


async def heleket_webhook_route(request: web.Request) -> web.Response:
    service: HeleketService = app_required(request, "heleket_service", HeleketService)
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


def _unwrap_result(response: dict) -> Any:
    return response.get("result") if isinstance(response, dict) else None


async def _create_payment(service: HeleketService, req: CreatePaymentRequest) -> CreateResult:
    return await service.create_payment_link(
        payment_db_id=req.payment.payment_id,
        amount=req.amount,
        currency=req.currency,
        description=req.description,
        url_callback=service.config.full_webhook_url(service.settings.WEBHOOK_BASE_URL),
    )


async def _reuse_payment(service: HeleketService, payment: Any) -> str | None:
    return await service.try_reuse_pending_payment(payment)


_DESCRIPTOR: LinkPaymentDescriptor[HeleketService] = LinkPaymentDescriptor(
    spec=SPEC,
    provider_key="heleket",
    pending_status="pending_heleket",
    display_name="Heleket",
    log_prefix=_LOG,
    service_app_key="heleket_service",
    service_type=HeleketService,
    create=_create_payment,
    reuse=_reuse_payment,
    extract_url=lambda r: first_value(_unwrap_result(r), "url"),
    extract_provider_id=lambda r: first_value(_unwrap_result(r), "uuid"),
    webapp_currency=lambda ctx, settings, service: (
        ctx.currency or default_payment_currency_code_for_settings(settings)
    ),
)
