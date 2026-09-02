from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import quote, unquote_to_bytes, urlsplit, urlunsplit


class KumaStatusPageUrlError(ValueError):
    """The configured URL is not a published Uptime Kuma status page."""


@dataclass(frozen=True)
class KumaStatusPage:
    origin: str
    base_path: str
    slug: str

    def api_url(self, endpoint: str | None = None) -> str:
        endpoint_path = f"/{endpoint}" if endpoint else ""
        return f"{self.origin}{self.base_path}/api/status-page{endpoint_path}/{self.slug}"


_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)


def _normalized_segment(segment: str) -> str:
    if not segment or re.search(r"%(?![0-9A-Fa-f]{2})", segment):
        raise KumaStatusPageUrlError("invalid path segment")
    try:
        decoded = unquote_to_bytes(segment).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KumaStatusPageUrlError("invalid path segment") from exc
    if (
        decoded in {".", ".."}
        or "/" in decoded
        or "\\" in decoded
        or any(ord(char) < 32 for char in decoded)
    ):
        raise KumaStatusPageUrlError("invalid path segment")
    return quote(decoded, safe="")


def _validated_origin(value: str) -> tuple[str, list[str]]:
    if not value or value != value.strip() or any(char.isspace() for char in value):
        raise KumaStatusPageUrlError("URL is required")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise KumaStatusPageUrlError("invalid URL") from exc
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise KumaStatusPageUrlError("invalid URL")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            normalized_hostname = hostname.rstrip(".").encode("idna").decode("ascii").lower()
            labels = normalized_hostname.split(".")
        except UnicodeError as exc:
            raise KumaStatusPageUrlError("invalid host") from exc
        if not labels or any(not _HOST_LABEL.fullmatch(label) for label in labels):
            raise KumaStatusPageUrlError("invalid host") from None
    else:
        normalized_hostname = str(address)
        if address.version == 6:
            normalized_hostname = f"[{normalized_hostname}]"
    if port is not None and not 1 <= port <= 65535:
        raise KumaStatusPageUrlError("invalid port")
    raw_segments = parsed.path.split("/")
    if raw_segments and raw_segments[0] == "":
        raw_segments = raw_segments[1:]
    if raw_segments and raw_segments[-1] == "":
        raw_segments = raw_segments[:-1]
    if any(not segment for segment in raw_segments):
        raise KumaStatusPageUrlError("invalid path")
    segments = [_normalized_segment(segment) for segment in raw_segments]
    netloc = normalized_hostname if port is None else f"{normalized_hostname}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, "", "", "")), segments


def parse_kuma_status_page_url(value: str) -> KumaStatusPage:
    """Parse a published `/status/<slug>` URL, including an optional proxy base path."""
    origin, segments = _validated_origin(value)
    if len(segments) < 2 or segments[-2] != "status":
        raise KumaStatusPageUrlError("expected /status/<slug> path")
    return KumaStatusPage(
        origin=origin,
        base_path="/" + "/".join(segments[:-2]) if len(segments) > 2 else "",
        slug=segments[-1],
    )


def parse_legacy_kuma_status_page_url(base_url: str, slug: str) -> KumaStatusPage:
    """Deprecated: keep old base-URL plus slug deployments working during migration."""
    origin, segments = _validated_origin(base_url)
    normalized_slug = _normalized_segment(slug.strip())
    return KumaStatusPage(
        origin=origin,
        base_path="/" + "/".join(segments) if segments else "",
        slug=normalized_slug,
    )
