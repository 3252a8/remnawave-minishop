"""Resolve changed panel references from a complete, unambiguous identity snapshot."""

from collections import defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.panel_identity_match import panel_candidate_matches_account
from db.dal import subscription_panel_identity_dal, user_panel_squad_override_dal
from db.models import User

from .sync_admin_common import _coerce_panel_telegram_id, _normalize_panel_email


async def finish_sync_panel_relink(
    session: AsyncSession, *, user_id: int, old_reference: str, new_reference: str
) -> None:
    # Structural updates happen after the version-fenced entitlement sync. Moving
    # rows first would change xmin and invalidate that sync's purchase protection.
    await subscription_panel_identity_dal.relink_panel_subscriptions(
        session,
        user_id=user_id,
        old_panel_user_uuid=old_reference,
        new_panel_user_uuid=new_reference,
        panel_subscription_uuid=None,
    )
    await user_panel_squad_override_dal.merge_panel_user_uuid(
        session,
        user_id=user_id,
        old_panel_user_uuid=old_reference,
        new_panel_user_uuid=new_reference,
    )


def bind_sync_panel_identity(
    user: User, candidate: dict[str, Any], origin: str | None, *, telegram_duplicate: bool
) -> bool:
    if (getattr(user, "panel_origin", None) and user.panel_origin != origin) or (
        (user.panel_user_uuid != candidate["uuid"] or not getattr(user, "panel_origin", None))
        and not telegram_duplicate
        and not panel_candidate_matches_account(user, candidate)
    ):
        return False
    user.panel_origin = origin
    username = str(candidate.get("username") or "").strip()
    if username and not telegram_duplicate:
        user.panel_username = username
        user.panel_username_state = "current" if username == user.minishop_id else "legacy_pending"
    return True


class PanelSyncIdentityIndex:
    def __init__(self, panel_users: list[dict[str, Any]]) -> None:
        self.references: set[str] = set()
        self.by_telegram: dict[int, set[str]] = defaultdict(set)
        self.by_email: dict[str, set[str]] = defaultdict(set)
        self.by_username: dict[str, set[str]] = defaultdict(set)
        for candidate in panel_users:
            reference = str(candidate.get("uuid") or "")
            if not reference:
                continue
            self.references.add(reference)
            telegram_id = _coerce_panel_telegram_id(candidate.get("telegramId"))
            if telegram_id:
                self.by_telegram[telegram_id].add(reference)
            email = _normalize_panel_email(candidate.get("email"))
            if email:
                self.by_email[email].add(reference)
            username = str(candidate.get("username") or "").strip()
            if username:
                self.by_username[username].add(reference)

    def stale_owners(
        self, candidates: list[dict[str, Any]], users: dict[int, User]
    ) -> dict[str, User]:
        # Resolve the whole batch before writes expire computed account fields.
        return {
            str(candidate["uuid"]): owner
            for candidate in candidates
            if candidate.get("uuid") and (owner := self.stale_owner(candidate, users)) is not None
        }

    def stale_owner(self, candidate: dict[str, Any], users: dict[int, User]) -> User | None:
        owners = [
            user for user in users.values() if panel_candidate_matches_account(user, candidate)
        ]
        if len(owners) != 1:
            return None
        user = owners[0]
        if not user.panel_user_uuid or str(user.panel_user_uuid) in self.references:
            return None

        references: set[str] = set()
        if user.telegram_id:
            references.update(self.by_telegram.get(int(user.telegram_id), set()))
            candidate_telegram = _coerce_panel_telegram_id(candidate.get("telegramId"))
            if candidate_telegram and candidate_telegram != user.telegram_id:
                return None
        if user.email_verified_at and user.email:
            email = user.email.strip().lower()
            references.update(self.by_email.get(email, set()))
            candidate_email = _normalize_panel_email(candidate.get("email"))
            if candidate_email and candidate_email != email:
                return None
        for username in (user.panel_username, user.minishop_id):
            if username:
                references.update(self.by_username.get(username, set()))
        return user if references == {str(candidate["uuid"])} else None
