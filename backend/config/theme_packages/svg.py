"""Validate imported SVG assets with the shared static markup policy."""

from pathlib import Path

from config.svg_icons import svg_markup_error

from .models import PackageError


def validate_svg(path: Path, relative: str) -> None:
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise PackageError("unsafe_svg", f"{relative}: SVG must be valid UTF-8 XML") from exc
    if error := svg_markup_error(text):
        raise PackageError("unsafe_svg", f"{relative}: {error}")
