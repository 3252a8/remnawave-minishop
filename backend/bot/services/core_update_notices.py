"""Notify each linked administrator once per published revision."""

from __future__ import annotations

import asyncio
import logging

from aiogram.exceptions import TelegramAPIError
from redis.exceptions import RedisError

from bot.infra.redis import get_redis, redis_key, redis_lock
from bot.plugins.spec import PluginContext
from bot.services.core_updates import available, check_image, image_tag
from bot.utils.app_version import resolve_app_version, resolve_build_provenance

logger = logging.getLogger(__name__)


async def deliver_update_notices(ctx: PluginContext) -> None:
    notifier = ctx.notification_service
    if not ctx.bot or not notifier or resolve_build_provenance() != "official":
        return
    settings = ctx.settings
    redis = await get_redis(settings)
    prefix = redis_key(settings, "core-update")
    if redis is None or await redis.get(f"{prefix}:notify") == "0":
        return
    async with redis_lock(settings, "core-update-notices", ttl_seconds=120) as acquired:
        if not acquired:
            return
        registry = await redis.get(f"{prefix}:registry")
        release = await check_image(
            image_tag(), "ghcr.io" if registry == "ghcr.io" else "docker.io"
        )
        if not release or not available(release):
            return
        text = ctx.require_i18n().gettext(
            settings.DEFAULT_LANGUAGE,
            "admin_core_update_telegram",
            current=resolve_app_version(),
            version=release.version,
            tag=release.tag,
        )
        for chat_id in await notifier.admin_telegram_ids():
            key = f"{prefix}:notified:{chat_id}"
            if await redis.get(key) == release.revision:
                continue
            try:
                await ctx.bot.send_message(chat_id, text, parse_mode=None)
            except TelegramAPIError:
                logger.warning("Core update notification could not be delivered")
                continue
            await redis.set(key, release.revision)


async def run_core_update_notices(ctx: PluginContext) -> None:
    while True:
        try:
            await deliver_update_notices(ctx)
        except (RedisError, OSError, TimeoutError):
            logger.warning("Core update notifications temporarily unavailable")
        await asyncio.sleep(900)
