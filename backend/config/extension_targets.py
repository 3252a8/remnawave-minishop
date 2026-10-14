"""Syntax shared by configuration, messaging and customer navigation."""

import re

_PAGE = re.compile(r"/extensions/([a-z][a-z0-9_-]{0,63})/([a-z][a-z0-9-]{1,63})\Z")


def extension_page_parts(value: str) -> tuple[str, str] | None:
    match = _PAGE.fullmatch(value)
    return (match[1], match[2]) if match else None


def extension_start_parameter(value: str) -> str | None:
    parts = extension_page_parts(value)
    return f"ext_{parts[0]}__{parts[1]}" if parts else None
