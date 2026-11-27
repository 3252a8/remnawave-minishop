"""Parse source snapshots and download them through Minishop's network guard."""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass

from aiohttp import ClientError, ClientSession, ClientTimeout, DummyCookieJar, TCPConnector
from yarl import URL

from bot.utils.outbound_network import GuardedResolver, OutboundPolicy

from .settings import MAX_URL_LENGTH, SourceNetworkPolicy, SourceURLValidationError, source_url

MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_LINE_LENGTH = 16384
MAX_SOURCE_RECORDS = 50000
MAX_TELEGRAM_ID = 2**63 - 1
MAX_REDIRECTS = 3
SOURCE_TIMEOUT_SECONDS = 20
_REDIRECTS = {301, 302, 303, 307, 308}
_ID = re.compile(r"[0-9]{1,19}\Z")
_LINK = re.compile(
    r"\[([^\[\]\r\n]{1,200})\]\((https?://[^\s<>()]+)\)"
    r"|<(https?://[^\s<>]+)>"
    r"|\((https?://[^\s<>()]+)\)"
    r"|(https?://[^\s<>\"']+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Reason:
    text: str
    links: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedSource:
    entries: dict[int, tuple[Reason, ...]]
    invalid_lines: int
    content_sha256: str


class SourceError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def merge_reasons(groups: Iterable[tuple[Reason, ...]]) -> tuple[Reason, ...]:
    by_text: dict[str, dict[str, None]] = {}
    for group in groups:
        for reason in group:
            if reason.text or reason.links:
                by_text.setdefault(reason.text, {}).update(dict.fromkeys(reason.links))
    return tuple(Reason(text, tuple(links)) for text, links in by_text.items())


def _extract_reason(value: str) -> Reason:
    links: dict[str, None] = {}

    def extract(match: re.Match[str]) -> str:
        label, markdown, bracketed, parenthesized, bare = match.groups()
        candidate = markdown or bracketed or parenthesized or bare
        if not candidate:
            return match[0]
        trailing = ""
        if bare:
            candidate = candidate.rstrip(".,;!?…")
            closing = len(candidate) - len(candidate.rstrip(")"))
            unmatched = max(0, candidate.count(")") - candidate.count("("))
            trim = min(closing, unmatched)
            if trim:
                candidate = candidate[:-trim]
            trailing = bare[len(candidate) :]
        try:
            url = URL(candidate)
            if (
                len(candidate) > MAX_URL_LENGTH
                or url.scheme not in {"http", "https"}
                or not url.host
                or url.user is not None
                or url.password is not None
                or url.port is None
                or not 0 < url.port <= 65535
                or len(str(url)) > MAX_URL_LENGTH
            ):
                return match[0]
        except ValueError:
            return match[0]
        links[str(url)] = None
        return (label or "") + trailing

    text = _LINK.sub(extract, value).strip()
    if links:
        text = re.sub(r"[ \t]{2,}", " ", text).strip(" \t,;·—–")
        if re.fullmatch(r"[.!?…()]*", text):
            text = ""
    return Reason(text, tuple(links))


def parse_source(content: bytes) -> ParsedSource:
    if len(content) > MAX_SOURCE_BYTES:
        raise SourceError("source_too_large")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeError as exc:
        raise SourceError("source_invalid_encoding") from exc
    by_id: dict[int, list[Reason]] = {}
    invalid_lines = 0
    record_count = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        identifier, _, reason = line.partition("#")
        identifier = identifier.strip()
        if len(line) > MAX_LINE_LENGTH or "\0" in line or not _ID.fullmatch(identifier):
            invalid_lines += 1
            continue
        telegram_id = int(identifier)
        if not 0 < telegram_id <= MAX_TELEGRAM_ID:
            invalid_lines += 1
            continue
        record_count += 1
        if record_count > MAX_SOURCE_RECORDS:
            raise SourceError("source_too_large")
        by_id.setdefault(telegram_id, []).append(_extract_reason(reason.strip()))
    if invalid_lines and not by_id:
        raise SourceError("source_invalid_format")
    entries = {
        telegram_id: merge_reasons([tuple(reasons)]) for telegram_id, reasons in by_id.items()
    }
    return ParsedSource(entries, invalid_lines, hashlib.sha256(content).hexdigest())


async def _download(session: ClientSession, address: str, policy: OutboundPolicy) -> bytes:
    for _ in range(MAX_REDIRECTS + 1):
        url = source_url(address, policy)
        async with session.get(url, allow_redirects=False) as response:
            if response.status in _REDIRECTS:
                location = response.headers.get("Location")
                if not location:
                    raise SourceError("source_redirect_blocked")
                address = str(url.join(URL(location)))
                continue
            if response.status != 200:
                raise SourceError("source_http_error")
            if response.headers.get("Content-Encoding", "identity").strip().lower() != "identity":
                raise SourceError("source_invalid_format")
            if response.content_length is not None and response.content_length > MAX_SOURCE_BYTES:
                raise SourceError("source_too_large")
            body = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                if len(body) + len(chunk) > MAX_SOURCE_BYTES:
                    raise SourceError("source_too_large")
                body.extend(chunk)
            return bytes(body)
    raise SourceError("source_redirect_blocked")


async def fetch_source(address: str, previous_sha256: str | None) -> ParsedSource | None:
    """Connect only to vetted public addresses, including on each HTTPS redirect."""
    policy = SourceNetworkPolicy()
    connector = TCPConnector(resolver=GuardedResolver(policy), use_dns_cache=False, limit=1)
    try:
        async with (
            asyncio.timeout(SOURCE_TIMEOUT_SECONDS),
            ClientSession(
                connector=connector,
                timeout=ClientTimeout(sock_connect=7, sock_read=10),
                headers={"Accept-Encoding": "identity"},
                cookie_jar=DummyCookieJar(),
                trust_env=False,
                auto_decompress=False,
            ) as session,
        ):
            content = await _download(session, address, policy)
        if previous_sha256 and hashlib.sha256(content).hexdigest() == previous_sha256:
            return None
        return await asyncio.to_thread(parse_source, content)
    except TimeoutError as exc:
        raise SourceError("source_timeout") from exc
    except SourceURLValidationError as exc:
        raise SourceError("source_address_blocked") from exc
    except SourceError:
        raise
    except ValueError as exc:
        raise SourceError("source_address_blocked") from exc
    except (ClientError, OSError) as exc:
        raise SourceError("source_unavailable") from exc
