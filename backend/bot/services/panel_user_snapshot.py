"""Adaptive panel-user loading shared by workers, audiences, and broadcasts."""

import asyncio
import logging
import math
from dataclasses import dataclass
from typing import Any

from bot.services.panel_api_service import PanelApiService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PanelUsersSnapshot:
    users_by_reference: dict[str, dict[str, Any]]
    strategy: str
    panel_total: int


def _known_panel_user_count(panel_service: PanelApiService) -> int:
    getter = getattr(panel_service, "panel_user_count_hint", None)
    if not callable(getter):
        return 0
    raw_known = getter()
    try:
        return max(0, int(raw_known)) if isinstance(raw_known, (int, str)) else 0
    except (TypeError, ValueError):
        return 0


async def panel_user_count_hint(panel_service: PanelApiService) -> int:
    """Return a cached count, refreshing it through the small system-stats response."""
    known = _known_panel_user_count(panel_service)
    if known > 0:
        return known
    stats_getter = getattr(panel_service, "get_system_stats", None)
    if not callable(stats_getter):
        return 0
    try:
        stats = await stats_getter()
    except Exception:
        logger.exception("Failed to fetch Remnawave user count for adaptive loading")
        return 0
    users = stats.get("users") if isinstance(stats, dict) else None
    raw_total = users.get("totalUsers") if isinstance(users, dict) else None
    try:
        total = max(0, int(raw_total or 0))
    except (TypeError, ValueError):
        return 0
    if total > 0:
        remember = getattr(panel_service, "remember_panel_user_count", None)
        if callable(remember):
            remember(total)
    return total


async def should_use_full_panel_user_scan(
    panel_service: PanelApiService,
    candidate_count: int,
    *,
    threshold: int,
    concurrency: int,
) -> tuple[bool, int]:
    """Compare sequential cursor pages with concurrent point-read rounds."""
    candidates = max(0, int(candidate_count))
    if candidates < max(1, int(threshold)):
        return False, _known_panel_user_count(panel_service)
    total = await panel_user_count_hint(panel_service)
    if total <= 0:
        # Unknown panel size must not turn a small local candidate set into an
        # unbounded full-panel scan.
        return False, 0
    page_size_getter = getattr(panel_service, "_resolve_all_users_page_size", None)
    raw_page_size = page_size_getter() if callable(page_size_getter) else 1000
    page_size = int(raw_page_size) if isinstance(raw_page_size, (int, str)) else 1000
    page_size = max(1, page_size)
    # The legacy 2.8 offset iterator needs one final empty-page request when
    # the total is an exact page multiple; the conservative estimate also
    # keeps future stream behavior from selecting a full scan too eagerly.
    stream_pages = max(1, total // page_size + 1)
    point_rounds = max(1, math.ceil(candidates / max(1, int(concurrency))))
    return stream_pages <= point_rounds, total


async def load_panel_users_by_reference(
    panel_service: PanelApiService,
    references: list[str],
    *,
    threshold: int = 50,
    concurrency: int = 10,
) -> PanelUsersSnapshot:
    """Load requested users through a full stream only when it is cheaper."""
    unique_refs = list(
        dict.fromkeys(str(value).strip() for value in references if str(value).strip())
    )
    if not unique_refs:
        return PanelUsersSnapshot({}, "empty", _known_panel_user_count(panel_service))

    use_full_scan, total = await should_use_full_panel_user_scan(
        panel_service,
        len(unique_refs),
        threshold=threshold,
        concurrency=concurrency,
    )
    if use_full_scan:
        try:
            users = await panel_service.get_all_panel_users(log_responses=False)
        except Exception:
            logger.exception("Adaptive Remnawave user stream failed; using point reads")
        else:
            if users is not None:
                requested = set(unique_refs)
                by_reference = {
                    str(user.get("uuid")): user
                    for user in users
                    if isinstance(user, dict) and str(user.get("uuid") or "") in requested
                }
                logger.info(
                    "metric panel_user_snapshot strategy=stream candidates=%s panel_users=%s "
                    "matched=%s",
                    len(unique_refs),
                    len(users),
                    len(by_reference),
                )
                return PanelUsersSnapshot(by_reference, "stream", len(users))

    semaphore = asyncio.Semaphore(max(1, int(concurrency)))

    async def resolve(reference: str) -> tuple[str, dict[str, Any] | None]:
        async with semaphore:
            try:
                user = await panel_service.get_user_by_uuid(reference)
            except Exception:
                logger.exception("Adaptive Remnawave point read failed")
                return reference, None
        return reference, user if isinstance(user, dict) else None

    resolved = await asyncio.gather(*(resolve(reference) for reference in unique_refs))
    by_reference = {reference: user for reference, user in resolved if user is not None}
    logger.info(
        "metric panel_user_snapshot strategy=point candidates=%s panel_users=%s matched=%s",
        len(unique_refs),
        total,
        len(by_reference),
    )
    return PanelUsersSnapshot(by_reference, "point", total)
