"""Check the configured refresh schedule using the Minishop worker lifecycle."""

import asyncio
import logging

from bot.plugins.packages import generation_is_current
from bot.plugins.spec import PluginContext

from .refresh import refresh_sources

logger = logging.getLogger(__name__)


async def run_refresh_worker(ctx: PluginContext) -> None:
    session_factory = ctx.require_session_factory()
    while generation_is_current():
        try:
            await refresh_sources(session_factory)
        except Exception:
            logger.error("Blacklist refresh failed before source status could be recorded")
        await asyncio.sleep(30)
