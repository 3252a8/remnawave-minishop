import json
import logging
from typing import TYPE_CHECKING, Any

from aiogram import Bot, F, Router, types
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from db.dal import payment_dal

from ..base import (
    PaymentProviderSpec,
    ServiceFactoryContext,
    WebAppPaymentContext,
)
from ..shared import (
    CreatePaymentRequest,
    HttpClientMixin,
    LinkPaymentDescriptor,
    PaymentSuccessRequest,
    constant_time_compare,
    finalize_successful_payment,
    first_value,
    format_number_for_payload,
    notify_user_payment_failed,
    payment_amount_and_currency_match,
    payment_units_for_activation,
    run_callback_payment,
    run_reuse_webapp_payment,
    run_webapp_payment,
)
from ..shared import post_json_request as post_json_request
from ..shared.app_context import app_required
from .config import (
    PlategaAllMethodsPresentation,
    PlategaCardPresentation,
    PlategaConfig,
    PlategaCryptoPresentation,
    PlategaInternationalPresentation,
    PlategaSbpPresentation,
    PlategaSubscriptionPresentation,
)
from .manifest import CARD_CONFIG_MANIFEST, CONFIG_MANIFEST, platega_presentation_manifest
from .subscriptions import (
    SUBSCRIPTION_STATUSES,
    PlategaSubscriptionMixin,
    callback_value,
    subscription_context_supported,
    subscription_promo_supported,
)
from .transactions import PlategaTransactionMixin

if TYPE_CHECKING:
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService
else:
    ReferralService = object
    SubscriptionService = object

logger = logging.getLogger(__name__)

_LOG = "platega"


class PlategaService(PlategaTransactionMixin, HttpClientMixin, PlategaSubscriptionMixin):
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
            logger.warning(
                "PlategaService initialized but not fully configured. Payments disabled."
            )
        else:
            logger.info(
                "PlategaService configured. SBP button: %s (method=%s), Card button: %s "
                "(method=%s), Crypto button: %s (method=%s), International button: %s "
                "(method=%s), Method chooser: %s, Subscription button: %s (method=%s)",
                "ON" if config.SBP_ENABLED else "OFF",
                self.sbp_method,
                "ON" if config.CARD_ENABLED else "OFF",
                self.card_method,
                "ON" if config.CRYPTO_ENABLED else "OFF",
                self.crypto_method,
                "ON" if config.INTERNATIONAL_ENABLED else "OFF",
                self.international_method,
                "ON" if config.ALL_METHODS_ENABLED else "OFF",
                "ON" if config.SUBSCRIPTION_ENABLED else "OFF",
                self.subscription_method,
            )

    async def get_transaction(self, transaction_id: str) -> tuple[bool, dict[str, Any]]:
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
                    logger.warning(
                        "Platega get_transaction failed: id=%s status=%s body=%s",
                        transaction_id,
                        response.status,
                        data,
                    )
                    return False, {"status": response.status, "message": data}
                return True, data
        except Exception as exc:
            logger.exception("Platega get_transaction request failed: id=%s", transaction_id)
            return False, {"message": str(exc)}

    async def try_reuse_pending_transaction(
        self,
        payment: Any,
        *,
        user_id: int,
        sale_mode: str,
        variant: str,
    ) -> str | None:
        transaction_id = str(getattr(payment, "provider_payment_id", None) or "").strip()
        payment_url = str(getattr(payment, "provider_payment_url", None) or "").strip()
        if not transaction_id or not payment_url:
            return None

        success, data = await self.get_transaction(transaction_id)
        if not success or str(data.get("status") or "").upper() != "PENDING":
            return None
        if str(first_value(data, "id", "transactionId") or "") != transaction_id:
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
            logger.exception("Platega webhook: failed to parse JSON.")
            return web.Response(status=400, text="bad_request")

        header_merchant = request.headers.get("X-MerchantId")
        header_secret = request.headers.get("X-Secret")
        if not (
            constant_time_compare(header_merchant, self.merchant_id)
            and constant_time_compare(header_secret, self.secret)
        ):
            logger.error("Platega webhook: invalid auth headers")
            return web.Response(status=403, text="forbidden")

        # Subscription callbacks reuse this route but carry their own shapes;
        # they are recognised before the one-off transaction handling below.
        status = str(callback_value(data, "status") or "").upper()
        if status in SUBSCRIPTION_STATUSES:
            return await self.handle_subscription_status_callback(data)
        if callback_value(data, "SubscriptionId"):
            return await self.handle_subscription_charge_callback(data)

        transaction_id = str(data.get("id") or data.get("transactionId") or "").strip()
        amount_raw = data.get("amount")
        currency = data.get("currency")

        if not transaction_id or not status:
            logger.error("Platega webhook: missing transaction id or status in payload: %s", data)
            return web.Response(status=400, text="missing_fields")

        async with self.async_session_factory() as session:
            payment = await payment_dal.get_payment_by_provider_payment_id(
                session,
                "platega",
                transaction_id,
            )
            if not payment:
                logger.error(
                    "Platega webhook: payment not found for transaction %s", transaction_id
                )
                return web.Response(status=404, text="payment_not_found")

            if payment.status == "succeeded" and status == "CONFIRMED":
                return web.Response(text="ok")

            if status == "CONFIRMED":
                if not payment_amount_and_currency_match(
                    expected_amount=payment.amount,
                    expected_currency=payment.currency,
                    received_amount=amount_raw,
                    received_currency=currency,
                    # Platega receives the raw numeric amount passed to
                    # create_transaction, so preserve that invoice precision.
                    places=None,
                    allow_overpayment=True,
                ):
                    logger.warning(
                        "Platega webhook: amount or currency mismatch for payment %s "
                        "(expected=%s %s, got=%s %s)",
                        payment.payment_id,
                        payment.amount,
                        payment.currency,
                        amount_raw,
                        currency,
                    )
                    return web.Response(status=400, text="amount_mismatch")

                try:
                    claimed_payment = await payment_dal.claim_payment_finalization(
                        session,
                        payment.payment_id,
                        provider_payment_id=transaction_id,
                    )
                except Exception:
                    await session.rollback()
                    logger.exception(
                        "Platega webhook: failed to mark payment %s as succeeded.", transaction_id
                    )
                    return web.Response(status=500, text="processing_error")

                if claimed_payment is None:
                    return web.Response(text="ok")
                payment = claimed_payment

                sale_mode = payment.sale_mode or (
                    "traffic" if self.settings.traffic_sale_mode else "subscription"
                )
                payment_months = payment_units_for_activation(payment, sale_mode)

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
                        currency=str(payment.currency),
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
                    logger.exception(
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

            logger.warning(
                "Platega webhook: unhandled status '%s' for transaction %s", status, transaction_id
            )
            return web.Response(status=202, text="status_ignored")


async def platega_webhook_route(request: web.Request) -> web.Response:
    service: PlategaService = app_required(request, "platega_service", PlategaService)
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_platega_router")


@router.callback_query(
    F.data.startswith("pay_platega_sbp:")
    | F.data.startswith("pay_platega_card:")
    | F.data.startswith("pay_platega_crypto:")
    | F.data.startswith("pay_platega_international:")
    | F.data.startswith("pay_platega_all_methods:")
    | F.data.startswith("pay_platega_sub:")
    | F.data.startswith("pay_platega:")
)
async def pay_platega_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    platega_service: PlategaService,
    session: AsyncSession,
) -> None:
    callback_prefix, _, _ = (callback.data or "").partition(":")
    await run_callback_payment(
        _platega_descriptor_for_callback_prefix(callback_prefix),
        callback,
        settings,
        i18n_data,
        platega_service,
        session,
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


async def create_sbp_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_SBP_DESCRIPTOR, ctx)


async def create_card_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_CARD_DESCRIPTOR, ctx)


async def create_crypto_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_CRYPTO_DESCRIPTOR, ctx)


async def create_international_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_INTERNATIONAL_DESCRIPTOR, ctx)


async def create_all_methods_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_ALL_METHODS_DESCRIPTOR, ctx)


async def create_subscription_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_SUBSCRIPTION_DESCRIPTOR, ctx)


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> str | None:
    descriptor = _DESCRIPTORS_BY_METHOD.get(ctx.method, _SBP_DESCRIPTOR)
    return await run_reuse_webapp_payment(descriptor, ctx, payment)


def _context_for_variant(
    variant: str,
) -> Any:
    def _callback_context(
        callback: types.CallbackQuery,
        parts: Any,
        service: PlategaService,
    ) -> dict[str, Any]:
        return {
            "platega_variant": variant,
            "user_id": callback.from_user.id,
            "sale_mode": parts.sale_mode,
            "source": "callback",
        }

    return _callback_context


def _webapp_context_for_variant(variant: str) -> Any:
    def _webapp_context(ctx: WebAppPaymentContext) -> dict[str, Any]:
        return {
            "platega_variant": variant,
            "user_id": ctx.user_id,
            "sale_mode": ctx.sale_mode,
            "source": "webapp",
            "traffic_gb": ctx.traffic_gb,
            "hwid_device_count": ctx.hwid_device_count,
        }

    return _webapp_context


def _platega_method_id(service: PlategaService, variant: str) -> int | None:
    if variant == "card":
        return service.config.CARD_METHOD
    if variant == "crypto":
        return service.config.CRYPTO_METHOD
    if variant == "international":
        return service.config.INTERNATIONAL_METHOD
    if variant == "all_methods":
        return None
    if variant == "subscription":
        return service.subscription_method
    return service.config.sbp_method_resolved


async def _create_payment(
    service: PlategaService,
    request: CreatePaymentRequest,
) -> tuple[bool, dict]:
    context = request.provider_context or {}
    variant = str(context.get("platega_variant") or "sbp")
    payload_data: dict[str, Any] = {
        "payment_db_id": request.payment.payment_id,
        "user_id": request.user_id,
        "months": request.months,
        "sale_mode": request.sale_mode,
        "platega_variant": variant,
    }
    if context.get("source") == "webapp":
        traffic_gb = getattr(request.payment, "purchased_gb", None)
        hwid_devices = getattr(request.payment, "purchased_hwid_devices", None)
        payload_data.update(
            {
                "months": request.months if traffic_gb is None else 0,
                "traffic_gb": format_number_for_payload(traffic_gb)
                if traffic_gb is not None
                else None,
                "hwid_devices": hwid_devices,
                "source": "webapp",
            }
        )
    if variant == "subscription":
        return await service.create_subscription(
            amount=request.amount,
            currency=request.currency,
            description=request.description,
            months=request.months,
            payload=json.dumps(payload_data),
        )
    payer_id = str(request.user_id)
    return await service.create_transaction(
        amount=request.amount,
        currency=request.currency,
        description=request.description,
        payload=json.dumps(payload_data),
        metadata={"userId": payer_id, "userName": payer_id},
        payment_method=_platega_method_id(service, variant),
        allow_method_selection=variant == "all_methods",
    )


async def _reuse_payment_with_context(
    service: PlategaService,
    payment: Any,
    context: dict[str, Any] | None,
) -> str | None:
    if not context:
        return None
    variant = str(context["platega_variant"])
    if variant == "subscription":
        return await service.try_reuse_pending_subscription(payment)
    return await service.try_reuse_pending_transaction(
        payment,
        user_id=int(context["user_id"]),
        sale_mode=str(context["sale_mode"]),
        variant=variant,
    )


def _extract_payment_url(response_data: dict) -> str | None:
    return first_value(response_data, "redirect", "url", "paymentUrl")


def _extract_provider_id(response_data: dict) -> str | None:
    if not _extract_payment_url(response_data):
        return None
    return first_value(response_data, "transactionId", "id")


def _platega_webapp_available(variant: str) -> Any:
    def _available(service: PlategaService) -> bool:
        if not service.configured:
            return False
        if variant == "card":
            return bool(service.config.CARD_ENABLED or service.config.CARD_ADMIN_ONLY_ENABLED)
        if variant == "crypto":
            return bool(service.config.CRYPTO_ENABLED or service.config.CRYPTO_ADMIN_ONLY_ENABLED)
        if variant == "international":
            return bool(
                service.config.INTERNATIONAL_ENABLED
                or service.config.INTERNATIONAL_ADMIN_ONLY_ENABLED
            )
        if variant == "all_methods":
            return bool(
                service.config.ALL_METHODS_ENABLED or service.config.ALL_METHODS_ADMIN_ONLY_ENABLED
            )
        if variant == "subscription":
            return bool(service.subscriptions_enabled)
        return bool(service.config.SBP_ENABLED or service.config.SBP_ADMIN_ONLY_ENABLED)

    return _available


def _platega_descriptor_for_callback_prefix(
    callback_prefix: str,
) -> LinkPaymentDescriptor[PlategaService]:
    if callback_prefix == "pay_platega_card":
        return _CARD_DESCRIPTOR
    if callback_prefix == "pay_platega_crypto":
        return _CRYPTO_DESCRIPTOR
    if callback_prefix == "pay_platega_international":
        return _INTERNATIONAL_DESCRIPTOR
    if callback_prefix == "pay_platega_all_methods":
        return _ALL_METHODS_DESCRIPTOR
    if callback_prefix == "pay_platega_sub":
        return _SUBSCRIPTION_DESCRIPTOR
    return _SBP_DESCRIPTOR


_SBP_MANIFEST = CONFIG_MANIFEST + platega_presentation_manifest(
    "Platega",
    "CreditCard",
    "PLATEGA_SBP",
)


SBP_SPEC = PaymentProviderSpec(
    id="platega_sbp",
    provider_key="platega",
    label="Platega",
    webapp_label="Platega · SBP",
    webapp_labels={"ru": "Pay with card (SBP)", "en": "Pay with card (SBP)"},
    webapp_icon="CreditCard",
    logo_url="/provider-logos/platega.png",
    telegram_labels={"ru": "Pay via SBP", "en": "Pay via SBP"},
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
    manifest_fields=_SBP_MANIFEST,
    supported_currencies_resolver=lambda config: getattr(config, "SUPPORTED_CURRENCIES", "RUB"),
    currency_support_note=(
        "Platega currencies are merchant/method-specific; configure the codes "
        "enabled for your account."
    ),
    info_url="https://platega.io/",
    currency_support_url="https://docs.platega.io/",
)

CARD_SPEC = PaymentProviderSpec(
    id="platega_card",
    provider_key="platega",
    label="Platega",
    webapp_label="Platega · Card",
    webapp_labels={"ru": "Pay by card", "en": "Pay by card"},
    webapp_icon="CreditCard",
    logo_url="/provider-logos/platega.png",
    telegram_labels={"ru": "Pay by card", "en": "Pay by card"},
    telegram_emoji="💳",
    pending_status="pending_platega",
    enabled=lambda config: bool(
        getattr(config, "ENABLED", False) and getattr(config, "CARD_ENABLED", False)
    ),
    admin_only_enabled=lambda config: bool(getattr(config, "CARD_ADMIN_ONLY_ENABLED", False)),
    admin_only_config_attr="CARD_ADMIN_ONLY_ENABLED",
    service_key="platega_service",
    callback_prefix="pay_platega_card",
    create_webapp_payment=create_card_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=PlategaConfig,
    presentation_class=PlategaCardPresentation,
    manifest_fields=CARD_CONFIG_MANIFEST
    + platega_presentation_manifest("Platega", "CreditCard", "PLATEGA_CARD"),
    supported_currencies_resolver=lambda config: getattr(config, "SUPPORTED_CURRENCIES", "RUB"),
    currency_support_note=(
        "Platega currencies are merchant/method-specific; configure the codes "
        "enabled for your account."
    ),
    info_url="https://platega.io/",
    currency_support_url="https://docs.platega.io/",
)

CRYPTO_SPEC = PaymentProviderSpec(
    id="platega_crypto",
    provider_key="platega",
    label="Platega",
    webapp_label="Platega · Crypto",
    webapp_labels={"ru": "Crypto", "en": "Crypto"},
    webapp_icon="Bitcoin",
    logo_url="/provider-logos/platega.png",
    telegram_labels={"ru": "Pay with crypto", "en": "Pay with crypto"},
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
    manifest_fields=platega_presentation_manifest("Platega", "Bitcoin", "PLATEGA_CRYPTO"),
    supported_currencies_resolver=lambda config: getattr(config, "SUPPORTED_CURRENCIES", "RUB"),
    currency_support_note=(
        "Platega currencies are merchant/method-specific; configure the codes "
        "enabled for your account."
    ),
    info_url="https://platega.io/",
    currency_support_url="https://docs.platega.io/",
)

INTERNATIONAL_SPEC = PaymentProviderSpec(
    id="platega_international",
    provider_key="platega",
    label="Platega",
    webapp_label="Platega · International",
    webapp_labels={"ru": "International cards", "en": "International cards"},
    webapp_icon="Globe2",
    logo_url="/provider-logos/platega.png",
    telegram_labels={
        "ru": "Pay with an international card",
        "en": "Pay with an international card",
    },
    telegram_emoji="🌍",
    pending_status="pending_platega",
    enabled=lambda config: bool(
        getattr(config, "ENABLED", False) and getattr(config, "INTERNATIONAL_ENABLED", False)
    ),
    admin_only_enabled=lambda config: bool(
        getattr(config, "INTERNATIONAL_ADMIN_ONLY_ENABLED", False)
    ),
    admin_only_config_attr="INTERNATIONAL_ADMIN_ONLY_ENABLED",
    service_key="platega_service",
    callback_prefix="pay_platega_international",
    create_webapp_payment=create_international_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=PlategaConfig,
    presentation_class=PlategaInternationalPresentation,
    manifest_fields=platega_presentation_manifest(
        "Platega",
        "Globe2",
        "PLATEGA_INTERNATIONAL",
    ),
    supported_currencies_resolver=lambda config: getattr(config, "SUPPORTED_CURRENCIES", "RUB"),
    currency_support_note=(
        "Platega international-payment currencies depend on the merchant account; "
        "configure the codes enabled for your account."
    ),
    info_url="https://platega.io/",
    currency_support_url=(
        "https://docs.platega.io/"
        "%D1%81%D0%BE%D0%B7%D0%B4%D0%B0%D0%BD%D0%B8%D0%B5-"
        "%D0%BF%D0%BB%D0%B0%D1%82%D0%B5%D0%B6%D0%BD%D0%BE%D0%B9-"
        "%D1%81%D1%81%D1%8B%D0%BB%D0%BA%D0%B8-%D1%81-%D0%B7%D0%B0%D0%B4%D0%B0%D0%BD%D0%BD%D1%8B%D0%BC-"
        "%D0%BC%D0%B5%D1%82%D0%BE%D0%B4%D0%BE%D0%BC-29203843e0"
    ),
)

ALL_METHODS_SPEC = PaymentProviderSpec(
    id="platega_all_methods",
    provider_key="platega",
    label="Platega",
    webapp_label="Platega · All methods",
    webapp_labels={"ru": "All payment methods", "en": "All payment methods"},
    webapp_icon="WalletCards",
    logo_url="/provider-logos/platega.png",
    telegram_labels={"ru": "Choose payment method", "en": "Choose payment method"},
    telegram_emoji="💳",
    pending_status="pending_platega",
    enabled=lambda config: bool(
        getattr(config, "ENABLED", False) and getattr(config, "ALL_METHODS_ENABLED", False)
    ),
    admin_only_enabled=lambda config: bool(
        getattr(config, "ALL_METHODS_ADMIN_ONLY_ENABLED", False)
    ),
    admin_only_config_attr="ALL_METHODS_ADMIN_ONLY_ENABLED",
    service_key="platega_service",
    callback_prefix="pay_platega_all_methods",
    create_webapp_payment=create_all_methods_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=PlategaConfig,
    presentation_class=PlategaAllMethodsPresentation,
    manifest_fields=platega_presentation_manifest(
        "Platega",
        "WalletCards",
        "PLATEGA_ALL_METHODS",
    ),
    supported_currencies_resolver=lambda config: getattr(config, "SUPPORTED_CURRENCIES", "RUB"),
    currency_support_note=(
        "The hosted Platega page shows the methods enabled for the merchant account; "
        "configure every currency that those methods can accept."
    ),
    info_url="https://platega.io/",
    currency_support_url=(
        "https://docs.platega.io/"
        "%D1%81%D0%BE%D0%B7%D0%B4%D0%B0%D0%BD%D0%B8%D0%B5-"
        "%D0%BF%D0%BB%D0%B0%D1%82%D0%B5%D0%B6%D0%BD%D0%BE%D0%B9-"
        "%D1%81%D1%81%D1%8B%D0%BB%D0%BA%D0%B8-%D0%B1%D0%B5%D0%B7-"
        "%D0%B7%D0%B0%D0%B4%D0%B0%D0%BD%D0%BD%D0%BE%D0%B3%D0%BE-"
        "%D0%BC%D0%B5%D1%82%D0%BE%D0%B4%D0%B0-33845703e0"
    ),
)

SUBSCRIPTION_SPEC = PaymentProviderSpec(
    id="platega_subscription",
    provider_key="platega",
    label="Platega",
    webapp_label="Platega · Subscription",
    webapp_labels={"ru": "Subscription (SBP)", "en": "Subscription (SBP)"},
    webapp_icon="RefreshCw",
    logo_url="/provider-logos/platega.png",
    telegram_labels={"ru": "Subscribe via SBP", "en": "Subscribe via SBP"},
    telegram_emoji="🔁",
    pending_status="pending_platega",
    enabled=lambda config: bool(
        getattr(config, "ENABLED", False) and getattr(config, "SUBSCRIPTION_ENABLED", False)
    ),
    admin_only_enabled=lambda config: bool(
        getattr(config, "SUBSCRIPTION_ADMIN_ONLY_ENABLED", False)
    ),
    admin_only_config_attr="SUBSCRIPTION_ADMIN_ONLY_ENABLED",
    service_key="platega_service",
    callback_prefix="pay_platega_sub",
    create_webapp_payment=create_subscription_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=PlategaConfig,
    presentation_class=PlategaSubscriptionPresentation,
    manifest_fields=platega_presentation_manifest("Platega", "RefreshCw", "PLATEGA_SUBSCRIPTION"),
    supported_currencies_resolver=lambda config: getattr(config, "SUPPORTED_CURRENCIES", "RUB"),
    # Platega owns the schedule for this button, so the renewal worker must
    # stay away from it: ``manages_recurring`` grants the customer a cancel
    # path without ever making the worker charge a saved method.
    manages_recurring=True,
    payment_context_resolver=subscription_context_supported,
    checkout_promo_resolver=subscription_promo_supported,
    currency_support_note=(
        "Platega SBP subscriptions bill in RUB; only 1-month and 12-month periods "
        "map to a Platega interval."
    ),
    info_url="https://platega.io/",
    currency_support_url="https://docs.platega.io/",
)

SPECS = (
    SBP_SPEC,
    CARD_SPEC,
    CRYPTO_SPEC,
    INTERNATIONAL_SPEC,
    ALL_METHODS_SPEC,
    SUBSCRIPTION_SPEC,
)


def _one_off_descriptor(
    spec: PaymentProviderSpec,
    variant: str,
) -> LinkPaymentDescriptor[PlategaService]:
    return LinkPaymentDescriptor(
        spec=spec,
        provider_key="platega",
        pending_status="pending_platega",
        display_name="Platega",
        log_prefix=_LOG,
        service_app_key="platega_service",
        service_type=PlategaService,
        create=_create_payment,
        reuse=lambda service, payment: service.try_reuse_pending_transaction(
            payment,
            user_id=getattr(payment, "user_id", 0),
            sale_mode=str(getattr(payment, "sale_mode", "") or ""),
            variant=variant,
        ),
        reuse_with_context=_reuse_payment_with_context,
        extract_url=_extract_payment_url,
        extract_provider_id=_extract_provider_id,
        callback_context=_context_for_variant(variant),
        webapp_context=_webapp_context_for_variant(variant),
        webapp_available=_platega_webapp_available(variant),
    )


_SBP_DESCRIPTOR = _one_off_descriptor(SBP_SPEC, "sbp")
_CARD_DESCRIPTOR = _one_off_descriptor(CARD_SPEC, "card")
_CRYPTO_DESCRIPTOR = _one_off_descriptor(CRYPTO_SPEC, "crypto")
_INTERNATIONAL_DESCRIPTOR = _one_off_descriptor(INTERNATIONAL_SPEC, "international")
_ALL_METHODS_DESCRIPTOR = _one_off_descriptor(ALL_METHODS_SPEC, "all_methods")

_SUBSCRIPTION_DESCRIPTOR: LinkPaymentDescriptor[PlategaService] = LinkPaymentDescriptor(
    spec=SUBSCRIPTION_SPEC,
    provider_key="platega",
    pending_status="pending_platega",
    display_name="Platega",
    log_prefix=_LOG,
    service_app_key="platega_service",
    service_type=PlategaService,
    create=_create_payment,
    reuse=lambda service, payment: service.try_reuse_pending_subscription(payment),
    reuse_with_context=_reuse_payment_with_context,
    extract_url=_extract_payment_url,
    extract_provider_id=_extract_provider_id,
    callback_context=_context_for_variant("subscription"),
    webapp_context=_webapp_context_for_variant("subscription"),
    webapp_available=_platega_webapp_available("subscription"),
)

_DESCRIPTORS_BY_METHOD: dict[str, LinkPaymentDescriptor[PlategaService]] = {
    "platega_sbp": _SBP_DESCRIPTOR,
    "platega": _SBP_DESCRIPTOR,
    "platega_card": _CARD_DESCRIPTOR,
    "platega_crypto": _CRYPTO_DESCRIPTOR,
    "platega_international": _INTERNATIONAL_DESCRIPTOR,
    "platega_all_methods": _ALL_METHODS_DESCRIPTOR,
    "platega_subscription": _SUBSCRIPTION_DESCRIPTOR,
}

_DESCRIPTOR = _SBP_DESCRIPTOR
