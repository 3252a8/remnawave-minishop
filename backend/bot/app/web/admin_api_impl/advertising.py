"""Advertising management; all operations use the existing admin boundary."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from aiohttp import web
from pydantic import ValidationError
from sqlalchemy import func, or_, select, update

from bot.app.web.context import get_bot_username, get_session_factory, get_settings
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    RouteContract,
    ok_envelope_for,
    register_contract,
    schema_ref,
)
from bot.services.advertising.imports import (
    build_candidates,
    confirm_import,
    lock_import_account,
    preview_import,
    revert_import,
)
from bot.services.advertising.links import create_link, link_urls
from bot.services.advertising.offers import binding_terms, offer_statistics
from bot.services.advertising.reporting import campaign_report
from bot.services.advertising.validation import (
    currency_scale,
    minor_units,
    normalize_utm,
    start_code,
)
from db.advertising_models import (
    AdAudit,
    AdImportBatch,
    AdLink,
    AdMatchCandidate,
    AdPromoBinding,
    AdSpendEntry,
    AdTouchpoint,
    AdUtmRule,
)
from db.models import AdAttribution, AdCampaign, PromoCode

from .activity_schemas import AdOut, AdToggleBody
from .advertising_access import require_advertising_admin
from .advertising_export import admin_ad_export_route
from .advertising_schemas import (
    AdAuditOut,
    AdBindingBody,
    AdBindingOut,
    AdCandidateDecisionBody,
    AdCandidateOut,
    AdCandidatesBody,
    AdDetailOut,
    AdEditBody,
    AdImportConfirmBody,
    AdImportOut,
    AdImportPreviewBody,
    AdImportPreviewOut,
    AdLinkBody,
    AdLinkOut,
    AdListQuery,
    AdReportQuery,
    AdSpendBody,
    AdSpendOut,
    AdTouchOut,
    AdUnassignedBody,
    AdUnassignedOut,
)
from .common import _error, _ok


def audit(
    session: Any,
    campaign_id: int | None,
    actor_id: int,
    action: str,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        AdAudit(
            campaign_id=campaign_id,
            actor_id=actor_id,
            action=action,
            details_json=json.dumps(details or {}, default=str),
        )
    )


def touch_out(touch: AdTouchpoint) -> AdTouchOut:
    return AdTouchOut(
        id=touch.id,
        user_id=touch.user_id,
        original_user_id=touch.original_user_id,
        channel=touch.channel,
        evidence=touch.evidence,
        occurred_at=touch.occurred_at,
        received_at=touch.received_at,
        is_new_user=touch.is_new_user,
        utm=json.loads(touch.observed_utm_json),
    )


def import_out(batch: AdImportBatch) -> AdImportOut:
    rows = json.loads(batch.rows_json)
    return AdImportOut(
        id=batch.id,
        status=batch.status,
        account=batch.account,
        timezone=batch.timezone,
        fingerprint=batch.fingerprint,
        rows=len(rows),
        granularity=rows[0]["granularity"] if rows else "daily",
        created_at=batch.created_at,
    )


async def admin_ad_detail_route(request: web.Request) -> web.Response:
    require_advertising_admin(request)
    try:
        query = AdReportQuery.model_validate(dict(request.query))
    except ValidationError:
        return _error(400, "invalid_ad_period")
    async with get_session_factory(request)() as session:
        campaign = await session.get(AdCampaign, int(request.match_info["campaign_id"]))
        if campaign is None:
            return _error(404, "not_found")
        links = list(
            (
                await session.execute(
                    select(AdLink)
                    .where(AdLink.campaign_id == campaign.ad_campaign_id)
                    .order_by(AdLink.id)
                )
            ).scalars()
        )
        bindings = (
            await session.execute(
                select(AdPromoBinding, PromoCode)
                .join(PromoCode)
                .where(AdPromoBinding.campaign_id == campaign.ad_campaign_id)
                .order_by(AdPromoBinding.id.desc())
            )
        ).all()
        spends = list(
            (
                await session.execute(
                    select(AdSpendEntry)
                    .where(AdSpendEntry.campaign_id == campaign.ad_campaign_id)
                    .order_by(AdSpendEntry.occurred_at.desc())
                    .limit(100)
                )
            ).scalars()
        )
        touch_query = select(AdTouchpoint).where(
            AdTouchpoint.campaign_id == campaign.ad_campaign_id
        )
        if query.period_mode == "events":
            if query.start:
                touch_query = touch_query.where(AdTouchpoint.occurred_at >= query.start)
            if query.end:
                touch_query = touch_query.where(AdTouchpoint.occurred_at < query.end)
        else:
            acquisition = select(AdAttribution.user_id).where(
                AdAttribution.ad_campaign_id == campaign.ad_campaign_id
            )
            if query.start:
                acquisition = acquisition.where(AdAttribution.first_start_at >= query.start)
            if query.end:
                acquisition = acquisition.where(AdAttribution.first_start_at < query.end)
            touch_query = touch_query.where(AdTouchpoint.user_id.in_(acquisition))
        if query.link_id:
            touch_query = touch_query.where(AdTouchpoint.link_id == query.link_id)
        if query.evidence:
            touch_query = touch_query.where(AdTouchpoint.evidence == query.evidence)
        if query.channel:
            touch_query = touch_query.where(AdTouchpoint.channel == query.channel)
        total = int(
            (
                await session.execute(select(func.count()).select_from(touch_query.subquery()))
            ).scalar()
            or 0
        )
        touches = list(
            (
                await session.execute(
                    touch_query.order_by(AdTouchpoint.occurred_at.desc(), AdTouchpoint.id.desc())
                    .offset(query.page * query.page_size)
                    .limit(query.page_size)
                )
            ).scalars()
        )
        batches = list(
            (
                await session.execute(
                    select(AdImportBatch)
                    .where(AdImportBatch.campaign_id == campaign.ad_campaign_id)
                    .order_by(AdImportBatch.created_at.desc())
                    .limit(100)
                )
            ).scalars()
        )
        candidates = list(
            (
                await session.execute(
                    select(AdMatchCandidate)
                    .join(AdImportBatch)
                    .where(AdImportBatch.campaign_id == campaign.ad_campaign_id)
                    .order_by(AdMatchCandidate.id.desc())
                    .limit(100)
                )
            ).scalars()
        )
        changes = list(
            (
                await session.execute(
                    select(AdAudit)
                    .where(AdAudit.campaign_id == campaign.ad_campaign_id)
                    .order_by(AdAudit.id.desc())
                    .limit(100)
                )
            ).scalars()
        )
        codes = list(
            (
                await session.execute(
                    select(PromoCode)
                    .where(PromoCode.archived_at.is_(None), PromoCode.user_id.is_(None))
                    .limit(1000)
                )
            ).scalars()
        )
        offer_stats = await offer_statistics(session, int(campaign.ad_campaign_id))
        report = await campaign_report(
            session,
            campaign,
            start=query.start,
            end=query.end,
            period_mode=query.period_mode,
            link_id=query.link_id,
            evidence=query.evidence,
            channel=query.channel,
            currency=query.currency,
        )
        warning = None
        try:
            start_code(campaign.start_param or "")
        except ValueError:
            warning = "invalid_ad_start_param"
        response = AdDetailOut(
            campaign=AdOut.from_orm_ad(campaign),
            name=campaign.name or campaign.source or "",
            description=campaign.description or "",
            archived_at=campaign.archived_at,
            report_currency=campaign.report_currency,
            attribution_window_days=campaign.attribution_window_days,
            spend_source=campaign.spend_source,
            report=report,
            links=[
                AdLinkOut(
                    id=link.id,
                    code=link.code,
                    label=link.label,
                    destination=link.destination,
                    landing_path=link.landing_path,
                    utm=json.loads(link.utm_json),
                    is_active=link.is_active,
                    urls=link_urls(
                        get_settings(request),
                        link.code,
                        json.loads(link.utm_json),
                        link.landing_path,
                        bot_username=get_bot_username(request),
                        app_name=request.query.get("app_name", ""),
                    ),
                )
                for link in links
            ],
            bindings=[
                AdBindingOut(
                    id=binding.id,
                    promo_code_id=binding.promo_code_id,
                    code=binding.code_snapshot or promo.archived_code or promo.code,
                    link_id=binding.link_id,
                    purpose=binding.purpose,
                    starts_at=binding.starts_at,
                    ends_at=binding.ends_at,
                    version=binding.version,
                    is_active=bool(promo.is_active),
                    effects=json.loads(binding.effects_json),
                    **offer_stats.get(binding.id, {}),
                )
                for binding, promo in bindings
            ],
            spends=[
                AdSpendOut(
                    id=spend.id,
                    amount_minor=str(spend.amount_minor),
                    currency=spend.currency,
                    scale=spend.currency_scale,
                    occurred_at=spend.occurred_at,
                    source=spend.source,
                    note=spend.note,
                )
                for spend in spends
            ],
            touches=[touch_out(touch) for touch in touches],
            touch_total=total,
            imports=[import_out(batch) for batch in batches],
            candidates=[
                AdCandidateOut(
                    id=c.id,
                    batch_id=c.batch_id,
                    touchpoint_id=c.touchpoint_id,
                    status=c.status,
                    delta_seconds=c.delta_seconds,
                    reason=c.reason,
                    window_seconds=c.window_seconds,
                    bot_id=c.bot_id,
                    method_version=c.method_version,
                )
                for c in candidates
            ],
            audit=[
                AdAuditOut(id=c.id, action=c.action, actor_id=c.actor_id, created_at=c.created_at)
                for c in changes
            ],
            legacy_urls=link_urls(
                get_settings(request),
                campaign.start_param or "",
                {},
                bot_username=get_bot_username(request),
            )
            if warning is None
            else {},
            legacy_warning=warning,
            available_codes={str(code.code): int(code.promo_code_id) for code in codes},
        )
        return _ok(response.model_dump(mode="json"))


async def admin_ad_edit_route(request: web.Request) -> web.Response:
    actor = require_advertising_admin(request)
    body = await parse_body_or_400(request, AdEditBody)
    async with get_session_factory(request)() as session:
        campaign = await session.get(AdCampaign, int(request.match_info["campaign_id"]))
        if campaign is None:
            return _error(404, "not_found")
        before = {key: getattr(campaign, key) for key in body.model_fields_set}
        for key, value in body.model_dump(exclude_unset=True).items():
            setattr(campaign, key, value)
        audit(
            session,
            int(campaign.ad_campaign_id),
            actor,
            "campaign.updated",
            {"before": before, "after": body.model_dump()},
        )
        await session.commit()
    return _ok({})


async def admin_ad_archive_route(request: web.Request) -> web.Response:
    actor = require_advertising_admin(request)
    async with get_session_factory(request)() as session:
        campaign = await session.get(AdCampaign, int(request.match_info["campaign_id"]))
        if campaign is None:
            return _error(404, "not_found")
        campaign.archived_at = datetime.now(UTC)
        campaign.is_active = False
        audit(session, int(campaign.ad_campaign_id), actor, "campaign.archived")
        await session.commit()
    return _ok({})


async def admin_ad_link_create_route(request: web.Request) -> web.Response:
    actor = require_advertising_admin(request)
    body = await parse_body_or_400(request, AdLinkBody)
    ident = int(request.match_info["campaign_id"])
    async with get_session_factory(request)() as session:
        campaign = await session.get(AdCampaign, ident)
        if campaign is None or campaign.archived_at is not None:
            return _error(404, "not_found")
        link = await create_link(session, ident, **body.model_dump())
        audit(session, ident, actor, "link.created", {"link_id": link.id})
        await session.commit()
    return _ok({})


async def admin_ad_link_toggle_route(request: web.Request) -> web.Response:
    actor = require_advertising_admin(request)
    body = await parse_body_or_400(request, AdToggleBody)
    async with get_session_factory(request)() as session:
        link = await session.get(AdLink, int(request.match_info["link_id"]))
        if link is None or link.campaign_id != int(request.match_info["campaign_id"]):
            return _error(404, "not_found")
        before = link.is_active
        link.is_active = body.is_active
        audit(
            session,
            link.campaign_id,
            actor,
            "link.toggled",
            {"link_id": link.id, "before": before, "after": body.is_active},
        )
        await session.commit()
    return _ok({})


async def admin_ad_binding_create_route(request: web.Request) -> web.Response:
    actor = require_advertising_admin(request)
    body = await parse_body_or_400(request, AdBindingBody)
    ident = int(request.match_info["campaign_id"])
    async with get_session_factory(request)() as session:
        from bot.services.advertising.locking import lock_advertising

        await lock_advertising(session, "offers")
        campaign = await session.get(AdCampaign, ident)
        promo = await session.get(PromoCode, body.promo_code_id)
        link = await session.get(AdLink, body.link_id) if body.link_id else None
        if (
            campaign is None
            or campaign.archived_at is not None
            or promo is None
            or (body.link_id and (link is None or link.campaign_id != ident))
        ):
            return _error(404, "not_found")
        if promo.user_id is not None:
            return _error(400, "personal_activation_code_not_allowed")
        previous = list(
            (
                await session.execute(
                    select(AdPromoBinding).where(
                        AdPromoBinding.campaign_id == ident, AdPromoBinding.link_id == body.link_id
                    )
                )
            ).scalars()
        )
        now = datetime.now(UTC)
        for binding in previous:
            if binding.ends_at is None:
                binding.ends_at = now
        version = max((item.version for item in previous), default=0) + 1
        session.add(
            AdPromoBinding(
                campaign_id=ident,
                **body.model_dump(),
                starts_at=now,
                version=version,
                **binding_terms(promo),
            )
        )
        audit(session, ident, actor, "binding.created", body.model_dump())
        await session.commit()
    return _ok({})


async def admin_ad_binding_end_route(request: web.Request) -> web.Response:
    actor = require_advertising_admin(request)
    async with get_session_factory(request)() as session:
        binding = await session.get(AdPromoBinding, int(request.match_info["binding_id"]))
        if binding is None or binding.campaign_id != int(request.match_info["campaign_id"]):
            return _error(404, "not_found")
        binding.ends_at = datetime.now(UTC)
        audit(session, binding.campaign_id, actor, "binding.ended", {"binding_id": binding.id})
        await session.commit()
    return _ok({})


async def admin_ad_spend_create_route(request: web.Request) -> web.Response:
    actor = require_advertising_admin(request)
    body = await parse_body_or_400(request, AdSpendBody)
    try:
        amount = minor_units(body.amount, body.currency)
    except ValueError:
        return _error(400, "invalid_ad_amount")
    ident = int(request.match_info["campaign_id"])
    async with get_session_factory(request)() as session:
        if await session.get(AdCampaign, ident) is None:
            return _error(404, "not_found")
        session.add(
            AdSpendEntry(
                campaign_id=ident,
                amount_minor=amount,
                currency=body.currency,
                currency_scale=currency_scale(body.currency),
                occurred_at=body.occurred_at,
                note=body.note,
                created_by=actor,
            )
        )
        audit(session, ident, actor, "spend.created", body.model_dump())
        await session.commit()
    return _ok({})


async def admin_ad_import_preview_route(request: web.Request) -> web.Response:
    actor = require_advertising_admin(request)
    if request.content_type == "text/csv":
        try:
            metadata = dict(request.query)
            metadata["mapping"] = json.loads(metadata.get("mapping", "{}"))
            metadata["csv"] = await request.text()
            body = AdImportPreviewBody.model_validate(metadata)
        except (ValueError, UnicodeError):
            return _error(400, "invalid_import_request")
    else:
        body = await parse_body_or_400(request, AdImportPreviewBody)
    ident = int(request.match_info["campaign_id"])
    async with get_session_factory(request)() as session:
        if await session.get(AdCampaign, ident) is None:
            return _error(404, "not_found")
        try:
            batch = await preview_import(
                session,
                campaign_id=ident,
                user_id=actor,
                source=body.csv,
                mapping=body.mapping,
                timezone_name=body.timezone,
                account=body.account,
                granularity=body.granularity,
                currency=body.currency,
                delimiter=body.delimiter,
            )
        except ValueError as error:
            return _error(400, str(error))
        audit(session, ident, actor, "import.preview", {"batch_id": batch.id})
        await session.commit()
        return _ok(
            {
                "batch": import_out(batch).model_dump(mode="json"),
                "preview": [
                    {
                        **row,
                        "cost_minor": str(row["cost_minor"])
                        if row.get("cost_minor") is not None
                        else None,
                    }
                    for row in json.loads(batch.rows_json)[:20]
                ],
            }
        )


async def _batch_action(request: web.Request, action: str) -> web.Response:
    actor = require_advertising_admin(request)
    body = await parse_body_or_400(request, AdImportConfirmBody) if action == "confirm" else None
    candidates_body = (
        await parse_body_or_400(request, AdCandidatesBody) if action == "candidates" else None
    )
    async with get_session_factory(request)() as session:
        batch = await session.get(AdImportBatch, request.match_info["batch_id"])
        if batch is None or batch.campaign_id != int(request.match_info["campaign_id"]):
            return _error(404, "not_found")
        try:
            if action == "confirm":
                await confirm_import(session, batch, replace=bool(body and body.replace))
            elif action == "revert":
                await revert_import(session, batch)
            elif candidates_body:
                await build_candidates(session, batch, **candidates_body.model_dump())
        except ValueError as error:
            await session.rollback()
            return _error(409, str(error))
        audit(session, batch.campaign_id, actor, "import." + action, {"batch_id": batch.id})
        await session.commit()
    return _ok({})


async def admin_ad_import_confirm_route(request: web.Request) -> web.Response:
    return await _batch_action(request, "confirm")


async def admin_ad_import_revert_route(request: web.Request) -> web.Response:
    return await _batch_action(request, "revert")


async def admin_ad_candidates_route(request: web.Request) -> web.Response:
    return await _batch_action(request, "candidates")


async def admin_ad_candidate_decide_route(request: web.Request) -> web.Response:
    actor = require_advertising_admin(request)
    body = await parse_body_or_400(request, AdCandidateDecisionBody)
    async with get_session_factory(request)() as session:
        candidate = await session.get(AdMatchCandidate, int(request.match_info["candidate_id"]))
        if candidate is None:
            return _error(404, "not_found")
        batch = await session.get(AdImportBatch, candidate.batch_id)
        if batch is not None:
            await lock_import_account(session, batch.account)
            await session.refresh(batch)
            await session.refresh(candidate)
        if (
            batch is None
            or batch.campaign_id != int(request.match_info["campaign_id"])
            or batch.status != "confirmed"
        ):
            return _error(409, "invalid_import_state")
        await session.execute(
            select(AdCampaign)
            .where(AdCampaign.ad_campaign_id == batch.campaign_id)
            .with_for_update()
        )
        if body.status == "confirmed_by_operator":
            claimed = (
                await session.execute(
                    select(AdMatchCandidate.id).where(
                        AdMatchCandidate.id != candidate.id,
                        or_(
                            AdMatchCandidate.event_key == candidate.event_key,
                            AdMatchCandidate.touchpoint_id == candidate.touchpoint_id,
                        ),
                        AdMatchCandidate.status == "confirmed_by_operator",
                    )
                )
            ).first()
            if claimed or candidate.touchpoint_id is None:
                return _error(409, "ambiguous_import_match")
        audit(
            session,
            batch.campaign_id,
            actor,
            "candidate.decided",
            {"candidate_id": candidate.id, "before": candidate.status, "after": body.status},
        )
        candidate.status, candidate.decided_by, candidate.decided_at = (
            body.status,
            actor,
            datetime.now(UTC),
        )
        await session.commit()
    return _ok({})


async def admin_ad_unassigned_route(request: web.Request) -> web.Response:
    require_advertising_admin(request)
    try:
        query = AdListQuery.model_validate(dict(request.query))
    except ValidationError:
        return _error(400, "invalid_ad_period")
    async with get_session_factory(request)() as session:
        touches = list(
            (
                await session.execute(
                    select(AdTouchpoint)
                    .where(AdTouchpoint.campaign_id.is_(None))
                    .order_by(AdTouchpoint.id.desc())
                    .offset(query.page * query.page_size)
                    .limit(query.page_size)
                )
            ).scalars()
        )
        total = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(AdTouchpoint)
                    .where(AdTouchpoint.campaign_id.is_(None))
                )
            ).scalar()
            or 0
        )
        campaigns = (
            await session.execute(
                select(AdCampaign.ad_campaign_id, AdCampaign.name, AdCampaign.source)
                .where(
                    AdCampaign.archived_at.is_(None),
                    AdCampaign.is_active.is_(True),
                    or_(
                        AdCampaign.name.ilike("%" + query.search + "%"),
                        AdCampaign.source.ilike("%" + query.search + "%"),
                    ),
                )
                .order_by(AdCampaign.ad_campaign_id.desc())
                .limit(100)
            )
        ).all()
        return _ok(
            {
                "touches": [touch_out(touch).model_dump(mode="json") for touch in touches],
                "total": total,
                "campaigns": {
                    str(ident): name or source or str(ident) for ident, name, source in campaigns
                },
            }
        )


async def admin_ad_unassigned_assign_route(request: web.Request) -> web.Response:
    actor = require_advertising_admin(request)
    body = await parse_body_or_400(request, AdUnassignedBody)
    try:
        utm = normalize_utm(body.utm)
    except ValueError as error:
        return _error(400, str(error))
    if not utm:
        return _error(400, "invalid_ad_utm")
    serialized = json.dumps(utm, sort_keys=True)
    fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
    async with get_session_factory(request)() as session:
        if await session.get(AdCampaign, body.campaign_id) is None:
            return _error(404, "not_found")
        rule = await session.get(AdUtmRule, fingerprint)
        if rule is not None:
            return _error(409, "duplicate_ad_utm_rule")
        session.add(
            AdUtmRule(
                fingerprint=fingerprint,
                campaign_id=body.campaign_id,
                utm_json=serialized,
                created_by=actor,
            )
        )
        await session.execute(
            update(AdTouchpoint)
            .where(AdTouchpoint.campaign_id.is_(None), AdTouchpoint.utm_fingerprint == fingerprint)
            .values(campaign_id=body.campaign_id, evidence="operator_utm_mapping")
        )
        from bot.services.advertising.capture import project_mapped_contacts

        await project_mapped_contacts(session, body.campaign_id, fingerprint)
        audit(session, body.campaign_id, actor, "utm.assigned", {"utm": utm})
        await session.commit()
    return _ok({})


def setup_advertising_routes(router: web.UrlDispatcher) -> None:
    prefix = "/api/admin/ads/{campaign_id:\\d+}"
    definitions = (
        ("GET", "/detail", admin_ad_detail_route, None, AdDetailOut),
        ("POST", "/edit", admin_ad_edit_route, AdEditBody, None),
        ("POST", "/archive", admin_ad_archive_route, None, None),
        ("POST", "/links", admin_ad_link_create_route, AdLinkBody, None),
        ("POST", "/links/{link_id:\\d+}/toggle", admin_ad_link_toggle_route, AdToggleBody, None),
        ("POST", "/bindings", admin_ad_binding_create_route, AdBindingBody, None),
        ("POST", "/bindings/{binding_id:\\d+}/end", admin_ad_binding_end_route, None, None),
        ("POST", "/spend", admin_ad_spend_create_route, AdSpendBody, None),
        (
            "POST",
            "/imports/preview",
            admin_ad_import_preview_route,
            AdImportPreviewBody,
            AdImportPreviewOut,
        ),
        (
            "POST",
            "/imports/{batch_id:[0-9a-f]{32}}/confirm",
            admin_ad_import_confirm_route,
            AdImportConfirmBody,
            None,
        ),
        (
            "POST",
            "/imports/{batch_id:[0-9a-f]{32}}/revert",
            admin_ad_import_revert_route,
            None,
            None,
        ),
        (
            "POST",
            "/imports/{batch_id:[0-9a-f]{32}}/candidates",
            admin_ad_candidates_route,
            AdCandidatesBody,
            None,
        ),
        (
            "POST",
            "/candidates/{candidate_id:\\d+}",
            admin_ad_candidate_decide_route,
            AdCandidateDecisionBody,
            None,
        ),
    )
    for method, path, handler, request_model, response_model in definitions:
        register_contract(
            handler.__name__,
            RouteContract(
                request_model=request_model,
                response_schema=ok_envelope_for(response_model),
                models=tuple(model for model in (request_model, response_model) if model),
            ),
        )
        router.add_route(method, prefix + path, handler)
    register_contract(
        "admin_ad_import_preview_route",
        RouteContract(
            request_model=AdImportPreviewBody,
            response_schema=ok_envelope_for(AdImportPreviewOut),
            request_content={
                "application/json": schema_ref(AdImportPreviewBody),
                "text/csv": {"type": "string"},
            },
            models=(AdImportPreviewBody, AdImportPreviewOut),
        ),
    )
    router.add_get(prefix + "/export", admin_ad_export_route)
    register_contract(
        "admin_ad_export_route",
        RouteContract(response_content_type="text/csv", response_schema={"type": "string"}),
    )
    router.add_get("/api/admin/ads/unassigned", admin_ad_unassigned_route)
    router.add_post("/api/admin/ads/unassigned/assign", admin_ad_unassigned_assign_route)
    register_contract(
        "admin_ad_unassigned_route",
        RouteContract(response_schema=ok_envelope_for(AdUnassignedOut), models=(AdUnassignedOut,)),
    )
    register_contract(
        "admin_ad_unassigned_assign_route",
        RouteContract(
            request_model=AdUnassignedBody,
            response_schema=ok_envelope_for(),
            models=(AdUnassignedBody,),
        ),
    )
