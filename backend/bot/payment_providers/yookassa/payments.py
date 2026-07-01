import logging
from typing import Any, Optional

from aiohttp import web

from db.dal import payment_dal

from ..base import (
    WebAppPaymentContext,
)
from ..shared import (
    create_webapp_payment_record,
    format_number_for_payload,
    mark_payment_failed_creation,
    payment_failed,
    payment_link_response,
    payment_record_amounts,
    payment_unavailable,
)
from ..shared.app_context import app_optional, app_required
from .service import YooKassaService
from .shared import _metadata_iso

logger = logging.getLogger(__name__)


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    service: YooKassaService = app_required(ctx.request, "yookassa_service", YooKassaService)
    if not service or not service.configured:
        return payment_unavailable()
    currency = (ctx.currency or "RUB").upper()

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
            currency=currency,
            status="pending_yookassa",
            provider="yookassa",
        )
        metadata = {
            "user_id": str(ctx.user_id),
            "subscription_months": str(
                int(float(ctx.months))
                if not amounts.traffic_sale and not amounts.hwid_devices_sale
                else 0
            ),
            "payment_db_id": str(payment.payment_id),
            "sale_mode": ctx.sale_mode,
            "source": "webapp",
        }
        if amounts.traffic_sale:
            metadata["traffic_gb"] = format_number_for_payload(ctx.traffic_gb or ctx.months)
        if amounts.purchased_hwid_devices:
            metadata["hwid_devices"] = str(int(amounts.purchased_hwid_devices))
            hwid_metadata = {
                "hwid_valid_from": _metadata_iso(ctx.hwid_valid_from),
                "hwid_valid_until": _metadata_iso(ctx.hwid_valid_until),
                "hwid_pricing_period_months": ctx.hwid_pricing_period_months,
                "hwid_proration_ratio": ctx.hwid_proration_ratio,
                "hwid_full_price": ctx.hwid_full_price,
            }
            metadata.update(
                {key: str(value) for key, value in hwid_metadata.items() if value is not None}
            )
        if amounts.tariff_key:
            metadata["tariff_key"] = amounts.tariff_key
        if ctx.promo_code_id is not None:
            metadata["promo_code_id"] = str(ctx.promo_code_id)
        response = await service.create_payment(
            amount=ctx.price,
            currency=currency,
            description=ctx.description,
            metadata=metadata,
            receipt_email=service.config.DEFAULT_RECEIPT_EMAIL,
            save_payment_method=False,
        )
        payment_url = response.get("confirmation_url") if response else None
        provider_payment_id = str(response.get("id") or "") if response else ""
        if not payment_url:
            logger.error(
                "YooKassa WebApp payment creation failed for payment %s "
                "(user_id=%s, has_provider_payment_id=%s, response=%s).",
                payment.payment_id,
                ctx.user_id,
                bool(provider_payment_id),
                response,
            )
            await mark_payment_failed_creation(ctx.session, payment.payment_id)
            return payment_failed()

        await payment_dal.update_payment_status_by_db_id(
            ctx.session,
            payment.payment_id,
            "pending_yookassa",
            yk_payment_id=provider_payment_id or None,
        )
        await ctx.session.commit()
        return payment_link_response(payment_url=payment_url, payment_id=payment.payment_id)
    except Exception:
        await ctx.session.rollback()
        logger.exception("YooKassa WebApp payment failed")
        return payment_failed()


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> Optional[str]:
    service = app_optional(ctx.request, "yookassa_service", YooKassaService)
    if not service or not service.configured:
        return None

    provider_payment_id = str(
        getattr(payment, "yookassa_payment_id", None)
        or getattr(payment, "provider_payment_id", None)
        or ""
    ).strip()
    if not provider_payment_id:
        return None

    info = await service.get_payment_info(provider_payment_id)
    if not info or str(info.get("status") or "").strip().lower() != "pending":
        return None
    if bool(info.get("paid")):
        return None

    metadata_raw = info.get("metadata")
    metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
    expected_metadata = {
        "user_id": str(ctx.user_id),
        "payment_db_id": str(payment.payment_id),
        "sale_mode": str(ctx.sale_mode),
    }
    if any(str(metadata.get(key) or "") != value for key, value in expected_metadata.items()):
        return None
    return str(info.get("confirmation_url") or "").strip() or None
