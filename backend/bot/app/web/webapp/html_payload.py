"""Encoding at the HTML boundary, separate from JSON API serialization."""

import html


def image_preload_markup(url: str) -> str:
    return (
        f'<link rel="preload" href="{html.escape(url, quote=True)}" '
        'as="image" fetchpriority="high">'
    )
