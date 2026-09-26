"""Safe resolution of file-backed public Markdown pages."""

from __future__ import annotations

import os
import re
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

MAX_INFORMATION_PAGE_BYTES = 512 * 1024
MAX_INFORMATION_PAGE_PATH_LENGTH = 256
_PAGE_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_RESERVED_ROOT_SEGMENTS = frozenset(
    {
        "admin",
        "api",
        "auth",
        "checkout",
        "devices",
        "favicon.ico",
        "fonts",
        "health",
        "home",
        "icon-192.png",
        "icon-512.png",
        "install",
        "invite",
        "login",
        "open-app",
        "partner",
        "plans",
        "robots.txt",
        "s",
        "subscription_webapp.css",
        "subscription_webapp.js",
        "support",
        "settings",
        "unsubscribe",
        "webapp-default-logo.webp",
        "webapp-favicon",
        "webapp-logo",
        "webapp-theme-assets",
        "webapp-theme-css",
        "webapp-uploaded-logo",
        "status",
        "trial",
    }
)


class InformationPagePathError(ValueError):
    """Raised when a URL cannot name a file-backed information page."""


class InformationPageConflictError(ValueError):
    """Raised when moving a document would overwrite another page."""


class InformationPageWriteError(ValueError):
    """Raised when a document cannot be written safely."""


@dataclass(frozen=True)
class InformationPage:
    path: str
    markdown: str


def normalize_information_page_path(value: object) -> str:
    """Return a canonical absolute page route without accepting path traversal."""

    raw = str(value or "").strip()
    if not raw or len(raw) > MAX_INFORMATION_PAGE_PATH_LENGTH:
        raise InformationPagePathError("page path is empty or too long")
    if not raw.startswith("/") or "?" in raw or "#" in raw or "\\" in raw or "%" in raw:
        raise InformationPagePathError("page path must be an absolute URL path")

    segments = raw.strip("/").split("/")
    if not segments or len(segments) > 8:
        raise InformationPagePathError("page path has an invalid number of segments")
    if any(not _PAGE_SEGMENT_RE.fullmatch(segment) for segment in segments):
        raise InformationPagePathError("page path contains an invalid segment")
    if segments[0] in _RESERVED_ROOT_SEGMENTS:
        raise InformationPagePathError("page path conflicts with an application route")
    if segments == ["legal"]:
        raise InformationPagePathError("page path does not name a legal document")
    return "/" + "/".join(segments)


def information_page_file_path(app_root: Path, page_path: object) -> tuple[str, Path]:
    """Map a validated public route to its Markdown file below the data directory."""

    path = normalize_information_page_path(page_path)
    segments = path.strip("/").split("/")
    if segments[0] == "legal":
        root = app_root / "data" / "legal"
        relative_parts = segments[1:]
    else:
        root = app_root / "data" / "pages"
        relative_parts = segments
    if not relative_parts:
        raise InformationPagePathError("page path does not name a document")

    candidate = root.joinpath(*relative_parts).with_suffix(".md")
    root_resolved = root.resolve()
    candidate_resolved = candidate.resolve()
    if not candidate_resolved.is_relative_to(root_resolved):
        raise InformationPagePathError("page path escapes its data directory")
    return path, candidate_resolved


def load_information_page(app_root: Path, page_path: object) -> InformationPage | None:
    """Load a bounded UTF-8 Markdown page, or return ``None`` when it is absent/invalid."""

    try:
        path, file_path = information_page_file_path(app_root, page_path)
        if not file_path.is_file() or file_path.stat().st_size > MAX_INFORMATION_PAGE_BYTES:
            return None
        return InformationPage(path=path, markdown=file_path.read_text(encoding="utf-8"))
    except (InformationPagePathError, OSError, UnicodeError):
        return None


def save_information_page(
    app_root: Path,
    page_path: object,
    markdown: object,
    *,
    previous_path: object | None = None,
) -> InformationPage:
    """Atomically save a Markdown page and optionally move it from an old route.

    A route change is deliberately conservative: an occupied target is never
    overwritten. The replacement file is fsynced and atomically installed
    before the old document is removed, so a failed move cannot lose content.
    """

    path, file_path = information_page_file_path(app_root, page_path)
    body = str(markdown)
    try:
        body_bytes = body.encode("utf-8")
    except UnicodeError as exc:
        raise InformationPageWriteError("page markdown must be UTF-8") from exc
    if len(body_bytes) > MAX_INFORMATION_PAGE_BYTES:
        raise InformationPageWriteError("page markdown is too large")

    old_path: str | None = None
    old_file_path: Path | None = None
    if previous_path is not None and str(previous_path).strip():
        old_path, old_file_path = information_page_file_path(app_root, previous_path)
        if old_path != path and file_path.exists():
            raise InformationPageConflictError("the destination page already exists")

    temporary_path: Path | None = None
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="wb",
            dir=file_path.parent,
            prefix=f".{file_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(body_bytes)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, file_path)
        temporary_path = None
        if old_file_path is not None and old_path != path and old_file_path.exists():
            old_file_path.unlink()
    except OSError as exc:
        raise InformationPageWriteError("could not write the information page") from exc
    finally:
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)

    return InformationPage(path=path, markdown=body)
