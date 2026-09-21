# SQLAlchemy legacy Column declarations expose instance attributes as Column[T]
# to mypy; these routes intentionally mutate loaded ORM instances.
# mypy: disable-error-code="assignment,arg-type"

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import get_bot_username, get_session_factory, get_settings
from bot.app.web.partner_schemas import (
    AdminPartnerApplicationDecisionIn,
    AdminPartnerBalanceAdjustmentIn,
    AdminPartnerCreateIn,
    AdminPartnerRateIn,
    AdminPartnerReferralImportIn,
    AdminPartnerStatusIn,
    AdminPartnerWithdrawalTransitionIn,
)
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import register_contract
from bot.services.partner_commission_service import PartnerCommissionService
from bot.services.partner_common import PartnerError, compact_json, currency_scale
from bot.services.partner_program_service import PartnerProgramService
from bot.services.partner_withdrawal_service import PartnerWithdrawalService
from db.dal import partner_dal, partner_profile_reporting_dal, user_dal, user_reads_dal

from ..partner_serialization import (
    application_out,
    balance_out,
    commission_out,
    profile_out,
    withdrawal_out,
)
from .auth import _require_admin_user_id
from .common import _error, _ok
from .partner_contracts import PARTNER_ADMIN_ROUTE_CONTRACTS
from .users_common import _bulk_user_avatar_keys

for _handler_name, _contract in PARTNER_ADMIN_ROUTE_CONTRACTS.items():
    register_contract(_handler_name, _contract)


def _dump(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _partner_error(exc: PartnerError) -> web.Response:
    return _error(exc.status, exc.code, exc.message or exc.code)


def _pagination(request: web.Request) -> tuple[int, int]:
    maximum = get_settings(request).partner_settings.list_page_limit
    try:
        limit = max(1, min(maximum, int(request.query.get("limit", maximum) or maximum)))
        offset = max(0, int(request.query.get("offset", 0) or 0))
    except (TypeError, ValueError) as exc:
        raise PartnerError("invalid_pagination", 400) from exc
    return limit, offset


async def _profile_payload(
    session: Any,
    profile: Any,
    *,
    currency: str = "RUB",
    user_labels: dict[int, tuple[str | None, str | None]] | None = None,
    avatar_keys: dict[int, str] | None = None,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _dump(profile_out(profile))
    user_id = int(profile.user_id) if profile.user_id is not None else None
    if user_id is not None:
        if user_labels is None:
            user_labels = await user_reads_dal.get_user_labels(session, [user_id])
        if avatar_keys is None:
            avatar_keys = await _bulk_user_avatar_keys(session, [user_id])
        username, live_name = user_labels.get(user_id, (None, None))
        payload["display_label"] = live_name or payload["display_label"]
        payload["username"] = username
        payload["avatar_url"] = (
            f"/api/admin/users/{user_id}/avatar?v={avatar_keys[user_id]}"
            if user_id in avatar_keys
            else None
        )
    else:
        payload["username"] = None
        payload["avatar_url"] = None
    if summary is not None:
        payload.update(summary)
        payload["currency"] = currency
        return payload
    payload["balances"] = [
        _dump(balance_out(item))
        for item in await partner_dal.balance_summaries(session, int(profile.partner_id))
    ]
    clients, clients_total = await partner_dal.list_clients(
        session,
        int(profile.partner_id),
        currency=None,
        limit=1,
        offset=0,
    )
    payload["clients_count"] = clients_total
    payload["latest_client"] = str(clients[0][0].public_label_snapshot) if clients else None
    payload.update(
        await partner_dal.profile_currency_metrics(
            session,
            int(profile.partner_id),
            currency,
        )
    )
    payload["currency"] = currency
    return payload


def _apply_user_identity(
    payload: dict[str, Any],
    user_id: int | None,
    *,
    user_labels: dict[int, tuple[str | None, str | None]],
    avatar_keys: dict[int, str],
) -> dict[str, Any]:
    payload["user_id"] = user_id
    if user_id is None:
        payload["username"] = None
        payload["avatar_url"] = None
        return payload
    username, live_name = user_labels.get(user_id, (None, None))
    payload["display_label"] = live_name or payload.get("display_label")
    payload["username"] = username
    payload["avatar_url"] = (
        f"/api/admin/users/{user_id}/avatar?v={avatar_keys[user_id]}"
        if user_id in avatar_keys
        else None
    )
    return payload


async def _application_payload(
    session: Any,
    application: Any,
    *,
    user_labels: dict[int, tuple[str | None, str | None]] | None = None,
    avatar_keys: dict[int, str] | None = None,
) -> dict[str, Any]:
    payload = _dump(application_out(application))
    user_id = int(application.user_id) if application.user_id is not None else None
    if user_id is not None:
        if user_labels is None:
            user_labels = await user_reads_dal.get_user_labels(session, [user_id])
        if avatar_keys is None:
            avatar_keys = await _bulk_user_avatar_keys(session, [user_id])
    return _apply_user_identity(
        payload,
        user_id,
        user_labels=user_labels or {},
        avatar_keys=avatar_keys or {},
    )


async def _withdrawal_payload(
    session: Any,
    withdrawal: Any,
    *,
    profiles_by_id: dict[int, Any] | None = None,
    user_labels: dict[int, tuple[str | None, str | None]] | None = None,
    avatar_keys: dict[int, str] | None = None,
) -> dict[str, Any]:
    payload = _dump(withdrawal_out(withdrawal))
    partner_id = int(withdrawal.partner_id)
    if profiles_by_id is None:
        profiles_by_id = await partner_dal.get_profiles_by_ids(session, [partner_id])
    profile = profiles_by_id.get(partner_id)
    user_id = int(profile.user_id) if profile is not None and profile.user_id is not None else None
    if profile is not None:
        payload["display_label"] = str(profile.display_label_snapshot)
    if user_id is not None:
        if user_labels is None:
            user_labels = await user_reads_dal.get_user_labels(session, [user_id])
        if avatar_keys is None:
            avatar_keys = await _bulk_user_avatar_keys(session, [user_id])
    return _apply_user_identity(
        payload,
        user_id,
        user_labels=user_labels or {},
        avatar_keys=avatar_keys or {},
    )


async def admin_partner_attention_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        counts = await partner_dal.attention_counts(session)
    return _ok(counts)


async def admin_partner_overview_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    currency = str(request.query.get("currency") or "RUB").strip().upper()
    raw_days = str(request.query.get("days", 30) or 30).strip().lower()
    if raw_days == "all":
        since = None
    else:
        try:
            days = max(7, min(1095, int(raw_days)))
        except (TypeError, ValueError):
            return _error(400, "invalid_range")
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        since = today_start - timedelta(days=days - 1)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        metrics = await partner_dal.overview_metrics(session, currency=currency)
        series = await partner_dal.overview_series(
            session,
            currency=currency,
            since=since,
        )
    return _ok(
        {
            "currency": currency,
            "currency_scale": currency_scale(currency),
            "metrics": metrics,
            "series": series,
        }
    )


async def admin_partners_list_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    try:
        limit, offset = _pagination(request)
    except PartnerError as exc:
        return _partner_error(exc)
    status = str(request.query.get("status") or "").strip().lower() or None
    search = str(request.query.get("search") or "").strip() or None
    currency = str(request.query.get("currency") or "RUB").strip().upper()
    sort = str(request.query.get("sort") or "clients_desc").strip().lower()
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        profiles, total = await partner_dal.list_profiles(
            session,
            status=status,
            search=search,
            currency=currency,
            sort=sort,
            limit=limit,
            offset=offset,
        )
        user_ids = [int(profile.user_id) for profile in profiles if profile.user_id is not None]
        user_labels = await user_reads_dal.get_user_labels(session, user_ids)
        avatar_keys = await _bulk_user_avatar_keys(session, user_ids)
        partner_ids = [int(profile.partner_id) for profile in profiles]
        balances = await partner_profile_reporting_dal.balance_summaries_by_ids(
            session, partner_ids
        )
        clients = await partner_profile_reporting_dal.client_summaries_by_ids(session, partner_ids)
        metrics = await partner_profile_reporting_dal.currency_metrics_by_ids(
            session, partner_ids, currency
        )
        partners = [
            await _profile_payload(
                session,
                profile,
                currency=currency,
                user_labels=user_labels,
                avatar_keys=avatar_keys,
                summary={
                    "balances": [
                        _dump(balance_out(item)) for item in balances[int(profile.partner_id)]
                    ],
                    **clients[int(profile.partner_id)],
                    **metrics[int(profile.partner_id)],
                },
            )
            for profile in profiles
        ]
    return _ok({"partners": partners, "total": total, "limit": limit, "offset": offset})


async def admin_partner_detail_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    partner_id = int(request.match_info["id"])
    currency = str(request.query.get("currency") or "RUB").strip().upper()
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        profile = await partner_dal.get_profile_by_id(session, partner_id)
        if not profile:
            return _error(404, "partner_not_found")
        partner = await _profile_payload(session, profile, currency=currency)
        clients, clients_total = await partner_dal.list_clients(
            session,
            partner_id,
            currency=currency,
            limit=200,
            offset=0,
        )
        commissions, commissions_total = await partner_dal.list_commissions(
            session,
            partner_id,
            currency=currency,
            status=None,
            limit=200,
            offset=0,
        )
        withdrawals, withdrawals_total = await partner_dal.list_withdrawals(
            session,
            partner_id=partner_id,
            currency=currency,
            limit=200,
            offset=0,
        )
        ledger = await partner_dal.list_ledger_entries(
            session,
            partner_id,
            currency=currency,
        )
        running_balance = await partner_dal.balance_minor(session, partner_id, currency)
        ledger_payload: list[dict[str, Any]] = []
        for item in ledger:
            ledger_payload.append(
                {
                    "ledger_entry_id": int(item.entry_id),
                    "kind": str(item.kind),
                    "state": str(item.state),
                    "amount_minor": int(item.amount_minor),
                    "balance_after_minor": running_balance,
                    "currency": str(item.currency),
                    "currency_scale": int(item.currency_scale),
                    "created_at": item.created_at.isoformat(),
                    "internal_reference": str(item.reference_id),
                }
            )
            if item.state == "posted":
                running_balance -= int(item.amount_minor)
        audit = await partner_dal.list_audit_events(session, partner_id)
        partner["links"] = PartnerProgramService(get_settings(request)).links(
            profile,
            bot_username=get_bot_username(request),
        )
    return _ok(
        {
            "partner": partner,
            "clients": [
                {
                    "partner_client_id": int(client.partner_client_id),
                    "client_user_id": (
                        int(client.client_user_id) if client.client_user_id is not None else None
                    ),
                    "public_client_id": str(client.public_client_id),
                    "label": str(client.public_label_snapshot),
                    "source": str(client.source),
                    "attributed_at": client.attributed_at.isoformat(),
                    "payments_count": payments_count,
                    "gross_minor": gross_minor,
                    "currency": currency,
                    "currency_scale": currency_scale,
                }
                for client, payments_count, gross_minor, currency_scale in clients
            ],
            "clients_total": clients_total,
            "commissions": [_dump(commission_out(item, client)) for item, client in commissions],
            "commissions_total": commissions_total,
            "withdrawals": [_dump(withdrawal_out(item)) for item in withdrawals],
            "withdrawals_total": withdrawals_total,
            "ledger": ledger_payload,
            "audit": [
                {
                    "audit_event_id": int(item.audit_event_id),
                    "event_type": str(item.event_type),
                    "actor_type": str(item.actor_type),
                    "actor_user_id": (
                        int(item.actor_user_id) if item.actor_user_id is not None else None
                    ),
                    "reason": item.reason,
                    "created_at": item.created_at.isoformat(),
                }
                for item in audit
            ],
        }
    )


async def admin_partner_create_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    body = await parse_body_or_400(request, AdminPartnerCreateIn)
    async_session_factory: sessionmaker = get_session_factory(request)
    try:
        async with async_session_factory() as session, session.begin():
            user = await user_dal.get_user_by_id(session, body.user_id)
            if not user:
                raise PartnerError("user_not_found", 404)
            profile = await PartnerProgramService(get_settings(request)).create_profile_for_user(
                session,
                user=user,
                commission_bps=body.commission_bps,
                welcome_message=body.welcome_message,
                actor_admin_id=actor_id,
            )
    except PartnerError as exc:
        return _partner_error(exc)
    return _ok({"partner": _dump(profile_out(profile))})


async def admin_partner_referral_import_preview_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    partner_id = int(request.match_info["id"])
    async_session_factory: sessionmaker = get_session_factory(request)
    try:
        async with async_session_factory() as session:
            preview = await PartnerProgramService(get_settings(request)).referral_import_preview(
                session,
                partner_id=partner_id,
            )
    except PartnerError as exc:
        return _partner_error(exc)
    return _ok({"preview": preview})


async def admin_partner_referral_import_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    partner_id = int(request.match_info["id"])
    body = await parse_body_or_400(request, AdminPartnerReferralImportIn)
    if not body.confirm_without_retroactive_commission:
        return _error(400, "confirmation_required")
    async_session_factory: sessionmaker = get_session_factory(request)
    try:
        async with async_session_factory() as session, session.begin():
            result = await PartnerProgramService(get_settings(request)).execute_referral_import(
                session,
                partner_id=partner_id,
                actor_admin_id=actor_id,
            )
    except PartnerError as exc:
        return _partner_error(exc)
    return _ok({"result": result})


async def admin_partner_bulk_referral_import_preview_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    try:
        async with async_session_factory() as session:
            preview = await PartnerProgramService(
                get_settings(request)
            ).bulk_referral_import_preview(session)
    except PartnerError as exc:
        return _partner_error(exc)
    return _ok({"preview": preview})


async def admin_partner_bulk_referral_import_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    body = await parse_body_or_400(request, AdminPartnerReferralImportIn)
    if not body.confirm_without_retroactive_commission:
        return _error(400, "confirmation_required")
    async_session_factory: sessionmaker = get_session_factory(request)
    try:
        async with async_session_factory() as session, session.begin():
            result = await PartnerProgramService(
                get_settings(request)
            ).execute_bulk_referral_import(
                session,
                actor_admin_id=actor_id,
            )
    except PartnerError as exc:
        return _partner_error(exc)
    return _ok({"result": result})


async def admin_partner_rate_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    body = await parse_body_or_400(request, AdminPartnerRateIn)
    partner_id = int(request.match_info["id"])
    async_session_factory: sessionmaker = get_session_factory(request)
    try:
        async with async_session_factory() as session, session.begin():
            profile = await PartnerCommissionService(get_settings(request)).change_commission_rate(
                session,
                partner_id=partner_id,
                commission_bps=body.commission_bps,
                actor_admin_id=actor_id,
                reason=body.reason,
            )
    except PartnerError as exc:
        return _partner_error(exc)
    return _ok({"partner": _dump(profile_out(profile))})


async def admin_partner_balance_adjustment_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    body = await parse_body_or_400(request, AdminPartnerBalanceAdjustmentIn)
    partner_id = int(request.match_info["id"])
    async_session_factory: sessionmaker = get_session_factory(request)
    try:
        async with async_session_factory() as session, session.begin():
            entry, result = await PartnerCommissionService(get_settings(request)).adjust_balance(
                session,
                partner_id=partner_id,
                currency=body.currency,
                scale=body.currency_scale,
                mode=body.mode,
                amount_minor=body.amount_minor,
                reason=body.reason,
                actor_admin_id=actor_id,
                idempotency_key=body.idempotency_key,
                allow_negative=body.allow_negative,
                internal_reference=body.internal_reference,
            )
    except PartnerError as exc:
        return _partner_error(exc)
    return _ok(
        {
            "entry_id": int(entry.entry_id),
            "amount_minor": int(entry.amount_minor),
            "balance_minor": result,
        }
    )


async def _status_route(request: web.Request, status: str) -> web.Response:
    actor_id = _require_admin_user_id(request)
    body = await parse_body_or_400(request, AdminPartnerStatusIn)
    partner_id = int(request.match_info["id"])
    async_session_factory: sessionmaker = get_session_factory(request)
    try:
        async with async_session_factory() as session, session.begin():
            profile = await PartnerProgramService(get_settings(request)).change_status(
                session,
                partner_id=partner_id,
                status=status,
                actor_admin_id=actor_id,
                reason=body.reason,
            )
    except PartnerError as exc:
        return _partner_error(exc)
    return _ok({"partner": _dump(profile_out(profile))})


async def admin_partner_pause_route(request: web.Request) -> web.Response:
    return await _status_route(request, "paused")


async def admin_partner_resume_route(request: web.Request) -> web.Response:
    return await _status_route(request, "active")


async def admin_partner_close_route(request: web.Request) -> web.Response:
    return await _status_route(request, "closed")


async def admin_partner_link_rotate_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    partner_id = int(request.match_info["id"])
    async_session_factory: sessionmaker = get_session_factory(request)
    try:
        async with async_session_factory() as session, session.begin():
            profile = await PartnerProgramService(get_settings(request)).rotate_link(
                session,
                partner_id=partner_id,
                actor_admin_id=actor_id,
            )
    except PartnerError as exc:
        return _partner_error(exc)
    return _ok({"partner": _dump(profile_out(profile))})


async def admin_partner_applications_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    try:
        limit, offset = _pagination(request)
    except PartnerError as exc:
        return _partner_error(exc)
    status = str(request.query.get("status") or "").strip().lower() or None
    search = str(request.query.get("search") or "").strip() or None
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        rows, total = await partner_dal.list_applications(
            session,
            status=status,
            search=search,
            limit=limit,
            offset=offset,
        )
        user_ids = [int(item.user_id) for item in rows if item.user_id is not None]
        user_labels = await user_reads_dal.get_user_labels(session, user_ids)
        avatar_keys = await _bulk_user_avatar_keys(session, user_ids)
        applications = [
            await _application_payload(
                session,
                item,
                user_labels=user_labels,
                avatar_keys=avatar_keys,
            )
            for item in rows
        ]
    return _ok(
        {
            "applications": applications,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    )


async def admin_partner_application_detail_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    application_id = int(request.match_info["id"])
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        application = await partner_dal.get_application_by_id(session, application_id)
        if not application:
            return _error(404, "application_not_found")
        payload = await _application_payload(session, application)
    return _ok({"application": payload})


async def _application_decision_route(request: web.Request, approve: bool) -> web.Response:
    actor_id = _require_admin_user_id(request)
    application_id = int(request.match_info["id"])
    body = await parse_body_or_400(request, AdminPartnerApplicationDecisionIn)
    async_session_factory: sessionmaker = get_session_factory(request)
    try:
        async with async_session_factory() as session, session.begin():
            application, profile = await PartnerProgramService(
                get_settings(request)
            ).decide_application(
                session,
                application_id=application_id,
                approve=approve,
                actor_admin_id=actor_id,
                decision_message=body.decision_message,
                commission_bps=body.commission_bps,
                welcome_message=body.welcome_message,
            )
            application_payload = await _application_payload(session, application)
    except PartnerError as exc:
        return _partner_error(exc)
    payload: dict[str, Any] = {"application": application_payload}
    if profile:
        payload["partner"] = _dump(profile_out(profile))
    return _ok(payload)


async def admin_partner_application_approve_route(request: web.Request) -> web.Response:
    return await _application_decision_route(request, True)


async def admin_partner_application_reject_route(request: web.Request) -> web.Response:
    return await _application_decision_route(request, False)


async def admin_partner_application_reopen_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    application_id = int(request.match_info["id"])
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session, session.begin():
        application = await partner_dal.get_application_by_id(
            session,
            application_id,
            for_update=True,
        )
        if not application:
            return _error(404, "application_not_found")
        if application.status != "rejected":
            return _error(409, "application_not_rejected")
        application.reapply_allowed_at = datetime.now(UTC)
        await partner_dal.create_audit_event(
            session,
            event_type="application_reopened",
            actor_type="admin",
            application_id=application_id,
            actor_user_id=actor_id,
            new_values_json=compact_json({"reapply_allowed": True}),
        )
        payload = await _application_payload(session, application)
    return _ok({"application": payload})


async def admin_partner_withdrawals_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    try:
        limit, offset = _pagination(request)
    except PartnerError as exc:
        return _partner_error(exc)
    status = str(request.query.get("status") or "").strip().lower() or None
    currency = str(request.query.get("currency") or "").strip().upper() or None
    search = str(request.query.get("search") or "").strip() or None
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        rows, total = await partner_dal.list_withdrawals(
            session,
            status=status,
            currency=currency,
            search=search,
            limit=limit,
            offset=offset,
        )
        partner_ids = [int(item.partner_id) for item in rows]
        profiles_by_id = await partner_dal.get_profiles_by_ids(session, partner_ids)
        user_ids = [
            int(profile.user_id)
            for profile in profiles_by_id.values()
            if profile.user_id is not None
        ]
        user_labels = await user_reads_dal.get_user_labels(session, user_ids)
        avatar_keys = await _bulk_user_avatar_keys(session, user_ids)
        withdrawals = [
            await _withdrawal_payload(
                session,
                item,
                profiles_by_id=profiles_by_id,
                user_labels=user_labels,
                avatar_keys=avatar_keys,
            )
            for item in rows
        ]
    return _ok(
        {
            "withdrawals": withdrawals,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    )


async def admin_partner_withdrawal_detail_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    withdrawal_id = int(request.match_info["id"])
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        withdrawal = await partner_dal.get_withdrawal_by_id(session, withdrawal_id)
        if not withdrawal:
            return _error(404, "withdrawal_not_found")
        payload = await _withdrawal_payload(session, withdrawal)
    return _ok({"withdrawal": payload})


async def admin_partner_withdrawal_reveal_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    withdrawal_id = int(request.match_info["id"])
    async_session_factory: sessionmaker = get_session_factory(request)
    try:
        async with async_session_factory() as session, session.begin():
            requisites = await PartnerWithdrawalService(get_settings(request)).reveal_requisites(
                session,
                withdrawal_id=withdrawal_id,
                actor_admin_id=actor_id,
            )
    except PartnerError as exc:
        return _partner_error(exc)
    return _ok({"requisites": requisites})


async def _withdrawal_transition_route(request: web.Request, status: str) -> web.Response:
    actor_id = _require_admin_user_id(request)
    withdrawal_id = int(request.match_info["id"])
    body = await parse_body_or_400(request, AdminPartnerWithdrawalTransitionIn)
    async_session_factory: sessionmaker = get_session_factory(request)
    try:
        async with async_session_factory() as session, session.begin():
            withdrawal = await PartnerWithdrawalService(get_settings(request)).admin_transition(
                session,
                withdrawal_id=withdrawal_id,
                status=status,
                expected_version=body.status_version,
                actor_admin_id=actor_id,
                message=body.message,
                external_reference=body.external_reference,
                settlement_amount=body.settlement_amount,
            )
            payload = await _withdrawal_payload(session, withdrawal)
    except PartnerError as exc:
        return _partner_error(exc)
    return _ok({"withdrawal": payload})


async def admin_partner_withdrawal_processing_route(request: web.Request) -> web.Response:
    return await _withdrawal_transition_route(request, "processing")


async def admin_partner_withdrawal_paid_route(request: web.Request) -> web.Response:
    return await _withdrawal_transition_route(request, "paid")


async def admin_partner_withdrawal_reject_route(request: web.Request) -> web.Response:
    return await _withdrawal_transition_route(request, "rejected")


async def admin_partner_withdrawal_fail_route(request: web.Request) -> web.Response:
    return await _withdrawal_transition_route(request, "failed")
