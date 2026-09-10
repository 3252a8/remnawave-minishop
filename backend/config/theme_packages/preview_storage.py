"""Persistent previews kept outside immutable theme package revisions."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .models import PackageError
from .paths import atomic_bytes, confined, registry_lock, relative_path

MAX_PREVIEW_BYTES = 5 * 1024 * 1024
MAX_PREVIEW_WIDTH = 4096
MAX_PREVIEW_HEIGHT = 2560
PREVIEW_NAME = "desktop.webp"


def preview_file(root: Path, key: str) -> Path:
    relative_path(key)
    return confined(root, f"_previews/{key}.webp")


def preview_url(key: str, generation: int) -> str:
    return f"/webapp-theme-assets/{key}/previews/{PREVIEW_NAME}?v={generation}"


def normalize_preview(content: bytes) -> bytes:
    if not content or len(content) > MAX_PREVIEW_BYTES:
        raise PackageError("preview_too_large", status=413)
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.width < 1 or image.height < 1:
                raise PackageError("invalid_preview")
            if image.width > MAX_PREVIEW_WIDTH or image.height > MAX_PREVIEW_HEIGHT:
                raise PackageError("preview_dimensions_invalid")
            output = io.BytesIO()
            image.convert("RGB").save(output, format="WEBP", quality=85, method=6)
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise PackageError("invalid_preview") from exc
    result = output.getvalue()
    if len(result) > MAX_PREVIEW_BYTES:
        raise PackageError("preview_too_large", status=413)
    return result


def save_preview(root: Path, key: str, content: bytes) -> tuple[str, int]:
    from .registry import read_registry, write_registry

    normalized = normalize_preview(content)
    with registry_lock(root):
        state = read_registry(root)
        atomic_bytes(preview_file(root, key), normalized)
        if entry := state.entries.get(key):
            entry.preview_override = PREVIEW_NAME
        write_registry(root, state)
        return preview_url(key, state.generation), state.generation
