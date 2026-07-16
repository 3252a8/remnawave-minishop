import json
import logging
import time
from typing import Any, cast

from bot.infra.redis import get_redis, redis_key
from config.settings import Settings

logger = logging.getLogger(__name__)

_WEBHOOK_DEDUPE_TTL_SECONDS = 24 * 60 * 60
_ENQUEUE_DEDUPED_WEBHOOK_SCRIPT = """
if redis.call("exists", KEYS[1]) == 1 then
    return 0
end
-- Queue first because Redis does not roll back earlier Lua writes after a later error.
redis.call("lpush", KEYS[2], ARGV[2])
redis.call("set", KEYS[1], "1", "EX", ARGV[1])
return 1
"""


def webhook_queue_key(settings: Settings) -> str:
    return cast(str, redis_key(settings, "queue", settings.WEBHOOK_QUEUE_NAME))


async def enqueue_webhook_event(
    settings: Settings,
    provider: str,
    payload: dict[str, Any],
    *,
    event_id: str | None = None,
) -> bool:
    redis = await get_redis(settings)
    if redis is None:
        return False

    try:
        dedupe_id = event_id or payload.get("id") or payload.get("event_id")
        message = {
            "provider": provider,
            "event_id": dedupe_id,
            "payload": payload,
            "enqueued_at": time.time(),
        }
        serialized_message = json.dumps(message, ensure_ascii=False)
        queue_key = webhook_queue_key(settings)
        if dedupe_id:
            dedupe_key = redis_key(settings, "webhook", "seen", provider, dedupe_id)
            enqueued = await redis.eval(
                _ENQUEUE_DEDUPED_WEBHOOK_SCRIPT,
                2,
                dedupe_key,
                queue_key,
                _WEBHOOK_DEDUPE_TTL_SECONDS,
                serialized_message,
            )
            if not enqueued:
                logger.info("Skipping duplicate %s webhook event %s", provider, dedupe_id)
            return True

        await redis.lpush(queue_key, serialized_message)
        return True
    except Exception as exc:
        logger.warning("Redis webhook enqueue failed for %s: %s", provider, exc)
        return False


async def pop_webhook_event(settings: Settings, timeout_seconds: int = 5) -> dict | None:
    redis = await get_redis(settings)
    if redis is None:
        return None
    try:
        item = await redis.brpop(webhook_queue_key(settings), timeout=timeout_seconds)
    except Exception as exc:
        logger.warning("Redis webhook pop failed: %s", exc)
        return None
    if not item:
        return None
    _, raw = item
    try:
        decoded = json.loads(raw)
        return decoded if isinstance(decoded, dict) else None
    except json.JSONDecodeError:
        logger.warning("Invalid webhook queue payload discarded")
        return None


async def webhook_queue_depth(settings: Settings) -> int:
    redis = await get_redis(settings)
    if redis is None:
        return 0
    try:
        return int(await redis.llen(webhook_queue_key(settings)))
    except Exception as exc:
        logger.warning("Redis webhook queue depth failed: %s", exc)
        return 0
