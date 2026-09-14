"""User and referral import, legacy referral code preservation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.auth_models import UserEmailAddress, UserExternalIdentity
from db.dal import user_dal
from db.models import (
    LegacyReferralCode,
    MessageLog,
    User,
)

from .common import (
    SOURCE,
    _as_utc,
    _json_dumps,
    _split_name,
    _to_int,
    _truthy,
)
from .remnashop_data import (
    _legacy_user_metadata,
    remnashop_target_user_id,
)
from .remnashop_tariffs import _RemnashopTariffsSection
from .safety import DryRunSession

logger = logging.getLogger(__name__)


def _string(value: Any, limit: int | None = None) -> str | None:
    result = str(value or "").strip()
    if not result:
        return None
    return result[:limit] if limit else result


class _RemnashopUsersSection(_RemnashopTariffsSection):
    async def _upsert_legacy_referral_code(self, *, code: str, user_id: int) -> None:
        if len(code) > 128:
            self.summary["warnings"].append(
                f"Skipped an overlong legacy referral code for user {user_id}: "
                f"{len(code)} characters"
            )
            return
        now = datetime.now(UTC)
        stmt = (
            pg_insert(LegacyReferralCode)
            .values(
                source=SOURCE,
                code=code,
                user_id=user_id,
                is_active=True,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=[LegacyReferralCode.source, LegacyReferralCode.code],
                set_={"user_id": user_id, "is_active": True, "updated_at": now},
            )
        )
        await self.target.execute(stmt)

    async def _record_user_state_note(
        self,
        *,
        source_id: int,
        user_id: int,
        metadata: dict[str, Any],
    ) -> None:
        if not metadata:
            return
        if await self._get_mapping("user_state", source_id):
            return
        log = MessageLog(
            user_id=None,
            target_user_id=user_id,
            event_type="legacy_remnashop_user_state",
            content=_json_dumps(metadata),
            is_admin_event=True,
        )
        self.target.add(log)
        await self.target.flush()
        await self._upsert_mapping(
            entity_type="user_state",
            source_id=source_id,
            target_table="message_logs",
            target_id=log.log_id,
            metadata=metadata,
        )

    async def _source_referral_code_conflicts(self, code: str, user_id: int) -> bool:
        existing = await user_dal.get_user_by_referral_code(
            self.target,
            code,
            include_legacy=False,
        )
        return bool(existing and int(existing.user_id) != int(user_id))

    async def _oauth_rows_by_user(self) -> dict[int, list[dict[str, Any]]]:
        result: dict[int, list[dict[str, Any]]] = {}
        if "user_oauth_providers" not in self.tables:
            return result
        for row in await self._fetch_rows("user_oauth_providers", order_by="id"):
            source_user_id = _to_int(row.get("user_id"))
            if source_user_id is not None:
                result.setdefault(source_user_id, []).append(row)
        return result

    async def _identity_candidates(
        self,
        row: dict[str, Any],
        oauth_rows: list[dict[str, Any]],
        panel_uuid: str | None,
    ) -> set[int]:
        candidates: set[int] = set()
        source_id = _to_int(row.get("id"))
        mapped = await self._mapped_user_id(source_id)
        if mapped is not None:
            candidates.add(mapped)
        telegram_id = _to_int(row.get("telegram_id"))
        if telegram_id is not None:
            query = await self.target.execute(
                select(User.user_id).where(
                    (User.telegram_id == telegram_id) | (User.user_id == telegram_id)
                )
            )
            candidates.update(int(value) for value in query.scalars().all())
        email = _string(row.get("email"), 254)
        if email and _truthy(row.get("is_email_verified")):
            query = await self.target.execute(
                select(User.user_id).where(func.lower(User.email) == email.lower())
            )
            candidates.update(int(value) for value in query.scalars().all())
            query = await self.target.execute(
                select(UserEmailAddress.user_id).where(
                    func.lower(UserEmailAddress.email) == email.lower()
                )
            )
            candidates.update(int(value) for value in query.scalars().all())
        if panel_uuid:
            query = await self.target.execute(
                select(User.user_id).where(User.panel_user_uuid == panel_uuid)
            )
            candidates.update(int(value) for value in query.scalars().all())
        for oauth in oauth_rows:
            provider = _string(oauth.get("provider"), 32)
            subject = _string(oauth.get("provider_id"), 255)
            if not provider or not subject:
                continue
            query = await self.target.execute(
                select(UserExternalIdentity.user_id).where(
                    UserExternalIdentity.provider == provider.lower(),
                    UserExternalIdentity.subject == subject,
                )
            )
            candidates.update(int(value) for value in query.scalars().all())
        return candidates

    async def _import_identities(
        self,
        *,
        row: dict[str, Any],
        oauth_rows: list[dict[str, Any]],
        target: User,
    ) -> None:
        email = _string(row.get("email"), 254)
        verified = bool(email and _truthy(row.get("is_email_verified")))
        verified_at = _as_utc(row.get("updated_at") or row.get("created_at")) or datetime.now(UTC)
        if email and verified:
            existing = await self.target.execute(
                select(UserEmailAddress).where(func.lower(UserEmailAddress.email) == email.lower())
            )
            address = existing.scalar_one_or_none()
            if address is None:
                target_addresses = await self.target.execute(
                    select(UserEmailAddress.email_address_id).where(
                        UserEmailAddress.user_id == int(target.user_id),
                        (UserEmailAddress.is_primary.is_(True))
                        | (UserEmailAddress.is_notification.is_(True)),
                    )
                )
                has_primary_address = target_addresses.first() is not None
                matches_account_email = bool(
                    target.email and str(target.email).strip().lower() == email.lower()
                )
                self.target.add(
                    UserEmailAddress(
                        user_id=int(target.user_id),
                        email=email.lower(),
                        source=SOURCE,
                        verified_at=verified_at,
                        is_primary=matches_account_email and not has_primary_address,
                        is_notification=matches_account_email and not has_primary_address,
                    )
                )
                self.summary["identities"]["verified_emails"] += 1
            elif int(address.user_id) != int(target.user_id):
                self.summary["identity_conflicts"].append(
                    {
                        "source_user_id": _to_int(row.get("id")),
                        "email": email,
                        "target_user_ids": [int(target.user_id), int(address.user_id)],
                    }
                )
        display_name = _string(row.get("name"), 255)
        for oauth in oauth_rows:
            provider = (_string(oauth.get("provider"), 32) or "").lower()
            subject = _string(oauth.get("provider_id"), 255)
            if not provider or not subject:
                continue
            existing = await self.target.execute(
                select(UserExternalIdentity).where(
                    (UserExternalIdentity.provider == provider)
                    & (
                        (UserExternalIdentity.subject == subject)
                        | (UserExternalIdentity.user_id == int(target.user_id))
                    )
                )
            )
            identities = list(existing.scalars().all())
            identity = next(
                (item for item in identities if item.subject == subject),
                None,
            )
            user_provider_identity = next(
                (item for item in identities if int(item.user_id) == int(target.user_id)),
                None,
            )
            if identity is None:
                if user_provider_identity is not None:
                    self.summary["identities"]["oauth_conflicts"] += 1
                    continue
                self.target.add(
                    UserExternalIdentity(
                        user_id=int(target.user_id),
                        provider=provider,
                        subject=subject,
                        email=email,
                        email_verified=verified,
                        display_name=display_name,
                        created_at=_as_utc(oauth.get("created_at")),
                        updated_at=_as_utc(oauth.get("updated_at")),
                    )
                )
                self.summary["identities"]["oauth"] += 1
            elif int(identity.user_id) != int(target.user_id):
                self.summary["identities"]["oauth_conflicts"] += 1

    async def import_users(self) -> None:
        rows = await self._fetch_rows("users", order_by="id")
        panel_by_user = await self._latest_panel_uuid_by_source_user_id()
        oauth_by_user = await self._oauth_rows_by_user()
        for row in rows:
            self._remember_source_user(row)
            source_id = _to_int(row.get("id"))
            telegram_id = _to_int(row.get("telegram_id"))
            email = _string(row.get("email"), 254)
            if source_id is None or (telegram_id is None and email is None):
                self.summary["users"]["skipped"] += 1
                continue

            first_name, last_name = _split_name(row.get("name"))
            panel_uuid = panel_by_user.get(source_id)
            referral_code = str(row.get("referral_code") or "").strip() or None
            created_at = _as_utc(row.get("created_at")) or datetime.now(UTC)
            language = str(row.get("language") or "ru").strip().lower()[:8] or "ru"
            oauth_rows = oauth_by_user.get(source_id, [])

            candidates = await self._identity_candidates(row, oauth_rows, panel_uuid)
            if len(candidates) > 1:
                self.summary["identity_conflicts"].append(
                    {"source_user_id": source_id, "target_user_ids": sorted(candidates)}
                )
                self.summary["users"]["conflict"] += 1
                continue
            target_id = next(
                iter(candidates),
                remnashop_target_user_id(source_id, telegram_id),
            )
            existing = await self.target.get(User, target_id)
            if existing is not None and not candidates:
                self.summary["identity_conflicts"].append(
                    {"source_user_id": source_id, "target_user_ids": [target_id]}
                )
                self.summary["users"]["conflict"] += 1
                continue
            if existing and self.on_conflict == "skip":
                target = existing
                self.summary["users"]["skipped"] += 1
            elif existing:
                target = existing
                if self._can_merge_existing():
                    self._merge_existing_user_profile(
                        target,
                        username=row.get("username"),
                        first_name=first_name,
                        last_name=last_name,
                        language=language,
                    )
                    self._assign_if_allowed(target, "panel_user_uuid", panel_uuid)
                    if _truthy(row.get("is_email_verified")):
                        self._assign_if_allowed(target, "email", email.lower() if email else None)
                        self._assign_if_allowed(target, "notification_email", email)
                        self._assign_if_allowed(
                            target,
                            "email_verified_at",
                            _as_utc(row.get("updated_at") or row.get("created_at"))
                            or datetime.now(UTC),
                        )
                    if bool(row.get("is_blocked")):
                        target.is_banned = True
                    elif self._can_overwrite():
                        target.is_banned = False
                    if bool(row.get("is_bot_blocked")):
                        target.telegram_notifications_status = "blocked"
                        target.telegram_notifications_checked_at = datetime.now(UTC)
                        target.telegram_notifications_blocked_at = datetime.now(UTC)
                    if (
                        referral_code
                        and len(referral_code) <= 64
                        and not target.referral_code
                        and not await self._source_referral_code_conflicts(
                            referral_code,
                            int(target.user_id),
                        )
                    ):
                        target.referral_code = referral_code
                    self.summary["users"]["updated"] += 1
            else:
                new_referral_code = None
                if referral_code and len(referral_code) <= 64:
                    conflict = await self._source_referral_code_conflicts(
                        referral_code,
                        target_id,
                    )
                    if not conflict:
                        new_referral_code = referral_code

                import_email = email.lower() if email else None
                if import_email and not _truthy(row.get("is_email_verified")):
                    email_owner = await self.target.execute(
                        select(User.user_id).where(func.lower(User.email) == import_email)
                    )
                    address_owner = await self.target.execute(
                        select(UserEmailAddress.user_id).where(
                            func.lower(UserEmailAddress.email) == import_email
                        )
                    )
                    if (
                        email_owner.scalar_one_or_none() is not None
                        or address_owner.scalar_one_or_none() is not None
                    ):
                        import_email = None
                        self.summary["users"]["unverified_email_conflict"] += 1

                user_data = {
                    "user_id": target_id,
                    "telegram_id": telegram_id,
                    "username": row.get("username"),
                    "email": import_email,
                    "email_verified_at": (
                        _as_utc(row.get("updated_at") or row.get("created_at")) or datetime.now(UTC)
                    )
                    if email and _truthy(row.get("is_email_verified"))
                    else None,
                    "notification_email": email
                    if email and _truthy(row.get("is_email_verified"))
                    else None,
                    "first_name": first_name,
                    "last_name": last_name,
                    "language_code": language,
                    "registration_date": created_at,
                    "is_banned": bool(row.get("is_blocked")),
                    "panel_user_uuid": panel_uuid,
                    "referral_code": new_referral_code,
                    "telegram_notifications_status": "blocked"
                    if bool(row.get("is_bot_blocked"))
                    else "unknown",
                    "telegram_notifications_checked_at": datetime.now(UTC)
                    if bool(row.get("is_bot_blocked"))
                    else None,
                    "telegram_notifications_blocked_at": datetime.now(UTC)
                    if bool(row.get("is_bot_blocked"))
                    else None,
                }
                if isinstance(self.target, DryRunSession):
                    target = User(**user_data)
                    self.target.add(target)
                    await self.target.flush()
                    created = True
                else:
                    target, created = await user_dal.create_user(
                        self.target,
                        user_data,
                        # Bulk migration import, not a live registration.
                        registered_via=None,
                    )
                self.summary["users"]["created" if created else "updated"] += 1

            if not target:
                self.summary["users"]["skipped"] += 1
                continue

            self.user_map[source_id] = int(target.user_id)
            if telegram_id is not None:
                self.telegram_user_map[telegram_id] = int(target.user_id)
            if referral_code:
                await self._upsert_legacy_referral_code(code=referral_code, user_id=target.user_id)

            await self._import_identities(row=row, oauth_rows=oauth_rows, target=target)

            metadata = _legacy_user_metadata(row)
            if panel_uuid:
                metadata["panel_user_uuid"] = panel_uuid
            await self._upsert_mapping(
                entity_type="user",
                source_id=source_id,
                target_table="users",
                target_id=target.user_id,
                metadata=metadata,
            )
            await self._record_user_state_note(
                source_id=source_id,
                user_id=int(target.user_id),
                metadata=metadata,
            )

        await self.target.flush()

    async def import_referrals(self) -> None:
        rows = await self._fetch_rows("referrals", order_by="id")
        for row in rows:
            referrer_id = await self._mapped_user_id(row.get("referrer_id"))
            referred_id = await self._mapped_user_id(row.get("referred_id"))
            referrer = (
                await self.target.get(User, referrer_id)
                if referrer_id
                else await self._target_user_for_telegram(row.get("referrer_telegram_id"))
            )
            referred = (
                await self.target.get(User, referred_id)
                if referred_id
                else await self._target_user_for_telegram(row.get("referred_telegram_id"))
            )
            if not referrer or not referred or referrer.user_id == referred.user_id:
                self.summary["referrals"]["skipped"] += 1
                continue
            if referred.referred_by_id and not self._can_overwrite():
                self.summary["referrals"]["skipped"] += 1
                continue
            referred.referred_by_id = int(referrer.user_id)
            self.summary["referrals"]["updated"] += 1
            await self._upsert_mapping(
                entity_type="referral",
                source_id=row.get("id") or f"{referrer.user_id}:{referred.user_id}",
                target_table="users",
                target_id=referred.user_id,
                metadata={
                    "referrer_user_id": referrer.user_id,
                    "referred_user_id": referred.user_id,
                },
            )
        await self.target.flush()
