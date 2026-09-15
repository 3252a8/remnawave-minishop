"""Bounded ZIP extraction and per-theme validation; no package code runs."""

from __future__ import annotations

import hashlib
import io
import stat
import time
import zipfile
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from config.webapp_themes_models import WebappTheme

from .css import validate_css, validate_token
from .models import (
    MAX_ARCHIVE,
    MAX_DEPTH,
    MAX_EXPANDED,
    MAX_FILE,
    MAX_FILES,
    MAX_THEMES,
    Candidate,
    Collection,
    PackageError,
    PackageMetadata,
    ThemeKey,
)
from .paths import confined, read_json, relative_path
from .svg import validate_svg

RESOURCE_SUFFIXES = {
    ".json",
    ".css",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".ico",
    ".svg",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".md",
    ".txt",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico"}
IGNORED = {".git", ".github", ".gitlab", "node_modules", "__MACOSX", "__pycache__", ".DS_Store"}


def allowed_file(path: Path) -> bool:
    return path.suffix.lower() in RESOURCE_SUFFIXES or path.name.upper() in {
        "LICENSE",
        "LICENCE",
        "COPYING",
        "README",
    }


def extract_archive(body: bytes, destination: Path) -> None:
    if not body or len(body) > MAX_ARCHIVE:
        raise PackageError("archive_too_large" if body else "empty_archive")
    destination.mkdir(parents=True, exist_ok=False)
    deadline = time.monotonic() + 30
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_FILES:
                raise PackageError("too_many_files")
            seen: set[str] = set()
            expanded = 0
            for item in entries:
                raw = item.orig_filename.rstrip("/")
                name = relative_path(raw)
                if name.casefold() in seen:
                    raise PackageError("duplicate_path", name)
                seen.add(name.casefold())
                mode = item.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or item.flag_bits & 1:
                    raise PackageError("unsupported_zip_entry", name)
                if item.file_size > MAX_FILE or item.file_size > max(item.compress_size, 1) * 200:
                    raise PackageError("archive_limit", name)
                if len(Path(name).parts) > MAX_DEPTH + 8:
                    raise PackageError("archive_too_deep", name)
                if any(part in IGNORED for part in Path(name).parts):
                    continue
                target = confined(destination, name)
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                count = 0
                with archive.open(item) as source, target.open("xb") as output:
                    while chunk := source.read(64 * 1024):
                        count += len(chunk)
                        expanded += len(chunk)
                        if (
                            count > MAX_FILE
                            or expanded > MAX_EXPANDED
                            or time.monotonic() > deadline
                        ):
                            raise PackageError("archive_limit", name)
                        output.write(chunk)
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError) as exc:
        raise PackageError("invalid_archive") from exc


def content_digest(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise PackageError("unsafe_path", path.name)
        if not path.is_file():
            continue
        name = path.relative_to(folder).as_posix().encode("utf-8")
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name)
        digest.update(path.stat().st_size.to_bytes(8, "big"))
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(64 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def package_root(extracted: Path, subdir: str = "") -> Path:
    root = extracted
    if subdir:
        # Providers wrap snapshots in one generated directory; ordinary ZIPs may not.
        direct = confined(root, subdir)
        if direct.is_dir():
            return direct
        children = [path for path in root.iterdir() if path.name not in IGNORED]
        if len(children) == 1 and children[0].is_dir():
            nested = confined(children[0], subdir)
            if nested.is_dir():
                return nested
        raise PackageError("subdirectory_not_found", subdir)
    while not (root / "theme.json").exists() and not (root / "minishop-themes.json").exists():
        children = [path for path in root.iterdir() if path.name not in IGNORED]
        if len(children) != 1 or not children[0].is_dir():
            break
        root = children[0]
    return root


def inspect_theme(folder: Path, relative: str) -> Candidate:
    candidate = Candidate(path=relative)
    try:
        data = read_json(folder / "theme.json")
        if not isinstance(data, dict):
            raise PackageError("invalid_theme_manifest")
        raw_key = data.get("key")
        from pydantic import TypeAdapter

        key = TypeAdapter(ThemeKey).validate_python(raw_key)
        candidate.key = key
        theme = WebappTheme.model_validate(data)
        if theme.variant_alias_for or theme.hidden:
            raise PackageError("theme_alias_not_allowed", key)
        if len(theme.names) > 12 or any(len(value) > 120 for value in theme.names.values()):
            raise PackageError("theme_name_too_long", key)
        metadata_file = folder / "theme-package.json"
        metadata = (
            PackageMetadata.model_validate(read_json(metadata_file))
            if metadata_file.exists()
            else PackageMetadata()
        )
        candidate.metadata = metadata
        if metadata.compatibility.theme_api != 1:
            raise PackageError("incompatible_theme_api", key)
        if not metadata_file.exists():
            candidate.warnings.append("legacy_package")
        files = [p for p in folder.rglob("*") if p.is_file()]
        if not files or len(files) > MAX_FILES:
            raise PackageError("too_many_files")
        for path in files:
            relative_path(path.relative_to(folder).as_posix())
            if path.is_symlink() or not allowed_file(path):
                raise PackageError("unsupported_theme_file", path.relative_to(folder).as_posix())
            if path.stat().st_size > MAX_FILE:
                raise PackageError("theme_file_too_large", path.name)
            if path.suffix.lower() == ".css":
                validate_css(
                    path.read_text(encoding="utf-8"), folder, path.relative_to(folder).as_posix()
                )
            elif path.suffix.lower() in IMAGE_SUFFIXES:
                try:
                    with Image.open(path) as image:
                        if image.width * image.height > 16_000_000:
                            raise PackageError("image_too_large", path.name)
                        image.verify()
                except (
                    UnidentifiedImageError,
                    OSError,
                    Image.DecompressionBombError,
                    Image.DecompressionBombWarning,
                ) as exc:
                    raise PackageError("invalid_image", path.name) from exc
            elif path.suffix.lower() == ".svg":
                validate_svg(path, path.relative_to(folder).as_posix())
        if theme.css_file:
            css_path = confined(folder, theme.css_file)
            if css_path.suffix.lower() != ".css" or not css_path.is_file():
                raise PackageError("missing_css_file", theme.css_file)
        if metadata.preview:
            preview = confined(folder, metadata.preview)
            if not preview.is_file() or preview.suffix.lower() not in IMAGE_SUFFIXES:
                raise PackageError("invalid_preview")
        for tokens in [theme.tokens, *theme.variants.values()]:
            for value in tokens.model_dump(exclude_none=True).values():
                if isinstance(value, str):
                    validate_token(value)
        candidate.theme = theme
        candidate.digest = content_digest(folder)
        candidate.size = sum(path.stat().st_size for path in files)
        candidate.files = len(files)
    except PackageError as exc:
        candidate.error, candidate.detail = exc.code, exc.detail
    except (ValidationError, ValueError, UnicodeError, OSError) as exc:
        candidate.error, candidate.detail = "invalid_theme_manifest", str(exc)[:500]
    return candidate


def inspect_collection(extracted: Path, subdir: str = "") -> list[Candidate]:
    root = package_root(extracted, subdir)
    index = root / "minishop-themes.json"
    if index.exists():
        try:
            collection = Collection.model_validate(read_json(index))
        except ValidationError as exc:
            raise PackageError("invalid_collection", str(exc)[:300]) from exc
        folders = [confined(root, entry.path) for entry in collection.themes]
        if len({str(p).casefold() for p in folders}) != len(folders):
            raise PackageError("duplicate_collection_path")
    else:
        folders = sorted(
            path.parent
            for path in root.rglob("theme.json")
            if len(path.relative_to(root).parts) <= MAX_DEPTH + 1
        )
    if not folders:
        raise PackageError("no_themes_found")
    if len(folders) > MAX_THEMES:
        raise PackageError("too_many_themes")
    if any(a != b and a.is_relative_to(b) for a in folders for b in folders):
        raise PackageError("nested_theme_manifests")
    results = [
        inspect_theme(folder, folder.relative_to(extracted).as_posix()) for folder in folders
    ]
    keys: set[str] = set()
    for item in results:
        if item.key in keys:
            for duplicate in results:
                if duplicate.key == item.key:
                    duplicate.error, duplicate.detail = "duplicate_theme_key", item.key
        keys.add(item.key)
    return results


def deterministic_zip(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(relative_path(name), (2020, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    return stream.getvalue()
