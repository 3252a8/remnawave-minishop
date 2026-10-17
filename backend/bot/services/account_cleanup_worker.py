"""Opt-in deletion of provably unused Telegram accounts, panel first."""

import asyncio
import json
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import sessionmaker

from bot.app.web.webapp.cache_helpers import invalidate_webapp_user_caches
from bot.infra.redis import cache_delete_pattern, redis_key, redis_lock
from bot.services.panel_activity import panel_user_is_confirmed_unused
from bot.services.panel_api_service import PanelApiService
from bot.services.settings_override_service import refresh_overrides_from_db
from config.settings import Settings
from db.dal import account_cleanup_dal, message_log_dal, subscription_dal, user_dal

logger = logging.getLogger(__name__)
CLEANUP_SETTING_KEYS = {
    "UNUSED_ACCOUNTS_CLEANUP_ENABLED",
    "UNUSED_ACCOUNTS_NO_TRIAL_ENABLED",
    "UNUSED_ACCOUNTS_UNUSED_TRIAL_ENABLED",
    "UNUSED_ACCOUNTS_NO_TRIAL_DAYS",
    "UNUSED_ACCOUNTS_UNUSED_TRIAL_DAYS",
}


class AccountCleanupWorker:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker,
        panel_service: PanelApiService,
    ):
        self.settings = settings
        self.session_factory = session_factory
        self.panel_service = panel_service
        self.after_id = 0

    async def run(self) -> None:
        while True:
            try:
                await refresh_overrides_from_db(
                    self.settings, self.session_factory, keys=CLEANUP_SETTING_KEYS
                )
                await self.tick()
            except Exception:
                logger.exception("Unused-account cleanup tick failed")
            await asyncio.sleep(300)

    async def tick(self) -> None:
        if not self.settings.UNUSED_ACCOUNTS_CLEANUP_ENABLED or self.settings.panel_dry_run_enabled:
            return
        async with redis_lock(self.settings, "unused-account-cleanup", ttl_seconds=900) as acquired:
            if not acquired:
                return
            async with self.session_factory() as session:
                ids = await account_cleanup_dal.cleanup_candidate_ids(
                    session, self.settings, datetime.now(UTC), self.after_id
                )
            self.after_id = ids[-1] if ids else 0
            for user_id in ids:
                try:
                    await refresh_overrides_from_db(
                        self.settings, self.session_factory, keys=CLEANUP_SETTING_KEYS
                    )
                    await self.cleanup_user(user_id)
                except Exception:
                    logger.exception("Unused-account cleanup failed for user_id=%s", user_id)

    async def cleanup_user(self, user_id: int) -> bool:
        if not self.settings.UNUSED_ACCOUNTS_CLEANUP_ENABLED or self.settings.panel_dry_run_enabled:
            return False
        async with self.session_factory() as session:
            # Entitlement changes take this same row lock. Recheck eligibility after it.
            user = await user_dal.lock_user_by_id(session, user_id)
            now = datetime.now(UTC)
            if user is None or not await account_cleanup_dal.still_cleanup_candidate(
                session, self.settings, now, user_id
            ):
                return False
            uuids = await user_dal.get_panel_user_uuids_for_user(session, user_id, user=user)
            if user.__dict__.get("panel_user_uuid") and not uuids:
                return False
            account_id = str(user.__dict__["account_id"])
            intent = await account_cleanup_dal.get_cleanup_intent(session, account_id)
            resumable = intent is not None and json.loads(intent.panel_uuids) == sorted(uuids)
            for panel_uuid in uuids:
                if await account_cleanup_dal.panel_identity_is_shared(session, user_id, panel_uuid):
                    return False
                lookup = await self.panel_service.get_user_by_uuid_lookup(
                    panel_uuid, log_response=False
                )
                if resumable and lookup.get("not_found") is True:
                    continue
                # Unknown/missing panel state is never evidence of "never connected".
                if not lookup.get("ok") or not panel_user_is_confirmed_unused(
                    lookup.get("user"), now
                ):
                    return False
            # For the no-trial rule a panel UUID is still verified above; no UUID means
            # no panel identity to delete. A trial without an identity is ambiguous.
            telegram_id = int(user.__dict__["telegram_id"])
            is_trial = await subscription_dal.has_any_subscription_for_user(session, user_id)
            if is_trial and not uuids:
                return False
            if not resumable:
                await account_cleanup_dal.save_cleanup_intent(
                    session, account_id, json.dumps(sorted(uuids)), now
                )
                # Durable intent makes a confirmed 404 safe on retry after a panel
                # deletion succeeded but the shop transaction failed or crashed.
                await session.commit()
                user = await user_dal.lock_user_by_id(session, user_id)
                if (
                    user is None
                    or str(user.__dict__["account_id"]) != account_id
                    or not await account_cleanup_dal.still_cleanup_candidate(
                        session, self.settings, datetime.now(UTC), user_id
                    )
                    or sorted(
                        await user_dal.get_panel_user_uuids_for_user(session, user_id, user=user)
                    )
                    != sorted(uuids)
                ):
                    return False
            for panel_uuid in uuids:
                deleted = await self.panel_service.delete_user_from_panel(
                    panel_uuid, log_response=False
                )
                if not deleted:
                    lookup = await self.panel_service.get_user_by_uuid_lookup(
                        panel_uuid, log_response=False
                    )
                    if lookup.get("not_found") is not True:
                        return False
            if is_trial:
                await account_cleanup_dal.remember_cleaned_trial(session, telegram_id, now)
            if not await user_dal.delete_user_and_relations(session, user_id):
                await session.rollback()
                return False
            await message_log_dal.create_message_log_no_commit(
                session,
                {
                    "event_type": "unused_account_cleanup",
                    "is_admin_event": True,
                    "content": (
                        f"Deleted unused account user_id={user_id}; "
                        f"panel_accounts={len(uuids)}; trial={is_trial}"
                    ),
                },
            )
            await session.commit()
            logger.info("Unused-account cleanup committed for user_id=%s", user_id)
        await invalidate_webapp_user_caches(self.settings, user_id, include_devices=True)
        await cache_delete_pattern(
            self.settings, redis_key(self.settings, "trial-captcha", user_id, "*")
        )
        await cache_delete_pattern(
            self.settings, redis_key(self.settings, "cache", "admin:users_list", "*")
        )
        return True
