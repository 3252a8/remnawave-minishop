"""Operator visibility and recovery for extension-owned work, without private payloads."""

import json
import logging
from datetime import UTC, datetime
from typing import Literal

from aiohttp import web
from pydantic import ConfigDict, Field
from sqlalchemy import select, true
from sqlalchemy.dialects.postgresql import insert

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from bot.plugins.extensions.commerce import order_snapshot, request_refund
from bot.plugins.extensions.contracts import ExtensionError
from bot.plugins.extensions.jobs import utc
from bot.plugins.extensions.presentation import preferences
from bot.plugins.extensions.registry import get_registry, identifier
from bot.plugins.packages import generation_is_current, package_root, read_state
from bot.services.partner_common import currency_scale
from db.extension_models import ExtensionOperation, ExtensionOrder, ExtensionPresentation
from db.models import User

from .auth import _require_admin_user_id
from .common import _error, _ok

logger = logging.getLogger(__name__)


class ExtensionOperationOut(HttpResponseModel):
    id: str
    kind: str
    user_id: int | None
    user_minishop_id: str | None = None
    state: str
    attempts: int
    error: str | None


class ExtensionAdminOrderOut(HttpResponseModel):
    id: str
    user_id: int
    user_minishop_id: str | None = None
    title: str
    amount_minor: int
    currency: str
    currency_scale: int
    can_refund: bool
    payment_state: str
    fulfillment_state: str


class ExtensionPresentationOut(HttpResponseModel):
    target: str
    label: str
    enabled: bool
    position: int


class ExtensionAdminOut(HttpResponseModel):
    operations: list[ExtensionOperationOut]
    orders: list[ExtensionAdminOrderOut]
    presentation: list[ExtensionPresentationOut]


class ExtensionAdminAction(HttpBodyModel):
    model_config = ConfigDict(extra="forbid")
    owner: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    action: Literal["retry", "refund"]
    reason: str = Field(min_length=3, max_length=500)


class ExtensionPresentationUpdate(HttpBodyModel):
    model_config = ConfigDict(extra="forbid")
    owner: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    target: str = Field(pattern=r"^(view|guide):[a-z][a-z0-9_-]{0,63}$")
    enabled: bool = Field(strict=True)
    position: int = Field(ge=-10000, le=10000, strict=True)


class ExtensionActionOut(HttpResponseModel):
    accepted: bool = True


def _current(request: web.Request) -> int:
    actor = _require_admin_user_id(request)
    if not generation_is_current():
        raise web.HTTPServiceUnavailable(
            text='{"ok":false,"error":"extension_generation_changed"}',
            content_type="application/json",
        )
    return actor


async def admin_extensions_route(request: web.Request) -> web.Response:
    _current(request)
    try:
        owner = identifier(request.query.get("owner", ""))
        cursor = request.query.get("cursor", "")
        async with get_session_factory(request)() as session:
            operations = (
                await session.scalars(
                    select(ExtensionOperation)
                    .where(
                        ExtensionOperation.owner == owner,
                        ExtensionOperation.id < cursor if cursor else true(),
                    )
                    .order_by(ExtensionOperation.id.desc())
                    .limit(100)
                )
            ).all()
            orders = (
                await session.scalars(
                    select(ExtensionOrder)
                    .where(
                        ExtensionOrder.owner == owner,
                        ExtensionOrder.id < request.query["orders_cursor"]
                        if request.query.get("orders_cursor")
                        else true(),
                    )
                    .order_by(ExtensionOrder.id.desc())
                    .limit(100)
                )
            ).all()
            choices = await preferences(session, owner)
            user_ids = {
                int(item.user_id) for item in (*operations, *orders) if item.user_id is not None
            }
            public_ids: dict[int, str] = {}
            if user_ids:
                rows = await session.execute(
                    select(User.user_id, User.minishop_id).where(User.user_id.in_(user_ids))
                )
                public_ids = {int(user_id): str(public_id) for user_id, public_id in rows}
        targets: dict[str, tuple[str, int]] = {}
        entry = get_registry().owners().get(owner)
        if entry:
            targets.update(
                {f"guide:{item.id}": (item.id, 100) for item in entry.contributions.guides}
            )
        installation = read_state(package_root())["installations"].get(owner)
        if installation:
            path = package_root() / "releases" / owner / installation["digest"] / "plugin.json"
            frontend = (
                json.loads(path.read_text(encoding="utf-8")).get("frontend", {}).get("user", {})
            )
            for view in [*frontend.get("pages", []), *frontend.get("slots", [])]:
                targets[f"view:{view['id']}"] = (view["label"], view.get("order", 100))
        payload = ExtensionAdminOut(
            operations=[
                ExtensionOperationOut(
                    id=str(item.id),
                    kind=str(item.kind),
                    user_id=item.user_id,
                    user_minishop_id=public_ids.get(int(item.user_id)) if item.user_id else None,
                    state=str(item.state),
                    attempts=int(item.attempts),
                    error=item.error_code,
                )
                for item in operations
            ],
            orders=[
                ExtensionAdminOrderOut(
                    id=str(item.id),
                    user_id=int(item.user_id),
                    user_minishop_id=public_ids.get(int(item.user_id)),
                    title=order_snapshot(item).quote.title,
                    amount_minor=order_snapshot(item).quote.amount_minor,
                    currency=order_snapshot(item).quote.currency,
                    currency_scale=currency_scale(order_snapshot(item).quote.currency),
                    can_refund=(
                        item.payment_state == "paid"
                        and order_snapshot(item).quote.currency
                        == get_settings(request).USER_BALANCE_CURRENCY
                    ),
                    payment_state=str(item.payment_state),
                    fulfillment_state=str(item.fulfillment_state),
                )
                for item in orders
            ],
            presentation=[
                ExtensionPresentationOut(
                    target=target,
                    label=label,
                    enabled=choices.get(target, (True, position))[0],
                    position=choices.get(target, (True, position))[1],
                )
                for target, (label, position) in sorted(targets.items())
            ],
        )
        return _ok(payload.model_dump(mode="json"))
    except ExtensionError as exc:
        return _error(exc.status, exc.code)


async def admin_extension_action_route(request: web.Request) -> web.Response:
    actor = _current(request)
    body = await parse_body_or_400(request, ExtensionAdminAction)
    try:
        async with get_session_factory(request)() as session:
            if body.action == "refund":
                order = await session.get(ExtensionOrder, body.id)
                if order is None or order.owner != body.owner:
                    raise ExtensionError("extension_order_not_found", 404)
                if (
                    order_snapshot(order).quote.currency
                    != get_settings(request).USER_BALANCE_CURRENCY
                ):
                    raise ExtensionError("extension_refund_currency_unavailable")
                await request_refund(session, order_id=body.id, user_id=int(order.user_id))
            else:
                operation = await session.scalar(
                    select(ExtensionOperation)
                    .where(
                        ExtensionOperation.id == body.id,
                        ExtensionOperation.owner == body.owner,
                    )
                    .with_for_update()
                )
                if operation is None:
                    raise ExtensionError("extension_operation_not_found", 404)
                if operation.state not in {"failed", "blocked"}:
                    raise ExtensionError("extension_operation_not_retryable")
                if operation.lease_until and utc(operation.lease_until) > datetime.now(UTC):
                    raise ExtensionError("extension_operation_running")
                operation.state = "queued"
                operation.attempts = 0
                operation.error_code = None
                operation.not_before = datetime.now(UTC)
                operation.lease_token = operation.lease_until = None
            await session.commit()
        logger.info(
            "Extension action actor=%s owner=%s action=%s id=%s reason=%r",
            actor,
            body.owner,
            body.action,
            body.id,
            body.reason,
        )
        return _ok({"accepted": True})
    except ExtensionError as exc:
        return _error(exc.status, exc.code)


async def admin_extension_presentation_route(request: web.Request) -> web.Response:
    actor = _current(request)
    body = await parse_body_or_400(request, ExtensionPresentationUpdate)
    async with get_session_factory(request)() as session:
        statement = insert(ExtensionPresentation).values(**body.model_dump())
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[ExtensionPresentation.owner, ExtensionPresentation.target],
                set_={"enabled": body.enabled, "position": body.position},
            )
        )
        await session.commit()
    logger.info(
        "Extension presentation actor=%s owner=%s target=%s", actor, body.owner, body.target
    )
    return _ok({"accepted": True})


def setup_extension_admin(router: web.UrlDispatcher) -> None:
    router.add_get("/api/admin/extensions", admin_extensions_route)
    router.add_post("/api/admin/extensions/action", admin_extension_action_route)
    router.add_post("/api/admin/extensions/presentation", admin_extension_presentation_route)


register_contract(
    "admin_extensions_route",
    RouteContract(
        response_schema=ok_envelope_for(ExtensionAdminOut),
        models=(ExtensionAdminOut,),
    ),
)
for _name, _model in (
    ("admin_extension_action_route", ExtensionAdminAction),
    ("admin_extension_presentation_route", ExtensionPresentationUpdate),
):
    register_contract(
        _name,
        RouteContract(
            request_model=_model,
            response_schema=ok_envelope_for(ExtensionActionOut),
            models=(ExtensionActionOut,),
        ),
    )
