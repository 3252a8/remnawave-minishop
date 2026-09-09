from __future__ import annotations

import re

from .models import ItemStatus, OverallStatus, ProviderStatus, StatusGroup, StatusItem
from .parsing import finite_number, object_dict, object_list, parse_datetime, plain_text


def _group_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"xray:{slug or 'servers'}"


def parse_xray_proxies(payload: object) -> ProviderStatus:
    response = object_dict(payload)
    if response is None or response.get("success") is not True:
        raise ValueError("invalid xray-checker response")

    grouped: dict[str, list[StatusItem]] = {}
    for proxy in object_list(response.get("data")):
        stable_id = str(proxy.get("stableId") or "").strip()
        if not stable_id:
            continue
        group_name = plain_text(proxy.get("groupName")) or "Servers"
        online = proxy.get("online")
        item_status: ItemStatus = (
            "online" if online is True else "offline" if online is False else "unknown"
        )
        grouped.setdefault(group_name, []).append(
            StatusItem(
                id=f"xray:{stable_id}",
                name=plain_text(proxy.get("name")) or stable_id,
                status=item_status,
                latency_ms=finite_number(proxy.get("latencyMs")),
                uptime_24h=None,
                last_check=parse_datetime(proxy.get("lastCheck")),
                provider="xray-checker",
            )
        )

    groups = [
        StatusGroup(id=_group_id(name), name=name, items=items) for name, items in grouped.items()
    ]
    items = [item for group in groups for item in group.items]
    status: OverallStatus
    if not items:
        status = "unknown"
    elif all(item.status == "offline" for item in items):
        status = "major_outage"
    elif any(item.status == "offline" for item in items):
        status = "partial_outage"
    else:
        status = "operational"
    return ProviderStatus(provider="xray-checker", status=status, groups=groups)
