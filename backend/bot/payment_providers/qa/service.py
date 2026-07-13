from __future__ import annotations

import hashlib
import hmac
import json
import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from aiohttp import web
from pydantic_settings import SettingsConfigDict

from db.dal import payment_dal

from ..base import (
    BaseProviderService,
    PaymentProviderSpec,
    ProviderEnvConfig,
    ProviderWebhookPayload,
    ServiceFactoryContext,
    WebAppPaymentContext,
)
from ..shared import (
    create_webapp_payment_record,
    payment_amount_and_currency_match,
    payment_link_response,
    payment_unavailable,
    payment_units_for_activation,
    sale_mode_is_traffic,
)
from ..shared.app_context import app_required
from ..shared.success import (
    PaymentSuccessRequest,
    finalize_successful_payment,
)
from ..shared.webhooks import notify_user_payment_failed

logger = logging.getLogger(__name__)

QA_PROVIDER = "qa"
QA_SERVICE_KEY = "qa_service"
QA_PENDING_STATUS = "pending_qa"
QA_RUNTIME_MODES = {"dev", "development", "local", "test", "testing"}
QA_SIGNATURE_HEADER = "X-QA-Payment-Signature"


class QaPaymentConfig(ProviderEnvConfig):
    ENABLED: bool = False
    SECRET: str = ""

    model_config = SettingsConfigDict(
        env_prefix="QA_PAYMENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


def _runtime_allows_qa(settings: Any) -> bool:
    runtime = str(settings.APP_RUNTIME_MODE or "production")
    return runtime.strip().lower() in QA_RUNTIME_MODES


def _qa_enabled(source: Any) -> bool:
    return bool(getattr(source, "QA_PAYMENT_ENABLED", getattr(source, "ENABLED", False)))


def _qa_admin_only_enabled(source: Any) -> bool:
    return bool(
        getattr(
            source,
            "QA_PAYMENT_ADMIN_ONLY_ENABLED",
            getattr(source, "ADMIN_ONLY_ENABLED", False),
        )
    )


def _public_payment_url(settings: Any, payment_id: int) -> str:
    for candidate in (
        settings.SUBSCRIPTION_MINI_APP_URL,
        settings.WEBHOOK_BASE_URL,
    ):
        base = str(candidate or "").strip()
        if base:
            return f"{base.rstrip('/')}/?qa_payment_id={payment_id}"
    return f"http://127.0.0.1:8082/?qa_payment_id={payment_id}"


def _json_mapping(data: Any) -> Mapping[str, Any]:
    return data if isinstance(data, Mapping) else {}


def _int_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


class QaPaymentService(BaseProviderService):
    provider_key = QA_PROVIDER
    disabled_response_text = "QA payment provider is disabled"

    def __init__(
        self,
        *,
        settings: Any,
        bot: Any,
        async_session_factory: Any,
        i18n: Any,
        subscription_service: Any,
        referral_service: Any,
        config: QaPaymentConfig,
    ) -> None:
        self.settings = settings
        self.bot = bot
        self.async_session_factory = async_session_factory
        self.i18n = i18n
        self.subscription_service = subscription_service
        self.referral_service = referral_service
        self.config = config

    @property
    def configured(self) -> bool:
        return bool(
            _runtime_allows_qa(self.settings)
            and (self.config.ENABLED or self.config.ADMIN_ONLY_ENABLED)
            and str(self.config.SECRET or "").strip()
        )

    async def parse_payload(self, request: web.Request) -> ProviderWebhookPayload:
        raw_body = await request.read()
        signature = str(request.headers.get(QA_SIGNATURE_HEADER, "") or "")
        try:
            data = json.loads(raw_body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = {"_invalid_json": True}
        return ProviderWebhookPayload(raw_body=raw_body, signature=signature, data=data)

    def verify_signature(self, payload: ProviderWebhookPayload) -> bool:
        secret = str(self.config.SECRET or "").strip()
        signature = str(payload.signature or "").strip()
        if signature.startswith("sha256="):
            signature = signature.split("=", 1)[1]
        if not secret or not signature:
            return False
        expected = hmac.new(secret.encode("utf-8"), payload.raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def handle_verified_webhook(
        self,
        request: web.Request,
        payload: ProviderWebhookPayload,
    ) -> web.Response:
        data = _json_mapping(payload.data)
        if data.get("_invalid_json"):
            return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

        payment_id = _int_value(data.get("payment_id") or data.get("order_id"))
        if payment_id is None:
            return web.json_response({"ok": False, "error": "missing_payment_id"}, status=400)

        provider_payment_id = str(data.get("provider_payment_id") or f"qa:{payment_id}").strip()
        status = str(data.get("status") or "succeeded").strip().lower()

        async with self.async_session_factory() as session:
            payment = await payment_dal.get_payment_by_db_id(session, payment_id)
            if payment is None:
                return web.json_response({"ok": False, "error": "payment_not_found"}, status=404)
            if str(payment.provider or "").strip().lower() != QA_PROVIDER:
                return web.json_response({"ok": False, "error": "provider_mismatch"}, status=400)

            if status in {"failed", "fail", "declined", "canceled", "cancelled"}:
                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        provider_payment_id,
                        "failed",
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logger.exception(
                        "QA payment webhook failed to mark payment %s failed.", payment_id
                    )
                    return web.json_response({"ok": False, "error": "processing_error"}, status=500)
                await notify_user_payment_failed(
                    bot=self.bot,
                    settings=self.settings,
                    i18n=self.i18n,
                    session=session,
                    payment=payment,
                )
                return web.json_response({"ok": True, "status": "failed"})

            if status not in {"succeeded", "success", "paid"}:
                return web.json_response({"ok": False, "error": "unsupported_status"}, status=400)

            if str(payment.status or "").strip().lower() == "succeeded":
                return web.json_response({"ok": True, "status": "succeeded", "duplicate": True})

            amount = data.get("amount")
            currency = data.get("currency")
            if not payment_amount_and_currency_match(
                expected_amount=payment.amount,
                expected_currency=payment.currency,
                received_amount=amount,
                received_currency=currency,
                places=None,
            ):
                logger.warning(
                    "QA payment webhook: amount or currency mismatch for payment %s "
                    "(expected=%s %s, got=%s %s)",
                    payment.payment_id,
                    payment.amount,
                    payment.currency,
                    amount,
                    currency,
                )
                return web.json_response({"ok": False, "error": "amount_mismatch"}, status=400)

            try:
                claimed_payment = await payment_dal.claim_payment_finalization(
                    session,
                    payment.payment_id,
                    provider_payment_id=provider_payment_id,
                )
            except Exception:
                await session.rollback()
                logger.exception(
                    "QA payment webhook failed to mark payment %s pending.", payment_id
                )
                return web.json_response({"ok": False, "error": "processing_error"}, status=500)

            if claimed_payment is None:
                return web.json_response({"ok": True, "status": "succeeded", "duplicate": True})
            payment = claimed_payment

            sale_mode = payment.sale_mode or "subscription"
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
                    user_id=int(payment.user_id),
                    amount=float(payment.amount),
                    currency=str(payment.currency or "RUB"),
                    sale_mode=sale_mode,
                    months=payment_units,
                    traffic_amount=float(payment_units)
                    if sale_mode_is_traffic(sale_mode)
                    else None,
                    provider_subscription=QA_PROVIDER,
                    provider_notification=QA_PROVIDER,
                    db_user=payment.user,
                    log_prefix="QA payment webhook",
                    skip_keyboard=True,
                    skip_user_notification=True,
                )
            )
            if outcome is None:
                return web.json_response({"ok": False, "error": "activation_failed"}, status=500)

            final_end_date = outcome.final_end_date
            final_end_date_text = (
                final_end_date.isoformat() if isinstance(final_end_date, datetime) else None
            )
            return web.json_response(
                {
                    "ok": True,
                    "payment_id": payment.payment_id,
                    "status": "succeeded",
                    "final_end_date": final_end_date_text,
                }
            )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    service = app_required(ctx.request, QA_SERVICE_KEY, QaPaymentService)
    if not service or not service.configured:
        return payment_unavailable()

    try:
        payment = await create_webapp_payment_record(
            ctx,
            amount=ctx.price,
            currency=(ctx.currency or "RUB").upper(),
            status=QA_PENDING_STATUS,
            provider=QA_PROVIDER,
        )
        provider_payment_id = f"qa:{payment.payment_id}"
        payment_url = _public_payment_url(service.settings, payment.payment_id)
        await payment_dal.update_provider_payment_and_status(
            ctx.session,
            payment.payment_id,
            provider_payment_id,
            QA_PENDING_STATUS,
            provider_payment_url=payment_url,
        )
        await ctx.session.commit()
        return payment_link_response(payment_url=payment_url, payment_id=payment.payment_id)
    except Exception:
        await ctx.session.rollback()
        logger.exception("QA WebApp payment failed")
        return web.json_response(
            {"ok": False, "error": "payment_failed", "message": "Failed to create payment"},
            status=502,
        )


async def qa_payment_webhook_route(request: web.Request) -> web.Response:
    service = app_required(request, QA_SERVICE_KEY, QaPaymentService)
    return await service.webhook_route(request)


def create_service(ctx: ServiceFactoryContext) -> QaPaymentService:
    config = QaPaymentConfig(
        ENABLED=bool(getattr(ctx.settings, "QA_PAYMENT_ENABLED", False)),
        ADMIN_ONLY_ENABLED=bool(getattr(ctx.settings, "QA_PAYMENT_ADMIN_ONLY_ENABLED", False)),
        SECRET=str(getattr(ctx.settings, "QA_PAYMENT_SECRET", "") or ""),
    )
    return QaPaymentService(
        settings=ctx.settings,
        bot=ctx.bot,
        async_session_factory=ctx.async_session_factory,
        i18n=ctx.i18n,
        subscription_service=ctx.subscription_service,
        referral_service=ctx.referral_service,
        config=config,
    )


SPEC = PaymentProviderSpec(
    id=QA_PROVIDER,
    provider_key=QA_PROVIDER,
    label="QA Payment",
    pending_status=QA_PENDING_STATUS,
    enabled=_qa_enabled,
    admin_only_enabled=_qa_admin_only_enabled,
    service_key=QA_SERVICE_KEY,
    webapp_label="QA Payment",
    webapp_labels={"ru": "QA Payment", "en": "QA Payment"},
    webapp_icon="BadgeCheck",
    telegram_labels={"ru": "QA Payment", "en": "QA Payment"},
    telegram_emoji="QA",
    create_service=create_service,
    webhook_path=lambda source: "/webhook/qa-payment",
    webhook_route=qa_payment_webhook_route,
    create_webapp_payment=create_webapp_payment,
    enabled_manifest_key="QA_PAYMENT_ENABLED",
    admin_only_manifest_key="QA_PAYMENT_ADMIN_ONLY_ENABLED",
    supported_currencies=("RUB",),
)
