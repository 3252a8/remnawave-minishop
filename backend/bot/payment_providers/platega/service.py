import hmac
import json
import logging
from typing import Any, Dict, Optional, Tuple

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
    format_number_for_payload,
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
    MERCHANT_ID: Optional[str] = None
    SECRET: Optional[str] = None
    PAYMENT_METHOD: int = Field(default=2)
    SBP_ENABLED: bool = Field(default=False)
    SBP_ADMIN_ONLY_ENABLED: bool = Field(default=False)
    CRYPTO_ENABLED: bool = Field(default=False)
    CRYPTO_ADMIN_ONLY_ENABLED: bool = Field(default=False)
    SBP_METHOD: int = Field(default=2)
    CRYPTO_METHOD: int = Field(default=13)
    RETURN_URL: Optional[str] = None
    FAILED_URL: Optional[str] = None
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

    WEBAPP_LABEL_RU: Optional[str] = None
    WEBAPP_LABEL_EN: Optional[str] = None
    WEBAPP_ICON: Optional[str] = None
    TELEGRAM_LABEL_RU: Optional[str] = None
    TELEGRAM_LABEL_EN: Optional[str] = None
    TELEGRAM_EMOJI: Optional[str] = None


class PlategaCryptoPresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_PLATEGA_CRYPTO_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: Optional[str] = None
    WEBAPP_LABEL_EN: Optional[str] = None
    WEBAPP_ICON: Optional[str] = None
    TELEGRAM_LABEL_RU: Optional[str] = None
    TELEGRAM_LABEL_EN: Optional[str] = None
    TELEGRAM_EMOJI: Optional[str] = None


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
            logging.warning(
                "PlategaService initialized but not fully configured. Payments disabled."
            )
        else:
            logging.info(
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
    def merchant_id(self) -> Optional[str]:
        return self.config.MERCHANT_ID

    @property
    def secret(self) -> Optional[str]:
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
    def _auth_headers(self) -> Dict[str, str]:
        return {
            "X-MerchantId": self.merchant_id or "",
            "X-Secret": self.secret or "",
            "Content-Type": "application/json",
        }

    async def create_transaction(
        self,
        *,
        amount: float,
        currency: Optional[str],
        description: str,
        payload: Optional[str] = None,
        payment_method: Optional[int] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            logging.error("PlategaService is not configured. Cannot create transaction.")
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

        body: Dict[str, Any] = {
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
        logging.info(
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

    async def get_transaction(self, transaction_id: str) -> Tuple[bool, Dict[str, Any]]:
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
                    logging.warning(
                        "Platega get_transaction failed: id=%s status=%s body=%s",
                        transaction_id,
                        response.status,
                        data,
                    )
                    return False, {"status": response.status, "message": data}
                return True, data
        except Exception as exc:
            logging.exception("Platega get_transaction request failed: id=%s", transaction_id)
            return False, {"message": str(exc)}

    async def try_reuse_pending_transaction(
        self,
        payment: Any,
        *,
        user_id: int,
        sale_mode: str,
        variant: str,
    ) -> Optional[str]:
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
            logging.exception("Platega webhook: failed to parse JSON.")
            return web.Response(status=400, text="bad_request")

        header_merchant = request.headers.get("X-MerchantId")
        header_secret = request.headers.get("X-Secret")
        if not (
            hmac.compare_digest(str(header_merchant or ""), str(self.merchant_id or ""))
            and hmac.compare_digest(str(header_secret or ""), str(self.secret or ""))
        ):
            logging.error("Platega webhook: invalid auth headers")
            return web.Response(status=403, text="forbidden")

        transaction_id = str(data.get("id") or data.get("transactionId") or "").strip()
        status = str(data.get("status") or "").upper()
        amount_raw = data.get("amount")
        currency = data.get("currency") or self.settings.DEFAULT_CURRENCY_SYMBOL or "RUB"

        if not transaction_id or not status:
            logging.error("Platega webhook: missing transaction id or status in payload: %s", data)
            return web.Response(status=400, text="missing_fields")

        async with self.async_session_factory() as session:
            payment = await payment_dal.get_payment_by_provider_payment_id(session, transaction_id)
            if not payment:
                logging.error(
                    "Platega webhook: payment not found for transaction %s", transaction_id
                )
                return web.Response(status=404, text="payment_not_found")

            if payment.status == "succeeded" and status == "CONFIRMED":
                return web.Response(text="ok")

            sale_mode = payment.sale_mode or (
                "traffic" if self.settings.traffic_sale_mode else "subscription"
            )
            payment_months = payment_units_for_activation(payment, sale_mode)

            if status == "CONFIRMED":
                if amount_raw is not None:
                    try:
                        if not decimal_amounts_equal(amount_raw, payment.amount):
                            logging.warning(
                                "Platega webhook: amount mismatch for payment %s (expected %s, got %s)",  # noqa: E501
                                payment.payment_id,
                                format_decimal_amount(payment.amount),
                                format_decimal_amount(amount_raw),
                            )
                    except Exception as exc:
                        logging.warning(
                            "Platega webhook: failed to compare amounts for %s: %s",
                            payment.payment_id,
                            exc,
                        )

                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        transaction_id,
                        PAYMENT_STATUS_PENDING_FINALIZATION,
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logging.exception(
                        "Platega webhook: failed to mark payment %s as succeeded.", transaction_id
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
                        currency=str(currency),
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
                    logging.exception(
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

            logging.warning(
                "Platega webhook: unhandled status '%s' for transaction %s", status, transaction_id
            )
            return web.Response(status=202, text="status_ignored")


async def platega_webhook_route(request: web.Request) -> web.Response:
    service: PlategaService = request.app["platega_service"]
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_platega_router")


def _resolve_platega_variant(
    callback_prefix: str, config: PlategaConfig
) -> Optional[Tuple[str, int]]:
    """Map the callback prefix to (variant, payment_method_id) or ``None`` if disabled."""
    if callback_prefix == "pay_platega_crypto":
        if not (config.CRYPTO_ENABLED or config.CRYPTO_ADMIN_ONLY_ENABLED):
            return None
        return "crypto", config.CRYPTO_METHOD
    if callback_prefix == "pay_platega_sbp":
        if not (config.SBP_ENABLED or config.SBP_ADMIN_ONLY_ENABLED):
            return None
        return "sbp", config.sbp_method_resolved
    # Legacy "pay_platega:" callback — keep working as SBP.
    return "sbp", config.sbp_method_resolved


def _platega_spec_for_callback_prefix(callback_prefix: str) -> PaymentProviderSpec:
    if callback_prefix == "pay_platega_crypto":
        return CRYPTO_SPEC
    return SBP_SPEC


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
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    from ..shared import make_translator

    translator = make_translator(i18n, current_lang)

    if not i18n or not callback.message:
        await notify_callback_parse_error(callback, translator)
        return

    callback_prefix, _, _ = (callback.data or "").partition(":")
    spec = _platega_spec_for_callback_prefix(callback_prefix)
    if not spec.is_available_to_user(
        settings,
        user_id=callback.from_user.id,
        require_configured=False,
    ):
        await notify_service_unavailable(callback, translator)
        return

    variant = (
        _resolve_platega_variant(callback_prefix, platega_service.config)
        if platega_service
        else None
    )
    if variant is None:
        await safe_callback_answer(callback)
        return
    platega_variant, platega_method_id = variant

    if not platega_service or not platega_service.configured:
        logging.error("Platega service is not configured or unavailable.")
        await notify_service_unavailable(callback, translator)
        return

    parts = parse_payment_callback(callback.data or "")
    if not parts:
        logging.error("Invalid pay_platega data in callback: %s", callback.data)
        await notify_callback_parse_error(callback, translator)
        return
    parts, hwid_quote = await quote_hwid_callback_parts(
        session=session,
        user_id=callback.from_user.id,
        parts=parts,
        subscription_service=platega_service.subscription_service,
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
        status="pending_platega",
        description=payment_description,
        months=parts.months,
        provider="platega",
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
        provider="platega",
        pending_status="pending_platega",
        amount=parts.price,
        currency=currency_code,
        sale_mode=parts.sale_mode,
        months=reuse_amounts.months,
        purchased_gb=reuse_amounts.purchased_gb,
        purchased_hwid_devices=reuse_amounts.purchased_hwid_devices,
        tariff_key=reuse_amounts.tariff_key,
    )
    if reusable_payment is not None:
        reusable_url = await platega_service.try_reuse_pending_transaction(
            reusable_payment,
            user_id=callback.from_user.id,
            sale_mode=parts.sale_mode,
            variant=platega_variant,
        )
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
            "Platega: failed to create payment record for user %s.", callback.from_user.id
        )
        await notify_payment_record_failure(callback, translator)
        return

    payload_meta = json.dumps(
        {
            "payment_db_id": payment_record.payment_id,
            "user_id": callback.from_user.id,
            "months": parts.months,
            "sale_mode": parts.sale_mode,
            "platega_variant": platega_variant,
        }
    )

    success, response_data = await platega_service.create_transaction(
        amount=parts.price,
        currency=currency_code,
        description=payment_description,
        payload=payload_meta,
        payment_method=platega_method_id,
    )
    transaction_id = first_value(response_data, "transactionId", "id")
    redirect_url = first_value(response_data, "redirect", "url", "paymentUrl")
    # Platega requires *both* a transaction id and a redirect url to count as a
    # usable payment — neither field is sufficient on its own. Skipping the
    # persistence step when the redirect is missing matches the pre-refactor
    # behavior (we never stored a transaction id without a link).
    persistable_id = transaction_id if redirect_url else None
    await render_link_or_fail(
        callback,
        translator=translator,
        current_lang=current_lang,
        i18n=i18n,
        parts=parts,
        session=session,
        payment=payment_record,
        api_success=success,
        payment_url=redirect_url,
        provider_payment_id=persistable_id,
        provider_response=response_data,
        log_prefix=_LOG,
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


async def _create_webapp_payment(ctx: WebAppPaymentContext, variant: str) -> web.Response:
    settings: Settings = ctx.request.app["settings"]
    service: PlategaService = ctx.request.app["platega_service"]
    if not service or not service.configured:
        return payment_unavailable()
    if variant == "platega_crypto":
        if not (service.config.CRYPTO_ENABLED or service.config.CRYPTO_ADMIN_ONLY_ENABLED):
            return payment_unavailable()
        platega_method_id = service.config.CRYPTO_METHOD
    else:
        if variant == "platega_sbp" and not (
            service.config.SBP_ENABLED or service.config.SBP_ADMIN_ONLY_ENABLED
        ):
            return payment_unavailable()
        platega_method_id = service.config.sbp_method_resolved

    try:
        amounts = payment_record_amounts(
            months=ctx.months,
            sale_mode=ctx.sale_mode,
            traffic_gb=ctx.traffic_gb,
            hwid_device_count=ctx.hwid_device_count,
        )
        payment = await create_webapp_payment_record(
            ctx,
            amount=ctx.price,
            currency=ctx.currency or settings.DEFAULT_CURRENCY_SYMBOL or "RUB",
            status="pending_platega",
            provider="platega",
        )
        payload = json.dumps(
            {
                "payment_db_id": payment.payment_id,
                "user_id": ctx.user_id,
                "months": amounts.months if not amounts.traffic_sale else 0,
                "sale_mode": ctx.sale_mode,
                "traffic_gb": format_number_for_payload(ctx.traffic_gb or ctx.months)
                if amounts.traffic_sale
                else None,
                "hwid_devices": amounts.purchased_hwid_devices,
                "source": "webapp",
                "platega_variant": "crypto" if variant == "platega_crypto" else "sbp",
            }
        )
        success, response_data = await service.create_transaction(
            amount=ctx.price,
            currency=ctx.currency or settings.DEFAULT_CURRENCY_SYMBOL or "RUB",
            description=ctx.description,
            payload=payload,
            payment_method=platega_method_id,
        )
    except Exception:
        await ctx.session.rollback()
        logging.exception("Platega WebApp payment failed")
        return payment_failed()

    return await finalize_webapp_link_payment(
        session=ctx.session,
        payment=payment,
        api_success=success,
        payment_url=(
            first_value(response_data, "redirect", "url", "paymentUrl") if success else None
        ),
        provider_payment_id=first_value(response_data, "transactionId", "id"),
        provider_response=response_data,
        log_prefix="Platega",
    )


async def create_sbp_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await _create_webapp_payment(ctx, "platega_sbp")


async def create_crypto_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await _create_webapp_payment(ctx, "platega_crypto")


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> Optional[str]:
    service: PlategaService = ctx.request.app.get("platega_service")
    if not service or not service.configured:
        return None
    variant = "crypto" if ctx.method == "platega_crypto" else "sbp"
    return await service.try_reuse_pending_transaction(
        payment,
        user_id=ctx.user_id,
        sale_mode=ctx.sale_mode,
        variant=variant,
    )


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
    currency_support_url="https://docs.platega.io/",
)

CRYPTO_SPEC = PaymentProviderSpec(
    id="platega_crypto",
    provider_key="platega",
    label="Platega",
    webapp_label="Platega · Crypto",
    webapp_labels={"ru": "Крипта", "en": "Crypto"},
    webapp_icon="Bitcoin",
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
    currency_support_url="https://docs.platega.io/",
)

SPECS = (SBP_SPEC, CRYPTO_SPEC)
