"""RivaraPay registry entries and shared hosted-checkout adapters."""

from functools import partial
from typing import Any, Literal

from aiogram import F, Router, types
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from db.models import Payment

from ..base import (
    PaymentProviderSpec,
    ProviderManifestField,
    ServiceFactoryContext,
    WebAppPaymentContext,
)
from ..shared import (
    CreatePaymentRequest,
    LinkPaymentDescriptor,
    run_callback_payment,
    run_reuse_webapp_payment,
    run_webapp_payment,
)
from ..shared.app_context import app_required
from .config import CONFIG_MANIFEST, RivaraPayConfig
from .service import (
    PENDING_STATUS,
    PROVIDER_KEYS,
    WEBHOOK_PATH,
    RivaraPayService,
    checkout_url,
    intent_id,
)

router = Router(name="user_subscription_payments_rivarapay_router")


def create_service(ctx: ServiceFactoryContext) -> RivaraPayService:
    bundle = ctx.config_for("rivarapay_service")
    config = bundle.config if bundle else None
    if not isinstance(config, RivaraPayConfig):
        config = RivaraPayConfig()
    return RivaraPayService(ctx, config)


async def rivarapay_webhook_route(request: web.Request) -> web.Response:
    service = app_required(request, "rivarapay_service", RivaraPayService)
    return await service.webhook_route(request)


@router.callback_query(F.data.startswith(("pay_rvs:", "pay_rvc:")))
async def pay_rivarapay_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    rivarapay_service: RivaraPayService,
    session: AsyncSession,
) -> None:
    prefix, _, _ = (callback.data or "").partition(":")
    await run_callback_payment(
        _DESCRIPTORS_BY_PREFIX[prefix],
        callback,
        settings,
        i18n_data,
        rivarapay_service,
        session,
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_DESCRIPTORS_BY_METHOD[ctx.method], ctx)


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Payment) -> str | None:
    return await run_reuse_webapp_payment(_DESCRIPTORS_BY_METHOD[ctx.method], ctx, payment)


def _spec(
    provider_key: str,
    method: str,
    *,
    group: Literal["fiat", "crypto"],
    callback_prefix: str,
    method_label: str,
    icon: str,
    first: bool = False,
) -> PaymentProviderSpec:
    enabled_attr = f"{method}_ENABLED"
    admin_only_attr = f"{method}_ADMIN_ONLY_ENABLED"
    method_fields = tuple(
        ProviderManifestField(
            f"RIVARAPAY_{attr}",
            "bool",
            label,
            subsection="RivaraPay",
            attr=attr,
        )
        for attr, label in (
            (enabled_attr, f"Enable {method_label}"),
            (admin_only_attr, f"{method_label} for admins only"),
        )
    )
    return PaymentProviderSpec(
        id=provider_key,
        provider_key=provider_key,
        label="RivaraPay",
        pending_status=PENDING_STATUS,
        enabled=lambda config: bool(getattr(config, enabled_attr, False)),
        admin_only_config_attr=admin_only_attr,
        service_key="rivarapay_service",
        callback_prefix=callback_prefix,
        webapp_label=f"RivaraPay {method_label}",
        webapp_icon=icon,
        router=router if first else None,
        create_service=create_service if first else None,
        webhook_path=(lambda _source: WEBHOOK_PATH) if first else None,
        webhook_route=rivarapay_webhook_route if first else None,
        webhook_requires_base_url=True,
        create_webapp_payment=create_webapp_payment,
        reuse_webapp_payment=reuse_webapp_payment,
        config_class=RivaraPayConfig,
        manifest_fields=(CONFIG_MANIFEST if first else ()) + method_fields,
        reporting_fee_method=method.lower(),
        payment_group=group,
        info_url="https://rivarapay.io/",
        currency_support_url="https://rivarapay.io/docs",
    )


SBP_SPEC = _spec(
    PROVIDER_KEYS[0],
    "SBP",
    group="fiat",
    callback_prefix="pay_rvs",
    method_label="SBP",
    icon="QrCode",
    first=True,
)
CRYPTO_SPEC = _spec(
    PROVIDER_KEYS[1],
    "CRYPTO",
    group="crypto",
    callback_prefix="pay_rvc",
    method_label="crypto",
    icon="Bitcoin",
)
SPECS = (SBP_SPEC, CRYPTO_SPEC)


async def _create_payment(
    service: RivaraPayService, request: CreatePaymentRequest, *, method: str
) -> tuple[bool, dict[str, Any]]:
    return await service.create_payment(request, method)


def _descriptor(spec: PaymentProviderSpec, method: str) -> LinkPaymentDescriptor[RivaraPayService]:
    return LinkPaymentDescriptor(
        spec=spec,
        provider_key=spec.provider_key,
        pending_status=spec.pending_status,
        display_name=spec.label,
        log_prefix=spec.provider_key,
        service_app_key="rivarapay_service",
        service_type=RivaraPayService,
        create=partial(_create_payment, method=method),
        reuse=lambda service, payment: service.try_reuse_pending_payment(payment),
        extract_url=checkout_url,
        extract_provider_id=lambda data: intent_id(data) if checkout_url(data) else None,
        provider_method=method.lower(),
    )


_DESCRIPTOR = _descriptor(SBP_SPEC, "SBP")
_CRYPTO_DESCRIPTOR = _descriptor(CRYPTO_SPEC, "CRYPTO")
_DESCRIPTORS_BY_METHOD = {entry.spec.id: entry for entry in (_DESCRIPTOR, _CRYPTO_DESCRIPTOR)}
_DESCRIPTORS_BY_PREFIX = {
    entry.spec.callback_prefix: entry for entry in _DESCRIPTORS_BY_METHOD.values()
}
