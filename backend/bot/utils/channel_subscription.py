from typing import Optional


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
