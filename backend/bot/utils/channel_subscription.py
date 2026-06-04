import logging
import re
from typing import Any, Optional

_TELEGRAM_LINK_RE = re.compile(r"^(?:https?://|tg://)", re.IGNORECASE)
_TELEGRAM_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,64}$")


def normalize_required_channel_id(value: object) -> Optional[int]:
    if value is None:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    try:
        channel_id = int(raw)
    except (TypeError, ValueError):
        return None

    if channel_id == 0:
        return None

    if channel_id > 0:
        return int(f"-100{channel_id}")

    raw_abs = str(abs(channel_id))
    if raw.startswith("-100"):
        return channel_id
    if abs(channel_id) < 1_000_000_000:
        return channel_id
    return -int(f"100{raw_abs}")


def normalize_required_channel_link(value: object) -> Optional[str]:
    if value is None:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    if _TELEGRAM_LINK_RE.match(raw):
        return raw

    raw = raw.lstrip("@").strip()
    if not raw or re.search(r"\s", raw):
        return None

    if raw.startswith(("t.me/", "telegram.me/")):
        return f"https://{raw}"

    if raw.startswith(("+", "joinchat/", "c/")):
        return f"https://t.me/{raw}"

    if _TELEGRAM_USERNAME_RE.fullmatch(raw):
        return f"https://t.me/{raw}"

    return None


def _required_channel_link_from_chat(chat: Any) -> Optional[str]:
    username = str(getattr(chat, "username", "") or "").strip().lstrip("@")
    if username:
        return f"https://t.me/{username}"

    invite_link = normalize_required_channel_link(getattr(chat, "invite_link", None))
    if invite_link:
        return invite_link

    return None


async def resolve_required_channel_link(
    bot: Any,
    required_channel_id: Optional[int],
    configured_link: object,
) -> Optional[str]:
    if bot is not None and required_channel_id:
        try:
            chat = await bot.get_chat(required_channel_id)
            resolved_link = _required_channel_link_from_chat(chat)
            if resolved_link:
                return resolved_link
        except Exception as error:
            logging.warning(
                "Failed to resolve required channel link from chat %s: %s",
                required_channel_id,
                error,
            )

    return normalize_required_channel_link(configured_link)


def is_required_channel_access_error(error: BaseException) -> bool:
    message = str(error).lower()
    configuration_markers = (
        "chat not found",
        "bot is not a member",
        "not enough rights",
        "have no rights",
        "kicked",
    )
    return any(marker in message for marker in configuration_markers)
