"""Isolated bulk loading of trusted, namespaced message shortcode values."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from bot.plugins.extensions import MessageShortcode, MessageShortcodeContext
from bot.plugins.extensions.registry import get_registry
from bot.plugins.packages import generation_is_current

if TYPE_CHECKING:
    from bot.services.broadcast_personalization import BroadcastUserContext

logger = logging.getLogger(__name__)


def plugin_shortcodes() -> dict[str, tuple[str, MessageShortcode]]:
    if not generation_is_current():
        return {}
    return {
        f"{owner}.{spec.id}": (owner, spec)
        for owner, entry in get_registry().owners().items()
        for spec in entry.contributions.message_shortcodes
    }


async def load_plugin_shortcodes(
    context: MessageShortcodeContext,
    contexts: dict[int, BroadcastUserContext],
    needed: set[str],
) -> None:
    for name, (_, spec) in plugin_shortcodes().items():
        if name not in needed:
            continue
        try:
            # A bad plugin query must not poison the enclosing broadcast transaction.
            async with (
                context.session.begin_nested(),
                asyncio.timeout(15 if spec.cost == "panel" else 5),
            ):
                values = await spec.resolve(context)
                if not isinstance(values, dict) or any(
                    type(uid) is not int
                    or uid not in contexts
                    or (value is not None and (not isinstance(value, str) or len(value) > 8192))
                    for uid, value in values.items()
                ):
                    raise ValueError("invalid_message_shortcode_values")
            for user_id, value in values.items():
                if value is not None:
                    contexts[user_id].plugin_values[name] = value
        except Exception:
            logger.warning("Plugin shortcode %s unavailable", name, exc_info=True)
