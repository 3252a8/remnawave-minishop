"""Best-effort user audit for explicitly published plugin events."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from bot.infra import events
from db.dal import message_log_dal, user_dal

if TYPE_CHECKING:
    from .spec import PluginContext

logger = logging.getLogger(__name__)


async def emit_plugin_event(
    ctx: PluginContext,
    plugin_name: str,
    event_name: str,
    payload: dict[str, Any],
    *,
    content: str | None = None,
) -> None:
    """Audit a plugin event, then deliver the original public bus payload.

    Only an existing internal ``user_id`` is attributed. Payloads are never
    copied into logs; callers may explicitly supply a safe human summary.
    Audit errors must not prevent delivery to existing event subscribers.
    """
    if (
        not plugin_name
        or not event_name
        or any(char in plugin_name + event_name for char in "\r\n")
        or ":" in plugin_name
    ):
        raise ValueError("Plugin and event names must be nonempty single-line identifiers")

    user_id = payload.get("user_id")
    if type(user_id) is int and -(2**63) <= user_id < 2**63 and ctx.session_factory is not None:
        try:
            async with ctx.session_factory() as session:
                user = await user_dal.get_user_by_id(session, user_id)
                if user is not None:
                    await message_log_dal.create_message_log(
                        session,
                        {
                            "user_id": user_id,
                            "telegram_username": user.username,
                            "telegram_first_name": user.first_name,
                            "event_type": f"plugin:{plugin_name}:{event_name}",
                            "content": (content if content is not None else event_name)[:1000],
                            "is_admin_event": False,
                            "target_user_id": None,
                            "timestamp": datetime.now(UTC),
                        },
                    )
        except Exception:
            logger.exception("Failed to audit plugin %s event %s", plugin_name, event_name)

    await events.emit(event_name, payload)
