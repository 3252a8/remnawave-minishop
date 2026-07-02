import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra.redis import cache_get_json, cache_set_json, redis_key
from bot.utils.text_sanitizer import sanitize_display_name, sanitize_username
from config.settings import Settings
from db.dal import user_dal

logger = logging.getLogger(__name__)

_LOCAL_PROFILE_SYNC_CHECKS: dict[int, float] = {}


class ProfileSyncMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session = cast(AsyncSession | None, data.get("session"))
        tg_user: TgUser | None = data.get("event_from_user")
        settings: Settings | None = data.get("settings")

        if session and tg_user:
            if settings and await _profile_sync_recently_checked(settings, int(tg_user.id)):
                return await handler(event, data)

            try:
                db_user = await user_dal.get_user_by_telegram_id(session, tg_user.id)
                if not db_user:
                    db_user = await user_dal.get_user_by_id(session, tg_user.id)
                if db_user:
                    update_payload: dict[str, Any] = {}
                    sanitized_username = sanitize_username(tg_user.username)
                    sanitized_first_name = sanitize_display_name(tg_user.first_name)
                    sanitized_last_name = sanitize_display_name(tg_user.last_name)

                    if db_user.telegram_id != tg_user.id:
                        update_payload["telegram_id"] = tg_user.id
                    if db_user.username != sanitized_username:
                        update_payload["username"] = sanitized_username
                    if db_user.first_name != sanitized_first_name:
                        update_payload["first_name"] = sanitized_first_name
                    if db_user.last_name != sanitized_last_name:
                        update_payload["last_name"] = sanitized_last_name

                    if update_payload:
                        await user_dal.update_user(session, db_user.user_id, update_payload)
                        logger.info(
                            "ProfileSyncMiddleware: Updated user %s profile fields: %s",
                            tg_user.id,
                            list(update_payload.keys()),
                        )

                        # Keep panel identity fields fresh, but do not rewrite
                        # description from profile changes. Remnawave may return
                        # description with lossy encoding in list views.
                        try:
                            panel_service = data.get("panel_service")
                            if panel_service and db_user.panel_user_uuid:
                                panel_payload = {
                                    "telegramId": tg_user.id,
                                }
                                if db_user.email:
                                    panel_payload["email"] = db_user.email
                                await panel_service.update_user_details_on_panel(
                                    db_user.panel_user_uuid,
                                    panel_payload,
                                )
                        except Exception as e_upd_desc:
                            logger.warning(
                                "ProfileSyncMiddleware: Failed to update panel identity for user "
                                "%s: %s",
                                tg_user.id,
                                e_upd_desc,
                            )
            except Exception as e:
                logger.exception(
                    "ProfileSyncMiddleware: Failed to sync profile for user %s: %s",
                    getattr(tg_user, "id", "N/A"),
                    e,
                )
            finally:
                if settings:
                    await _mark_profile_sync_checked(settings, int(tg_user.id))

        return await handler(event, data)


async def _profile_sync_recently_checked(settings: Settings, telegram_id: int) -> bool:
    ttl_seconds = int(settings.PROFILE_SYNC_CACHE_TTL_SECONDS or 0)
    if ttl_seconds <= 0:
        return False

    now = time.monotonic()
    expires_at = _LOCAL_PROFILE_SYNC_CHECKS.get(telegram_id)
    if expires_at and expires_at > now:
        return True

    key = redis_key(settings, "cache", "profile-sync", telegram_id)
    try:
        cached = await cache_get_json(settings, key)
    except Exception:
        cached = None
    if cached:
        _LOCAL_PROFILE_SYNC_CHECKS[telegram_id] = now + ttl_seconds
        return True
    return False


async def _mark_profile_sync_checked(settings: Settings, telegram_id: int) -> None:
    ttl_seconds = int(settings.PROFILE_SYNC_CACHE_TTL_SECONDS or 0)
    if ttl_seconds <= 0:
        return

    _LOCAL_PROFILE_SYNC_CHECKS[telegram_id] = time.monotonic() + ttl_seconds
    key = redis_key(settings, "cache", "profile-sync", telegram_id)
    with contextlib.suppress(Exception):
        await cache_set_json(settings, key, {"checked": True}, ttl_seconds)
