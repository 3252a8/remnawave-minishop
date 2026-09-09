from __future__ import annotations

from typing import Any

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_bot_username,
    get_session_factory,
    get_settings,
)
from bot.app.web.partner_schemas import (
    PartnerApplicationCreateIn,
    PartnerBalanceRenewIn,
    PartnerLinksOut,
    PartnerOverviewOut,
    PartnerWithdrawalCreateIn,
    PartnerWithdrawalMethodOut,
)
from bot.services.partner_balance_service import PartnerBalanceService
from bot.services.partner_common import PartnerError, currency_scale
from bot.services.partner_program_service import PartnerProgramService
from bot.services.partner_withdrawal_service import PartnerWithdrawalService
from config.settings import Settings
from db.dal import partner_dal, user_dal

from ..partner_serialization import (
    application_out,
    balance_out,
    client_out,
    commission_out,
    profile_out,
    withdrawal_out,
)
from .common import _json_error, _parse_model_payload, _require_user_id
from .response_helpers import json_response


def _error(exc: PartnerError) -> web.Response:
    return _json_error(exc.status, exc.code, exc.message or exc.code)


def _pagination(request: web.Request, default_limit: int) -> tuple[int, int]:
    try:
        limit = int(request.query.get("limit", default_limit) or default_limit)
        offset = int(request.query.get("offset", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise PartnerError("invalid_pagination", 400) from exc
    return max(1, min(default_limit, limit)), max(0, offset)


def _dump(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")


async def partner_overview_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    program = PartnerProgramService(settings)
    withdrawals = PartnerWithdrawalService(settings)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session, session.begin():
        user = await user_dal.get_user_by_id(session, user_id)
        profile = await program.auto_enroll_user(session, user=user) if user is not None else None
        if profile is None:
            profile = await partner_dal.get_profile_by_user_id(session, user_id)
        application = await partner_dal.latest_application_for_user(session, user_id)
        raw_balances = (
            await partner_dal.balance_summaries(session, int(profile.partner_id)) if profile else []
        )
    balances_by_currency = {str(item["currency"]): item for item in raw_balances}
    for currency in settings.partner_settings.eligible_currencies:
        balances_by_currency.setdefault(
            currency,
            {
                "currency": currency,
                "currency_scale": currency_scale(currency),
                "available_minor": 0,
                "pending_minor": 0,
                "reserved_minor": 0,
                "lifetime_earned_minor": 0,
            },
        )
    overview = PartnerOverviewOut(
        program_enabled=settings.partner_settings.enabled,
        withdrawals_enabled=settings.partner_settings.withdrawals_enabled,
        balance_payment_enabled=settings.partner_settings.balance_payment_enabled,
        encryption_available=withdrawals.encryption_available(),
        application_message_max_length=settings.partner_settings.application_message_max_length,
        application=application_out(application) if application else None,
        profile=profile_out(profile) if profile else None,
        balances=[balance_out(item) for item in balances_by_currency.values()],
        links=(
            PartnerLinksOut.model_validate(
                program.links(profile, bot_username=get_bot_username(request))
            )
            if profile
            else None
        ),
        withdrawal_methods=[
            PartnerWithdrawalMethodOut.model_validate(method.model_dump(mode="json"))
            for method in settings.partner_settings.withdrawal_methods
        ],
    )
    return json_response({"ok": True, **_dump(overview)})


async def partner_application_create_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    body = await _parse_model_payload(request, PartnerApplicationCreateIn)
    async_session_factory: sessionmaker = get_session_factory(request)
    try:
        async with async_session_factory() as session, session.begin():
            application = await PartnerProgramService(get_settings(request)).submit_application(
                session,
                user_id=user_id,
                message=body.message,
            )
    except PartnerError as exc:
        return _error(exc)
    return json_response({"ok": True, "application": _dump(application_out(application))})


async def partner_clients_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings = get_settings(request)
    try:
        limit, offset = _pagination(request, settings.partner_settings.list_page_limit)
    except PartnerError as exc:
        return _error(exc)
    currency = str(request.query.get("currency") or "").strip().upper() or None
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        profile = await partner_dal.get_profile_by_user_id(session, user_id)
        if not profile:
            return _error(PartnerError("partner_not_found", 404))
        rows, total = await partner_dal.list_clients(
            session,
            int(profile.partner_id),
            currency=currency,
            limit=limit,
            offset=offset,
        )
    clients = [
        _dump(
            client_out(
                client,
                payments_count=payments_count,
                gross_minor=gross_minor,
                currency=currency,
                currency_scale=currency_scale,
            )
        )
        for client, payments_count, gross_minor, currency_scale in rows
    ]
    return json_response(
        {"ok": True, "clients": clients, "total": total, "limit": limit, "offset": offset}
    )


async def partner_commissions_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings = get_settings(request)
    try:
        limit, offset = _pagination(request, settings.partner_settings.list_page_limit)
    except PartnerError as exc:
        return _error(exc)
    currency = str(request.query.get("currency") or "").strip().upper() or None
    status = str(request.query.get("status") or "").strip().lower() or None
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        profile = await partner_dal.get_profile_by_user_id(session, user_id)
        if not profile:
            return _error(PartnerError("partner_not_found", 404))
        rows, total = await partner_dal.list_commissions(
            session,
            int(profile.partner_id),
            currency=currency,
            status=status,
            limit=limit,
            offset=offset,
        )
    return json_response(
        {
            "ok": True,
            "commissions": [_dump(commission_out(item, client)) for item, client in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    )


async def partner_withdrawals_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings = get_settings(request)
    try:
        limit, offset = _pagination(request, settings.partner_settings.list_page_limit)
    except PartnerError as exc:
        return _error(exc)
    status = str(request.query.get("status") or "").strip().lower() or None
    currency = str(request.query.get("currency") or "").strip().upper() or None
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        profile = await partner_dal.get_profile_by_user_id(session, user_id)
        if not profile:
            return _error(PartnerError("partner_not_found", 404))
        rows, total = await partner_dal.list_withdrawals(
            session,
            partner_id=int(profile.partner_id),
            status=status,
            currency=currency,
            limit=limit,
            offset=offset,
        )
    return json_response(
        {
            "ok": True,
            "withdrawals": [_dump(withdrawal_out(item)) for item in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    )


async def partner_withdrawal_create_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    body = await _parse_model_payload(request, PartnerWithdrawalCreateIn)
    async_session_factory: sessionmaker = get_session_factory(request)
    try:
        async with async_session_factory() as session, session.begin():
            withdrawal = await PartnerWithdrawalService(get_settings(request)).create_request(
                session,
                user_id=user_id,
                method_id=body.method_id,
                amount_minor=body.amount_minor,
                currency=body.currency,
                requisites=body.requisites,
                network=body.network,
                idempotency_key=body.idempotency_key,
            )
    except PartnerError as exc:
        return _error(exc)
    return json_response({"ok": True, "withdrawal": _dump(withdrawal_out(withdrawal))})


async def partner_withdrawal_cancel_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    withdrawal_id = int(request.match_info["id"])
    async_session_factory: sessionmaker = get_session_factory(request)
    try:
        async with async_session_factory() as session, session.begin():
            withdrawal = await PartnerWithdrawalService(get_settings(request)).cancel_request(
                session,
                user_id=user_id,
                withdrawal_id=withdrawal_id,
            )
    except PartnerError as exc:
        return _error(exc)
    return json_response({"ok": True, "withdrawal": _dump(withdrawal_out(withdrawal))})


async def partner_balance_renew_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    body = await _parse_model_payload(request, PartnerBalanceRenewIn)
    try:
        result = await PartnerBalanceService.from_request(request).renew(
            user_id=user_id,
            tariff_key=body.tariff_key,
            months=body.months,
            duration_days=body.duration_days,
            promo_code=body.promo_code,
            idempotency_key=body.idempotency_key,
        )
    except PartnerError as exc:
        return _error(exc)
    return json_response({"ok": True, **result})
