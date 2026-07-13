"""Shared link-payment orchestration engine.

Every "link" provider (the user gets a hosted payment URL) repeated the same
three flows with only a handful of seams differing: the pending-status string,
the ``provider`` key, the concrete ``create_*`` call signature, and which JSON
fields hold the redirect URL / provider payment id. This module lifts that
orchestration into one tested engine driven by a small per-provider
:class:`LinkPaymentDescriptor`.

Providers keep their own ``Service`` (HTTP + signing) and a thin
``pay_<name>_callback_handler`` / ``create_webapp_payment`` /
``reuse_webapp_payment`` that delegate here. The handler wrappers stay because
aiogram injects the provider service by *parameter name* and the webapp
factories are referenced by ``SPEC``; only the duplicated body moves.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from aiogram import types
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from config.tariffs_config import (
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
)
from db.dal import payment_dal

from ..base import PaymentProviderSpec, WebAppPaymentContext
from .app_context import app_optional, app_required
from .callbacks import (
    describe_payment,
    notify_callback_parse_error,
    notify_payment_record_failure,
    notify_service_unavailable,
    parse_payment_callback,
    quote_hwid_callback_parts,
    render_link_or_fail,
    render_payment_link,
    safe_callback_answer,
)
from .common import (
    build_payment_record_payload,
    create_webapp_payment_record,
    detached_payment_snapshot,
    make_translator,
    payment_failed,
    payment_record_amounts,
    payment_unavailable,
)
from .webapp import finalize_webapp_link_payment

logger = logging.getLogger(__name__)


class LinkFlowService(Protocol):
    """Structural contract the engine needs from a provider service."""

    @property
    def configured(self) -> bool: ...

    @property
    def subscription_service(self) -> Any: ...


ServiceT = TypeVar("ServiceT", bound=LinkFlowService)

# Returned by every provider ``create_*`` call: (api_success, raw_response_dict).
CreateResult = tuple[bool, dict]


@dataclass(frozen=True)
class CreatePaymentRequest:
    """Everything a provider ``create_*`` adapter might need, from either flow.

    The callback flow fills it from the parsed callback ``parts``; the webapp
    flow fills it from the :class:`WebAppPaymentContext`. Each provider's
    ``create`` adapter reads only the fields its API actually uses (e.g. severpay
    needs ``user_id``, lava needs ``description``).
    """

    payment: Any
    user_id: int
    amount: Any
    currency: str
    description: str
    months: float
    sale_mode: str
    language: str | None = None
    provider_context: dict[str, Any] | None = None


@dataclass(frozen=True)
class LinkPaymentDescriptor[ServiceT: LinkFlowService]:
    """Per-provider seams for the shared link-payment engine.

    ``provider_key`` / ``pending_status`` are persisted strings — never change
    them. ``log_prefix`` mirrors each module's historical ``_LOG`` (used for the
    render helpers); ``display_name`` mirrors the human label used in log lines
    and the webapp finalize prefix. The four callables absorb the per-provider
    API shape so the orchestration stays identical.
    """

    spec: PaymentProviderSpec
    provider_key: str
    pending_status: str
    display_name: str
    log_prefix: str
    service_app_key: str
    service_type: type[ServiceT]
    create: Callable[[ServiceT, CreatePaymentRequest], Awaitable[CreateResult]]
    reuse: Callable[[ServiceT, Any], Awaitable[str | None]]
    extract_url: Callable[[dict], str | None]
    extract_provider_id: Callable[[dict], str | None]
    callback_currency: Callable[[ServiceT, Settings], str] | None = None
    callback_payment_allowed: Callable[[ServiceT, Settings, int, Any, str], bool] | None = None
    callback_lead_text: (
        Callable[[CreatePaymentRequest, dict, Callable[..., str]], str | None] | None
    ) = None
    callback_before_create: Callable[[types.CallbackQuery], Awaitable[None]] | None = None
    callback_context: (
        Callable[[types.CallbackQuery, Any, ServiceT], dict[str, Any] | None] | None
    ) = None
    webapp_context: Callable[[WebAppPaymentContext], dict[str, Any] | None] | None = None
    reuse_payment_allowed: Callable[[Any, dict[str, Any] | None], bool] | None = None
    reuse_with_context: (
        Callable[[ServiceT, Any, dict[str, Any] | None], Awaitable[str | None]] | None
    ) = None
    callback_reuse_since_minutes: Callable[[ServiceT, dict[str, Any] | None], int | None] | None = (
        None
    )
    callback_reuse_enabled: bool = True
    callback_reuse_answer: bool = False
    webapp_available: Callable[[ServiceT], bool] | None = None
    # Optional per-provider webapp currency policy. When unset, the webapp flow
    # uses ``ctx.currency or settings.DEFAULT_CURRENCY_SYMBOL or "RUB"`` (the
    # common case). Providers whose webapp resolution differs supply their own.
    webapp_currency: Callable[[WebAppPaymentContext, Settings, ServiceT], str] | None = None


def _resolve_callback_currency[ServiceT: LinkFlowService](
    descriptor: LinkPaymentDescriptor[ServiceT],
    service: ServiceT,
    settings: Settings,
) -> str:
    if descriptor.callback_currency is not None:
        return descriptor.callback_currency(service, settings)
    return default_payment_currency_code_for_settings(settings)


def _resolve_webapp_currency[ServiceT: LinkFlowService](
    descriptor: LinkPaymentDescriptor[ServiceT],
    ctx: WebAppPaymentContext,
    settings: Settings,
    service: ServiceT,
) -> str:
    if descriptor.webapp_currency is not None:
        return descriptor.webapp_currency(ctx, settings, service)
    return ctx.currency or settings.DEFAULT_CURRENCY_SYMBOL or "RUB"


def _webapp_service_available[ServiceT: LinkFlowService](
    descriptor: LinkPaymentDescriptor[ServiceT],
    service: ServiceT,
) -> bool:
    if descriptor.webapp_available is not None:
        return descriptor.webapp_available(service)
    return bool(service.configured)


async def _reuse_payment[ServiceT: LinkFlowService](
    descriptor: LinkPaymentDescriptor[ServiceT],
    service: ServiceT,
    payment: Any,
    provider_context: dict[str, Any] | None,
) -> str | None:
    if descriptor.reuse_payment_allowed is not None and not descriptor.reuse_payment_allowed(
        payment,
        provider_context,
    ):
        return None
    if descriptor.reuse_with_context is not None:
        return await descriptor.reuse_with_context(service, payment, provider_context)
    return await descriptor.reuse(service, payment)


async def run_callback_payment[ServiceT: LinkFlowService](
    descriptor: LinkPaymentDescriptor[ServiceT],
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    service: ServiceT,
    session: AsyncSession,
) -> None:
    """Shared body of every ``pay_<name>_callback_handler``."""
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n = i18n_data.get("i18n_instance")
    translator = make_translator(i18n, current_lang)

    if not i18n or not callback.message:
        await notify_callback_parse_error(callback, translator)
        return

    if not descriptor.spec.is_available_to_user(
        settings,
        user_id=callback.from_user.id,
        require_configured=False,
    ):
        await notify_service_unavailable(callback, translator)
        return

    if not service or not service.configured:
        logger.error("%s service is not configured or unavailable.", descriptor.display_name)
        await notify_service_unavailable(callback, translator)
        return

    parts = parse_payment_callback(callback.data or "")
    if not parts:
        logger.error(
            "Invalid %s data in callback: %s", descriptor.spec.callback_prefix, callback.data
        )
        await notify_callback_parse_error(callback, translator)
        return
    parts, hwid_quote = await quote_hwid_callback_parts(
        session=session,
        user_id=callback.from_user.id,
        parts=parts,
        subscription_service=service.subscription_service,
        currency=default_currency_key_for_settings(settings),
        settings=settings,
    )
    if not parts:
        await notify_callback_parse_error(callback, translator)
        return

    currency_code = _resolve_callback_currency(descriptor, service, settings)
    if descriptor.callback_payment_allowed is not None and not descriptor.callback_payment_allowed(
        service,
        settings,
        callback.from_user.id,
        parts.price,
        currency_code,
    ):
        await notify_service_unavailable(callback, translator)
        return
    provider_context = (
        descriptor.callback_context(callback, parts, service)
        if descriptor.callback_context is not None
        else None
    )
    payment_description = describe_payment(translator, parts)
    record_payload = build_payment_record_payload(
        user_id=callback.from_user.id,
        amount=parts.price,
        currency=currency_code,
        status=descriptor.pending_status,
        description=payment_description,
        months=parts.months,
        provider=descriptor.provider_key,
        sale_mode=parts.sale_mode,
        hwid_quote=hwid_quote,
    )

    reusable_payment = None
    if descriptor.callback_reuse_enabled:
        reuse_amounts = payment_record_amounts(
            months=parts.months,
            sale_mode=parts.sale_mode,
            hwid_device_count=hwid_quote.get("device_count") if hwid_quote else None,
        )
        reuse_since_minutes = (
            descriptor.callback_reuse_since_minutes(service, provider_context)
            if descriptor.callback_reuse_since_minutes is not None
            else None
        )
        reusable_payment = await payment_dal.find_recent_pending_provider_payment(
            session,
            user_id=callback.from_user.id,
            provider=descriptor.provider_key,
            pending_status=descriptor.pending_status,
            amount=parts.price,
            currency=currency_code,
            sale_mode=parts.sale_mode,
            months=reuse_amounts.months,
            purchased_gb=reuse_amounts.purchased_gb,
            purchased_hwid_devices=reuse_amounts.purchased_hwid_devices,
            tariff_key=reuse_amounts.tariff_key,
            since_minutes=reuse_since_minutes,
        )
    if reusable_payment is not None:
        reusable_payment = detached_payment_snapshot(reusable_payment)
        await session.rollback()
        reusable_url = await _reuse_payment(
            descriptor,
            service,
            reusable_payment,
            provider_context,
        )
        if reusable_url:
            if descriptor.callback_reuse_answer:
                await safe_callback_answer(callback)
            await render_payment_link(
                callback,
                translator=translator,
                current_lang=current_lang,
                i18n=i18n,
                parts=parts,
                payment_url=reusable_url,
                log_prefix=descriptor.log_prefix,
            )
            return

    try:
        payment_record = await payment_dal.create_payment_record(session, record_payload)
        await session.commit()
    except Exception:
        await session.rollback()
        logger.exception(
            "%s: failed to create payment record for user %s.",
            descriptor.display_name,
            callback.from_user.id,
        )
        await notify_payment_record_failure(callback, translator)
        return

    if descriptor.callback_before_create is not None:
        await descriptor.callback_before_create(callback)

    create_request = CreatePaymentRequest(
        payment=payment_record,
        user_id=callback.from_user.id,
        amount=parts.price,
        currency=currency_code,
        description=payment_description,
        months=float(parts.months),
        sale_mode=str(parts.sale_mode),
        language=current_lang,
        provider_context=provider_context,
    )
    success, response_data = await descriptor.create(service, create_request)
    lead_text = (
        descriptor.callback_lead_text(create_request, response_data, translator)
        if success and descriptor.callback_lead_text is not None
        else None
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
        payment_url=descriptor.extract_url(response_data),
        provider_payment_id=descriptor.extract_provider_id(response_data),
        provider_response=response_data,
        lead_text=lead_text,
        log_prefix=descriptor.log_prefix,
    )


async def run_webapp_payment[ServiceT: LinkFlowService](
    descriptor: LinkPaymentDescriptor[ServiceT],
    ctx: WebAppPaymentContext,
) -> web.Response:
    """Shared body of every link provider's ``create_webapp_payment``."""
    settings = app_required(ctx.request, "settings", Settings)
    service = app_required(ctx.request, descriptor.service_app_key, descriptor.service_type)
    if not service or not _webapp_service_available(descriptor, service):
        return payment_unavailable()

    currency = _resolve_webapp_currency(descriptor, ctx, settings, service)
    provider_context = (
        descriptor.webapp_context(ctx) if descriptor.webapp_context is not None else None
    )
    try:
        payment = await create_webapp_payment_record(
            ctx,
            amount=ctx.price,
            currency=currency,
            status=descriptor.pending_status,
            provider=descriptor.provider_key,
        )
        success, response_data = await descriptor.create(
            service,
            CreatePaymentRequest(
                payment=payment,
                user_id=ctx.user_id,
                amount=ctx.price,
                currency=currency,
                description=ctx.description,
                months=float(getattr(ctx, "months", 0) or 0),
                sale_mode=str(getattr(ctx, "sale_mode", "") or ""),
                provider_context=provider_context,
            ),
        )
    except Exception:
        await ctx.session.rollback()
        logger.exception("%s WebApp payment failed", descriptor.display_name)
        return payment_failed()

    return await finalize_webapp_link_payment(
        session=ctx.session,
        payment=payment,
        api_success=success,
        payment_url=(descriptor.extract_url(response_data) if success else None),
        provider_payment_id=descriptor.extract_provider_id(response_data),
        provider_response=response_data,
        log_prefix=descriptor.display_name,
    )


async def run_reuse_webapp_payment[ServiceT: LinkFlowService](
    descriptor: LinkPaymentDescriptor[ServiceT],
    ctx: WebAppPaymentContext,
    payment: Any,
) -> str | None:
    """Shared body of every link provider's ``reuse_webapp_payment``."""
    service = app_optional(ctx.request, descriptor.service_app_key, descriptor.service_type)
    if not service or not service.configured:
        return None
    provider_context = (
        descriptor.webapp_context(ctx) if descriptor.webapp_context is not None else None
    )
    return await _reuse_payment(descriptor, service, payment, provider_context)
