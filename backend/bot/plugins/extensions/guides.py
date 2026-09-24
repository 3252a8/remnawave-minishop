"""Add authenticated plugin guide fragments without replacing the selected Core source."""

import asyncio
import copy
import logging
from typing import Any

from bot.plugins.packages import generation_is_current
from config.subscription_guides_config import validate_subscription_guides_config

from .contracts import UserContext
from .presentation import preferences
from .registry import get_registry

logger = logging.getLogger(__name__)


def _rewrite_icons(value: Any, icons: dict[str, str]) -> None:
    if isinstance(value, dict):
        if isinstance(value.get("svgIconKey"), str):
            value["svgIconKey"] = icons.get(value["svgIconKey"], value["svgIconKey"])
        for child in value.values():
            _rewrite_icons(child, icons)
    elif isinstance(value, list):
        for child in value:
            _rewrite_icons(child, icons)


async def merge_guides(context: UserContext, base: dict[str, Any] | None) -> dict[str, Any] | None:
    if not generation_is_current():
        return copy.deepcopy(base)
    result = copy.deepcopy(base)
    positions: dict[str, tuple[int, str, str, int]] = {
        key: (index, "", "", 0) for index, key in enumerate((base or {}).get("platforms", {}))
    }
    fragments = []
    for owner, entry in get_registry().owners().items():
        if not entry.contributions.guides:
            continue
        presentation = await preferences(context.session, owner)
        for provider in entry.contributions.guides:
            choice = presentation.get(f"guide:{provider.id}")
            if choice is not None and not choice[0]:
                continue
            try:
                async with asyncio.timeout(5):
                    fragment = await provider.resolve(context)
                if fragment is None:
                    continue
                if type(fragment.order) is not int or not -10000 <= fragment.order <= 10000:
                    raise ValueError("Invalid guide order")
                config = validate_subscription_guides_config(fragment.config)
                fragments.append(
                    (choice[1] if choice else fragment.order, owner, provider.id, config)
                )
            except Exception:
                logger.warning("Extension guide %s:%s is unavailable", owner, provider.id)
    for order, owner, provider_id, config in sorted(fragments, key=lambda item: item[:3]):
        if result is None:
            result = copy.deepcopy(config)
            result["platforms"] = {}
            result["svgLibrary"] = {}
        icons = {key: f"{owner}--{provider_id}--{key}" for key in config["svgLibrary"]}
        platforms = copy.deepcopy(config["platforms"])
        _rewrite_icons(platforms, icons)
        names = {key: f"{owner}--{provider_id}--{key}" for key in platforms}
        if any(len(key) > 64 or key in result["platforms"] for key in names.values()):
            logger.warning("Extension guide identifiers conflict: %s:%s", owner, provider_id)
            continue
        for index, (key, platform) in enumerate(platforms.items()):
            combined = f"{owner}--{provider_id}--{key}"
            result["platforms"][combined] = platform
            positions[combined] = (order, owner, provider_id, index)
        result["svgLibrary"].update(
            {icons[key]: value for key, value in config["svgLibrary"].items()}
        )
    if result is not None and not result["platforms"]:
        return None
    if result is not None:
        result["platforms"] = {
            key: result["platforms"][key]
            for key in sorted(result["platforms"], key=lambda key: positions[key])
        }
    return result
