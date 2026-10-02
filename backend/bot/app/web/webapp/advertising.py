"""Public capture discloses only link context and never accepts a user identity."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from aiohttp import web
from aiohttp.typedefs import Handler
from pydantic import Field
from sqlalchemy import select

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from bot.app.web.session import WEBAPP_SESSION_COOKIE_NAME, extract_authenticated_user_id
from bot.app.web.webapp_auth import verify_webapp_session_token
from bot.services.advertising.capture import (
    VISIT_COOKIE,
    capture_contact,
    claim_visit,
    resolve_code,
)
from bot.services.advertising.links import public_offer
from db.advertising_models import AdLink, AdTouchpoint
from db.models import AdCampaign

from .rate_limits import check_request_limits, client_ip
from .response_helpers import json_response


class AdCaptureBody(HttpBodyModel):
    code: str = Field("", max_length=64)
    utm: dict[str, str] = Field(default_factory=dict)
    event_id: str = Field("", max_length=64, pattern=r"^[A-Za-z0-9_-]*$")


class AdPublicContextOut(HttpResponseModel):
    code: str
    landing_path: str
    utm: dict[str, str]
    offer_code: str | None = None
    offer_mode: str = "none"
    offer_available: bool = False


class AdCaptureOut(HttpResponseModel):
    captured: bool
    context: AdPublicContextOut | None = None


async def public_context(session: Any, code: str) -> AdPublicContextOut | None:
    campaign, link = await resolve_code(session, code)
    if campaign is None:
        return None
    offer, mode, available = await public_offer(
        session, int(campaign.ad_campaign_id), link.id if link else None
    )
    return AdPublicContextOut(
        code=code,
        landing_path=link.landing_path if link else "/",
        utm=json.loads(link.utm_json) if link else {},
        offer_code=offer,
        offer_mode=mode,
        offer_available=available,
    )


async def advertising_capture_route(request: web.Request) -> web.Response:
    if not get_settings(request).ADVERTISING_ENABLED:
        return json_response({"ok": True, "captured": False, "context": None})
    blocked = await check_request_limits(
        request, [(f"advertising:{client_ip(request)}", 30)], window_seconds=60
    )
    if blocked is not None:
        return blocked
    if request.content_length is not None and request.content_length > 4096:
        return json_response({"ok": False, "error": "payload_too_large"}, status=413)
    body = await parse_body_or_400(request.clone(client_max_size=4096), AdCaptureBody)
    async with get_session_factory(request)() as session:
        try:
            visit_id = await capture_contact(
                session,
                code=body.code,
                observed_utm=body.utm,
                visit_id=request.cookies.get(VISIT_COOKIE),
                user_id=extract_authenticated_user_id(request),
                event_key=body.event_id or None,
            )
        except ValueError as error:
            return json_response({"ok": False, "error": str(error)}, status=400)
        context = await public_context(session, body.code)
        await session.commit()
    response = json_response(
        {
            "ok": True,
            **AdCaptureOut(captured=bool(visit_id), context=context).model_dump(mode="json"),
        }
    )
    if visit_id:
        response.set_cookie(
            VISIT_COOKIE,
            visit_id,
            httponly=True,
            secure=request.secure,
            samesite="None" if request.secure else "Lax",
            max_age=30 * 86400,
            path="/",
        )
    return response


async def advertising_context_route(request: web.Request) -> web.Response:
    if not get_settings(request).ADVERTISING_ENABLED:
        return json_response({"ok": True, "captured": False, "context": None})
    code = str(request.query.get("code", ""))
    if len(code) > 64:
        return json_response({"ok": False, "error": "invalid_ad_start_param"}, status=400)
    async with get_session_factory(request)() as session:
        if not code:
            user_id = extract_authenticated_user_id(request)
            visit_id = request.cookies.get(VISIT_COOKIE, "")
            condition = (
                AdTouchpoint.user_id == user_id
                if user_id
                else ((AdTouchpoint.visit_id == visit_id) & AdTouchpoint.user_id.is_(None))
            )
            touch = (
                await session.execute(
                    select(AdTouchpoint)
                    .where(
                        condition,
                        AdTouchpoint.campaign_id.is_not(None),
                        AdTouchpoint.occurred_at >= datetime.now(UTC) - timedelta(days=30),
                    )
                    .order_by(AdTouchpoint.occurred_at.desc(), AdTouchpoint.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if touch:
                link = await session.get(AdLink, touch.link_id) if touch.link_id else None
                campaign = await session.get(AdCampaign, touch.campaign_id)
                code = link.code if link else campaign.start_param if campaign else ""
        context = await public_context(session, code)
    return json_response(
        {
            "ok": True,
            "captured": False,
            "context": context.model_dump(mode="json") if context else None,
        }
    )


@web.middleware
async def advertising_identity_middleware(
    request: web.Request, handler: Handler
) -> web.StreamResponse:
    visit_id = str(request.cookies.get(VISIT_COOKIE, ""))
    if (
        re.fullmatch(r"[0-9a-f]{32}", visit_id)
        and request.path.startswith("/api/")
        and not request.path.startswith("/api/admin/")
    ):
        user_id = extract_authenticated_user_id(request)
        if user_id:
            async with get_session_factory(request)() as session:
                await claim_visit(session, visit_id, user_id)
                await session.commit()
    try:
        response = await handler(request)
    except web.HTTPException as redirect:
        response = redirect
    # All authentication methods issue the same signed session cookie. Linking the
    # opaque visit here also covers OAuth redirects and an already active session.
    token = response.cookies.get(WEBAPP_SESSION_COOKIE_NAME)
    if token and re.fullmatch(r"[0-9a-f]{32}", visit_id):
        user_id = verify_webapp_session_token(get_settings(request), token.value)
        if user_id:
            async with get_session_factory(request)() as session:
                await claim_visit(session, visit_id, user_id)
                await session.commit()
    return response


def setup_advertising_public_routes(router: web.UrlDispatcher) -> None:
    router.add_post("/api/advertising/capture", advertising_capture_route)
    router.add_get("/api/advertising/context", advertising_context_route)
    register_contract(
        "advertising_capture_route",
        RouteContract(
            request_model=AdCaptureBody,
            response_schema=ok_envelope_for(AdCaptureOut),
            models=(AdCaptureBody, AdCaptureOut, AdPublicContextOut),
            security=[],
        ),
    )
    register_contract(
        "advertising_context_route",
        RouteContract(
            response_schema=ok_envelope_for(AdCaptureOut),
            models=(AdCaptureOut, AdPublicContextOut),
            security=[],
        ),
    )
