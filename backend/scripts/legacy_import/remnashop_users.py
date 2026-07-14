"""User and referral import, legacy referral code preservation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.dal import user_dal
from db.models import (
    LegacyReferralCode,
    MessageLog,
)

from .common import (
    SOURCE,
    _as_utc,
    _json_dumps,
    _split_name,
    _to_int,
)
from .remnashop_data import (
    _legacy_user_metadata,
)
from .remnashop_tariffs import _RemnashopTariffsSection

logger = logging.getLogger(__name__)


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
        telegram_id: int,
        user_id: int,
        metadata: dict[str, Any],
    ) -> None:
        if not metadata:
            return
        if await self._get_mapping("user_state", telegram_id):
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
            source_id=telegram_id,
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

    async def import_users(self) -> None:
        rows = await self._fetch_rows("users", order_by="telegram_id")
        panel_by_tg = await self._latest_panel_uuid_by_telegram()
        for row in rows:
            self._remember_source_user(row)
            telegram_id = _to_int(row.get("telegram_id"))
            if telegram_id is None:
                self.summary["users"]["skipped"] += 1
                continue

            first_name, last_name = _split_name(row.get("name"))
            panel_uuid = panel_by_tg.get(telegram_id)
            referral_code = str(row.get("referral_code") or "").strip() or None
            created_at = _as_utc(row.get("created_at")) or datetime.now(UTC)
            language = str(row.get("language") or "ru").strip().lower()[:8] or "ru"

            existing = await self._target_user_for_telegram(telegram_id)
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
                        telegram_id,
                    )
                    if not conflict:
                        new_referral_code = referral_code

                target, created = await user_dal.create_user(
                    self.target,
                    {
                        "user_id": telegram_id,
                        "telegram_id": telegram_id,
                        "username": row.get("username"),
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
                    },
                    # Bulk migration import, not a live registration.
                    registered_via=None,
                )
                self.summary["users"]["created" if created else "updated"] += 1

            if not target:
                self.summary["users"]["skipped"] += 1
                continue

            self.user_map[telegram_id] = int(target.user_id)
            if referral_code:
                await self._upsert_legacy_referral_code(code=referral_code, user_id=target.user_id)

            metadata = _legacy_user_metadata(row)
            if panel_uuid:
                metadata["panel_user_uuid"] = panel_uuid
            await self._upsert_mapping(
                entity_type="user",
                source_id=telegram_id,
                target_table="users",
                target_id=target.user_id,
                metadata=metadata,
            )
            await self._record_user_state_note(
                telegram_id=telegram_id,
                user_id=int(target.user_id),
                metadata=metadata,
            )

        await self.target.flush()

    async def import_referrals(self) -> None:
        rows = await self._fetch_rows("referrals", order_by="id")
        for row in rows:
            referrer_telegram_id = await self._source_row_telegram_id(
                row,
                user_id_key="referrer_id",
                telegram_id_key="referrer_telegram_id",
            )
            referred_telegram_id = await self._source_row_telegram_id(
                row,
                user_id_key="referred_id",
                telegram_id_key="referred_telegram_id",
            )
            referrer = await self._target_user_for_telegram(referrer_telegram_id)
            referred = await self._target_user_for_telegram(referred_telegram_id)
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
