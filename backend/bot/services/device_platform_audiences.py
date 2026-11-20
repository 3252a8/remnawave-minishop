"""Match broadcast recipients to the platforms of their registered devices."""

import asyncio
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from db.dal.user_reads_dal import panel_user_reference
from db.models import Subscription, User

PLATFORM_PREFIX = "platform:"
_PLATFORM_TARGET = re.compile(r"platform:[a-z0-9_.-]{1,55}")
_PLATFORM_NAMES = {
    "ios": "iOS",
    "ipados": "iPadOS",
    "macos": "macOS",
    "android": "Android",
    "windows": "Windows",
    "linux": "Linux",
    "tvos": "tvOS",
}


class DeviceInventoryUnavailable(Exception):
    """Raised when the panel cannot provide a complete inventory."""


def is_platform_target(target: str) -> bool:
    return _PLATFORM_TARGET.fullmatch(target) is not None


@dataclass
class PlatformGroup:
    label: str
    user_ids: set[int] = field(default_factory=set)


def _add_device(
    groups: dict[str, PlatformGroup], device: dict[str, Any], user_ids: set[int]
) -> None:
    label = str(device.get("platform") or "").strip()
    if not label or not device.get("hwid"):
        return
    key = label.casefold()
    target = PLATFORM_PREFIX + key
    if not is_platform_target(target) or key.startswith("id-"):
        target = PLATFORM_PREFIX + "id-" + hashlib.sha256(key.encode()).hexdigest()[:24]
    if target not in groups:
        groups[target] = PlatformGroup(_PLATFORM_NAMES.get(key, label))
    groups[target].user_ids.update(user_ids)


async def load_platform_groups(
    session_factory: sessionmaker, panel: Any, *, user_id: int | None = None
) -> dict[str, PlatformGroup]:
    latest_ref = (
        select(Subscription.panel_user_uuid)
        .where(
            Subscription.user_id == User.user_id,
            Subscription.is_active.is_(True),
            Subscription.panel_user_uuid != "",
        )
        .order_by(Subscription.end_date.desc(), Subscription.subscription_id.desc())
        .limit(1)
        .scalar_subquery()
    )
    stmt = select(
        User.user_id, func.coalesce(func.nullif(User.panel_user_uuid, ""), latest_ref)
    ).where(User.is_banned.is_(False))
    if user_id is not None:
        stmt = stmt.where(User.user_id == user_id)
    owners: dict[str, set[int]] = defaultdict(set)
    async with session_factory() as session:
        for uid, ref in await session.execute(stmt):
            if reference := panel_user_reference(ref):
                owners[reference].add(int(uid))
    groups: dict[str, PlatformGroup] = {}
    # Bulk rows carry a numeric userId on panels that still use UUID account links.
    # Resolve those links using the generation-aware, user-scoped endpoint.
    point_refs = list(owners)
    if sum(ref.isdecimal() for ref in owners) >= 32:
        start = 0
        while True:
            page = await panel.get_hwid_devices_page(start=start, size=500)
            if page is None:
                raise DeviceInventoryUnavailable()
            total, rows = page
            for device in rows:
                ref = str(device.get("userId") or device.get("userUuid") or "")
                if ref in owners:
                    _add_device(groups, device, owners[ref])
            start += len(rows)
            if start >= total:
                break
            if not rows:
                raise DeviceInventoryUnavailable()
        point_refs = [ref for ref in owners if not ref.isdecimal()]
    for offset in range(0, len(point_refs), 10):
        refs = point_refs[offset : offset + 10]
        results = await asyncio.gather(
            *(panel.get_user_devices(ref, force_refresh=True) for ref in refs)
        )
        for ref, devices in zip(refs, results, strict=True):
            if devices is None:
                lookup = await panel.get_user_by_uuid_lookup(ref)
                if lookup.get("not_found"):
                    continue
                raise DeviceInventoryUnavailable()
            for device in devices:
                _add_device(groups, device, owners[ref])
    return groups
