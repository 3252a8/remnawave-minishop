"""Short human-readable names for the browser and system behind a User-Agent."""

from __future__ import annotations

import re

# Order matters: Chromium-based browsers also announce "Chrome" and "Safari".
_BROWSERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"YaBrowser/|YaSearchBrowser/"), "Yandex Browser"),
    (re.compile(r"Edg(?:e|A|iOS)?/"), "Edge"),
    (re.compile(r"OPR/|Opera"), "Opera"),
    (re.compile(r"SamsungBrowser/"), "Samsung Internet"),
    (re.compile(r"Firefox/|FxiOS/"), "Firefox"),
    (re.compile(r"CriOS/|Chrome/|Chromium/"), "Chrome"),
    (re.compile(r"Version/[\d.]+.*Safari/"), "Safari"),
)
_SYSTEMS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"Windows NT"), "Windows"),
    (re.compile(r"Android"), "Android"),
    (re.compile(r"iPhone|iPod"), "iOS"),
    (re.compile(r"iPad"), "iPadOS"),
    (re.compile(r"CrOS"), "ChromeOS"),
    (re.compile(r"Mac OS X|Macintosh"), "macOS"),
    (re.compile(r"Linux|X11"), "Linux"),
)


def describe_user_agent(user_agent: str | None) -> tuple[str, str]:
    """Return ``(browser, system)``; either part is empty when the header does not say."""
    value = str(user_agent or "")
    browser = next((name for pattern, name in _BROWSERS if pattern.search(value)), "")
    system = next((name for pattern, name in _SYSTEMS if pattern.search(value)), "")
    return browser, system
