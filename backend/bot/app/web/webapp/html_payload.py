"""Encoding at the HTML boundary, separate from JSON API serialization."""

import html
import json
from typing import Any


def json_script_payload(value: Any) -> str:
    # HTML parses raw script text before JSON; escaping only quotes is insufficient.
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def image_preload_markup(url: str) -> str:
    return (
        f'<link rel="preload" href="{html.escape(url, quote=True)}" '
        'as="image" fetchpriority="high">'
    )
