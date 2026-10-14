"""Active customer page and message data contributions of installed plugins."""

import asyncio
import json
import logging
from functools import lru_cache
from pathlib import Path

from bot.plugins.extensions.registry import get_registry
from bot.plugins.packages import generation_is_current, package_root, read_state
from config.extension_targets import extension_page_parts

logger = logging.getLogger(__name__)


@lru_cache(maxsize=8)
def _package_pages(
    root: Path, generation: int, installations: tuple[tuple[str, str], ...]
) -> tuple[tuple[str, str, str, str, str], ...]:
    pages: list[tuple[str, str, str, str, str]] = []
    for owner, digest in installations:
        try:
            manifest = json.loads(
                (root / "releases" / owner / digest / "plugin.json").read_text(encoding="utf-8")
            )
            frontend = manifest.get("frontend", {}).get("user", {})
            for page in frontend.get("pages", []):
                path = f"/extensions/{owner}/{page['id']}"
                if extension_page_parts(path):
                    pages.append(
                        (path, str(page["label"]), owner, str(page.get("i18nKey", "")), page["id"])
                    )
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            logger.warning("Customer message targets unavailable for plugin %s", owner)
    return tuple(pages)


def active_message_pages() -> tuple[tuple[str, str, str, str, str], ...]:
    if not generation_is_current():
        return ()
    try:
        root = package_root()
        state = read_state(root)
        generation = state["generation"]
        if state["installations"] and not all(
            state.get("observations", {}).get(role)
            == {"generation": generation, "status": "active"}
            for role in ("backend", "worker")
        ):
            return ()
        owners = get_registry().owners()
        installations = tuple(
            sorted(
                (owner, value["digest"])
                for owner, value in state["installations"].items()
                if value["enabled"] and owner in owners
            )
        )
        return _package_pages(root, generation, installations)
    except (OSError, ValueError, KeyError, TypeError):
        return ()


def active_message_page(value: str) -> bool:
    return any(page[0] == value for page in active_message_pages())


async def message_pages() -> tuple[tuple[str, str, str, str, str], ...]:
    return await asyncio.to_thread(active_message_pages)
