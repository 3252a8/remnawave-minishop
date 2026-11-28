"""Notify each linked administrator once per published revision."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from html import escape

from aiogram.exceptions import TelegramAPIError
from aiogram.types import LinkPreviewOptions
from redis.exceptions import RedisError

from bot.infra.redis import get_redis, redis_key, redis_lock
from bot.plugins.spec import PluginContext
from bot.services.core_update_publications import build_publication, publication_time
from bot.services.core_updates import (
    Release,
    available,
    check_image,
    image_tag,
    notifications_enabled,
    notifications_key,
)
from bot.utils.app_version import resolve_app_version, resolve_build_provenance

logger = logging.getLogger(__name__)
_NOTICE_TIMEZONE = timezone(timedelta(hours=3))


def _version_details(version: str, revision: str, published_at: datetime | None) -> str:
    label = escape(version)
    if revision:
        label = f'<a href="https://gitlab.com/3252a8/remnawave-minishop/-/commit/{revision}">{label}</a>'
    if published_at:
        return f"{label}, {published_at.astimezone(_NOTICE_TIMEZONE):%d.%m.%Y %H:%M} UTC+3"
    return label


async def deliver_update_notices(ctx: PluginContext) -> None:
    notifier = ctx.notification_service
    if not ctx.bot or not notifier or resolve_build_provenance() != "official":
        return
    settings = ctx.settings
    redis = await get_redis(settings)
    prefix = redis_key(settings, "core-update")
    tag = image_tag()
    if redis is None or not notifications_enabled(
        tag, await redis.get(notifications_key(prefix, tag))
    ):
        return
    async with redis_lock(settings, "core-update-notices", ttl_seconds=120) as acquired:
        if not acquired:
            return
        registry = await redis.get(f"{prefix}:registry")
        release = await check_image(tag, "ghcr.io" if registry == "ghcr.io" else "docker.io")
        if not release or not available(release):
            return
        text = None
        for chat_id in await notifier.admin_telegram_ids():
            mode = "dev:" if tag == "dev" else ""
            key = f"{prefix}:notified:{mode}{chat_id}"
            if await redis.get(key) == release.revision:
                continue
            if text is None:
                text = await _notice_text(ctx, release)
            try:
                await ctx.bot.send_message(
                    chat_id,
                    text,
                    parse_mode="HTML",
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
            except TelegramAPIError:
                logger.warning("Core update notification could not be delivered")
                continue
            await redis.set(key, release.revision)


async def _notice_text(ctx: PluginContext, release: Release) -> str:
    current = resolve_app_version()
    current_label, current_revision = build_publication(current)
    current_time, release_time = await asyncio.gather(
        publication_time(current_label, current_revision),
        publication_time("dev" if release.tag == "dev" else release.version, release.revision),
    )
    current = current.removesuffix(current_revision) + current_revision[:8]
    return ctx.require_i18n().gettext(
        ctx.settings.DEFAULT_LANGUAGE,
        "admin_core_update_publication_telegram",
        current=_version_details(current, current_revision, current_time),
        version=_version_details(release.version, release.revision, release_time),
    )


async def run_core_update_notices(ctx: PluginContext) -> None:
    while True:
        try:
            await deliver_update_notices(ctx)
        except (RedisError, OSError, TimeoutError):
            logger.warning("Core update notifications temporarily unavailable")
        await asyncio.sleep(900)
