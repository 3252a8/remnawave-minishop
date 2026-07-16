import json
import logging
import time
from dataclasses import dataclass
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
_MOVE_CLAIMED_WEBHOOK_SCRIPT = """
local removed = redis.call("lrem", KEYS[1], 1, ARGV[1])
if removed == 1 then
    redis.call("lpush", KEYS[2], ARGV[2])
end
return removed
"""


@dataclass(frozen=True, slots=True)
class ClaimedWebhookEvent:
    event: dict[str, Any]
    raw: str


def webhook_queue_key(settings: Settings) -> str:
    return cast(str, redis_key(settings, "queue", settings.WEBHOOK_QUEUE_NAME))


def webhook_processing_queue_key(settings: Settings) -> str:
    return cast(str, redis_key(settings, "queue", settings.WEBHOOK_QUEUE_NAME, "processing"))


def webhook_dead_letter_queue_key(settings: Settings) -> str:
    return cast(str, redis_key(settings, "queue", settings.WEBHOOK_QUEUE_NAME, "dead-letter"))


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


async def pop_webhook_event(
    settings: Settings,
    timeout_seconds: int = 5,
) -> ClaimedWebhookEvent | None:
    redis = await get_redis(settings)
    if redis is None:
        return None
    try:
        raw = await redis.blmove(
            webhook_queue_key(settings),
            webhook_processing_queue_key(settings),
            timeout_seconds,
            src="RIGHT",
            dest="LEFT",
        )
    except Exception as exc:
        logger.warning("Redis webhook pop failed: %s", exc)
        return None
    if not raw:
        return None
    try:
        decoded = json.loads(raw)
        if isinstance(decoded, dict):
            return ClaimedWebhookEvent(event=decoded, raw=raw)
    except json.JSONDecodeError:
        pass
    logger.warning("Invalid webhook queue payload discarded")
    try:
        await redis.lrem(webhook_processing_queue_key(settings), 1, raw)
    except Exception as exc:
        logger.warning("Failed to discard invalid webhook queue payload: %s", exc)
    return None


async def acknowledge_webhook_event(
    settings: Settings,
    claimed: ClaimedWebhookEvent,
) -> bool:
    redis = await get_redis(settings)
    if redis is None:
        return False
    try:
        removed = await redis.lrem(webhook_processing_queue_key(settings), 1, claimed.raw)
        return bool(removed)
    except Exception as exc:
        logger.warning("Redis webhook acknowledgement failed: %s", exc)
        return False


async def _move_claimed_webhook_event(
    settings: Settings,
    claimed: ClaimedWebhookEvent,
    destination_key: str,
    event: dict[str, Any],
) -> bool:
    redis = await get_redis(settings)
    if redis is None:
        return False
    try:
        moved = await redis.eval(
            _MOVE_CLAIMED_WEBHOOK_SCRIPT,
            2,
            webhook_processing_queue_key(settings),
            destination_key,
            claimed.raw,
            json.dumps(event, ensure_ascii=False),
        )
        return bool(moved)
    except Exception as exc:
        logger.warning("Redis webhook move failed: %s", exc)
        return False


async def retry_webhook_event(
    settings: Settings,
    claimed: ClaimedWebhookEvent,
    *,
    delivery_attempts: int,
) -> bool:
    event = dict(claimed.event)
    event["delivery_attempts"] = delivery_attempts
    event["last_failed_at"] = time.time()
    return await _move_claimed_webhook_event(
        settings,
        claimed,
        webhook_queue_key(settings),
        event,
    )


async def dead_letter_webhook_event(
    settings: Settings,
    claimed: ClaimedWebhookEvent,
    *,
    delivery_attempts: int,
    error: BaseException,
) -> bool:
    event = dict(claimed.event)
    event["delivery_attempts"] = delivery_attempts
    event["last_failed_at"] = time.time()
    event["last_error"] = f"{type(error).__name__}: {error}"[:500]
    return await _move_claimed_webhook_event(
        settings,
        claimed,
        webhook_dead_letter_queue_key(settings),
        event,
    )


async def recover_webhook_events(settings: Settings) -> int:
    """Return unacknowledged events to the ready queue before consumers start."""
    redis = await get_redis(settings)
    if redis is None:
        return 0

    recovered = 0
    try:
        while await redis.lmove(
            webhook_processing_queue_key(settings),
            webhook_queue_key(settings),
            src="RIGHT",
            dest="LEFT",
        ):
            recovered += 1
    except Exception as exc:
        logger.warning("Redis webhook recovery failed after %s event(s): %s", recovered, exc)
    return recovered


async def webhook_queue_depth(settings: Settings) -> int:
    redis = await get_redis(settings)
    if redis is None:
        return 0
    try:
        return int(await redis.llen(webhook_queue_key(settings)))
    except Exception as exc:
        logger.warning("Redis webhook queue depth failed: %s", exc)
        return 0
