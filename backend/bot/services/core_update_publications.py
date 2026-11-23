"""Resolve timestamps from the public Core release and promotion records."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import aiohttp

from bot.utils.ttl_cache import AsyncTTLCache

_PROJECT = "3252a8/remnawave-minishop"
_GITHUB = f"https://api.github.com/repos/{_PROJECT}"
_GITLAB = "https://gitlab.com/api/v4/projects/3252a8%2Fremnawave-minishop"
_cache = AsyncTTLCache(ttl_seconds=600, max_entries=128, load_timeout=7)


def build_publication(version: str) -> tuple[str, str]:
    match = re.fullmatch(r"(.+)\+g([0-9a-f]{7,40})", version)
    if not match:
        return "", ""
    label, revision = match.groups()
    if label == "dev" or label.endswith("-dev"):
        return "dev", revision
    return label, revision


async def publication_time(version: str, revision: str) -> datetime | None:
    if not re.fullmatch(r"[0-9a-f]{7,40}", revision):
        return None
    stable = re.fullmatch(r"v?([0-9]+\.[0-9]+\.[0-9]+)", version)
    if stable:
        release = f"v{stable[1]}"
    elif version == "dev" and len(revision) == 40:
        release = "dev"
    else:
        return None
    try:
        result = await _cache.get_or_load(
            f"{release}:{revision}", lambda: _read_publication(release, revision)
        )
    except TimeoutError:
        return None
    return result if isinstance(result, datetime) else None


async def _read_publication(release: str, revision: str) -> datetime | str:
    try:
        async with aiohttp.ClientSession(
            raise_for_status=True, timeout=aiohttp.ClientTimeout(total=3)
        ) as session:
            if release == "dev":
                timestamp = await _dev_promotion(session, revision)
            else:
                async with session.get(f"{_GITLAB}/releases/{release}") as response:
                    data = await response.json()
                if data["tag_name"] != release or not data["commit"]["id"].startswith(revision):
                    return ""
                timestamp = data["released_at"]
        if not isinstance(timestamp, str):
            return ""
        value = datetime.fromisoformat(timestamp)
        return value.astimezone(UTC) if value.tzinfo and value <= datetime.now(UTC) else ""
    except (aiohttp.ClientError, TimeoutError, KeyError, AttributeError, TypeError, ValueError):
        return ""


async def _dev_promotion(session: aiohttp.ClientSession, revision: str) -> object:
    async with session.get(
        f"{_GITHUB}/actions/workflows/docker-dev.yml/runs",
        params={"head_sha": revision, "branch": "dev", "status": "success", "per_page": "10"},
    ) as response:
        data = await response.json()
    runs = [
        run
        for run in data["workflow_runs"]
        if run["head_sha"] == revision
        and run["head_branch"] == "dev"
        and run["conclusion"] == "success"
        and run["event"] in {"push", "workflow_dispatch"}
        and isinstance(run["id"], int)
    ]
    if not runs:
        return None
    run = min(runs, key=lambda item: item["created_at"])
    async with session.get(f"{_GITHUB}/actions/runs/{run['id']}/jobs") as response:
        data = await response.json()
    return next(
        (
            step["completed_at"]
            for job in data["jobs"]
            if job["name"] == "Promote all verified dev images" and job["conclusion"] == "success"
            for step in job["steps"]
            if step["name"] == "Verify revisions and update both registries"
            and step["conclusion"] == "success"
        ),
        None,
    )
