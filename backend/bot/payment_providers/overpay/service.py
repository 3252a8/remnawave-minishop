from __future__ import annotations

import base64
import binascii
import json
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from aiogram import Bot, F, Router, types
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from db.dal import payment_dal, user_billing_dal

from ..base import (
    PaymentProviderSpec,
    ServiceFactoryContext,
    WebAppPaymentContext,
    normalize_payment_currency_code,
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
    lookup_payment_by_order_or_provider_id,
    notify_user_payment_failed,
    payment_units_for_activation,
    post_json_request,
    run_callback_payment,
    run_reuse_webapp_payment,
    run_webapp_payment,
    safe_callback_answer,
)
from ..shared.app_context import app_required
from .config import (
    OVERPAY_SUPPORTED_CURRENCIES,
    OverpayConfig,
    OverpayPresentation,
    overpay_amount_to_minor_units,
)
from .manifest import _CONFIG_MANIFEST, _PRESENTATION_MANIFEST

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService
else:
    ReferralService = object
    SubscriptionService = object

_LOG = "overpay"

# Overpay / BeGateway transaction and checkout status strings.
_SUCCESS_STATUSES = {"successful", "success"}
_FAILED_STATUSES = {"failed", "declined", "error", "expired", "canceled", "cancelled"}
_PENDING_STATUSES = {"incomplete", "pending", "processing"}


def _nested(source: Mapping[str, Any] | None, *path: str) -> Any:
    current: Any = source
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _checkout_success(status: int, data: Any) -> bool:
    if status not in (200, 201):
        return False
    return bool(_nested(data, "checkout", "redirect_url"))


def _transaction_response_ok(status: int, data: Any) -> bool:
    return status in (200, 201) and isinstance((data or {}).get("transaction"), dict)


class OverpayService(HttpClientMixin):
    """Client for the Overpay checkout (payment token) and gateway APIs.

    Outgoing requests authenticate with HTTP Basic auth: the Shop ID is the
    username and the Secret Key is the password. The hosted checkout returns a
    ``redirect_url`` the user is sent to. Notifications arrive as JSON POSTs
    authenticated with the same HTTP Basic credentials; saved-card auto-renew
    charges reuse the ``credit_card.token`` returned for recurring contracts.
    """

    def __init__(
        self,
        *,
        bot: Bot,
        settings: Settings,
        config: OverpayConfig,
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
                "OverpayService initialized but not fully configured. Payments disabled."
            )

    @property
    def configured(self) -> bool:
        return bool(provider_runtime_enabled(self.config) and self.shop_id and self.secret_key)

    @property
    def checkout_base_url(self) -> str:
        return (self.config.CHECKOUT_URL or "https://checkout.overpay.io").rstrip("/")

    @property
    def gateway_base_url(self) -> str:
        return (self.config.GATEWAY_URL or "https://gateway.overpay.io").rstrip("/")

    @property
    def shop_id(self) -> str:
        return (self.config.SHOP_ID or "").strip()

    @property
    def secret_key(self) -> str:
        return (self.config.SECRET_KEY or "").strip()

    @property
    def return_url(self) -> str:
        return self.config.RETURN_URL or f"https://t.me/{self._default_return_url}"

    @property
    def recurring_active(self) -> bool:
        """Saved-token charges are available only when explicitly enabled."""
        return bool(self.configured and self.config.RECURRING_ENABLED)

    def _basic_auth_token(self) -> str:
        return base64.b64encode(f"{self.shop_id}:{self.secret_key}".encode()).decode("ascii")

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Basic {self._basic_auth_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-API-Version": "2",
        }

    def _notification_url(self) -> str | None:
        return self.config.full_webhook_url(getattr(self.settings, "WEBHOOK_BASE_URL", None))

    def _checkout_settings(self, language: str | None) -> dict[str, Any]:
        settings_block: dict[str, Any] = {}
        notification_url = self._notification_url()
        if notification_url:
            settings_block["notification_url"] = notification_url
        if self.config.SUCCESS_URL or self.return_url:
            settings_block["success_url"] = self.config.SUCCESS_URL or self.return_url
        if self.config.DECLINE_URL:
            settings_block["decline_url"] = self.config.DECLINE_URL
        if self.config.FAIL_URL:
            settings_block["fail_url"] = self.config.FAIL_URL
        if self.config.RETURN_URL or self.return_url:
            settings_block["return_url"] = self.config.RETURN_URL or self.return_url
        resolved_language = self.config.LANGUAGE or (
            str(language).strip().lower().split("-", 1)[0].split("_", 1)[0] if language else None
        )
        if resolved_language:
            settings_block["language"] = resolved_language
        return settings_block

    async def create_checkout(
        self,
        *,
        payment_db_id: int,
        amount: float,
        currency: str | None,
        description: str,
        language: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        if not self.configured:
            logger.error("OverpayService is not configured. Cannot create checkout.")
            return False, {"message": "service_not_configured"}

        currency_code = normalize_payment_currency_code(
            currency or self.settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
        )
        if currency_code not in OVERPAY_SUPPORTED_CURRENCIES:
            return False, {
                "message": "unsupported_currency",
                "currency": currency_code,
                "supported_currencies": list(OVERPAY_SUPPORTED_CURRENCIES),
            }
        try:
            minor_amount = overpay_amount_to_minor_units(amount, currency_code)
        except ValueError as exc:
            return False, {"message": str(exc)}

        checkout: dict[str, Any] = {
            "transaction_type": "payment",
            "test": bool(self.config.TEST_MODE),
            "order": {
                "amount": minor_amount,
                "currency": currency_code,
                "description": (description or "Payment")[:255],
                "tracking_id": str(payment_db_id),
            },
        }
        settings_block = self._checkout_settings(language)
        if settings_block:
            checkout["settings"] = settings_block
        if self.recurring_active:
            checkout["additional_data"] = {"contract": ["recurring"]}

        session = await self._get_session()
        success, data = await post_json_request(
            session,
            f"{self.checkout_base_url}/ctp/api/checkouts",
            body={"checkout": checkout},
            headers=self._auth_headers(),
            log_prefix="Overpay create_checkout",
            is_success=_checkout_success,
        )
        if not success:
            return False, data
        inner = data.get("checkout")
        return True, inner if isinstance(inner, dict) else data

    async def charge_token(
        self,
        *,
        payment_db_id: int,
        token: str,
        amount: float,
        currency: str | None,
        description: str,
        customer_email: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        if not self.configured:
            logger.error("OverpayService is not configured. Cannot charge token.")
            return False, {"message": "service_not_configured"}

        currency_code = normalize_payment_currency_code(
            currency or self.settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
        )
        if currency_code not in OVERPAY_SUPPORTED_CURRENCIES:
            return False, {
                "message": "unsupported_currency",
                "currency": currency_code,
                "supported_currencies": list(OVERPAY_SUPPORTED_CURRENCIES),
            }
        try:
            minor_amount = overpay_amount_to_minor_units(amount, currency_code)
        except ValueError as exc:
            return False, {"message": str(exc)}

        request_body: dict[str, Any] = {
            "amount": minor_amount,
            "currency": currency_code,
            "description": (description or "Payment")[:255],
            "tracking_id": str(payment_db_id),
            "test": bool(self.config.TEST_MODE),
            "credit_card": {"token": token},
            "additional_data": {"contract": ["recurring"]},
        }
        notification_url = self._notification_url()
        if notification_url:
            request_body["notification_url"] = notification_url
        if customer_email:
            request_body["customer"] = {"email": customer_email}

        session = await self._get_session()
        success, data = await post_json_request(
            session,
            f"{self.gateway_base_url}/transactions/payments",
            body={"request": request_body},
            headers=self._auth_headers(),
            log_prefix="Overpay token charge",
            is_success=_transaction_response_ok,
        )
        if not success:
            return False, data
        transaction = data.get("transaction")
        return True, transaction if isinstance(transaction, dict) else data

    async def charge_saved_payment_method(
        self, context: RecurringChargeContext
    ) -> RecurringChargeResult:
        """Charge a stored Overpay card token for auto-renew."""
        if not self.recurring_active:
            return RecurringChargeResult.failed("recurring_inactive")
        token = str(getattr(context.saved_method, "provider_payment_method_id", "") or "").strip()
        if not token:
            return RecurringChargeResult.failed("missing_saved_method")

        payment_payload = build_payment_record_payload(
            user_id=context.user_id,
            amount=float(context.amount),
            currency=context.currency,
            status="pending_overpay",
            description=context.description,
            months=context.months,
            provider="overpay",
            sale_mode=context.sale_mode,
            hwid_quote=dict(context.hwid_quote or {}) or None,
        )
        try:
            payment = await payment_dal.create_payment_record(context.session, payment_payload)
        except Exception as exc:
            logger.exception("Overpay auto-renew failed to create local payment record")
            return RecurringChargeResult.failed(str(exc))

        try:
            success, transaction = await self.charge_token(
                payment_db_id=payment.payment_id,
                token=token,
                amount=float(context.amount),
                currency=context.currency,
                description=context.description,
            )
        except Exception as exc:
            logger.exception("Overpay auto-renew token charge failed before API response")
            await self._mark_payment_failed_creation(context.session, payment.payment_id)
            return RecurringChargeResult.failed(str(exc))

        provider_payment_id = first_value(transaction, "uid", "id")
        status = str(first_value(transaction, "status") or "").lower() or None
        charge_declined = status in _FAILED_STATUSES
        if provider_payment_id:
            try:
                await payment_dal.update_provider_payment_and_status(
                    context.session,
                    payment.payment_id,
                    str(provider_payment_id),
                    "pending_overpay",
                )
            except Exception:
                logger.exception(
                    "Overpay auto-renew failed to store provider payment id %s",
                    provider_payment_id,
                )
        if not success or charge_declined:
            await self._mark_payment_failed_creation(context.session, payment.payment_id)
            message = first_value(transaction, "message") or str(transaction)
            return RecurringChargeResult.failed(message)
        return RecurringChargeResult.ok(
            provider_payment_id=str(provider_payment_id) if provider_payment_id else None,
            status=status,
        )

    async def _mark_payment_failed_creation(self, session: Any, payment_db_id: int) -> None:
        try:
            await payment_dal.update_payment_status_by_db_id(
                session,
                payment_db_id,
                "failed_creation",
            )
        except Exception:
            logger.exception(
                "Overpay auto-renew failed to mark payment %s as failed_creation",
                payment_db_id,
            )

    async def try_reuse_pending_payment(self, payment: Any) -> str | None:
        """Return the existing checkout URL when the local payment is still pending.

        A paid checkout would already have flipped the payment to ``succeeded``
        via the webhook (so it would not be selected as a reusable pending
        record). Reusing the stored link avoids spawning a duplicate checkout on
        re-clicks.
        """
        payment_url = str(getattr(payment, "provider_payment_url", None) or "").strip()
        return payment_url or None

    def verify_webhook_auth(self, request: web.Request) -> bool:
        """Verify the HTTP Basic credentials Overpay sends with every webhook."""
        header = str(request.headers.get("Authorization") or "").strip()
        scheme, _, value = header.partition(" ")
        if scheme.lower() != "basic" or not value.strip():
            logger.warning("Overpay webhook: missing or non-Basic Authorization header.")
            return False
        if not self.secret_key:
            logger.error("Overpay webhook: no secret key configured.")
            return False
        try:
            decoded = base64.b64decode(value.strip(), validate=True).decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            logger.warning("Overpay webhook: malformed Basic Authorization header.")
            return False
        expected = f"{self.shop_id}:{self.secret_key}"
        return constant_time_compare(decoded, expected)

    def _amount_matches_payment(self, webhook_amount: Any, payment: Any) -> bool:
        if webhook_amount is None or str(webhook_amount).strip() == "":
            return False
        try:
            expected_minor = overpay_amount_to_minor_units(payment.amount, payment.currency)
        except ValueError:
            return False
        try:
            received_minor = int(str(webhook_amount).strip())
        except (TypeError, ValueError):
            return False
        return received_minor >= expected_minor

    def _currency_matches_payment(self, webhook_currency: Any, payment: Any) -> bool:
        if webhook_currency is None or str(webhook_currency).strip() == "":
            return False
        expected_currency = normalize_payment_currency_code(payment.currency, default="")
        received_currency = normalize_payment_currency_code(webhook_currency, default="")
        return bool(expected_currency and expected_currency == received_currency)

    async def _persist_recurring_payment_method(
        self,
        session: AsyncSession,
        *,
        payment: Any,
        credit_card: Mapping[str, Any] | None,
    ) -> None:
        if not self.recurring_active or not credit_card:
            return
        token = str(credit_card.get("token") or "").strip()
        if not token:
            return
        user_id = getattr(payment, "user_id", None)
        if user_id is None:
            return
        card_last4 = first_value(credit_card, "last_4", "last_4d", "last4")
        card_network = first_value(credit_card, "brand", "stamp") or "Card"
        try:
            await user_billing_dal.upsert_user_payment_method(
                session,
                user_id=int(user_id),
                provider_payment_method_id=token,
                provider="overpay",
                card_last4=card_last4,
                card_network=card_network,
                set_default=True,
            )
        except Exception:
            logger.exception(
                "Overpay webhook: failed to persist saved payment token for user %s",
                user_id,
            )

    async def _parse_webhook_payload(self, request: web.Request) -> dict[str, Any]:
        raw_body = await request.read()
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.Response(status=503, text="overpay_disabled")

        trusted = self.config.trusted_ips_list
        ip_check = check_webhook_source_ip(
            request,
            trusted_ips=trusted,
            trusted_proxies=self.settings.trusted_proxies,
            allow_empty=True,
        )
        if not ip_check.allowed:
            logger.warning(
                "Overpay webhook denied from unauthorized IP source "
                "(client_ip=%s remote=%s x_forwarded_for=%s).",
                ip_check.client_ip,
                request.remote,
                request.headers.get("X-Forwarded-For"),
            )
            return web.Response(status=403, text="forbidden")

        if self.config.VERIFY_WEBHOOK_SIGNATURE and not self.verify_webhook_auth(request):
            logger.error("Overpay webhook: invalid authentication.")
            return web.Response(status=403, text="invalid_auth")

        payload = await self._parse_webhook_payload(request)
        inner = payload.get("transaction") or payload.get("checkout") or payload
        if not isinstance(inner, dict):
            inner = payload

        order_raw = inner.get("order")
        order: Mapping[str, Any] = order_raw if isinstance(order_raw, Mapping) else {}
        tracking_id = first_value(inner, "tracking_id") or first_value(order, "tracking_id")
        provider_payment_id = first_value(inner, "uid", "id")
        status = (
            str(
                first_value(inner, "status")
                or first_value(order, "status")
                or _nested(inner, "gateway_response", "payment", "status")
                or ""
            )
            .strip()
            .lower()
        )
        webhook_amount = inner.get("amount")
        if webhook_amount is None:
            webhook_amount = order.get("amount")
        webhook_currency = inner.get("currency")
        if webhook_currency is None:
            webhook_currency = order.get("currency")
        credit_card = inner.get("credit_card") or inner.get("card")

        if not tracking_id and not provider_payment_id:
            logger.error("Overpay webhook: missing identifiers: %s", payload)
            return web.Response(status=400, text="missing_fields")
        if not status:
            logger.warning("Overpay webhook: missing status for tracking_id=%s", tracking_id)
            return web.Response(text="status_ignored")

        async with self.async_session_factory() as session:
            payment = await lookup_payment_by_order_or_provider_id(
                session,
                order_id_raw=tracking_id,
                provider_payment_id=provider_payment_id,
            )
            if not payment:
                logger.error(
                    "Overpay webhook: payment not found (tracking_id=%s, provider_id=%s)",
                    tracking_id,
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
                    logger.info(
                        "Overpay webhook: payment %s already succeeded.", payment.payment_id
                    )
                    return web.Response(text="OK")

                if not self._amount_matches_payment(webhook_amount, payment):
                    logger.error(
                        "Overpay webhook: amount mismatch for payment %s "
                        "(expected=%s, received=%s)",
                        payment.payment_id,
                        payment.amount,
                        webhook_amount,
                    )
                    return web.Response(status=400, text="amount_mismatch")

                if not self._currency_matches_payment(webhook_currency, payment):
                    logger.error(
                        "Overpay webhook: currency mismatch for payment %s "
                        "(expected=%s, received=%s)",
                        payment.payment_id,
                        payment.currency,
                        webhook_currency,
                    )
                    return web.Response(status=400, text="currency_mismatch")

                try:
                    payment = await payment_dal.claim_payment_finalization(
                        session,
                        payment.payment_id,
                        provider_payment_id=resolved_provider_id,
                    )
                    if payment is None:
                        return web.Response(text="OK")
                    await self._persist_recurring_payment_method(
                        session,
                        payment=payment,
                        credit_card=credit_card if isinstance(credit_card, Mapping) else None,
                    )
                except Exception:
                    await session.rollback()
                    logger.exception(
                        "Overpay webhook: failed to mark payment %s as succeeded.",
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
                        provider_subscription="overpay",
                        provider_notification="overpay",
                        db_user=payment.user,
                        log_prefix="Overpay webhook",
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
                        "Overpay webhook: failed to mark payment %s as failed.",
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
                        "pending_overpay",
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logger.exception(
                        "Overpay webhook: failed to update pending status for %s.",
                        resolved_provider_id,
                    )
                return web.Response(text="OK")

            logger.warning(
                "Overpay webhook: unhandled status '%s' for payment %s",
                status,
                resolved_provider_id,
            )
            return web.Response(text="status_ignored")


async def overpay_webhook_route(request: web.Request) -> web.Response:
    service: OverpayService = app_required(request, "overpay_service", OverpayService)
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_overpay_router")


@router.callback_query(F.data.startswith("pay_overpay:"))
async def pay_overpay_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    overpay_service: OverpayService,
    session: AsyncSession,
) -> None:
    await run_callback_payment(
        _DESCRIPTOR,
        callback,
        settings,
        i18n_data,
        overpay_service,
        session,
    )


def create_service(ctx: ServiceFactoryContext) -> OverpayService:
    bundle = ctx.config_for("overpay_service")
    config = (
        bundle.config if bundle and isinstance(bundle.config, OverpayConfig) else OverpayConfig()
    )
    return OverpayService(
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
    service: OverpayService,
    request: CreatePaymentRequest,
) -> tuple[bool, dict]:
    return await service.create_checkout(
        payment_db_id=request.payment.payment_id,
        amount=request.amount,
        currency=request.currency,
        description=request.description,
        language=request.language,
    )


async def _reuse_payment(service: OverpayService, payment: Any) -> str | None:
    return await service.try_reuse_pending_payment(payment)


def _extract_payment_url(response_data: dict) -> str | None:
    return first_value(response_data, "redirect_url")


def _extract_provider_id(response_data: dict) -> str | None:
    return first_value(response_data, "token")


SPEC = PaymentProviderSpec(
    id="overpay",
    provider_key="overpay",
    label="Overpay",
    webapp_label="Overpay",
    webapp_labels={"ru": "Overpay", "en": "Overpay"},
    webapp_icon="CreditCard",
    logo_url="/provider-logos/overpay.png",
    telegram_labels={"ru": "Overpay", "en": "Overpay"},
    telegram_emoji="💳",
    pending_status="pending_overpay",
    enabled=lambda config: bool(getattr(config, "ENABLED", False)),
    service_key="overpay_service",
    callback_prefix="pay_overpay",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/overpay",
    webhook_route=overpay_webhook_route,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=OverpayConfig,
    presentation_class=OverpayPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supports_recurring=True,
    supported_currencies=OVERPAY_SUPPORTED_CURRENCIES,
    currency_support_note=(
        "Overpay checkouts accept USD, EUR, RUB, GBP and other currencies "
        "depending on your shop configuration."
    ),
    info_url="https://overpay.io/",
    currency_support_url="https://docs.overpay.io/en/",
)

_DESCRIPTOR: LinkPaymentDescriptor[OverpayService] = LinkPaymentDescriptor(
    spec=SPEC,
    provider_key="overpay",
    pending_status="pending_overpay",
    display_name="Overpay",
    log_prefix=_LOG,
    service_app_key="overpay_service",
    service_type=OverpayService,
    create=_create_payment,
    reuse=_reuse_payment,
    extract_url=_extract_payment_url,
    extract_provider_id=_extract_provider_id,
    callback_before_create=safe_callback_answer,
    callback_reuse_answer=True,
)
