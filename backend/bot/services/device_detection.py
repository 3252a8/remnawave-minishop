"""Classify panel device metadata without consulting user-assigned names.

These are presentation hints, not verified hardware identity or access policy.
Generic Linux/client user agents alone cannot establish that a device is a router.
"""

import re
from dataclasses import dataclass
from typing import Literal

DeviceType = Literal["phone", "tablet", "laptop", "desktop", "tv", "router", "unknown"]
RouterPlatform = Literal["openwrt", "keenetic", "routeros", "dd-wrt", "asuswrt", "tomato"]


@dataclass(frozen=True)
class DeviceDetection:
    device_type: DeviceType = "unknown"
    router_platform: RouterPlatform | None = None


def _words(pattern: str) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z0-9])(?:" + pattern + r")(?![a-z0-9])", re.IGNORECASE)


_ROUTERS: tuple[tuple[RouterPlatform, re.Pattern[str]], ...] = (
    ("openwrt", _words(r"open[\s_-]?wrt|lede")),
    ("keenetic", _words(r"keenetic(?:[\s_-]?os)?|ndms")),
    ("routeros", _words(r"router[\s_-]?os|mikrotik")),
    ("dd-wrt", _words(r"dd[\s_-]?wrt")),
    ("asuswrt", _words(r"asus[\s_-]?wrt(?:[\s_-]?merlin)?")),
    ("tomato", _words(r"fresh[\s_-]?tomato|advanced[\s_-]?tomato")),
)
_ROUTER = _words(r"router|wireless[\s_-]+gateway")
_SHAPES: tuple[tuple[DeviceType, re.Pattern[str]], ...] = (
    ("tv", _words(r"tv|tvos|appletv|shield|firestick|chromecast")),
    ("tablet", _words(r"ipad|tablet|tab|pad|surface")),
    ("laptop", _words(r"macbook|laptop|notebook|thinkpad|chromebook|book")),
    ("desktop", _words(r"imac|mac mini|mac studio|mac pro|desktop|pc")),
    ("phone", _words(r"iphone|phone|pixel|galaxy|xiaomi|redmi|oneplus")),
    ("phone", _words(r"android|harmonyos|grapheneos|ios|ipados")),
    ("laptop", _words(r"macos|mac os|macintosh|darwin|windows|win32|win64|winnt|microsoft")),
    ("desktop", _words(r"linux|ubuntu|debian|fedora|arch")),
)


def detect_device(
    *, device_model: str = "", platform: str = "", os_version: str = "", user_agent: str = ""
) -> DeviceDetection:
    """Use explicit router signatures before generic OS/form-factor hints."""
    text = " ".join((device_model, platform, os_version, user_agent))
    for router_platform, pattern in _ROUTERS:
        if pattern.search(text):
            return DeviceDetection("router", router_platform)
    if _ROUTER.search(text):
        return DeviceDetection("router")
    for device_type, pattern in _SHAPES:
        if pattern.search(text):
            return DeviceDetection(device_type)
    return DeviceDetection()
