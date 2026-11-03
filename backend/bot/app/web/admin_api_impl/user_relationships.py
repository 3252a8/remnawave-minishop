"""Admin-only graph of all referral and partner invitations."""

from typing import Literal

from aiohttp import web

from bot.app.web.context import get_session_factory
from bot.app.web.http_contracts import HttpResponseModel
from bot.app.web.route_contracts import (
    RouteContract,
    ok_envelope_with,
    register_contract,
    schema_ref,
)
from db.dal.user_relationships_dal import (
    load_relationship_subscription_and_revenue,
    load_user_relationships,
)

from .auth import _require_admin_user_id
from .common import _ok
from .user_schemas import AdminUserOut, AdminUserWithAvatarOut


class AdminUserRelationshipEdgeOut(HttpResponseModel):
    source: int
    target: int
    kind: Literal["referral", "partner"]


class AdminUserRelationshipNodeOut(AdminUserWithAvatarOut):
    subscription_active: bool | None
    current_tariff_key: str | None
    revenue_by_currency: dict[str, float]


class AdminUserRelationshipsOut(HttpResponseModel):
    nodes: list[AdminUserRelationshipNodeOut]
    edges: list[AdminUserRelationshipEdgeOut]


async def admin_user_relationships_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async with get_session_factory(request)() as session:
        users, edges = await load_user_relationships(session)
        subscriptions, revenue = (
            await load_relationship_subscription_and_revenue(session) if users else ({}, {})
        )
        nodes = []
        for user, avatar_updated_at in users:
            user_id = int(user.user_id)
            is_active, tariff_key = subscriptions.get(user_id, (None, None))
            node = AdminUserRelationshipNodeOut(
                **AdminUserOut.from_orm_user(user).model_dump(),
                subscription_active=is_active,
                current_tariff_key=tariff_key,
                revenue_by_currency=revenue.get(user_id, {}),
                avatar_url=(
                    f"/api/admin/users/{int(user.user_id)}/avatar?v={avatar_updated_at.isoformat()}"
                    if avatar_updated_at is not None
                    else None
                ),
            )
            nodes.append(node)
        payload = AdminUserRelationshipsOut(
            nodes=nodes,
            edges=[
                AdminUserRelationshipEdgeOut.model_validate(
                    {"source": source, "target": target, "kind": kind}
                )
                for source, target, kind in edges
            ],
        )
    return _ok(payload.model_dump(mode="json"))


register_contract(
    "admin_user_relationships_route",
    RouteContract(
        response_schema=ok_envelope_with(
            {
                "nodes": {"type": "array", "items": schema_ref(AdminUserRelationshipNodeOut)},
                "edges": {"type": "array", "items": schema_ref(AdminUserRelationshipEdgeOut)},
            }
        ),
        models=(AdminUserRelationshipNodeOut, AdminUserRelationshipEdgeOut),
    ),
)
