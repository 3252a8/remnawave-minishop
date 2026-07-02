import asyncio
import contextlib
import hashlib
import logging
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from bot.infra.redis import get_redis, redis_key
from config.settings import Settings

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_SECONDS = 60
DEFAULT_MAX_UPDATES_PER_WINDOW = 180
DEFAULT_MESSAGE_MAX_PER_WINDOW = 120
DEFAULT_CALLBACK_MAX_PER_WINDOW = 240
DEFAULT_INLINE_MAX_PER_WINDOW = 60
DEFAULT_START_MAX_PER_WINDOW = 30
DEFAULT_EXPENSIVE_CALLBACK_MAX_PER_WINDOW = 60
DEFAULT_PAYMENT_CALLBACK_COOLDOWN_SECONDS = 20
DEFAULT_TRIAL_CALLBACK_COOLDOWN_SECONDS = 30

EXPENSIVE_CALLBACK_PREFIXES = (
    "pay_",
    "trial_action:confirm_activate",
    "main_action:request_trial",
    "main_action:apply_promo",
    "main_action:bot_apply_promo",
    "tariff_change:apply:",
    "tariff_change:confirm_pay:",
    "tariff_change:pay:",
    "autorenew:confirm:",
    "disconnect_device:",
)

TRIAL_CALLBACK_PREFIXES = (
    "trial_action:confirm_activate",
    "main_action:request_trial",
)


@dataclass(frozen=True)
class RateLimitRule:
    window_seconds: int
    max_events: int


class UpdateAntiFloodMiddleware(BaseMiddleware):
    """Drop extreme update floods before DB-backed middleware runs."""

    def __init__(
        self,
        settings: Settings,
        *,
        default_rule: RateLimitRule | None = None,
        action_rules: dict[str, RateLimitRule] | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.default_rule = default_rule or RateLimitRule(
            window_seconds=int(
                settings.TELEGRAM_ANTIFLOOD_WINDOW_SECONDS or DEFAULT_WINDOW_SECONDS
            ),
            max_events=int(
                settings.TELEGRAM_ANTIFLOOD_MAX_UPDATES_PER_WINDOW or DEFAULT_MAX_UPDATES_PER_WINDOW
            ),
        )
        self.action_rules = action_rules or _default_action_rules(settings)
        self._local_buckets: dict[str, deque[float]] = defaultdict(deque)
        self._local_cooldowns: dict[str, float] = {}
        self._local_lock = asyncio.Lock()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        update = cast(Update, event)

        if bool(getattr(self.settings, "TELEGRAM_DROP_NON_PRIVATE_UPDATES", True)):
            chat_type = _message_or_callback_chat_type(update)
            if chat_type is not None and chat_type != "private":
                logger.info(
                    "Telegram update dropped outside private chat: chat_type=%s update_type=%s",
                    chat_type,
                    getattr(update, "event_type", "unknown"),
                )
                _mark_dropped(data)
                return None

        if not bool(getattr(self.settings, "TELEGRAM_ANTIFLOOD_ENABLED", True)):
            return await handler(event, data)

        actor_key = _update_actor_key(update)
        if not actor_key:
            return await handler(event, data)

        action_key = _update_action_key(update)
        cooldown = _update_action_cooldown(update, self.settings)
        if cooldown and await self._is_cooldown_active(cooldown[0], cooldown[1]):
            logger.info(
                "Telegram callback dropped by action cooldown: actor=%s cooldown=%s",
                actor_key,
                cooldown[0],
            )
            _mark_dropped(data)
            await _quietly_answer_callback(update)
            return None

        if await self._is_limited("updates", actor_key, self.default_rule) or (
            action_key
            and action_key in self.action_rules
            and await self._is_limited(action_key, actor_key, self.action_rules[action_key])
        ):
            logger.warning(
                "Telegram update dropped by anti-flood: actor=%s update_type=%s",
                actor_key,
                action_key or getattr(update, "event_type", "unknown"),
            )
            _mark_dropped(data)
            return None

        return await handler(event, data)

    async def _is_limited(self, bucket_name: str, actor_key: str, rule: RateLimitRule) -> bool:
        if rule.window_seconds <= 0 or rule.max_events <= 0:
            return False

        try:
            redis = await get_redis(self.settings)
            if redis is not None:
                key = redis_key(
                    self.settings,
                    "rate-limit",
                    "telegram",
                    bucket_name,
                    actor_key,
                )
                current = int(await redis.incr(key))
                if current == 1:
                    await redis.expire(key, rule.window_seconds)
                return current > rule.max_events
        except Exception as exc:
            logger.warning("Redis telegram anti-flood unavailable; using local fallback: %s", exc)

        return await self._is_limited_local(f"{bucket_name}:{actor_key}", rule)

    async def _is_cooldown_active(self, cooldown_key: str, ttl_seconds: int) -> bool:
        if ttl_seconds <= 0:
            return False

        try:
            redis = await get_redis(self.settings)
            if redis is not None:
                key = redis_key(
                    self.settings,
                    "cooldown",
                    "telegram",
                    cooldown_key,
                )
                acquired = await redis.set(key, "1", nx=True, ex=ttl_seconds)
                return not bool(acquired)
        except Exception as exc:
            logger.warning("Redis telegram cooldown unavailable; using local fallback: %s", exc)

        return await self._is_cooldown_active_local(cooldown_key, ttl_seconds)

    async def _is_cooldown_active_local(self, cooldown_key: str, ttl_seconds: int) -> bool:
        now = time.monotonic()
        async with self._local_lock:
            expired = [
                key for key, expires_at in self._local_cooldowns.items() if expires_at <= now
            ]
            for key in expired:
                self._local_cooldowns.pop(key, None)

            expires_at = self._local_cooldowns.get(cooldown_key)
            if expires_at and expires_at > now:
                return True

            self._local_cooldowns[cooldown_key] = now + ttl_seconds
        return False

    async def _is_limited_local(self, actor_key: str, rule: RateLimitRule) -> bool:
        now = time.monotonic()
        cutoff = now - rule.window_seconds
        async with self._local_lock:
            bucket = self._local_buckets[actor_key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            bucket.append(now)
            if len(bucket) > rule.max_events:
                return True
            if not bucket:
                self._local_buckets.pop(actor_key, None)
        return False


def _update_actor_key(update: Update) -> str | None:
    user_id = None
    chat_id = None

    if update.message:
        user_id = update.message.from_user.id if update.message.from_user else None
        chat_id = update.message.chat.id if update.message.chat else None
    elif update.callback_query:
        user_id = update.callback_query.from_user.id if update.callback_query.from_user else None
        if update.callback_query.message and update.callback_query.message.chat:
            chat_id = update.callback_query.message.chat.id
    elif update.inline_query:
        user_id = update.inline_query.from_user.id if update.inline_query.from_user else None

    if user_id is not None:
        return f"user:{int(user_id)}"
    if chat_id is not None:
        return f"chat:{int(chat_id)}"
    return None


def _message_or_callback_chat_type(update: Update) -> str | None:
    if update.message and update.message.chat:
        return str(update.message.chat.type)
    if (
        update.callback_query
        and update.callback_query.message
        and update.callback_query.message.chat
    ):
        return str(update.callback_query.message.chat.type)
    return None


def _update_action_key(update: Update) -> str:
    if update.message:
        text = update.message.text or ""
        if text.startswith("/start"):
            return "start"
        return "message"
    if update.callback_query:
        data = update.callback_query.data or ""
        if data.startswith(EXPENSIVE_CALLBACK_PREFIXES):
            return "expensive_callback"
        return "callback"
    if update.inline_query:
        return "inline"
    return "updates"


def _update_action_cooldown(update: Update, settings: Settings) -> tuple[str, int] | None:
    if not bool(settings.TELEGRAM_ACTION_COOLDOWN_ENABLED):
        return None
    if not update.callback_query or not update.callback_query.from_user:
        return None

    callback_data = update.callback_query.data or ""
    if not callback_data:
        return None

    user_id = int(update.callback_query.from_user.id)
    data_digest = hashlib.sha256(callback_data.encode("utf-8")).hexdigest()[:24]

    if callback_data.startswith("pay_"):
        ttl = int(
            settings.TELEGRAM_PAYMENT_CALLBACK_COOLDOWN_SECONDS
            or DEFAULT_PAYMENT_CALLBACK_COOLDOWN_SECONDS
        )
        return f"payment:user:{user_id}:data:{data_digest}", ttl

    if callback_data.startswith(TRIAL_CALLBACK_PREFIXES):
        ttl = int(
            settings.TELEGRAM_TRIAL_CALLBACK_COOLDOWN_SECONDS
            or DEFAULT_TRIAL_CALLBACK_COOLDOWN_SECONDS
        )
        return f"trial:user:{user_id}:data:{data_digest}", ttl

    return None


async def _quietly_answer_callback(update: Update) -> None:
    callback = update.callback_query
    if not callback:
        return
    with contextlib.suppress(Exception):
        await callback.answer()


def _mark_dropped(data: dict[str, Any]) -> None:
    data["antiflood_dropped"] = True
    data["skip_action_log"] = True


def _default_action_rules(settings: Settings) -> dict[str, RateLimitRule]:
    window_seconds = int(settings.TELEGRAM_ANTIFLOOD_WINDOW_SECONDS or DEFAULT_WINDOW_SECONDS)
    return {
        "message": RateLimitRule(
            window_seconds,
            int(
                settings.TELEGRAM_ANTIFLOOD_MESSAGE_MAX_PER_WINDOW or DEFAULT_MESSAGE_MAX_PER_WINDOW
            ),
        ),
        "callback": RateLimitRule(
            window_seconds,
            int(
                settings.TELEGRAM_ANTIFLOOD_CALLBACK_MAX_PER_WINDOW
                or DEFAULT_CALLBACK_MAX_PER_WINDOW
            ),
        ),
        "inline": RateLimitRule(
            window_seconds,
            int(settings.TELEGRAM_ANTIFLOOD_INLINE_MAX_PER_WINDOW or DEFAULT_INLINE_MAX_PER_WINDOW),
        ),
        "start": RateLimitRule(
            window_seconds,
            int(settings.TELEGRAM_ANTIFLOOD_START_MAX_PER_WINDOW or DEFAULT_START_MAX_PER_WINDOW),
        ),
        "expensive_callback": RateLimitRule(
            window_seconds,
            int(
                settings.TELEGRAM_ANTIFLOOD_EXPENSIVE_CALLBACK_MAX_PER_WINDOW
                or DEFAULT_EXPENSIVE_CALLBACK_MAX_PER_WINDOW
            ),
        ),
    }
