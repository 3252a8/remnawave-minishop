"""Versioned file storage for public Markdown documents."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

MAX_DOCUMENT_BYTES = 512 * 1024
MAX_DOCUMENT_TITLE_LENGTH = 160
MAX_DOCUMENT_GROUP_TITLE_LENGTH = 120
MAX_DOCUMENT_SLUG_LENGTH = 256
DOCUMENTS_INDEX_VERSION = 1
DOCUMENTS_INDEX_NAME = "index.json"
DOCUMENTS_BODIES_DIR_NAME = "bodies"
DocumentRole = Literal["none", "privacy_policy", "user_agreement"]
DOCUMENT_ROLES = frozenset({"none", "privacy_policy", "user_agreement"})
_SLUG_SEGMENT = r"[a-z0-9][a-z0-9-]{0,63}"
_SLUG_RE = re.compile(rf"^{_SLUG_SEGMENT}(?:/{_SLUG_SEGMENT})*$")
DOCUMENT_RESERVED_ROOTS = frozenset(
    {
        "admin",
        "api",
        "auth",
        "checkout",
        "devices",
        "extensions",
        "docs",
        "fonts",
        "health",
        "home",
        "install",
        "invite",
        "login",
        "open-app",
        "partner",
        "plans",
        "s",
        "settings",
        "status",
        "support",
        "trial",
        "unsubscribe",
        "webapp-favicon",
        "webapp-logo",
        "webapp-theme-assets",
        "webapp-theme-css",
        "webapp-uploaded-logo",
    }
)
_DOCUMENTS_LOCK = threading.RLock()


class DocumentError(ValueError):
    """Base error for document storage operations."""


class DocumentNotFoundError(DocumentError):
    """Raised when a requested document does not exist."""


class DocumentConflictError(DocumentError):
    """Raised when a slug or singleton legal role is already used."""


class DocumentStorageError(DocumentError):
    """Raised when persisted document data is malformed or cannot be written."""


@dataclass(frozen=True)
class DocumentMetadata:
    title: str
    slug: str
    role: DocumentRole = "none"
    show_in_settings: bool = False
    show_in_sidebar: bool = False
    group_title: str | None = None
    sort_order: int = 0


@dataclass(frozen=True)
class Document(DocumentMetadata):
    markdown: str = ""


def normalize_document_slug(value: object) -> str:
    slug = str(value or "").strip().lower().lstrip("/")
    if len(slug) > MAX_DOCUMENT_SLUG_LENGTH or not _SLUG_RE.fullmatch(slug):
        raise DocumentError("document slug is invalid")
    return slug


def document_public_path(slug: object) -> str:
    """Return the public URL path, preserving reserved application roots."""

    normalized_slug = normalize_document_slug(slug)
    prefix = "/docs/" if normalized_slug.split("/", 1)[0] in DOCUMENT_RESERVED_ROOTS else "/"
    return f"{prefix}{normalized_slug}"


def _normalize_title(value: object) -> str:
    title = str(value or "").strip()
    if not title or len(title) > MAX_DOCUMENT_TITLE_LENGTH:
        raise DocumentError("document title is invalid")
    return title


def _normalize_role(value: object) -> DocumentRole:
    role = str(value or "none").strip()
    if role == "none":
        return "none"
    if role == "privacy_policy":
        return "privacy_policy"
    if role == "user_agreement":
        return "user_agreement"
    raise DocumentError("document role is invalid")


def _normalize_group_title(value: object) -> str | None:
    if value is None:
        return None
    title = str(value).strip()
    if not title:
        return None
    if len(title) > MAX_DOCUMENT_GROUP_TITLE_LENGTH:
        raise DocumentError("document group title is invalid")
    return title


def _normalize_markdown(value: object) -> str:
    markdown = str(value)
    try:
        size = len(markdown.encode("utf-8"))
    except UnicodeError as exc:
        raise DocumentError("document markdown must be UTF-8") from exc
    if size > MAX_DOCUMENT_BYTES:
        raise DocumentError("document markdown is too large")
    return markdown


def normalize_document_metadata(
    *,
    title: object,
    slug: object,
    role: object = "none",
    show_in_settings: object = False,
    show_in_sidebar: object = False,
    group_title: object = None,
    sort_order: object = 0,
) -> DocumentMetadata:
    """Validate one document metadata record."""

    if isinstance(sort_order, bool) or not isinstance(sort_order, (int, str)):
        raise DocumentError("document sort order is invalid")
    try:
        normalized_sort_order = int(sort_order)
    except (TypeError, ValueError) as exc:
        raise DocumentError("document sort order is invalid") from exc
    if not -100_000 <= normalized_sort_order <= 100_000:
        raise DocumentError("document sort order is invalid")
    if not isinstance(show_in_settings, bool) or not isinstance(show_in_sidebar, bool):
        raise DocumentError("document visibility is invalid")
    return DocumentMetadata(
        title=_normalize_title(title),
        slug=normalize_document_slug(slug),
        role=_normalize_role(role),
        show_in_settings=show_in_settings,
        show_in_sidebar=show_in_sidebar,
        group_title=_normalize_group_title(group_title),
        sort_order=normalized_sort_order,
    )


def _documents_root(app_root: Path) -> Path:
    return app_root / "data" / "docs"


def _index_path(app_root: Path) -> Path:
    return _documents_root(app_root) / DOCUMENTS_INDEX_NAME


def _bodies_dir(app_root: Path) -> Path:
    return _documents_root(app_root) / DOCUMENTS_BODIES_DIR_NAME


def _assert_storage_directories(app_root: Path) -> None:
    root = _documents_root(app_root)
    bodies = _bodies_dir(app_root)
    for path in (root, bodies):
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise DocumentStorageError("document storage has an unsafe directory")


def _body_name(slug: str, markdown: str) -> str:
    slug_digest = hashlib.sha256(slug.encode("utf-8")).hexdigest()[:20]
    digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()[:20]
    return f"{slug_digest}-{digest}.md"


def _legacy_body_name(slug: str, markdown: str) -> str:
    digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()[:20]
    return f"{slug}-{digest}.md"


def _body_path(app_root: Path, body_name: str) -> Path:
    if not re.fullmatch(r"(?:[a-f0-9]{20}|[a-z0-9][a-z0-9-]{0,63})-[a-f0-9]{20}\.md", body_name):
        raise DocumentStorageError("document body reference is invalid")
    _assert_storage_directories(app_root)
    path = _bodies_dir(app_root) / body_name
    return path


@contextmanager
def _locked_storage(app_root: Path) -> Iterator[None]:
    """Serialize metadata changes across threads and backend worker processes."""

    with _DOCUMENTS_LOCK:
        lock_path = _documents_root(app_root) / ".lock"
        try:
            _assert_storage_directories(app_root)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with lock_path.open("a+b") as lock_file:
                if sys.platform == "win32":
                    import msvcrt

                    lock_file.seek(0, os.SEEK_END)
                    if lock_file.tell() == 0:
                        lock_file.write(b"\0")
                        lock_file.flush()
                    while True:
                        lock_file.seek(0)
                        try:
                            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                            break
                        except OSError as exc:
                            if exc.errno != errno.EACCES:
                                raise
                            time.sleep(0.05)
                else:
                    import fcntl

                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    if sys.platform == "win32":
                        import msvcrt

                        lock_file.seek(0)
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except OSError as exc:
            raise DocumentStorageError("could not lock document storage") from exc


def _atomic_write(path: Path, body: bytes) -> None:
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as temporary:
            temporary.write(body)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError as exc:
        raise DocumentStorageError("could not write document storage") from exc
    finally:
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)


def _record(metadata: DocumentMetadata, body_name: str) -> dict[str, object]:
    return {**asdict(metadata), "body": body_name}


def _read_records(app_root: Path) -> list[tuple[DocumentMetadata, str]]:
    _assert_storage_directories(app_root)
    index_path = _index_path(app_root)
    if index_path.is_symlink() or (index_path.exists() and not index_path.is_file()):
        raise DocumentStorageError("document index is unsafe")
    if not index_path.exists():
        return []
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DocumentStorageError("document index is unreadable") from exc
    if not isinstance(raw, dict) or raw.get("version") != DOCUMENTS_INDEX_VERSION:
        raise DocumentStorageError("document index has an unsupported version")
    raw_records = raw.get("documents")
    if not isinstance(raw_records, list):
        raise DocumentStorageError("document index is malformed")
    records: list[tuple[DocumentMetadata, str]] = []
    slugs: set[str] = set()
    roles: set[str] = set()
    for raw_record in raw_records:
        if not isinstance(raw_record, dict):
            raise DocumentStorageError("document index is malformed")
        try:
            metadata = normalize_document_metadata(
                title=raw_record.get("title"),
                slug=raw_record.get("slug"),
                role=raw_record.get("role", "none"),
                show_in_settings=raw_record.get("show_in_settings", False),
                show_in_sidebar=raw_record.get("show_in_sidebar", False),
                group_title=raw_record.get("group_title"),
                sort_order=raw_record.get("sort_order", 0),
            )
            body_name = str(raw_record["body"])
            if _body_path(app_root, body_name).is_symlink():
                raise DocumentStorageError("document body is unsafe")
        except (DocumentError, KeyError) as exc:
            raise DocumentStorageError("document index is malformed") from exc
        if metadata.slug in slugs or (metadata.role != "none" and metadata.role in roles):
            raise DocumentStorageError("document index contains duplicate records")
        slugs.add(metadata.slug)
        if metadata.role != "none":
            roles.add(metadata.role)
        records.append((metadata, body_name))
    return records


def _legacy_imported_roles(app_root: Path) -> set[str]:
    """Remember claimed roles even after their document is removed or reassigned."""

    records = _read_records(app_root)
    roles: set[str] = {metadata.role for metadata, _ in records if metadata.role != "none"}
    if not _index_path(app_root).exists():
        return roles
    try:
        raw = json.loads(_index_path(app_root).read_text(encoding="utf-8"))
        imported = raw.get("legacy_imported_roles", [])
        if not isinstance(imported, list) or any(
            role not in {"privacy_policy", "user_agreement"} for role in imported
        ):
            raise DocumentStorageError("document import history is malformed")
        return roles | set(imported)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise DocumentStorageError("document import history is unreadable") from exc


def legacy_document_imported(app_root: Path, role: DocumentRole) -> bool:
    """Whether a legal role has already been handed over to managed documents."""

    with _locked_storage(app_root):
        return role in _legacy_imported_roles(app_root)


def _write_records(app_root: Path, records: list[tuple[DocumentMetadata, str]]) -> None:
    _assert_storage_directories(app_root)
    if _index_path(app_root).is_symlink():
        raise DocumentStorageError("document index is unsafe")
    payload = {
        "version": DOCUMENTS_INDEX_VERSION,
        "documents": [_record(metadata, body_name) for metadata, body_name in records],
        "legacy_imported_roles": sorted(
            _legacy_imported_roles(app_root)
            | {metadata.role for metadata, _ in records if metadata.role != "none"}
        ),
    }
    body = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    _atomic_write(_index_path(app_root), body)


def _read_markdown(app_root: Path, slug: str, body_name: str) -> str | None:
    try:
        path = _body_path(app_root, body_name)
        if path.is_symlink():
            raise DocumentStorageError("document body is unsafe")
        if not path.is_file() or path.stat().st_size > MAX_DOCUMENT_BYTES:
            return None
        markdown = _normalize_markdown(path.read_text(encoding="utf-8"))
        if body_name not in {_body_name(slug, markdown), _legacy_body_name(slug, markdown)}:
            return None
        return markdown
    except DocumentStorageError:
        raise
    except (OSError, UnicodeError, DocumentError):
        return None


def _ordered(documents: list[Document]) -> list[Document]:
    return sorted(
        documents,
        key=lambda document: (document.sort_order, document.title.casefold(), document.slug),
    )


def _write_new_body(app_root: Path, metadata: DocumentMetadata, markdown: str) -> str:
    body_name = _body_name(metadata.slug, markdown)
    _atomic_write(_body_path(app_root, body_name), markdown.encode("utf-8"))
    return body_name


def _remove_body(app_root: Path, body_name: str) -> None:
    with suppress(OSError, DocumentStorageError):
        _body_path(app_root, body_name).unlink(missing_ok=True)


def _legacy_slug(preferred: str, occupied_slugs: set[str]) -> str:
    if preferred not in occupied_slugs:
        return preferred
    candidate = f"{preferred}-legacy"
    suffix = 2
    while candidate in occupied_slugs:
        candidate = f"{preferred}-legacy-{suffix}"
        suffix += 1
    return candidate


def _read_legacy_markdown(legacy_path: Path) -> str | None:
    parent = legacy_path.parent
    if parent.is_symlink() or not parent.is_dir() or legacy_path.is_symlink():
        return None
    try:
        if not legacy_path.is_file():
            return None
        return _normalize_markdown(legacy_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, DocumentError):
        return None


def _bootstrap_legacy_documents(app_root: Path) -> None:
    """Import each old legal role once, preserving subsequent administrator edits."""

    records = _read_records(app_root)
    occupied_roles = _legacy_imported_roles(app_root)
    occupied_slugs = {metadata.slug for metadata, _ in records}
    imports: tuple[tuple[DocumentRole, str, str, int, Path], ...] = (
        (
            "privacy_policy",
            "privacy-policy",
            "Privacy policy",
            10,
            app_root / "data" / "legal" / "policy.md",
        ),
        (
            "user_agreement",
            "user-agreement",
            "User agreement",
            20,
            app_root / "data" / "legal" / "terms.md",
        ),
    )
    for role, slug, title, sort_order, legacy_path in imports:
        if role in occupied_roles:
            continue
        markdown = _read_legacy_markdown(legacy_path)
        if markdown is None or not markdown.strip():
            continue
        metadata = normalize_document_metadata(
            title=title,
            slug=_legacy_slug(slug, occupied_slugs),
            role=role,
            show_in_settings=True,
            show_in_sidebar=True,
            sort_order=sort_order,
        )
        body_name = _write_new_body(app_root, metadata, markdown)
        try:
            _write_records(app_root, [*records, (metadata, body_name)])
        except DocumentError:
            _remove_body(app_root, body_name)
            raise
        records.append((metadata, body_name))
        occupied_roles.add(role)
        occupied_slugs.add(metadata.slug)


def bootstrap_legacy_documents(app_root: Path) -> None:
    """Import each old legal role once, preserving subsequent administrator edits."""

    with _locked_storage(app_root):
        _bootstrap_legacy_documents(app_root)


def list_documents(app_root: Path, *, bootstrap_legacy: bool = True) -> list[Document]:
    """Return every indexed document whose separately stored body validates."""

    with _locked_storage(app_root):
        if bootstrap_legacy:
            _bootstrap_legacy_documents(app_root)
        documents = [
            Document(**asdict(metadata), markdown=markdown)
            for metadata, body_name in _read_records(app_root)
            if (markdown := _read_markdown(app_root, metadata.slug, body_name)) is not None
        ]
        return _ordered(documents)


def get_document(app_root: Path, slug: object, *, bootstrap_legacy: bool = True) -> Document | None:
    normalized_slug = normalize_document_slug(slug)
    return next(
        (
            document
            for document in list_documents(app_root, bootstrap_legacy=bootstrap_legacy)
            if document.slug == normalized_slug
        ),
        None,
    )


def get_document_by_role(
    app_root: Path, role: str, *, bootstrap_legacy: bool = True
) -> Document | None:
    normalized_role = _normalize_role(role)
    if normalized_role == "none":
        return None
    return next(
        (
            document
            for document in list_documents(app_root, bootstrap_legacy=bootstrap_legacy)
            if document.role == normalized_role
        ),
        None,
    )


def create_document(app_root: Path, metadata: DocumentMetadata, markdown: object) -> Document:
    with _locked_storage(app_root):
        body = _normalize_markdown(markdown)
        records = _read_records(app_root)
        if any(item.slug == metadata.slug for item, _ in records) or (
            metadata.role != "none" and any(item.role == metadata.role for item, _ in records)
        ):
            raise DocumentConflictError("document slug or role already exists")
        body_name = _write_new_body(app_root, metadata, body)
        try:
            _write_records(app_root, [*records, (metadata, body_name)])
        except DocumentError:
            _remove_body(app_root, body_name)
            raise
        return Document(**asdict(metadata), markdown=body)


def update_document(
    app_root: Path, slug: object, metadata: DocumentMetadata, markdown: object
) -> Document:
    with _locked_storage(app_root):
        normalized_slug = normalize_document_slug(slug)
        body = _normalize_markdown(markdown)
        records = _read_records(app_root)
        previous = next(
            ((item, body_name) for item, body_name in records if item.slug == normalized_slug),
            None,
        )
        if previous is None:
            raise DocumentNotFoundError("document does not exist")
        if any(item.slug == metadata.slug and item.slug != normalized_slug for item, _ in records):
            raise DocumentConflictError("document slug already exists")
        if metadata.role != "none" and any(
            item.slug != normalized_slug and item.role == metadata.role for item, _ in records
        ):
            raise DocumentConflictError("document role already exists")
        new_body_name = _write_new_body(app_root, metadata, body)
        replaced = [
            (metadata, new_body_name) if item.slug == normalized_slug else (item, body_name)
            for item, body_name in records
        ]
        try:
            _write_records(app_root, replaced)
        except DocumentError:
            if new_body_name != previous[1]:
                _remove_body(app_root, new_body_name)
            raise
        if previous[1] != new_body_name:
            with suppress(OSError):
                _body_path(app_root, previous[1]).unlink(missing_ok=True)
        return Document(**asdict(metadata), markdown=body)


def delete_document(app_root: Path, slug: object) -> None:
    with _locked_storage(app_root):
        normalized_slug = normalize_document_slug(slug)
        records = _read_records(app_root)
        removed = [(item, name) for item, name in records if item.slug == normalized_slug]
        if not removed:
            raise DocumentNotFoundError("document does not exist")
        remaining = [(item, name) for item, name in records if item.slug != normalized_slug]
        _write_records(app_root, remaining)
        with suppress(OSError):
            _body_path(app_root, removed[0][1]).unlink(missing_ok=True)
