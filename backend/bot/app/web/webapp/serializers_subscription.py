from datetime import UTC, datetime
from typing import Any


def serialize_inactive_subscription(
    local_sub: Any | None,
    *,
    remaining_text: str,
) -> dict[str, Any]:
    end_date = getattr(local_sub, "end_date", None)
    if end_date and end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=UTC)
    local_status = str(getattr(local_sub, "status_from_panel", "") or "").strip().upper()
    expired = bool(local_status == "EXPIRED" or (end_date and end_date <= datetime.now(UTC)))
    return {
        "active": False,
        "status": "EXPIRED" if expired else local_status or "INACTIVE",
        "end_date": end_date.isoformat() if end_date else None,
        "end_date_text": end_date.strftime("%d.%m.%Y %H:%M") if end_date else None,
        "remaining_text": remaining_text,
        "days_left": 0,
        "config_link": None,
        "connect_url": None,
        "panel_short_uuid": None,
        "install_share_token": None,
        "install_share_url": None,
    }
