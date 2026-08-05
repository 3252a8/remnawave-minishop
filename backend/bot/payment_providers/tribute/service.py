from __future__ import annotations

import hashlib
import hmac
import json
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from aiogram import Bot, F, Router, types
from aiohttp import web
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from db.dal import payment_dal as payment_dal
from db.dal import subscription_dal as subscription_dal
from db.dal import tribute_dal as tribute_dal
from db.dal import user_dal as user_dal
from db.models import Payment as Payment
from db.models import TributeEntitlement as TributeEntitlement
from db.models import TributeWebhookEvent as TributeWebhookEvent

from ..base import (
    BaseProviderService,
    PaymentProviderSpec,
    ProviderManifestField,
    ProviderWebhookPayload,
    ServiceFactoryContext,
    WebAppPaymentContext,
    provider_runtime_enabled,
)
from ..shared import (
    CreatePaymentRequest,
    CreateResult,
    HttpClientMixin,
    LinkPaymentDescriptor,
    PaymentCallbackParts,
    PaymentSuccessOutcome,
    PaymentSuccessRequest,
    finalize_successful_payment,
    first_value,
    make_translator,
    notify_callback_parse_error,
    notify_service_unavailable,
    parse_payment_callback,
    payment_link_response,
    payment_unavailable,
    post_json_request,
    quote_hwid_callback_parts,
    render_payment_link,
    run_callback_payment,
    run_reuse_webapp_payment,
    run_webapp_payment,
    sale_mode_base,
)
from ..shared.app_context import app_required
from .config import (
    TRIBUTE_MAX_WEBHOOK_BYTES as TRIBUTE_MAX_WEBHOOK_BYTES,
)
from .config import (
    TRIBUTE_PENDING_STATUS as TRIBUTE_PENDING_STATUS,
)
from .config import (
    TRIBUTE_PROVIDER as TRIBUTE_PROVIDER,
)
from .config import (
    TRIBUTE_SERVICE_KEY as TRIBUTE_SERVICE_KEY,
)
from .config import (
    TRIBUTE_SIGNATURE_HEADER as TRIBUTE_SIGNATURE_HEADER,
)
from .config import (
    TRIBUTE_SUBSCRIPTION_TYPES as TRIBUTE_SUBSCRIPTION_TYPES,
)
from .config import (
    TRIBUTE_WEBHOOK_EVENTS as TRIBUTE_WEBHOOK_EVENTS,
)
from .config import (
    TributeConfig as TributeConfig,
)
from .config import (
    TributePlanBinding as TributePlanBinding,
)
from .config import (
    TributePresentation as TributePresentation,
)
from .config import (
    TributeProductBinding as TributeProductBinding,
)
from .config import (
    _as_utc as _as_utc,
)
from .config import (
    _binding_for_checkout as _binding_for_checkout,
)
from .config import (
    _binding_for_event as _binding_for_event,
)
from .config import (
    _event_fingerprint as _event_fingerprint,
)
from .config import (
    _event_order as _event_order,
)
from .config import (
    _has_active_tribute_recurrence as _has_active_tribute_recurrence,
)
from .config import (
    _normalized_datetime as _normalized_datetime,
)
from .config import (
    _product_binding_for_checkout as _product_binding_for_checkout,
)
from .config import (
    _product_binding_for_event as _product_binding_for_event,
)
from .config import (
    _shop_context_supported as _shop_context_supported,
)
from .config import (
    _shop_enabled_for_source as _shop_enabled_for_source,
)
from .config import (
    _shop_event_fingerprint as _shop_event_fingerprint,
)
from .config import (
    _subscriber_key as _subscriber_key,
)
from .config import (
    tribute_checkout_promo_supported as tribute_checkout_promo_supported,
)
from .config import (
    tribute_price_managed_externally as tribute_price_managed_externally,
)
from .config import (
    tribute_shop_amount_metadata as tribute_shop_amount_metadata,
)
from .config import (
    tribute_shop_amount_supported as tribute_shop_amount_supported,
)
from .config import (
    tribute_supports_checkout as tribute_supports_checkout,
)
from .creator import (
    TributeCreatorApiError as TributeCreatorApiError,
)
from .creator import (
    TributeCreatorCatalog as TributeCreatorCatalog,
)
from .creator import (
    TributeCreatorCatalogMixin,
)
from .models import (
    TributeDigitalProductPayload,
    TributeDigitalProductRefundPayload,
    TributeSubscriptionPayload,
    TributeWebhookEnvelope,
)
from .shop import (
    TRIBUTE_SHOP_API_BASE_URL,
    TRIBUTE_SHOP_WEBHOOK_EVENTS,
    TributeShopActionResponse,
    TributeShopErrorResponse,
    TributeShopOrderRequest,
    TributeShopOrderResponse,
    TributeShopRefundResponse,
    TributeShopTransactionsResponse,
    normalize_shop_currency,
    parse_tribute_shop_webhook_payload,
    tribute_shop_major_to_minor,
    tribute_shop_period_for_months,
    truncate_shop_description,
    truncate_shop_title,
)
from .shop import (
    TributeShopOrderCancelledPayload as TributeShopOrderCancelledPayload,
)
from .shop import (
    TributeShopOrderChargeFailedPayload as TributeShopOrderChargeFailedPayload,
)
from .shop import (
    TributeShopOrderChargeSuccessPayload as TributeShopOrderChargeSuccessPayload,
)
from .shop import (
    TributeShopOrderPayload as TributeShopOrderPayload,
)
from .shop import (
    TributeShopOrderPaymentFailedPayload as TributeShopOrderPaymentFailedPayload,
)
from .shop import (
    TributeShopOrderRefundedPayload as TributeShopOrderRefundedPayload,
)
from .shop import (
    TributeShopWebhookPayload as TributeShopWebhookPayload,
)
from .webhook_products import TributeProductWebhookMixin
from .webhook_shop import TributeShopWebhookMixin
from .webhook_subscriptions import TributeSubscriptionWebhookMixin

if TYPE_CHECKING:
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService
else:
    ReferralService = object
    SubscriptionService = object

logger = logging.getLogger(__name__)


class TributeService(
    TributeCreatorCatalogMixin,
    TributeProductWebhookMixin,
    TributeShopWebhookMixin,
    TributeSubscriptionWebhookMixin,
    HttpClientMixin,
    BaseProviderService,
):
    provider_key = TRIBUTE_PROVIDER
    disabled_response_text = "tribute_disabled"

    def __init__(
        self,
        *,
        bot: Bot,
        settings: Settings,
        config: TributeConfig,
        i18n: JsonI18n,
        async_session_factory: sessionmaker,
        subscription_service: SubscriptionService,
        referral_service: ReferralService,
    ) -> None:
        self.bot = bot
        self.settings = settings
        self.config = config
        self.i18n = i18n
        self.async_session_factory = async_session_factory
        self.subscription_service = subscription_service
        self.referral_service = referral_service
        self._init_http_client(total_timeout=lambda: self.settings.PAYMENT_REQUEST_TIMEOUT_SECONDS)

    async def _finalize_successful_payment(
        self,
        request: PaymentSuccessRequest,
    ) -> PaymentSuccessOutcome | None:
        return await finalize_successful_payment(request)

    @property
    def configured(self) -> bool:
        return bool(provider_runtime_enabled(self.config) and self.config.API_KEY)

    @property
    def shop_enabled(self) -> bool:
        # The Shop ID is part of "configured": every order and every webhook is
        # validated against it, so a missing one means Creator links only.
        return bool(self.configured and self.config.SHOP_ENABLED and (self.config.SHOP_ID or 0) > 0)

    async def create_shop_order(
        self,
        *,
        payment_db_id: int,
        user_id: int,
        amount: float,
        regular_amount: float | None = None,
        currency: str,
        title: str,
        description: str,
        months: float,
        sale_mode: str,
    ) -> CreateResult:
        if not self.shop_enabled:
            return False, {"message": "shop_not_enabled"}
        if not self.config.API_KEY:
            return False, {"message": "missing_api_key"}
        if self.config.SHOP_ID is None:
            return False, {"message": "missing_shop_id"}
        if not _shop_context_supported(months, sale_mode):
            return False, {"message": "unsupported_payment_context"}

        base = sale_mode_base(sale_mode)
        try:
            period = (
                tribute_shop_period_for_months(int(months)) if base == "subscription" else "onetime"
            )
            initial_minor_amount = tribute_shop_major_to_minor(
                Decimal(str(amount)),
                currency,
            )
            minor_amount = initial_minor_amount
            first_period_amount: int | None = None
            if base == "subscription" and regular_amount is not None:
                minor_amount = tribute_shop_major_to_minor(
                    Decimal(str(regular_amount)),
                    currency,
                )
                if initial_minor_amount != minor_amount:
                    first_period_amount = initial_minor_amount
            order_request = TributeShopOrderRequest(
                shopId=self.config.SHOP_ID,
                amount=minor_amount,
                currency=normalize_shop_currency(currency),
                title=truncate_shop_title(title),
                description=truncate_shop_description(description),
                customerId=f"telegram:{int(user_id)}",
                comment=f"minishop-payment:{int(payment_db_id)}",
                period=period,
                firstPeriodAmount=first_period_amount,
            )
        except (TypeError, ValueError, OverflowError) as exc:
            logger.warning("Tribute Shop order rejected before API call: %s", exc)
            return False, {"message": "invalid_shop_order", "detail": str(exc)}

        http_session = await self._get_session()
        success, response_data = await post_json_request(
            http_session,
            f"{TRIBUTE_SHOP_API_BASE_URL}/shop/orders",
            body=order_request.to_api_payload(),
            headers={"Api-Key": self.config.API_KEY},
            log_prefix="Tribute Shop create order",
            is_success=lambda status, data: status == 200 and isinstance(data, dict),
        )
        if not success:
            return False, response_data
        try:
            response = TributeShopOrderResponse.model_validate(response_data)
        except ValidationError as exc:
            logger.error("Tribute Shop returned an invalid order response: %s", exc)
            return False, {"message": "invalid_shop_response"}
        response_mismatch: str | None = None
        if response.shop_id != order_request.shop_id:
            response_mismatch = "shop_id_mismatch"
        elif response.amount != order_request.amount:
            response_mismatch = "amount_mismatch"
        elif response.currency != order_request.currency:
            response_mismatch = "currency_mismatch"
        elif response.period != order_request.period:
            response_mismatch = "period_mismatch"
        elif response.status != "pending":
            response_mismatch = "status_mismatch"
        elif response.first_period_amount != order_request.first_period_amount:
            response_mismatch = "first_period_amount_mismatch"
        if response_mismatch is not None:
            logger.error(
                "Tribute Shop create-order response snapshot mismatch: %s",
                response_mismatch,
            )
            return False, {
                "message": "invalid_shop_response",
                "detail": response_mismatch,
            }
        return True, response.model_dump(mode="json", by_alias=True, exclude_none=True)

    async def _cancel_shop_order(self, order_uuid: str) -> bool:
        api_key = str(self.config.API_KEY or "")
        if not self.shop_enabled or not api_key:
            return False
        http_session = await self._get_session()
        success, response_data = await post_json_request(
            http_session,
            f"{TRIBUTE_SHOP_API_BASE_URL}/shop/orders/{order_uuid}/cancel",
            body={},
            headers={"Api-Key": api_key},
            log_prefix="Tribute Shop cancel conflicting recurrence",
            is_success=lambda status, data: status in {200, 400} and isinstance(data, dict),
        )
        if not success:
            return False
        try:
            response = TributeShopActionResponse.model_validate(response_data)
        except ValidationError:
            try:
                error = TributeShopErrorResponse.model_validate(response_data)
            except ValidationError:
                return False
            return error.error == "error_already_cancelled"
        if response.success:
            return True
        normalized_message = response.message.lower().replace("-", "_").replace(" ", "_")
        return normalized_message in {
            "already_cancelled",
            "order_already_cancelled",
            "recurring_order_already_cancelled",
        }

    async def _get_shop_order_transactions(
        self,
        order_uuid: str,
    ) -> TributeShopTransactionsResponse | None:
        if not self.shop_enabled or not self.config.API_KEY:
            return None
        http_session = await self._get_session()
        try:
            async with http_session.get(
                f"{TRIBUTE_SHOP_API_BASE_URL}/shop/orders/{order_uuid}/transactions",
                headers={"Api-Key": self.config.API_KEY},
            ) as response:
                response_text = await response.text()
                response_data = json.loads(response_text) if response_text else {}
                if response.status != 200:
                    logger.error(
                        "Tribute Shop transaction lookup failed (status=%s, body=%s).",
                        response.status,
                        response_data,
                    )
                    return None
        except Exception:
            logger.exception("Tribute Shop transaction lookup failed.")
            return None
        try:
            return TributeShopTransactionsResponse.model_validate(response_data)
        except ValidationError as exc:
            logger.error("Tribute Shop returned invalid transactions: %s", exc)
            return None

    async def _refund_shop_order_exact_sell(
        self,
        order_uuid: str,
        *,
        expected_amount: Decimal,
        expected_currency: str,
    ) -> str | None:
        api_key = str(self.config.API_KEY or "")
        if not self.shop_enabled or not api_key:
            return None
        transactions = await self._get_shop_order_transactions(order_uuid)
        if transactions is None:
            return None
        normalized_currency = normalize_shop_currency(expected_currency)
        matches = [
            transaction
            for transaction in transactions.transactions
            if transaction.type == "shop_order_sell"
            and transaction.amount == expected_amount
            and transaction.currency == normalized_currency
        ]
        if len(matches) != 1:
            logger.error(
                "Tribute Shop refund requires exactly one matching sell transaction "
                "(order=%s, matches=%s).",
                order_uuid,
                len(matches),
            )
            return None
        transaction = matches[0]
        if transaction.is_refunded:
            return "already_refunded"
        if not transaction.is_refundable:
            logger.error(
                "Tribute Shop sell transaction is not refundable (order=%s, tx=%s).",
                order_uuid,
                transaction.id,
            )
            return None

        http_session = await self._get_session()
        success, response_data = await post_json_request(
            http_session,
            f"{TRIBUTE_SHOP_API_BASE_URL}/shop/orders/{order_uuid}"
            f"/transactions/{transaction.id}/refund",
            body={},
            headers={"Api-Key": api_key},
            log_prefix="Tribute Shop refund exact sell",
            is_success=lambda status, data: status in {200, 400} and isinstance(data, dict),
        )
        if not success:
            return None
        try:
            error = TributeShopErrorResponse.model_validate(response_data)
        except ValidationError:
            pass
        else:
            return "already_refunded" if error.error == "error_already_refunded" else None
        try:
            response = TributeShopRefundResponse.model_validate(response_data)
        except ValidationError as exc:
            logger.error("Tribute Shop returned an invalid refund response: %s", exc)
            return None
        return "initiated" if response.success else None

    async def try_reuse_shop_order(self, payment: Any) -> str | None:
        if not self.shop_enabled:
            return None
        provider_id = str(getattr(payment, "provider_payment_id", "") or "").strip()
        payment_url = str(getattr(payment, "provider_payment_url", "") or "").strip()
        if not provider_id or not payment_url:
            return None
        return payment_url

    async def parse_payload(self, request: web.Request) -> ProviderWebhookPayload:
        content_length = request.content_length
        if content_length is not None and content_length > TRIBUTE_MAX_WEBHOOK_BYTES:
            raise web.HTTPRequestEntityTooLarge(
                max_size=TRIBUTE_MAX_WEBHOOK_BYTES,
                actual_size=content_length,
            )
        raw_body = await request.read()
        if len(raw_body) > TRIBUTE_MAX_WEBHOOK_BYTES:
            raise web.HTTPRequestEntityTooLarge(
                max_size=TRIBUTE_MAX_WEBHOOK_BYTES,
                actual_size=len(raw_body),
            )
        return ProviderWebhookPayload(
            raw_body=raw_body,
            signature=str(request.headers.get(TRIBUTE_SIGNATURE_HEADER, "") or "").strip(),
        )

    def verify_signature(self, payload: ProviderWebhookPayload) -> bool:
        api_key = str(self.config.API_KEY or "")
        signature = str(payload.signature or "").strip()
        if not api_key or len(signature) != 64:
            return False
        try:
            received = bytes.fromhex(signature)
        except ValueError:
            return False
        if len(received) != hashlib.sha256().digest_size:
            return False
        expected = hmac.new(
            api_key.encode("utf-8"),
            payload.raw_body,
            hashlib.sha256,
        ).digest()
        return hmac.compare_digest(expected, received)

    async def handle_verified_webhook(
        self,
        request: web.Request,
        payload: ProviderWebhookPayload,
    ) -> web.Response:
        try:
            raw_data = json.loads(payload.raw_body.decode("utf-8"))
            envelope = TributeWebhookEnvelope.model_validate(raw_data)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, TypeError):
            return web.json_response({"ok": False, "error": "invalid_payload"}, status=400)

        if envelope.name not in TRIBUTE_WEBHOOK_EVENTS:
            logger.info("Ignoring unsupported Tribute webhook event %s.", envelope.name)
            return web.json_response({"ok": True, "status": "ignored"})

        if envelope.name == "new_digital_product":
            try:
                product_payload = TributeDigitalProductPayload.model_validate(envelope.payload)
            except ValidationError:
                return web.json_response({"ok": False, "error": "invalid_payload"}, status=400)
            try:
                return await self._process_digital_product_purchase(product_payload)
            except Exception:
                logger.exception(
                    "Tribute Digital Product processing failed (purchase=%s, product=%s).",
                    product_payload.purchase_id,
                    product_payload.product_id,
                )
                return web.json_response(
                    {"ok": False, "error": "processing_error"},
                    status=500,
                )

        if envelope.name == "digital_product_refunded":
            try:
                refund_payload = TributeDigitalProductRefundPayload.model_validate(envelope.payload)
            except ValidationError:
                return web.json_response({"ok": False, "error": "invalid_payload"}, status=400)
            try:
                return await self._process_digital_product_refund(refund_payload)
            except Exception:
                logger.exception(
                    "Tribute Digital Product refund processing failed (purchase=%s, product=%s).",
                    refund_payload.purchase_id,
                    refund_payload.product_id,
                )
                return web.json_response(
                    {"ok": False, "error": "processing_error"},
                    status=500,
                )

        if envelope.name in TRIBUTE_SHOP_WEBHOOK_EVENTS:
            try:
                shop_payload = parse_tribute_shop_webhook_payload(
                    envelope.name,
                    envelope.payload,
                )
            except (TypeError, ValueError, ValidationError):
                return web.json_response({"ok": False, "error": "invalid_payload"}, status=400)
            try:
                return await self._process_shop_event(envelope, shop_payload)
            except Exception:
                logger.exception(
                    "Tribute Shop webhook processing failed (event=%s, order=%s).",
                    envelope.name,
                    shop_payload.uuid,
                )
                return web.json_response(
                    {"ok": False, "error": "processing_error"},
                    status=500,
                )

        try:
            subscription_payload = TributeSubscriptionPayload.model_validate(envelope.payload)
        except ValidationError:
            return web.json_response({"ok": False, "error": "invalid_payload"}, status=400)

        subscription_type = subscription_payload.type or "regular"
        if subscription_type not in TRIBUTE_SUBSCRIPTION_TYPES:
            logger.warning(
                "Ignoring Tribute event %s with unsupported subscription type %s.",
                envelope.name,
                subscription_type,
            )
            return web.json_response({"ok": True, "status": "ignored"})

        if subscription_payload.telegram_user_id is None:
            logger.warning(
                "Ignoring Tribute subscription %s without a Telegram identity.",
                subscription_payload.subscription_id,
            )
            return web.json_response(
                {"ok": True, "status": "ignored", "reason": "missing_telegram_identity"}
            )

        fingerprint = _event_fingerprint(envelope, subscription_payload)
        try:
            return await self._process_subscription_event(
                envelope,
                subscription_payload,
                fingerprint,
            )
        except Exception:
            logger.exception(
                "Tribute webhook processing failed (event=%s, subscription=%s, fingerprint=%s).",
                envelope.name,
                subscription_payload.subscription_id,
                fingerprint[:12],
            )
            return web.json_response({"ok": False, "error": "processing_error"}, status=500)


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    service = app_required(ctx.request, TRIBUTE_SERVICE_KEY, TributeService)
    if not service or not service.configured:
        return payment_unavailable()
    if await _has_active_tribute_recurrence(
        ctx.session,
        user_id=int(ctx.user_id),
        sale_mode=str(ctx.sale_mode),
    ):
        return payment_unavailable()
    if sale_mode_base(str(ctx.sale_mode)) == "subscription" and ctx.hwid_device_count is not None:
        return payment_unavailable()
    if ctx.promo_code_id is not None and (
        not service.shop_enabled or not _shop_context_supported(ctx.months, str(ctx.sale_mode))
    ):
        # Static Creator links cannot carry Minishop's quoted price or local
        # entitlement effects.
        return payment_unavailable()
    if (
        service.shop_enabled
        and sale_mode_base(str(ctx.sale_mode)) == "subscription"
        and (
            int(ctx.promo_bonus_days or 0) > 0
            or ctx.promo_duration_multiplier is not None
            or ctx.promo_traffic_multiplier is not None
        )
    ):
        # Tribute controls the recurring schedule and authoritative expiry.
        # Only a price-only first-cycle promotion can be represented safely.
        return payment_unavailable()
    if service.shop_enabled and _shop_context_supported(ctx.months, str(ctx.sale_mode)):
        return await run_webapp_payment(_SHOP_DESCRIPTOR, ctx)
    if ctx.hwid_device_count is not None:
        return payment_unavailable()
    binding = _binding_for_checkout(
        service.settings,
        sale_mode=str(ctx.sale_mode),
        months=ctx.months,
    )
    if binding is None:
        return payment_unavailable()
    return payment_link_response(payment_url=binding.link, payment_id=None)


router = Router(name="user_subscription_payments_tribute_router")


@router.callback_query(F.data.startswith("pay_tribute:"))
async def pay_tribute_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    tribute_service: TributeService,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n = i18n_data.get("i18n_instance")
    translator = make_translator(i18n, current_lang)
    if not i18n or not callback.message:
        await notify_callback_parse_error(callback, translator)
        return
    if (
        not tribute_service
        or not tribute_service.configured
        or not SPEC.is_available_to_user(
            settings,
            user_id=callback.from_user.id,
            require_configured=False,
        )
    ):
        await notify_service_unavailable(callback, translator)
        return
    parts = parse_payment_callback(callback.data or "")
    if parts is None:
        await notify_callback_parse_error(callback, translator)
        return
    if await _has_active_tribute_recurrence(
        session,
        user_id=int(callback.from_user.id),
        sale_mode=str(parts.sale_mode),
    ):
        await notify_service_unavailable(callback, translator)
        return
    if tribute_service.shop_enabled and _shop_context_supported(
        parts.months,
        parts.sale_mode,
    ):
        await run_callback_payment(
            _SHOP_DESCRIPTOR,
            callback,
            settings,
            i18n_data,
            tribute_service,
            session,
        )
        return
    quoted_parts, hwid_quote = await quote_hwid_callback_parts(
        session=session,
        user_id=callback.from_user.id,
        parts=parts,
        subscription_service=tribute_service.subscription_service,
        settings=settings,
    )
    if quoted_parts is None or hwid_quote:
        await notify_service_unavailable(callback, translator)
        return
    binding = _binding_for_checkout(
        settings,
        sale_mode=quoted_parts.sale_mode,
        months=quoted_parts.months,
    )
    if binding is None:
        await notify_service_unavailable(callback, translator)
        return
    await render_payment_link(
        callback,
        translator=translator,
        current_lang=current_lang,
        i18n=i18n,
        parts=PaymentCallbackParts(
            months=quoted_parts.months,
            price=quoted_parts.price,
            sale_mode=quoted_parts.sale_mode,
        ),
        payment_url=binding.link,
        log_prefix="tribute",
    )


async def tribute_webhook_route(request: web.Request) -> web.Response:
    service = app_required(request, TRIBUTE_SERVICE_KEY, TributeService)
    return await service.webhook_route(request)


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> str | None:
    return await run_reuse_webapp_payment(_SHOP_DESCRIPTOR, ctx, payment)


def create_service(ctx: ServiceFactoryContext) -> TributeService:
    bundle = ctx.config_for(TRIBUTE_SERVICE_KEY)
    config = (
        bundle.config if bundle and isinstance(bundle.config, TributeConfig) else TributeConfig()
    )
    return TributeService(
        bot=ctx.bot,
        settings=ctx.settings,
        config=config,
        i18n=ctx.i18n,
        async_session_factory=ctx.async_session_factory,
        subscription_service=ctx.subscription_service,
        referral_service=ctx.referral_service,
    )


_CONFIG_MANIFEST = (
    ProviderManifestField(
        "TRIBUTE_ENABLED",
        "bool",
        "Enabled",
        description=(
            "Enable Tribute payments and signed webhook processing. Configured Creator "
            "links remain available when Shop Orders are disabled or unsupported."
        ),
        subsection="Tribute",
        attr="ENABLED",
    ),
    ProviderManifestField(
        "TRIBUTE_API_KEY",
        "string",
        "API key",
        description=(
            "API key for Tribute Shop/Creator API requests and HMAC-SHA256 verification "
            "of the trbt-signature webhook header."
        ),
        subsection="Tribute",
        secret=True,
        attr="API_KEY",
    ),
    ProviderManifestField(
        "TRIBUTE_SHOP_ID",
        "int",
        "Tribute Shop ID",
        description=(
            "Positive numeric ID of the exact Tribute Shop used to create orders and "
            "validate every Shop webhook. Required when the Shop API is enabled."
        ),
        subsection="Tribute",
        min=1,
        attr="SHOP_ID",
    ),
    ProviderManifestField(
        "TRIBUTE_SHOP_ENABLED",
        "bool",
        "Use Tribute Shop API",
        description=(
            "Use dynamic Shop Orders with exact local quotes as the primary flow. "
            "Recurring periods are limited to 1/3/6/12 months; unsupported contexts "
            "may use configured Creator links. Requires the numeric Tribute Shop ID."
        ),
        subsection="Tribute",
        attr="SHOP_ENABLED",
    ),
)

_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="Tribute",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_TRIBUTE_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_TRIBUTE_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_TRIBUTE_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "Gem",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_TRIBUTE_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_TRIBUTE_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_TRIBUTE_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            "💎",
            "TELEGRAM_EMOJI",
        ),
    )
)


SPEC = PaymentProviderSpec(
    id=TRIBUTE_PROVIDER,
    provider_key=TRIBUTE_PROVIDER,
    label="Tribute",
    pending_status=TRIBUTE_PENDING_STATUS,
    enabled=lambda config: bool(getattr(config, "ENABLED", False)),
    service_key=TRIBUTE_SERVICE_KEY,
    callback_prefix="pay_tribute",
    webapp_label="Tribute",
    webapp_labels={"ru": "Tribute", "en": "Tribute"},
    webapp_icon="Gem",
    logo_url="/provider-logos/tribute.png",
    telegram_labels={"ru": "Tribute", "en": "Tribute"},
    telegram_emoji="💎",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/tribute",
    webhook_route=tribute_webhook_route,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=TributeConfig,
    presentation_class=TributePresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    price_managed_externally=False,
    supported_currencies=("RUB", "USD", "EUR"),
    payment_amount_resolver=tribute_shop_amount_supported,
    payment_minimum_resolver=tribute_shop_amount_metadata,
    payment_context_resolver=tribute_supports_checkout,
    external_price_context_resolver=tribute_price_managed_externally,
    checkout_promo_resolver=tribute_checkout_promo_supported,
    info_url="https://wiki.tribute.tg/for-shops/api",
)


async def _create_shop_payment(
    service: TributeService,
    req: CreatePaymentRequest,
) -> CreateResult:
    regular_amount: float | None = None
    if sale_mode_base(str(req.sale_mode)) == "subscription":
        checkout_base_amount = getattr(req.payment, "checkout_base_amount", None)
        regular_amount = (
            float(checkout_base_amount) if checkout_base_amount is not None else float(req.amount)
        )
    return await service.create_shop_order(
        payment_db_id=int(req.payment.payment_id),
        user_id=int(req.user_id),
        amount=float(req.amount),
        regular_amount=regular_amount,
        currency=str(req.currency),
        title=str(req.description),
        description=str(req.description),
        months=float(req.months),
        sale_mode=str(req.sale_mode),
    )


async def _reuse_shop_payment(service: TributeService, payment: Any) -> str | None:
    return await service.try_reuse_shop_order(payment)


_SHOP_DESCRIPTOR = LinkPaymentDescriptor(
    spec=SPEC,
    provider_key=TRIBUTE_PROVIDER,
    pending_status=TRIBUTE_PENDING_STATUS,
    display_name="Tribute Shop",
    log_prefix="tribute",
    service_app_key=TRIBUTE_SERVICE_KEY,
    service_type=TributeService,
    create=_create_shop_payment,
    reuse=_reuse_shop_payment,
    extract_url=lambda data: first_value(data, "webappPaymentUrl", "paymentUrl"),
    extract_provider_id=lambda data: first_value(data, "uuid"),
    callback_reuse_enabled=True,
)
