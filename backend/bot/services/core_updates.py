"""Discover published Core images for the installation's selected Docker tag."""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any, Literal

import aiohttp
from pydantic import BaseModel

from bot.utils.app_version import resolve_app_version, resolve_build_provenance

TAG_PATTERN = r"^(?:latest|dev|[0-9]+\.[0-9]+\.[0-9]+)$"
IMAGE = "3252a8/remnawave-minishop-backend"
Registry = Literal["docker.io", "ghcr.io"]


class Release(BaseModel):
    tag: str
    revision: str
    version: str


def image_tag() -> str:
    return os.environ.get("IMAGE_TAG", "latest").strip() or "latest"


def available(release: Release | None) -> bool:
    current = re.search(r"\+g([0-9a-f]{7,40})$", resolve_app_version())
    return bool(
        release
        and current
        and resolve_build_provenance() == "official"
        and not release.revision.startswith(current[1])
    )


async def _published_image(tag: str, registry: Registry) -> Release:
    ghcr = registry == "ghcr.io"
    host = "https://ghcr.io" if ghcr else "https://registry-1.docker.io"
    auth = "https://ghcr.io/token" if ghcr else "https://auth.docker.io/token"
    media = ", ".join(
        [
            "application/vnd.oci.image.index.v1+json",
            "application/vnd.oci.image.manifest.v1+json",
            "application/vnd.docker.distribution.manifest.list.v2+json",
            "application/vnd.docker.distribution.manifest.v2+json",
        ]
    )
    async with aiohttp.ClientSession(raise_for_status=True) as session:
        async with session.get(
            auth,
            params={
                "service": "ghcr.io" if ghcr else "registry.docker.io",
                "scope": f"repository:{IMAGE}:pull",
            },
        ) as response:
            token = (await response.json())["token"]
        headers = {"Authorization": f"Bearer {token}", "Accept": media}

        async def fetch(kind: str, ref: str) -> dict[str, Any]:
            async with session.get(f"{host}/v2/{IMAGE}/{kind}/{ref}", headers=headers) as response:
                return await response.json(content_type=None)

        manifest = await fetch("manifests", tag)
        if "manifests" in manifest:
            child = next(
                (
                    m
                    for m in manifest["manifests"]
                    if m.get("platform", {}).get("os") == "linux"
                    and m["platform"].get("architecture") == "amd64"
                ),
                None,
            )
            if child is None:
                raise ValueError("Missing supported platform")
            manifest = await fetch("manifests", _digest(child))
        config = await fetch("blobs", _digest(manifest["config"]))
        labels = config["config"]["Labels"]
        revision = labels["org.opencontainers.image.revision"]
        if not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise ValueError("Image revision unavailable")
        version = str(labels.get("org.opencontainers.image.ref.name", tag))
        if not re.fullmatch(r"v?\d+\.\d+\.\d+", version):
            version = f"{tag} · {revision[:8]}"
        return Release(tag=tag, revision=revision, version=version)


def _digest(descriptor: dict[str, Any]) -> str:
    digest = str(descriptor["digest"])
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("Invalid image descriptor")
    return digest


_cache: dict[tuple[str, Registry], tuple[float, Release | None]] = {}
_lock = asyncio.Lock()


async def check_image(tag: str, registry: Registry, *, manual: bool = False) -> Release | None:
    if not re.fullmatch(TAG_PATTERN, tag) or len(tag) > 64:
        return None
    async with _lock:
        now = time.monotonic()
        cached = _cache.get((tag, registry))
        if cached and now - cached[0] < (15 if manual else 900 if cached[1] else 60):
            return cached[1]
        try:
            async with asyncio.timeout(8):
                release: Release | None = await _published_image(tag, registry)
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError, KeyError):
            release = None
        if len(_cache) >= 64:
            _cache.pop(next(iter(_cache)))
        _cache[tag, registry] = (now, release)
        return release
