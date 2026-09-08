"""Public GitHub/GitLab archives with pinned DNS and bounded redirects."""

from __future__ import annotations

import ipaddress
import json
import socket
from typing import Literal
from urllib.parse import quote, unquote, urljoin, urlsplit

from aiohttp import ClientError, ClientSession, ClientTimeout, DummyCookieJar, TCPConnector
from aiohttp.abc import ResolveResult
from aiohttp.resolver import ThreadedResolver

from .models import MAX_ARCHIVE, PackageError, RepositoryRequest, ThemeSource
from .paths import relative_path

ALLOWED_HOSTS = frozenset({"api.github.com", "codeload.github.com", "github.com", "gitlab.com"})


class PublicResolver(ThreadedResolver):
    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        results = await super().resolve(host, port, family)
        for result in results:
            address = ipaddress.ip_address(result["host"])
            if (
                not address.is_global
                or address.is_multicast
                or address.is_reserved
                or getattr(address, "ipv4_mapped", None) is not None
            ):
                raise PackageError("repository_address_blocked")
        return results


def safe_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or parsed.fragment
        ):
            raise ValueError
    except ValueError as exc:
        raise PackageError("invalid_repository_url") from exc
    return value


async def download(session: ClientSession, url: str, *, limit: int) -> bytes:
    for _ in range(5):
        safe_url(url)
        async with session.get(url, allow_redirects=False) as response:
            if response.status in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location", "")
                if not location:
                    raise PackageError("invalid_repository_redirect")
                url = urljoin(url, location)
                continue
            if response.status in {403, 429}:
                raise PackageError("repository_rate_limited", status=429)
            if response.status == 404:
                raise PackageError("repository_not_found", status=404)
            if response.status != 200:
                raise PackageError("repository_unavailable", status=502)
            if response.content_length is not None and response.content_length > limit:
                raise PackageError("archive_too_large")
            output = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                output.extend(chunk)
                if len(output) > limit:
                    raise PackageError("archive_too_large")
            return bytes(output)
    raise PackageError("too_many_repository_redirects")


async def metadata(session: ClientSession, url: str) -> dict[str, object]:
    try:
        result = json.loads(await download(session, url, limit=1024 * 1024))
    except (ValueError, UnicodeError) as exc:
        raise PackageError("invalid_repository_response", status=502) from exc
    if not isinstance(result, dict):
        raise PackageError("invalid_repository_response", status=502)
    return result


def repository_parts(request: RepositoryRequest) -> tuple[str, str, list[str]]:
    safe_url(request.url)
    if urlsplit(request.url).query:
        raise PackageError("invalid_repository_url")
    url = urlsplit(request.url)
    host = url.hostname or ""
    if host not in {"github.com", "gitlab.com"} or url.query:
        raise PackageError("invalid_repository_url")
    parts = [unquote(part) for part in url.path.strip("/").split("/") if part]
    if any(part in {".", ".."} or "/" in part or "\\" in part or ":" in part for part in parts):
        raise PackageError("invalid_repository_url")
    tree: list[str] = []
    if host == "github.com":
        if len(parts) > 2:
            if parts[2] != "tree" or len(parts) < 4:
                raise PackageError("invalid_repository_url")
            tree = parts[3:]
        parts = parts[:2]
    elif "-" in parts:
        marker = parts.index("-")
        if parts[marker + 1 : marker + 2] != ["tree"]:
            raise PackageError("invalid_repository_url")
        tree, parts = parts[marker + 2 :], parts[:marker]
    if len(parts) < 2:
        raise PackageError("invalid_repository_url")
    repo = "/".join(parts).removesuffix(".git")
    return host, repo, tree


async def fetch_repository(request: RepositoryRequest) -> tuple[bytes, ThemeSource]:
    host, project, tree = repository_parts(request)
    connector = TCPConnector(resolver=PublicResolver(), ttl_dns_cache=0, limit=2)
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "User-Agent": "Minishop-Theme-Installer",
    }
    try:
        async with ClientSession(
            connector=connector,
            timeout=ClientTimeout(total=60, sock_read=20),
            headers=headers,
            cookie_jar=DummyCookieJar(),
            trust_env=False,
            auto_decompress=False,
        ) as session:
            if host == "github.com":
                base = f"https://api.github.com/repos/{quote(project, safe='/')}"
                info = await metadata(session, base)
                commit_base = base + "/commits/"
                commit_field = "sha"
                kind: Literal["github", "gitlab"] = "github"
            else:
                base = f"https://gitlab.com/api/v4/projects/{quote(project, safe='')}"
                info = await metadata(session, base)
                commit_base = base + "/repository/commits/"
                commit_field = "id"
                kind = "gitlab"
            ref = request.ref or str(info.get("default_branch") or "")
            subdir = request.subdir
            if tree and not request.ref:
                found = False
                for count in range(min(len(tree), 8), 0, -1):
                    ref = "/".join(tree[:count])
                    try:
                        commit_info = await metadata(session, commit_base + quote(ref, safe=""))
                    except PackageError as exc:
                        if exc.code != "repository_not_found":
                            raise
                    else:
                        found = True
                        subdir = subdir or "/".join(tree[count:])
                        break
                if not found:
                    raise PackageError("repository_ref_not_found", status=404)
            else:
                if tree:
                    ref_parts = ref.split("/")
                    if tree[: len(ref_parts)] != ref_parts:
                        raise PackageError("repository_ref_ambiguous")
                    subdir = subdir or "/".join(tree[len(ref_parts) :])
                commit_info = await metadata(session, commit_base + quote(ref, safe=""))
            if subdir:
                relative_path(subdir)
            commit = str(commit_info.get(commit_field) or "")
            if len(commit) not in (40, 64) or any(
                char not in "0123456789abcdef" for char in commit
            ):
                raise PackageError("invalid_repository_commit", status=502)
            archive_url = (
                base + "/zipball/" + commit
                if host == "github.com"
                else base + "/repository/archive.zip?sha=" + commit
            )
            body = await download(session, archive_url, limit=MAX_ARCHIVE)
            source = ThemeSource(
                kind=kind,
                label=project,
                url=f"https://{host}/{project}",
                ref=ref,
                commit=commit,
                subdir=subdir,
            )
            return body, source
    except (ClientError, TimeoutError, OSError) as exc:
        raise PackageError("repository_unavailable", status=502) from exc
