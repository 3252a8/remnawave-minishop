"""The optional plugin built from source alongside the application image."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

BLACKLIST_ID = "minishop-blacklist"
BLACKLIST_ENTRY = "bot.plugins.builtin.blacklist:plugin"
DIST = Path(__file__).parent / "builtin" / "blacklist" / "dist"


@lru_cache(maxsize=1)
def blacklist_installation() -> dict[str, Any] | None:
    manifest = DIST / "plugin.json"
    if not manifest.is_file():
        return None
    data = manifest.read_bytes()
    package = json.loads(data)
    return {
        "digest": hashlib.sha256(data).hexdigest(),
        "version": package["version"],
        "publisher": package["publisher"],
        "source": {"kind": "image", "bundled": True},
        "enabled": False,
        "status": "installed",
    }


def is_bundled(owner: str, entry: dict[str, Any]) -> bool:
    return owner == BLACKLIST_ID and entry.get("source") == {"kind": "image", "bundled": True}


def release_directory(root: Path, owner: str, digest: str) -> Path:
    if owner == BLACKLIST_ID:
        bundled = blacklist_installation()
        if bundled and digest == bundled["digest"]:
            return DIST
    return root / "releases" / owner / digest
