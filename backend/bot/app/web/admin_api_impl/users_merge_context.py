"""Fresh, admin-only account information used before confirming a manual merge."""

from typing import Any

from aiohttp import web
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.context import get_session_factory
from bot.app.web.http_contracts import HttpResponseModel
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from db.dal import user_dal
from db.models import (
    AccountRole,
    AccountRoleEvent,
    UserEmailAddress,
    UserExternalIdentity,
    UserPasskeyCredential,
)

from .auth import _require_admin_user_id
from .common import _error, _ok


class AdminMergeIdentityOut(HttpResponseModel):
    provider: str
    email: str | None = None
    email_verified: bool
    display_name: str | None = None

    @classmethod
    def from_orm_identity(cls, identity: Any) -> "AdminMergeIdentityOut":
        return cls(
            provider=str(identity.provider),
            email=identity.email,
            email_verified=bool(identity.email_verified),
            display_name=identity.display_name,
        )


class AdminMergeEligibilityOut(HttpResponseModel):
    allowed: bool
    reason: str | None = None


class AdminUserMergeContextOut(HttpResponseModel):
    user_id: int
    auth_identities: list[AdminMergeIdentityOut]
    verified_emails: list[str]
    passkey_count: int
    password_available: bool
    merge_eligibility: AdminMergeEligibilityOut


register_contract(
    "admin_user_merge_context_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminUserMergeContextOut),
        models=(AdminUserMergeContextOut, AdminMergeIdentityOut, AdminMergeEligibilityOut),
    ),
)


async def has_admin_merge_privileges(session: AsyncSession, user_ids: tuple[int, ...]) -> bool:
    """Keep preview and the authoritative, locked mutation on the same role policy."""
    role = await session.scalar(
        select(AccountRole.user_id).where(AccountRole.user_id.in_(user_ids)).limit(1)
    )
    role_event = await session.scalar(
        select(AccountRoleEvent.event_id)
        .where(
            or_(
                AccountRoleEvent.user_id.in_(user_ids),
                AccountRoleEvent.actor_user_id.in_(user_ids),
            )
        )
        .limit(1)
    )
    return role is not None or role_event is not None


async def admin_user_merge_context_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    user_id = int(request.match_info["user_id"])
    async with get_session_factory(request)() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if user is None:
            return _error(404, "not_found")
        protected = await has_admin_merge_privileges(session, (user_id,))
        identities = (
            (
                await session.execute(
                    select(UserExternalIdentity)
                    .where(UserExternalIdentity.user_id == user_id)
                    .order_by(UserExternalIdentity.provider)
                )
            )
            .scalars()
            .all()
        )
        emails = set(
            (
                await session.execute(
                    select(UserEmailAddress.email).where(UserEmailAddress.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        if user.email and user.email_verified_at:
            emails.add(user.email)
        passkey_count = int(
            await session.scalar(
                select(func.count(UserPasskeyCredential.credential_pk)).where(
                    UserPasskeyCredential.user_id == user_id
                )
            )
            or 0
        )
        reason = (
            "account_merge_current_admin"
            if actor_id == user_id
            else "account_merge_privileged_source"
            if protected
            else "account_merge_banned"
            if user.is_banned
            else None
        )
        payload = AdminUserMergeContextOut(
            user_id=user_id,
            auth_identities=[AdminMergeIdentityOut.from_orm_identity(item) for item in identities],
            verified_emails=sorted(emails),
            passkey_count=passkey_count,
            password_available=bool(user.password_hash),
            merge_eligibility=AdminMergeEligibilityOut(allowed=reason is None, reason=reason),
        )
    response = _ok(payload.model_dump(mode="json"))
    response.headers["Cache-Control"] = "no-store"
    return response
