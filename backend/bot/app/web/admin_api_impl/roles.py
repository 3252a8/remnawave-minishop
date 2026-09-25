"""Owner-only role management for verified accounts."""

from aiohttp import web
from pydantic import BaseModel
from sqlalchemy import or_, select

from bot.app.web.context import get_session_factory
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from bot.services.account_roles import ROLE_OWNER, grant_role, has_role, revoke_role
from db.auth_models import AccountRole
from db.models import User

from .auth import _require_admin_user_id
from .common import _error, _ok


class AdminRoleGrantBody(BaseModel):
    email: str | None = None
    minishop_id: str | None = None
    role: str


class AdminRoleOut(BaseModel):
    user_id: int
    email: str | None
    minishop_id: str | None
    role: str


class AdminRolesListOut(BaseModel):
    roles: list[AdminRoleOut]


class AdminRoleCandidateOut(BaseModel):
    minishop_id: str
    email: str | None
    username: str | None
    first_name: str | None


class AdminRoleCandidatesOut(BaseModel):
    users: list[AdminRoleCandidateOut]


register_contract(
    "admin_roles_list_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminRolesListOut),
        models=(AdminRolesListOut, AdminRoleOut),
    ),
)
register_contract(
    "admin_role_grant_route",
    RouteContract(
        request_model=AdminRoleGrantBody,
        response_schema=ok_envelope_for(),
        models=(AdminRoleGrantBody,),
    ),
)
register_contract(
    "admin_role_candidates_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminRoleCandidatesOut),
        models=(AdminRoleCandidatesOut, AdminRoleCandidateOut),
    ),
)
register_contract(
    "admin_role_revoke_route",
    RouteContract(response_schema=ok_envelope_for()),
)


async def _require_owner(request: web.Request, session) -> int:
    actor_id = _require_admin_user_id(request)
    if not await has_role(session, actor_id, ROLE_OWNER):
        raise web.HTTPForbidden(reason="owner_role_required")
    return actor_id


async def admin_roles_list_route(request: web.Request) -> web.Response:
    async with get_session_factory(request)() as session:
        await _require_owner(request, session)
        rows = (
            await session.execute(
                select(AccountRole, User.email, User.minishop_id)
                .join(User, User.user_id == AccountRole.user_id)
                .where(AccountRole.revoked_at.is_(None))
                .order_by(AccountRole.user_id)
            )
        ).all()
        return _ok(
            {
                "roles": [
                    {
                        "user_id": int(role.user_id),
                        "email": email,
                        "minishop_id": minishop_id,
                        "role": role.role,
                    }
                    for role, email, minishop_id in rows
                ]
            }
        )


async def admin_role_candidates_route(request: web.Request) -> web.Response:
    query = str(request.query.get("q") or "").strip().lstrip("@")[:100]
    async with get_session_factory(request)() as session:
        await _require_owner(request, session)
        stmt = select(User).order_by(User.registration_date.desc(), User.user_id.desc()).limit(10)
        if query:
            like = f"%{query}%"
            stmt = stmt.where(
                or_(
                    User.minishop_id.ilike(like),
                    User.email.ilike(like),
                    User.username.ilike(like),
                    User.first_name.ilike(like),
                )
            )
        users = (await session.scalars(stmt)).all()
        return _ok(
            {
                "users": [
                    {
                        "minishop_id": str(user.minishop_id),
                        "email": user.email,
                        "username": user.username,
                        "first_name": user.first_name,
                    }
                    for user in users
                ]
            }
        )


async def admin_role_grant_route(request: web.Request) -> web.Response:
    payload = await parse_body_or_400(request, AdminRoleGrantBody)
    email = (payload.email or "").strip().lower()
    minishop_id = (payload.minishop_id or "").strip().lower()
    role = payload.role

    if bool(email) == bool(minishop_id):
        return _error(400, "account_identifier_required")
    async with get_session_factory(request)() as session:
        actor_id = await _require_owner(request, session)
        if minishop_id:
            user = await session.scalar(select(User).where(User.minishop_id == minishop_id))
        else:
            user = await session.scalar(
                select(User).where(User.email == email, User.email_verified_at.is_not(None))
            )
        if user is None:
            return _error(400, "account_not_found")
        try:
            await grant_role(session, int(user.user_id), role, actor_user_id=actor_id)
        except ValueError as exc:
            return _error(400, "invalid_role_request", str(exc))
        await session.commit()
    return _ok({})


async def admin_role_revoke_route(request: web.Request) -> web.Response:
    try:
        user_id = int(request.match_info["user_id"])
        role = str(request.match_info["role"])
    except (KeyError, TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(reason="invalid_role_request") from exc
    async with get_session_factory(request)() as session:
        actor_id = await _require_owner(request, session)
        try:
            await revoke_role(session, user_id, role, actor_user_id=actor_id)
        except ValueError as exc:
            return _error(400, "role_revoke_failed", str(exc))
        await session.commit()
    return _ok({})
